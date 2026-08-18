import streamlit as st
import pandas as pd
import numpy as np
from modele import (
    compter_matchs, absences_consecutives, alerte_blessure,
    predire_note_hybride, trouver_historique_n1, poste_vers_ligne, simuler_proba_but,
    calculer_regularite_brute, stabiliser_valeur_saison, stabiliser_stats_proba_but, normaliser_recherche,
    mediane_n1_par_poste, calculer_repli_stabilisation, SEUIL_BLESSURE_LONGUE,
)
from utils.table_style import inject_style, pill, dash, name_cell, table_html, separateur, escape

# ---------------------------------------------------------------------------
# Colonnes d'enchères disponibles selon la taille de ligue (fichier joueurs enrichi)
# ---------------------------------------------------------------------------
TAILLES_LIGUE = {
    "6 joueurs": {
        "enchere": "Enchere moy/L6",
        "achat_t1": "% achat T1/L6",
    },
    "8 joueurs": {
        "enchere": "Enchere moy/L8",
        "achat_t1": "% achat T1/L8",
    },
    "10 joueurs": {
        "enchere": "Enchere moy/L10",
        "achat_t1": "% achat T1/L10",
    },
    "Toutes tailles": {
        "enchere": "Enchere moy",
        "achat_t1": "% achat T1",
    },
}

# ---------------------------------------------------------------------------
# Grille de poids ProbaBut/ProbaArret (point 6)
# ---------------------------------------------------------------------------
POIDS_PROBA_BASE = 0.18
MULTIPLICATEUR_POSTE_PROBA = {'A': 1.3, 'MO': 1.1, 'MD': 0.9, 'DL': 0.8, 'DC': 0.7, 'G': 1.4}
MULTIPLICATEUR_STRATEGIE_PROBA = {'stars': 1.2, 'valeurs_sures': 1.0, 'equilibre': 0.9, 'pepites': 0.8}
POSTES_SENSIBLES_STRATEGIE = {'A', 'MO', 'G'}

# Répartition du poids restant (1 - poids_ProbaBut) entre Note / Variation_residu /
# %Titu / AchatT1, par stratégie (point 7). Fractions exactes sur quinzièmes pour
# que la somme retombe pile sur 1.0 (les pourcentages arrondis type "13.3%" du
# cahier des charges correspondent à 2/15, pas exactement 0.133).
#
# Cas particulier de Stars : Variation_residu (résidu d'une régression Variation ~
# Note + Cote) est construit pour être décorrélé de la Cote — or le seuil de
# qualification Stars (Cote_pct >= 0.85 et Note_pct >= 0.75) tasse déjà Note/
# ProbaBut/AchatT1 près de leur plafond parmi les qualifiés, alors que Variation_residu
# garde tout son étalement. Résultat : à poids égal (2/15 chacun), c'était Variation_residu
# qui décidait de facto du haut du classement Stars, au point de faire dépasser des
# joueurs bien moins chers/moins demandés (ex. Cote 18 devant Cote 39) — sans lien avec
# le prix ou la demande réelle, alors que Stars vise justement les valeurs sûres du haut
# du marché. Poids réduit à 3% pour Stars uniquement (Valeurs sûres/Équilibre/Pépites
# inchangés, le diagnostic n'ayant pas montré le même problème pour eux), le report se
# faisant sur AchatT1 (23,6%) pour renforcer le poids de la demande de marché réelle.
PROPORTIONS_RESTANT = {
    'stars':         {'note': 0.60, 'variation_residu': 0.03, 'titu': 2 / 15, 'achat_t1': 1 - 0.60 - 0.03 - 2 / 15},
    'valeurs_sures': {'note': 8 / 15, 'variation_residu': 3 / 15, 'titu': 2 / 15, 'achat_t1': 2 / 15},
    'equilibre':     {'note': 7 / 15, 'variation_residu': 2 / 15, 'titu': 3 / 15, 'achat_t1': 3 / 15},
    'pepites':       {'note': 7 / 15, 'variation_residu': 2 / 15, 'titu': 2 / 15, 'achat_t1': 4 / 15},
}


def _colonnes_taille(df, taille_label):
    # Priorité à la colonne spécifique à la taille choisie (ex. '% achat
    # T1/L6' pour "6 joueurs"), repli sur la colonne "Toutes tailles"
    # seulement si la colonne spécifique n'existe pas du tout dans le
    # fichier — jamais l'inverse, sans quoi sélectionner "6/8/10 joueurs"
    # afficherait quand même la tension/demande toutes tailles confondues
    # dès que '% achat T1' existe (col_enchere applique déjà cette priorité
    # dans le bon sens ; col_achat était inversée).
    cfg = TAILLES_LIGUE[taille_label]
    col_enchere = cfg["enchere"] if cfg["enchere"] in df.columns else "Enchere moy"
    col_achat = cfg["achat_t1"] if cfg["achat_t1"] in df.columns else "% achat T1"
    return col_enchere, col_achat


def _tension(pct):
    if pd.isna(pct):
        return "?"
    if pct >= 80:
        return "🔥🔥 Très demandé"
    if pct >= 50:
        return "🔥 Demandé"
    if pct >= 20:
        return "Peu demandé"
    return "Très peu demandé"


def _pill_demande(val):
    val = str(val)
    if 'Très demandé' in val:
        return pill(val, 'info')
    if 'Très peu demandé' in val:
        # Gris neutre plutôt que rouge : la plupart des joueurs de rotation
        # tombent naturellement ici (surtout depuis la suppression du plafond
        # d'affichage) — ce n'est pas une alerte, juste une demande faible.
        # Le rouge ('bad') reste réservé aux vraies alertes (À éviter, blessures).
        return pill(val, 'neutral')
    if 'Demandé' in val:
        return pill(val, 'good')
    if 'Peu demandé' in val:
        return pill(val, 'warn')
    return dash(val)


def _pill_alerte(val):
    val = '' if pd.isna(val) else str(val).strip()
    if not val:
        return dash()
    # 🆕 (jamais titulaire cette saison) n'est pas une alerte de blessure —
    # style neutre plutôt que 'bad' (rouge), réservé aux vraies blessures/
    # retours (🚑🩹🏥🐢).
    return pill(val, 'info' if val.startswith('🆕') else 'bad')


def _formater_cellule(col, val):
    # 'Demande'/'Enchère moy.' peuvent porter un suffixe dynamique ("(estimée
    # N-1)") tant que les vraies données d'enchères 26-27 ne sont pas
    # disponibles (cf. label_demande/label_enchere dans afficher_mercato) —
    # comparaison par préfixe pour continuer à matcher dans les deux cas.
    if col.startswith('Demande'):
        return _pill_demande(val)
    if col == 'Alerte':
        return _pill_alerte(val)
    if col == 'Joueur':
        return name_cell(val)
    if pd.isna(val):
        return dash()
    if col == 'Cote':
        return f"{val:.0f}"
    if col.startswith('Enchère moy.'):
        return f"{val:.1f}"
    if col == 'Note':
        return f"{val:.2f}"
    if col == 'Buts':
        return f"{val:.0f}"
    if col == '% Titu (estimé)':
        return f"{val:.0f}%"
    if col == 'Matchs joués':
        return f"{val:.0f}"
    if isinstance(val, (float, np.floating)):
        # Filet de sécurité : toute colonne numérique calculée non listée
        # explicitement ci-dessus est arrondie avant affichage, pour ne
        # jamais montrer les artefacts de virgule flottante bruts d'un
        # calcul (ex. 56.99999999999999 au lieu de 57).
        return f"{val:.2f}"
    return str(val)


def _table_html(df):
    return table_html(df, _formater_cellule)


def _moyenne_ecart_type_notes(row, cols_journees):
    """Moyenne/écart-type des notes jouées cette saison (mêmes conventions que
    utils/adversaire.py::_joueur_vers_mc). Replie sur la note saison brute
    (écart-type nul) si le joueur n'a encore aucune note exploitable cette
    saison."""
    notes = [row[col] for col in cols_journees if row[col] > 0]
    if not notes:
        return pd.Series({'MoyenneNote': float(row.get('Note', 5.0)), 'EcartTypeNote': 0.0})
    return pd.Series({'MoyenneNote': np.mean(notes), 'EcartTypeNote': np.std(notes)})


def calculer_score_mercato(row, strategie):
    """
    Score Mercato (point 6/7) : poids_ProbaBut = 0.18 × multiplicateur_poste ×
    multiplicateur_stratégie (ce dernier ne s'applique qu'aux postes A/MO/G),
    le reste (1 - poids_ProbaBut) se répartissant entre Note / Variation_residu
    / %Titu / AchatT1 selon des proportions fixes par stratégie. La somme des
    poids vaut toujours 1.0, quel que soit le poste ou la stratégie.

    Si AchatT1_norm est NaN (donnée '% achat T1' absente du fichier source pour
    ce joueur, pas une valeur nulle) : pas de repli fabriqué (une enchère à 0%
    n'a pas le même sens qu'une donnée manquante). Son poids est retiré et
    redistribué proportionnellement sur les 4 composantes restantes (ProbaBut,
    Note, Variation_residu, %Titu), pour que la somme des poids reste 1.0 —
    le score garde ainsi la même échelle, sans pénalité mécanique liée à une
    donnée simplement indisponible.
    """
    poste = row['Poste']
    mult_poste = MULTIPLICATEUR_POSTE_PROBA.get(poste, 1.0)
    mult_strategie = (
        MULTIPLICATEUR_STRATEGIE_PROBA[strategie] if poste in POSTES_SENSIBLES_STRATEGIE else 1.0
    )
    poids_proba = POIDS_PROBA_BASE * mult_poste * mult_strategie
    reste = 1 - poids_proba
    prop = PROPORTIONS_RESTANT[strategie]

    proba = row['ProbaBut_norm'] * 10
    note = row['NoteStabilisee']
    variation_residu = row['Variation_residu_norm'] * 10
    titu = row['TituStabilisee'] / 100 * 10

    poids_note = reste * prop['note']
    poids_variation = reste * prop['variation_residu']
    poids_titu = reste * prop['titu']
    poids_achat = reste * prop['achat_t1']

    if pd.isna(row['AchatT1_norm']):
        renormalisation = 1 / (1 - poids_achat)
        return (
            poids_proba * renormalisation * proba +
            poids_note * renormalisation * note +
            poids_variation * renormalisation * variation_residu +
            poids_titu * renormalisation * titu
        )

    achat_t1 = row['AchatT1_norm'] * 10
    if strategie in ('equilibre', 'pepites'):
        achat_t1 = 10 - achat_t1

    return (
        poids_proba * proba +
        poids_note * note +
        poids_variation * variation_residu +
        poids_titu * titu +
        poids_achat * achat_t1
    )


def _rarement_apparition(row, journee_actuelle, df_n1, cols_journees_n1):
    """Critère "Joue très peu" de "À éviter" (point 2) : matchs_joues /
    journee_actuelle < 20%, à partir de la journée 8 uniquement.

    Avant J8, l'échantillon de la saison en cours est trop petit pour juger
    équitablement — on applique à la place une présomption basée sur la
    participation N-1 du joueur (même correspondance que trouver_historique_n1,
    utilisée partout ailleurs) : un historique N-1 fiable montrant une faible
    participation (matchs_joues_N1 / nb_journees_N1 < 20%) classe le joueur "à
    éviter" par défaut pour ce critère — SAUF si sa saison en cours prouve déjà
    le contraire (dès que matchs_joues/journee_actuelle >= 20% cette saison,
    même sur un tout petit échantillon, ça l'emporte immédiatement sur son
    passif N-1). Sans historique N-1 fiable (recrue, débutant, homonyme
    ambigu) : aucune présomption dans un sens ou l'autre — ni "à éviter" par ce
    motif, ni exemption.

    Retourne (est_rare: bool, motif: str | None)."""
    ratio_actuelle = (row['Matchs_joues'] / journee_actuelle) if journee_actuelle > 0 else 0.0

    if journee_actuelle >= 8:
        if ratio_actuelle < 0.20:
            return True, "Joue très peu"
        return False, None

    row_n1 = trouver_historique_n1(row['Joueur'], row['Poste'], df_n1)
    if row_n1 is None:
        return False, None
    matchs_n1 = compter_matchs(row_n1, cols_journees_n1)
    ratio_n1 = matchs_n1 / len(cols_journees_n1) if len(cols_journees_n1) else 0.0
    if ratio_n1 >= 0.20:
        return False, None
    if ratio_actuelle >= 0.20:
        return False, None
    return True, "Jouait très peu la saison passée (présomption N-1)"


def afficher_mercato(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle):
    with st.container(key="mercato_page_wrap"):
        inject_style()
        separateur("TAILLE DE LA LIGUE")
        # --- Sélecteur de taille de ligue ---
        taille_choisie = st.radio(
            "Taille de la ligue :",
            list(TAILLES_LIGUE.keys()),
            horizontal=True,
            key="mercato_taille_ligue",
            label_visibility="collapsed"
        )
        col_enchere, col_achat = _colonnes_taille(df, taille_choisie)
        # Avant les vrais exports 6/8/10 joueurs (ex. tout début de saison, un seul
        # fichier source sans colonnes d'enchères) : aucune colonne Enchere/AchatT1
        # n'existe du tout dans df. Pour un joueur avec un historique N-1 fiable
        # (même correspondance trouver_historique_n1 que Note/%Titu/ProbaBut), son
        # enchère/demande RÉELLE de la saison 25-26 sert de référence — utilisée
        # silencieusement, sans mention technique dans le libellé affiché (même
        # convention que Note/%Titu : l'utilisateur voit une valeur, pas sa
        # provenance). Pour un joueur SANS historique N-1 (vraie recrue/inconnu),
        # aucune donnée n'est inventée (pas de repli sur une médiane de poste,
        # contrairement à Note/%Titu) : "—"/"?" comme avant, cohérent avec le
        # principe de ne jamais fabriquer une info pour un joueur dont on ne sait
        # vraiment rien.
        # AchatT1 devient une vraie valeur numérique pour les joueurs concernés,
        # donc AchatT1_norm n'est plus NaN pour eux et calculer_score_mercato()
        # utilise la formule pondérée normale au lieu de la redistribuer ; ce
        # mécanisme de redistribution reste actif tel quel pour les inconnus
        # (AchatT1 toujours NaN pour eux) — son cas d'usage d'origine.
        enchere_disponible = col_enchere in df.columns and col_achat in df.columns
        label_enchere = 'Enchère moy.'
        label_demande = 'Demande'

        if enchere_disponible and taille_choisie != "Toutes tailles" and TAILLES_LIGUE[taille_choisie]["enchere"] not in df.columns:
            st.caption(
                f"Pas de donnée détaillée pour les ligues à {taille_choisie.split()[0]} — "
                f"affichage de l'enchère moyenne toutes tailles confondues."
            )

        base_cols = ['Joueur', 'Club', 'Poste', 'Cote',
                     'Note', 'Variation', 'Buts', '%Titu', 'Indispo ?']
        df_mercato = df[base_cols].copy()

        if enchere_disponible:
            df_mercato['Enchere'] = df[col_enchere]
            df_mercato['AchatT1'] = df[col_achat]
        else:
            col_enchere_n1, col_achat_n1 = _colonnes_taille(df_n1, taille_choisie)

            def _enchere_n1(row):
                row_n1 = trouver_historique_n1(row['Joueur'], row['Poste'], df_n1)
                if row_n1 is not None and pd.notna(row_n1.get(col_enchere_n1)):
                    return row_n1[col_enchere_n1]
                return np.nan

            def _achat_n1(row):
                row_n1 = trouver_historique_n1(row['Joueur'], row['Poste'], df_n1)
                if row_n1 is not None and pd.notna(row_n1.get(col_achat_n1)):
                    return row_n1[col_achat_n1]
                return np.nan

            df_mercato['Enchere'] = df.apply(_enchere_n1, axis=1)
            df_mercato['AchatT1'] = df.apply(_achat_n1, axis=1)

        for col in ['Cote', 'Enchere', 'AchatT1', 'Note', 'Variation', 'Buts', '%Titu']:
            df_mercato[col] = pd.to_numeric(df_mercato[col], errors='coerce')

        df_mercato = df_mercato.dropna(subset=['Cote', 'Note', 'Variation', '%Titu'])
        df_mercato = df_mercato[df_mercato['Cote'] > 0]

        nb_journees = len(cols_journees)
        seuil_matchs = int(nb_journees * 0.40)

        df_mercato['Matchs_joues'] = df.apply(
            lambda row: compter_matchs(row, cols_journees), axis=1)
        df_mercato['Absences_recentes'] = df.apply(
            lambda row: absences_consecutives(row, cols_journees, journee_actuelle), axis=1)
        df_mercato['Alerte'] = df.apply(
            lambda row: alerte_blessure(row, cols_journees, journee_actuelle), axis=1)
        df_mercato['Ratio'] = df_mercato['Note'] / df_mercato['Cote']  # gardée pour affichage éventuel, plus utilisée dans les scores

        # Note stabilisée (point 9) : la Note brute d'un joueur à 1-2 matchs joués
        # cette saison n'est pas fiable (un seul bon match suffit à la faire
        # décoller) — on la mélange avec sa Note de saison N-1 selon la même
        # grille progressive (poids_phase) que predire_note_hybride(), mais
        # appliquée à la moyenne de saison plutôt qu'à la prédiction pondérée
        # récente de predire_note() : ça stabilise les petits échantillons sans
        # jamais réintroduire de biais de forme récente (Mercato n'utilise
        # volontairement pas de Forme 6J). Utilisée dans les formules de score/
        # percentile ci-dessous, ET dans la colonne 'Note' affichée (remplacée par
        # la valeur stabilisée juste après TituStabilisee, cf. plus bas) : la
        # moyenne brute de saison n'a aucun sens tant que la saison n'a pas
        # commencé (0 pour tout le monde), contrairement à Buts/Matchs joués qui
        # restent de vraies informations factuelles même à 0.
        #
        # Le repli poste (médiane de Note, calculé sur les joueurs à échantillon
        # fiable — >= 3 matchs cette saison) sert aussi de garde-fou côté N-1 :
        # si l'historique N-1 d'un joueur repose lui-même sur peu de matchs, il
        # est mélangé à ce repli plutôt que transféré tel quel (cf. docstring de
        # stabiliser_valeur_saison).
        df_fiable_note = df_mercato.loc[df_mercato['Matchs_joues'] >= 3]
        note_mediane_poste = df_fiable_note.groupby('Poste')['Note'].median().to_dict()
        note_repli_global = df_fiable_note['Note'].median()
        if pd.isna(note_repli_global):
            # Tout début de saison : personne n'a encore >= 3 matchs, le repli
            # "saison en cours" est vide -- repli sur la médiane N-1 par poste
            # (données réelles, disponibles indépendamment de l'avancement de la
            # saison en cours), pour qu'un joueur sans historique N-1 propre (ex.
            # transfert sans passage en Ligue 1 la saison passée, type Openda)
            # retombe sur une estimation crédible pour son poste plutôt qu'un
            # faux zéro brut.
            note_mediane_poste, note_repli_global = mediane_n1_par_poste(df_n1, 'Note')

        df_mercato['NoteStabilisee'] = df.apply(
            lambda row: stabiliser_valeur_saison(
                trouver_historique_n1(row['Joueur'], row['Poste'], df_n1), cols_journees_n1,
                row, cols_journees, journee_actuelle, 'Note',
                note_mediane_poste.get(row['Poste'], note_repli_global)
            ),
            axis=1
        )
        df_mercato['NoteStabilisee'] = df_mercato['NoteStabilisee'].fillna(df_mercato['Note'])

        # %Titu stabilisé (même principe que NoteStabilisee, même fonction générique) :
        # contrairement à Note, %Titu brut n'a AUCUN autre repli N-1 dans tout le code —
        # utilisé tel quel, il resterait bloqué à 0 pour 100% des joueurs tant qu'aucun
        # match 26-27 n'est joué (0 est la valeur brute correcte, mais rend Stars/
        # Valeurs sûres/Pépites structurellement vides puisque ces catégories exigent
        # %Titu >= 50/60 : aucun joueur ne peut jamais les atteindre sans ce repli).
        df_fiable_titu = df_mercato.loc[df_mercato['Matchs_joues'] >= 3]
        titu_mediane_poste = df_fiable_titu.groupby('Poste')['%Titu'].median().to_dict()
        titu_repli_global = df_fiable_titu['%Titu'].median()
        if pd.isna(titu_repli_global):
            # Même repli ultime que Note ci-dessus (médiane N-1 par poste).
            titu_mediane_poste, titu_repli_global = mediane_n1_par_poste(df_n1, '%Titu')

        df_mercato['TituStabilisee'] = df.apply(
            lambda row: stabiliser_valeur_saison(
                trouver_historique_n1(row['Joueur'], row['Poste'], df_n1), cols_journees_n1,
                row, cols_journees, journee_actuelle, '%Titu',
                titu_mediane_poste.get(row['Poste'], titu_repli_global)
            ),
            axis=1
        )
        df_mercato['TituStabilisee'] = df_mercato['TituStabilisee'].fillna(df_mercato['%Titu'])

        # Affichage : les colonnes visibles 'Note' et '%Titu' montrent désormais
        # la version stabilisée (100% N-1 tant que la saison en cours n'a rien à
        # offrir) plutôt que la valeur brute de saison en cours (0.00/0% pour
        # tout le monde en pré-saison, sans aucun sens pour l'utilisateur) —
        # cohérent avec le score/les seuils de catégorie, qui utilisent déjà ces
        # mêmes colonnes stabilisées. 'Buts' et 'Matchs_joues' restent bruts : ce
        # sont de vraies informations factuelles sur la saison en cours (0 y est
        # honnête), pas des estimations à stabiliser.
        df_mercato['Note'] = df_mercato['NoteStabilisee']
        df_mercato['%Titu'] = df_mercato['TituStabilisee']

        stats_notes = df.apply(lambda row: _moyenne_ecart_type_notes(row, cols_journees), axis=1)
        df_mercato['MoyenneNote'] = stats_notes['MoyenneNote']
        df_mercato['EcartTypeNote'] = stats_notes['EcartTypeNote']
        # Régularité : fonction centralisée (modele.py::calculer_regularite_brute),
        # avec repli sur le profil N-1 réel du joueur quand la saison en cours n'a
        # encore aucune note exploitable — même logique que Conseiller Hebdo et
        # Simuler le match (get_joueur_info), pour qu'un joueur fiable en N-1 ne
        # reste pas bloqué à 0.0 (et donc que Fiabilite ci-dessous ne se réduise
        # pas silencieusement à son seul terme %Titu tant que la saison n'a pas
        # commencé).
        df_mercato['Regularite'] = df.apply(
            lambda row: calculer_regularite_brute(
                row, cols_journees,
                trouver_historique_n1(row['Joueur'], row['Poste'], df_n1), cols_journees_n1
            ),
            axis=1
        )

        # Moyenne/écart-type stabilisés (même principe que NoteStabilisee) : un
        # joueur à 1-2 matchs joués a une moyenne non représentative (un seul bon
        # ou mauvais match) et un écart-type quasi nul (variance nulle sur un seul
        # échantillon), ce qui resserre artificiellement sa distribution simulée
        # et gonfle son ProbaBut à des valeurs irréalistes (souvent 100%/0%). Les
        # replis (moyenne/écart-type médians du poste) sont calculés par la même
        # fonction centralisée que Simuler le match (modele.py::
        # calculer_repli_stabilisation, sur les seuls joueurs à échantillon
        # fiable >= 3 matchs et lignes valides — Cote/Note/Variation/%Titu non
        # NaN et Cote > 0), pour ne jamais risquer que les deux pages retombent
        # sur des repli différents.
        (moyenne_mediane_poste, moyenne_repli_global,
         ecart_type_mediane_poste, ecart_type_repli_global) = calculer_repli_stabilisation(df, cols_journees)
        # Tout début de saison : personne n'a encore >= 3 matchs, la population
        # fiable est vide et ces médianes valent NaN — repli neutre (note 5/10,
        # écart-type modéré) plutôt qu'un NaN qui ferait planter simuler_proba_but()
        # (ecart_type <= 0 sur None lève une TypeError) pour tout joueur sans note
        # actuelle NI historique N-1 (ex. transfert sans historique Ligue 1 : Openda).
        if pd.isna(moyenne_repli_global):
            moyenne_repli_global = 5.0
        if pd.isna(ecart_type_repli_global):
            ecart_type_repli_global = 1.0

        stats_stabilisees = df.apply(
            lambda row: stabiliser_stats_proba_but(
                trouver_historique_n1(row['Joueur'], row['Poste'], df_n1), cols_journees_n1,
                row, cols_journees, journee_actuelle,
                moyenne_mediane_poste.get(row['Poste'], moyenne_repli_global),
                ecart_type_mediane_poste.get(row['Poste'], ecart_type_repli_global)
            ),
            axis=1, result_type='expand'
        )
        df_mercato['MoyenneStabilisee'] = stats_stabilisees[0]
        df_mercato['EcartTypeStabilise'] = stats_stabilisees[1]

        # --- Tension du marché (à partir du % achat T1) ---
        df_mercato['Tension'] = df_mercato['AchatT1'].apply(_tension)

        # --- Rangs percentile Cote/Note par poste (réutilisés par "À éviter" et par les
        # seuils de catégorie plus bas) ---
        df_mercato['Cote_pct'] = df_mercato.groupby('Poste')['Cote'].rank(pct=True)
        df_mercato['Note_pct'] = df_mercato.groupby('Poste')['NoteStabilisee'].rank(pct=True)

        # À éviter — 3 critères indépendants (logique OU) : un seul suffit à qualifier
        # le joueur, peu importe les autres. Calculé en mask pour pouvoir exclure ces
        # joueurs des 4 autres stratégies plus bas (mutuellement exclusif, cf. mask_stars
        # etc.) — un joueur "à éviter" n'apparaît jamais ailleurs, quel que soit le
        # critère qui l'y a placé.
        # 1. Cher pour SON poste (au-delà du 60e percentile) ET décevant pour SON poste
        #    (note sous la médiane) — seuils relatifs au poste, pas de seuil universel.
        mask_cher_decevant = (df_mercato['Cote_pct'] > 0.60) & (df_mercato['Note_pct'] < 0.50)
        # 2. Joue très peu (matchs_joues / journee_actuelle < 20%), à partir
        #    de la journée 8 — même seuil calendaire que celui déjà utilisé par le
        #    modèle hybride (poids_phase, plafond_calendaire=True). Avant J8, repli
        #    sur une présomption basée sur l'historique N-1 (cf. _rarement_apparition) :
        #    aucun repli fabriqué en l'absence d'historique N-1 fiable.
        rarement = df_mercato.apply(
            lambda row: _rarement_apparition(row, journee_actuelle, df_n1, cols_journees_n1),
            axis=1, result_type='expand'
        )
        df_mercato['_rarement_flag'] = rarement[0]
        df_mercato['_rarement_motif'] = rarement[1]
        mask_rarement = df_mercato['_rarement_flag']
        # 3. Particulièrement mauvais pour son poste (Note_pct <= 15%), peu importe le
        #    prix — un joueur pas cher mais très en dessous de son poste reste un
        #    mauvais choix, pas juste une "pépite" à cause de son prix bas.
        mask_note_tres_faible = df_mercato['Note_pct'] <= 0.15
        # 4. Blessure longue : Indispo=True ET SEUIL_BLESSURE_LONGUE+ matchs consécutifs
        #    sans jouer (constante partagée avec le badge 🚑 d'alerte_blessure, modele.py)
        #    — indépendant du prix/de la note, un joueur durablement indisponible est à
        #    éviter au mercato peu importe ses statistiques passées (colonnes déjà
        #    calculées plus haut : 'Indispo ?' vient directement de df, 'Absences_recentes'
        #    réutilise absences_consecutives()).
        mask_indispo_longue = (
            df_mercato['Indispo ?'].fillna(False).astype(bool)
            & (df_mercato['Absences_recentes'] >= SEUIL_BLESSURE_LONGUE)
        )
        mask_eviter = mask_cher_decevant | mask_rarement | mask_note_tres_faible | mask_indispo_longue
        # Masques exposés en colonnes pour que _raison_eviter() (plus bas) les LISE
        # au lieu de retaper les mêmes seuils en toutes lettres — un seul endroit à
        # faire évoluer si un seuil "À éviter" change un jour.
        df_mercato['_cher_decevant'] = mask_cher_decevant
        df_mercato['_note_tres_faible'] = mask_note_tres_faible
        df_mercato['_indispo_longue'] = mask_indispo_longue
        df_eviter = df_mercato[mask_eviter].copy()

        # --- ProbaBut / ProbaArret (point 1) : Monte Carlo face aux moyennes de ligne de la ligue ---
        df_mercato['Ligne'] = df_mercato['Poste'].apply(poste_vers_ligne)
        moyennes_lignes = df_mercato.groupby('Ligne')['MoyenneNote'].mean().to_dict()
        for ligne in ['ATT', 'MIL', 'DEF', 'GB']:
            moyennes_lignes.setdefault(ligne, 5.0)

        df_mercato['ProbaBut'] = df_mercato.apply(
            lambda row: simuler_proba_but(
                row['MoyenneStabilisee'], row['EcartTypeStabilise'], row['Poste'], moyennes_lignes
            ),
            axis=1
        )

        # --- Variation_residu (point 4) : résidu de Variation ~ Note + Cote ---
        X = np.column_stack([
            np.ones(len(df_mercato)),
            df_mercato['NoteStabilisee'].to_numpy(dtype=float),
            df_mercato['Cote'].to_numpy(dtype=float),
        ])
        y = df_mercato['Variation'].to_numpy(dtype=float)
        coeffs, *_ = np.linalg.lstsq(X, y, rcond=None)
        df_mercato['Variation_residu'] = y - X @ coeffs

        # --- Normalisation en rang percentile, séparément par poste (point 5) ---
        for col in ['ProbaBut', 'Variation_residu', 'AchatT1']:
            df_mercato[f'{col}_norm'] = df_mercato.groupby('Poste')[col].rank(pct=True)

        for strategie in ['stars', 'valeurs_sures', 'equilibre', 'pepites']:
            df_mercato[f'Score_{strategie}'] = df_mercato.apply(
                lambda row: calculer_score_mercato(row, strategie), axis=1
            )

        # --- Seuils de catégorie par poste, en RANG PERCENTILE (point 8) — 4 critères
        # RÉELLEMENT distincts (pas 3 bandes d'un même score, cf. correction ci-dessous) :
        # Stars = chers ET excellents ; Valeurs sûres = prix moyen-élevé ET fiables
        # (%Titu/régularité) ; Pépites = pas chers ET corrects ; Équilibre = catégorie
        # résiduelle (tout le reste), pour garantir que Stars+Valeurs+Équilibre+Pépites
        # couvrent 100% de chaque poste, sans trou. (Note_pct/Cote_pct déjà calculés
        # plus haut, réutilisés ici tels quels.)

        # Fiabilité (Valeurs sûres) : mélange %Titu (dispo) + régularité (constance des
        # notes), percentilée par poste — distincte de "Note" (qui mesure l'excellence,
        # pas la fiabilité).
        df_mercato['Fiabilite'] = 0.6 * (df_mercato['TituStabilisee'] / 100) + 0.4 * df_mercato['Regularite']
        df_mercato['Fiabilite_pct'] = df_mercato.groupby('Poste')['Fiabilite'].rank(pct=True)

        # Score pépite : prix bas (rang inversé) + note correcte, re-percentilé par poste
        # pour garantir un palier "top X%" exact (la combinaison brute n'est pas uniforme).
        #
        # Calculé UNIQUEMENT parmi les joueurs qui passent déjà le filtre de titularisation
        # de Pépites (%Titu >= 50) au sein du même poste — pas sur le poste entier. Sinon,
        # les joueurs jamais utilisés (prix plancher mécanique, souvent 3e/4e choix) polluent
        # le haut du classement "pas cher" avec une cherté nulle qu'ils n'ont jamais eu à
        # justifier par du temps de jeu, écrasant le rang des joueurs qui jouent réellement.
        # Diagnostic Gardiens : 32% de gardiens jamais utilisés cette saison, tous au prix
        # plancher du poste, contre seulement 5-10% sur les autres postes — assez pour que
        # le meilleur gardien réellement titulaire ne dépasse jamais le seuil de 0.85 alors
        # qu'il le devrait. Restreindre le pourcentile à la sous-population qui joue déjà
        # élimine cette pollution sur tous les postes, uniformément (effet mineur ailleurs,
        # où la proportion de joueurs jamais utilisés est bien plus faible).
        mask_titu_pepites = df_mercato['TituStabilisee'] >= 50
        df_actifs = df_mercato.loc[mask_titu_pepites]
        cote_pct_actifs = df_actifs.groupby('Poste')['Cote'].rank(pct=True)
        note_pct_actifs = df_actifs.groupby('Poste')['NoteStabilisee'].rank(pct=True)
        score_pepite_actifs = 0.6 * (1 - cote_pct_actifs) + 0.4 * note_pct_actifs
        df_mercato['Score_pepite_pct'] = np.nan
        df_mercato.loc[mask_titu_pepites, 'Score_pepite_pct'] = (
            score_pepite_actifs.groupby(df_actifs['Poste']).rank(pct=True)
        )

        mask_stars = (
            (df_mercato['Cote_pct'] >= 0.95) &
            (df_mercato['Note_pct'] >= 0.85) &
            (df_mercato['TituStabilisee'] >= 60) &
            (df_mercato['Tension'] != "Très peu demandé") &
            ~mask_eviter
        )
        # Pépites calculé avant Valeurs sûres : en cas de chevauchement (joueur cher-moyen
        # ET fiable ET par ailleurs "pas cher + correct" pour son poste), Pépites prime —
        # son critère de prix est le plus objectif et le plus attendu par un utilisateur
        # qui cherche justement un bon coup pas cher.
        mask_pepites = (
            (df_mercato['Score_pepite_pct'] >= 0.85) &
            (df_mercato['TituStabilisee'] >= 50) &
            ~mask_eviter
        )
        mask_valeurs = (
            (df_mercato['Cote_pct'] >= 0.50) & (df_mercato['Cote_pct'] < 0.85) &
            (df_mercato['Fiabilite_pct'] >= 0.60) &
            (df_mercato['TituStabilisee'] >= 60) &
            ~mask_eviter &
            ~mask_pepites
        )
        # Équilibre = tout le reste (catégorie résiduelle, aucun critère propre) : garantit
        # structurellement qu'aucun joueur n'est absent des 4 stratégies combinées. "À
        # éviter" en est explicitement exclu aussi (catégories mutuellement exclusives :
        # un joueur "à éviter" n'apparaît nulle part ailleurs).
        mask_equilibre = ~mask_stars & ~mask_valeurs & ~mask_pepites & ~mask_eviter

        # Étiquette de catégorie par joueur (les 5 masques sont mutuellement exclusifs,
        # cf. plus haut) — utilisée par la recherche globale ci-dessous pour indiquer
        # dans quelle stratégie chaque résultat apparaît, sans dépendre de l'onglet
        # actuellement sélectionné.
        df_mercato['Categorie'] = np.select(
            [mask_stars, mask_valeurs, mask_pepites, mask_eviter, mask_equilibre],
            ['Stars', 'Valeurs sûres', 'Pépites', 'À éviter', 'Équilibre'],
            default='?'
        )

        df_stars = df_mercato[mask_stars].copy()
        df_valeurs = df_mercato[mask_valeurs].copy()
        df_pepites = df_mercato[mask_pepites].copy()
        df_equilibre = df_mercato[mask_equilibre].copy()

        # ============================================================
        # BANDEAU TITRE + CHIFFRES CLÉS — habillage visuel, placé ici (après
        # tout le pipeline de scoring, avant la stratégie/le tableau) : le
        # repère contextuel a besoin de taille_choisie (résolue plus haut) et
        # les 4 cartouches lisent df_mercato/df_pepites déjà entièrement
        # calculés, sans dupliquer aucun calcul de score.
        # ============================================================
        repere_journee = "Pré-saison" if journee_actuelle == 0 else f"Journée {journee_actuelle}"
        st.markdown(
            f"""
            <div class="gs-page-header">
              <div class="gs-page-header-logo">MT</div>
              <div class="gs-page-header-text">
                <div class="gs-page-header-title">Conseiller Mercato</div>
              </div>
              <div class="gs-page-header-context">{escape(repere_journee)} · {escape(taille_choisie)}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # --- Pépite du moment : meilleur Score_pepites de la catégorie Pépites
        # (même colonne de tri que celle utilisée par l'onglet "Pépites" lui-même,
        # cf. plus bas : top = df_poste.sort_values(f'Score_{strategie_key}', ...)). ---
        if len(df_pepites) > 0:
            top_pepite = df_pepites.loc[df_pepites['Score_pepites'].idxmax()]
            pepite_valeur = top_pepite['Joueur']
            pepite_sub = f"{top_pepite['Poste']} · {top_pepite['Club']} · Cote {top_pepite['Cote']:.0f}"
        else:
            pepite_valeur = "—"
            pepite_sub = "Aucun joueur éligible"

        # --- Le plus demandé : AchatT1 (demande réelle, ou repli N-1 si les
        # vraies enchères ne sont pas encore disponibles) le plus élevé, pour
        # la taille de ligue actuellement sélectionnée. ---
        df_demande = df_mercato.dropna(subset=['AchatT1'])
        if len(df_demande) > 0:
            top_demande = df_demande.loc[df_demande['AchatT1'].idxmax()]
            demande_valeur = top_demande['Joueur']
            demande_sub = f"{top_demande['AchatT1']:.0f}% d'achat T1"
        else:
            demande_valeur = "—"
            demande_sub = "Aucune donnée de demande"

        # --- Écart Cote/Enchère : parmi les joueurs à Cote >= 10 (seuil pour
        # exclure les joueurs peu pertinents), le plus grand écart relatif
        # (Enchère - Cote)/Cote — un joueur que le marché valorise nettement
        # au-dessus de sa cote officielle. ---
        df_ecart = df_mercato[(df_mercato['Cote'] >= 10) & df_mercato['Enchere'].notna()].copy()
        if len(df_ecart) > 0:
            df_ecart['_ecart_pct'] = (df_ecart['Enchere'] - df_ecart['Cote']) / df_ecart['Cote'] * 100
            top_ecart = df_ecart.loc[df_ecart['_ecart_pct'].idxmax()]
            ecart_valeur = f"{top_ecart['_ecart_pct']:+.0f}%"
            ecart_sub = f"{top_ecart['Joueur']} ({top_ecart['Cote']:.0f} → {top_ecart['Enchere']:.1f})"
        else:
            ecart_valeur = "—"
            ecart_sub = "Aucun joueur éligible (Cote ≥ 10)"

        st.markdown(
            f"""
            <div class="gs-kpi-row">
              <div class="gs-kpi-card">
                <div class="gs-kpi-label">Pépite du moment</div>
                <div class="gs-kpi-value">{escape(pepite_valeur)}</div>
                <div class="gs-kpi-sub">{escape(pepite_sub)}</div>
              </div>
              <div class="gs-kpi-card">
                <div class="gs-kpi-label">Le plus demandé</div>
                <div class="gs-kpi-value">{escape(demande_valeur)}</div>
                <div class="gs-kpi-sub">{escape(demande_sub)}</div>
              </div>
              <div class="gs-kpi-card">
                <div class="gs-kpi-label">Écart Cote/Enchère</div>
                <div class="gs-kpi-value">{escape(ecart_valeur)}</div>
                <div class="gs-kpi-sub">{escape(ecart_sub)}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        separateur("STRATÉGIE MERCATO")
        # Sélection stratégie
        strategie_choisie = st.radio(
            "Stratégie mercato :",
            ["Stars", "Valeurs sûres", "Équilibre", "Pépites", "À éviter"],
            horizontal=True,
            key="mercato_strategie",
            label_visibility="collapsed"
        )

        recherche_joueur = st.text_input(
            "🔎 Rechercher un joueur",
            key="mercato_recherche_joueur",
            placeholder="Nom du joueur…",
            help="Recherche sur tous les postes et toutes les catégories (Stars/Valeurs sûres/"
                 "Équilibre/Pépites/À éviter) à la fois — inutile de changer d'onglet au préalable."
        ).strip()

        with st.expander("🏥 Légende blessures"):
            st.markdown("""
    |  | Statut |
    |---|---|
    | 🚑 | Blessé — 8+ matchs manqués |
    | 🩹 | Blessé — moins de 8 matchs manqués |
    | 🏥 | Retour de blessure — 8+ matchs d'absence |
    | 🐢 | Retour de blessure — 4 à 7 matchs d'absence |
    | 🆕 | Pas encore titularisé cette saison (n'a jamais joué — distinct d'un retour de blessure) |
    """)

        cols_affichage = ['Joueur', 'Club', 'Poste', 'Cote', 'Enchere', 'Tension',
                           'Note', 'Buts', '%Titu', 'Matchs_joues', 'Alerte']

        strategie_map = {
            "Stars": ('stars', df_stars),
            "Valeurs sûres": ('valeurs_sures', df_valeurs),
            "Équilibre": ('equilibre', df_equilibre),
            "Pépites": ('pepites', df_pepites),
        }

        if recherche_joueur:
            # Recherche globale (tous postes et toutes catégories confondus) : ne
            # dépend ni de la stratégie ni de l'onglet poste sélectionné, pour que
            # l'utilisateur n'ait pas à cliquer onglet par onglet pour retrouver un
            # joueur précis. La colonne Catégorie indique où il apparaît réellement
            # (un même nom peut correspondre à plusieurs joueurs différents, dans
            # des catégories/postes distincts — chacun listé sur sa propre ligne).
            # Comparaison normalisée (accents + casse + séparateurs) : sans quoi un nom
            # tapé sans accent (ex. "Said" au lieu de "Saïd") ne trouverait rien, alors
            # que str.contains(case=False) ne gère que la casse, pas les accents — et un
            # nom composé tapé avec le mauvais séparateur (ex. "Saint Maximin" ou
            # "SaintMaximin" au lieu de "Saint-Maximin") ne trouverait rien non plus.
            noms_normalises = df_mercato['Joueur'].apply(normaliser_recherche)
            recherche_normalisee = normaliser_recherche(recherche_joueur)
            resultats = df_mercato[
                noms_normalises.str.contains(recherche_normalisee, na=False, regex=False)
            ].copy()
            if len(resultats) == 0:
                st.info("Aucun joueur trouvé.")
            else:
                resultats['ProbaBut'] = resultats['ProbaBut'].apply(lambda x: f"{x*100:.0f}%")
                st.markdown(
                    _table_html(
                        resultats[['Joueur', 'Club', 'Poste', 'Categorie', 'Cote', 'Enchere', 'Tension',
                                   'Note', 'Buts', '%Titu', 'Matchs_joues', 'Alerte', 'ProbaBut']
                                   ].sort_values('Cote', ascending=False
                                   ).rename(columns={
                                       'Enchere': label_enchere, 'Tension': label_demande,
                                       'Matchs_joues': 'Matchs joués', 'ProbaBut': 'Proba but/arrêt',
                                       '%Titu': '% Titu (estimé)',
                                   }).reset_index(drop=True)
                    ),
                    unsafe_allow_html=True
                )
        elif strategie_choisie == "À éviter":
            st.markdown(
                '<div style="font-family:\'Oswald\',sans-serif; font-weight:700; '
                'font-size:1.05rem; letter-spacing:0.04em; text-transform:uppercase; '
                'color:#c8a84b; margin:0.4rem 0 0.8rem;">Joueurs à éviter</div>',
                unsafe_allow_html=True
            )
            df_eviter_affiche = df_eviter.copy()

            def _raison_eviter(row):
                # Les 4 critères sont indépendants (OU) : un joueur peut en cumuler
                # plusieurs (ex. cher+décevant ET apparaît rarement) — toutes les
                # raisons qui s'appliquent sont listées, pas seulement la première.
                # Lit les masques déjà calculés (mask_cher_decevant, etc., exposés en
                # colonnes '_cher_decevant'/'_note_tres_faible'/'_indispo_longue' plus
                # haut) plutôt que de retaper les mêmes seuils ici — un seul endroit
                # à faire évoluer si un seuil "À éviter" change. Accessoirement,
                # corrige un oubli : "Blessure longue" (mask_indispo_longue) n'était
                # jusqu'ici jamais listée comme raison, même quand c'était le SEUL
                # critère qui qualifiait le joueur (Raison affichée vide dans ce cas).
                raisons = []
                if row['_cher_decevant']:
                    raisons.append(
                        "Cher + peu de matchs" if row['Matchs_joues'] < seuil_matchs
                        else "Cher + note décevante"
                    )
                if row['_rarement_flag']:
                    raisons.append(row['_rarement_motif'])
                if row['_note_tres_faible']:
                    raisons.append("Note très faible pour son poste")
                if row['_indispo_longue']:
                    raisons.append("Blessure longue")
                return " · ".join(raisons)

            df_eviter_affiche['Raison'] = df_eviter_affiche.apply(_raison_eviter, axis=1)
            st.markdown(
                _table_html(
                    df_eviter_affiche[['Joueur', 'Club', 'Poste', 'Cote', 'Enchere', 'Tension',
                               'Note', 'Matchs_joues', '%Titu', 'Alerte', 'Raison']
                               ].rename(columns={
                                   'Enchere': label_enchere, 'Tension': label_demande, 'Matchs_joues': 'Matchs joués',
                                   '%Titu': '% Titu (estimé)',
                               }).reset_index(drop=True)
                ),
                unsafe_allow_html=True
            )
        else:
            strategie_key, df_s = strategie_map[strategie_choisie]
            postes = {
                'A': 'Attaquants', 'MO': 'Milieux Off.',
                'MD': 'Milieux Déf.', 'DC': 'Défenseurs C.',
                'DL': 'Défenseurs L.', 'G': 'Gardiens'
            }
            tabs = st.tabs(list(postes.values()), key="mercato_postes")
            for tab, (code, nom) in zip(tabs, postes.items()):
                with tab:
                    df_poste = df_s[df_s['Poste'] == code]

                    # Plus de plafond d'affichage (point 2) : la catégorie entière est
                    # montrée, triée par score.
                    top = df_poste.sort_values(
                        f'Score_{strategie_key}', ascending=False
                    ).copy()
                    nom_colonne_proba = 'Proba arrêt' if code == 'G' else 'Proba but'
                    top['ProbaBut'] = top['ProbaBut'].apply(lambda x: f"{x*100:.0f}%")

                    if len(top) > 0:
                        st.markdown(
                            _table_html(
                                top[cols_affichage + ['ProbaBut']
                                    ].rename(columns={
                                        'Enchere': label_enchere, 'Tension': label_demande,
                                        'Matchs_joues': 'Matchs joués', 'ProbaBut': nom_colonne_proba,
                                        '%Titu': '% Titu (estimé)',
                                    }).reset_index(drop=True)
                            ),
                            unsafe_allow_html=True
                        )
                        if code == 'G':
                            for idx_gardien in top.index:
                                row_actuelle = df.loc[idx_gardien]
                                row_n1 = trouver_historique_n1(row_actuelle['Joueur'], row_actuelle['Poste'], df_n1)
                                _, mode_gardien = predire_note_hybride(
                                    row_n1, cols_journees_n1, row_actuelle, cols_journees, journee_actuelle
                                )
                                if mode_gardien not in (None, "100%_actuelle", "aucune_prediction_possible"):
                                    st.warning(
                                        f"**{row_actuelle['Joueur']}** — ⚠️ Note basée en grande partie sur la "
                                        "saison précédente — vérifiez que ce gardien reste bien titulaire cette "
                                        "saison avant de miser dessus."
                                    )
                    else:
                        st.info("Aucun joueur disponible")
