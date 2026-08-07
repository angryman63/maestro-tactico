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
    chiffre après le 'D')."""
    renommage = {}
    for col in df.columns:
        m = re.match(r'^D-(\d{1,2})$', str(col))
        if m:
            renommage[col] = f"D{m.group(1)}"
    return df.rename(columns=renommage)


def _detecter_cols_journees(df):
    return [c for c in df.columns if re.match(r'^D\d{1,2}$', str(c))]


def _nettoyer_contamination_n1(df, df_n1, cols_journees):
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

    Retourne (df_corrige, rapport: dict)."""
    cols_journees_n1 = [c for c in df_n1.columns if re.match(r'^D\d{1,2}$', str(c))]

    # --- 1. D1-D34 : décision GLOBALE (tout ou rien), pas colonne par colonne
    # ---
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
        cellules_non_nulles = [c for c in cols_journees if row[c] != 0]
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
        for c in cols_journees:
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

    À N'UTILISER QUE tant qu'aucun vrai résultat 26-27 n'est disponible.
    Une fois les 3 exports par taille de ligue disponibles, bascule sur
    scripts/fusionner_joueurs.py — ne réutilise plus ce script-ci (le
    garde-fou SEUIL_CONTAMINATION limite le risque d'un mauvais usage, mais
    scripts/fusionner_joueurs.py reste le bon outil une fois la vraie saison
    lancée)."""
    df = pd.read_excel(fichier_entree)
    df = _renommer_colonnes_journee(df)
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

    df, rapport = _nettoyer_contamination_n1(df, df_n1, cols_journees)
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

    print(f"Journées vérifiables (historique N-1 résolu, >= {MATCHS_MIN_ECHANTILLON} "
          f"journées non nulles) : {rapport['joueurs_verifiables_d']} joueurs")
    print(f"Taux de contamination D1-D34 détecté : {rapport['taux_contamination_d']:.1%} "
          f"({rapport['joueurs_contamines_d']} joueurs)")

    if rapport['d_colonnes_corrigees']:
        print("✅ Recyclage N-1 confirmé sur D1-D34 (>= 50%) — remis à zéro pour tous les joueurs.")
    else:
        print(
            "⚠️  Taux de contamination sous le seuil (50%) — D1-D34 laissées TELLES QUELLES. "
            "Si la vraie saison 26-27 a commencé, c'est le comportement attendu (ne touche "
            "jamais de vrais résultats). Si ce fichier est censé être pré-saison, vérifie "
            "manuellement avant de continuer : quelque chose ne correspond pas au cas connu."
        )

    print(f"Note/Buts/%Titu/Variation remis à zéro pour les joueurs à 0 match cette saison "
          f"(après correction D1-D34 éventuelle) : {rapport['nb_agregats_corriges']} joueur(s) concerné(s).")

    df.to_excel(FICHIER_SORTIE, index=False)
    print(f"✅ Écrit : {len(df)} joueurs -> {FICHIER_SORTIE}")


if __name__ == "__main__":
    main()
