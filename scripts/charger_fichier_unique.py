import re
import sys
import os

# Permet d'importer modele/utils.fusion_joueurs depuis la racine du repo
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from modele import trouver_historique_n1, nettoyer_note, compter_matchs
from utils.fusion_joueurs import _corriger_noms, _verifier_cle_unique

FICHIER_SORTIE = "joueurs_fusionne.xlsx"
FICHIER_N1 = "data/n1/joueurs_fusionne_25-26.xlsx"

# En dessous de ce taux de correspondance cellule-à-cellule avec le fichier
# N-1 (25-26), le fichier chargé est considéré comme contenant de VRAIS
# résultats 26-27 pour cette colonne/ce joueur plutôt qu'un recyclage de la
# saison précédente — au-dessus, la colonne est mise à zéro. Fixé à 0.5 (très
# en dessous du ~99% observé sur le cas réel qui a motivé ce script) pour
# laisser une marge large avant de déclencher une correction, plutôt que de
# risquer d'écraser de vrais résultats sur un signal ambigu.
SEUIL_CONTAMINATION = 0.5
# Nombre minimum de journées non nulles chez un joueur pour que son profil
# D1-D34 soit pris en compte dans le calcul du taux de contamination — un
# joueur avec seulement 1-2 matchs joués ne fournit pas un échantillon fiable
# pour distinguer "recyclé" de "vraiment joué" (une poignée de coïncidences
# de notes ne prouve ni n'infirme rien).
MATCHS_MIN_ECHANTILLON = 20


def _renommer_colonnes_journee(df):
    """Renomme les colonnes de journée au format 'D-N' (export MPGStats du
    fichier à taille unique, contrairement aux exports 6/8/10 joueurs qui
    utilisent déjà 'DN') vers 'DN' — sans ce renommage, cols_journees
    (app.py) serait vide et casserait la détection de journée/Forme 6J/
    Matchs joués dans toute l'app. 'DMI' n'est jamais concerné (aucun
    chiffre après le 'D').

    Renvoie aussi cols_recyclables : les colonnes renommées ici (donc
    arrivées au format 'D-N' dans le fichier source) — par opposition à une
    colonne déjà au format 'DN' avant renommage (ex. 'D1' dès que la
    journée 1 a été réellement jouée, cf. le fichier post-J1 26-27), qui
    contient une vraie donnée de la saison en cours et n'est donc PAS une
    candidate au nettoyage de contamination N-1 (_nettoyer_contamination_n1
    ci-dessous) : cette distinction évite de recorriger/écraser une colonne
    réelle simplement parce qu'elle porte un nom 'DN' comme les colonnes
    recyclées."""
    renommage = {}
    cols_recyclables = []
    for col in df.columns:
        m = re.match(r'^D-(\d{1,2})$', str(col))
        if m:
            nouveau_nom = f"D{m.group(1)}"
            renommage[col] = nouveau_nom
            cols_recyclables.append(nouveau_nom)
    return df.rename(columns=renommage), cols_recyclables


def _renommer_colonnes_encheres(df):
    """Renomme les colonnes d'enchères/achat portant un suffixe de type
    ' W-N' (ex. 'Enchere moy W-3', '% achat T1/L6 W-3' — un marqueur de
    snapshot hebdomadaire ajouté par MPGStats sur cet export, dont le numéro
    peut changer d'un export à l'autre) vers leur nom sans suffixe (ex.
    'Enchere moy', '% achat T1/L6') — TAILLES_LIGUE (utils/mercato.py)
    n'accepte que ces noms exacts, sans quoi enchere_disponible resterait
    False et Mercato retomberait sur le repli N-1 alors que de vraies
    données d'enchères existent. Motif volontairement restreint aux
    colonnes 'Enchere ...'/'% achat ...' : ne touche aucune autre colonne."""
    renommage = {}
    for col in df.columns:
        m = re.match(r'^(Enchere .+|% achat .+) W-\d+$', str(col))
        if m:
            renommage[col] = m.group(1)
    return df.rename(columns=renommage), len(renommage)


def _detecter_cols_journees(df):
    return [c for c in df.columns if re.match(r'^D\d{1,2}$', str(c))]


def _nettoyer_contamination_n1(df, df_n1, cols_journees, cols_a_verifier):
    """Détecte et corrige le recyclage de la saison N-1 dans le fichier à
    taille unique 26-27 : avant les vrais résultats de matchs (et donc avant
    les 3 exports par taille de ligue), l'export MPGStats observé remplit
    D1-D34/Note/Buts/%Titu/Variation avec les valeurs de la saison PRÉCÉDENTE
    au lieu de vrais zéros — plutôt qu'une intervention manuelle ponctuelle
    (ce qui a été fait la première fois, sans garde-fou pour la suite), cette
    fonction re-applique la même correction automatiquement à CHAQUE
    chargement, et se protège contre un usage après le début de la vraie
    saison (voir SEUIL_CONTAMINATION) : si les valeurs ne ressemblent plus à
    un recyclage de N-1, rien n'est corrigé et un avertissement est levé
    plutôt que d'écraser silencieusement de vrais résultats.

    cols_journees : TOUTES les colonnes de journée (y compris une éventuelle
    D1 déjà réellement jouée), utilisées telles quelles pour compter les
    matchs joués (partie 2 ci-dessous) — une vraie journée jouée doit compter
    comme un match, pas seulement les colonnes recyclables.
    cols_a_verifier : le sous-ensemble RECYCLABLE (colonnes arrivées au
    format 'D-N', cf. _renommer_colonnes_journee) sur lequel porte le
    diagnostic ET la correction de contamination — une colonne déjà réelle
    (ex. 'D1' post-J1) n'y figure jamais, donc n'est ni inspectée ni écrasée
    par cette fonction.

    Retourne (df_corrige, rapport: dict)."""
    cols_journees_n1 = [c for c in df_n1.columns if re.match(r'^D\d{1,2}$', str(c))]

    # --- 1. Colonnes recyclables : décision GLOBALE (tout ou rien), pas
    # colonne par colonne ---
    # Le bug observé est un recyclage EN BLOC (toutes les journées de tous les
    # joueurs) : chercher un signal agrégé sur l'ensemble des joueurs, plutôt
    # que douze micro-décisions par journée, colle mieux à la nature réelle du
    # problème et reste simple à vérifier/expliquer.
    joueurs_verifiables = 0
    joueurs_contamines = 0
    for _, row in df.iterrows():
        row_n1 = trouver_historique_n1(row['Joueur'], row['Poste'], df_n1)
        if row_n1 is None:
            continue
        cellules_non_nulles = [c for c in cols_a_verifier if row[c] != 0]
        if len(cellules_non_nulles) < MATCHS_MIN_ECHANTILLON:
            continue
        joueurs_verifiables += 1
        correspondances = sum(
            1 for c in cellules_non_nulles
            if c in cols_journees_n1 and row[c] == row_n1[c]
        )
        if correspondances / len(cellules_non_nulles) >= 0.9:
            joueurs_contamines += 1

    taux_contamination_d = (joueurs_contamines / joueurs_verifiables) if joueurs_verifiables else 0.0
    d_corrigees = taux_contamination_d >= SEUIL_CONTAMINATION
    if d_corrigees:
        for c in cols_a_verifier:
            df[c] = 0

    # --- 2. Note/Buts/%Titu/Variation : invariant indépendant du diagnostic
    # ci-dessus --- un joueur sans AUCUN match réel cette saison (recalculé
    # sur D1-D34 APRÈS correction éventuelle ci-dessus) ne peut pas avoir un
    # agrégat de saison authentique, quelle que soit l'origine exacte de la
    # valeur résiduelle (recyclage confirmé pour certains joueurs, origine
    # non identifiable pour d'autres — même défaut de fond dans les deux
    # cas). Toujours sûr à appliquer, y compris en cours de saison réelle :
    # un joueur encore à 0 match reste à 0 match, peu importe la date.
    colonnes_agregats = [c for c in ['Note', 'Buts', '%Titu', 'Variation'] if c in df.columns]
    matchs_joues = df.apply(lambda row: compter_matchs(row, cols_journees), axis=1)
    joueurs_sans_match = matchs_joues == 0
    valeurs_avant = df.loc[joueurs_sans_match, colonnes_agregats].copy()
    nb_agregats_corriges = int((valeurs_avant != 0).any(axis=1).sum())
    for c in colonnes_agregats:
        df.loc[joueurs_sans_match, c] = 0

    rapport = {
        'cols_a_verifier': list(cols_a_verifier),
        'cols_reelles': [c for c in cols_journees if c not in cols_a_verifier],
        'joueurs_verifiables_d': joueurs_verifiables,
        'joueurs_contamines_d': joueurs_contamines,
        'taux_contamination_d': taux_contamination_d,
        'd_colonnes_corrigees': d_corrigees,
        'nb_agregats_corriges': nb_agregats_corriges,
    }
    return df, rapport


def charger_fichier_unique(fichier_entree):
    """Charge un export MPGStats à taille unique (avant que les 3 exports par
    taille de ligue 6/8/10 joueurs ne soient disponibles) et produit
    joueurs_fusionne.xlsx, avec les mêmes corrections qu'un chargement
    normal (renommage des colonnes journée, correction des noms) PLUS le
    nettoyage automatique du recyclage N-1 (voir _nettoyer_contamination_n1).

    Reste utilisable une fois les premières journées réellement jouées : les
    colonnes déjà réelles (arrivées au format 'DN' plutôt que 'D-N', cf.
    _renommer_colonnes_journee) sont automatiquement exclues du nettoyage de
    contamination, seules les colonnes encore au format recyclé 'D-N' sont
    vérifiées/corrigées. Une fois les 3 exports par taille de ligue
    disponibles, bascule sur scripts/fusionner_joueurs.py — ne réutilise plus
    ce script-ci (le garde-fou SEUIL_CONTAMINATION limite le risque d'un
    mauvais usage, mais scripts/fusionner_joueurs.py reste le bon outil une
    fois la vraie saison bien avancée)."""
    df = pd.read_excel(fichier_entree)
    df, cols_recyclables = _renommer_colonnes_journee(df)
    df, nb_colonnes_encheres_renommees = _renommer_colonnes_encheres(df)
    df = _corriger_noms(df)
    _verifier_cle_unique(df, fichier_entree)

    cols_journees = _detecter_cols_journees(df)
    if len(cols_journees) != 34:
        raise ValueError(
            f"{len(cols_journees)} colonnes de journée détectées après renommage "
            f"(34 attendues) — vérifie le format des colonnes D dans « {fichier_entree} »."
        )

    if not os.path.exists(FICHIER_N1):
        raise FileNotFoundError(
            f"Référence N-1 introuvable ({FICHIER_N1}) — impossible de détecter un "
            f"éventuel recyclage sans elle. Chargement interrompu par prudence."
        )
    df_n1 = pd.read_excel(FICHIER_N1)

    for c in cols_journees:
        df[c] = df[c].apply(nettoyer_note)
    cols_journees_n1 = [c for c in df_n1.columns if re.match(r'^D\d{1,2}$', str(c))]
    for c in cols_journees_n1:
        df_n1[c] = df_n1[c].apply(nettoyer_note)

    df, rapport = _nettoyer_contamination_n1(df, df_n1, cols_journees, cols_recyclables)
    rapport['nb_colonnes_encheres_renommees'] = nb_colonnes_encheres_renommees
    return df, rapport


def main():
    if len(sys.argv) != 2:
        print("Usage : python scripts/charger_fichier_unique.py <fichier_export.xlsx>")
        sys.exit(1)
    fichier_entree = sys.argv[1]
    if not os.path.exists(fichier_entree):
        print(f"❌ Fichier introuvable : {fichier_entree}")
        sys.exit(1)

    df, rapport = charger_fichier_unique(fichier_entree)

    if rapport['nb_colonnes_encheres_renommees'] > 0:
        print(f"✅ {rapport['nb_colonnes_encheres_renommees']} colonne(s) d'enchères/achat "
              f"renommée(s) (suffixe hebdomadaire retiré).")
    else:
        print("ℹ️  Aucune colonne d'enchères à renommer (fichier sans données d'enchères, "
              "ou déjà aux noms attendus).")

    if rapport['cols_reelles']:
        print(f"ℹ️  Colonnes déjà réelles (format 'DN' dans le fichier source, jamais touchées "
              f"par le nettoyage de contamination) : {', '.join(sorted(rapport['cols_reelles'], key=lambda c: int(c[1:])))}")
    print(f"Colonnes recyclables vérifiées (format 'D-N' dans le fichier source) : "
          f"{len(rapport['cols_a_verifier'])}")
    print(f"Journées vérifiables (historique N-1 résolu, >= {MATCHS_MIN_ECHANTILLON} "
          f"journées non nulles) : {rapport['joueurs_verifiables_d']} joueurs")
    print(f"Taux de contamination détecté (colonnes recyclables) : {rapport['taux_contamination_d']:.1%} "
          f"({rapport['joueurs_contamines_d']} joueurs)")

    if rapport['d_colonnes_corrigees']:
        print("✅ Recyclage N-1 confirmé (>= 50%) — colonnes recyclables remises à zéro pour tous les joueurs.")
    else:
        print(
            "⚠️  Taux de contamination sous le seuil (50%) — colonnes recyclables laissées TELLES "
            "QUELLES. Si la vraie saison 26-27 a commencé, c'est le comportement attendu (ne touche "
            "jamais de vrais résultats). Si ce fichier est censé être pré-saison, vérifie "
            "manuellement avant de continuer : quelque chose ne correspond pas au cas connu."
        )

    print(f"Note/Buts/%Titu/Variation remis à zéro pour les joueurs à 0 match cette saison "
          f"(après correction des colonnes recyclables éventuelle) : {rapport['nb_agregats_corriges']} joueur(s) concerné(s).")

    df.to_excel(FICHIER_SORTIE, index=False)
    print(f"✅ Écrit : {len(df)} joueurs -> {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()
