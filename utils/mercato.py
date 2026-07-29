import streamlit as st
import pandas as pd
import numpy as np
from modele import (
    nettoyer_note, compter_matchs, absences_consecutives, alerte_blessure,
    predire_note_hybride, trouver_historique_n1, poste_vers_ligne, simuler_proba_but,
    taux_regularite, stabiliser_note_saison,
)
from utils.table_style import inject_style, pill, dash, name_cell, table_html, separateur

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
PROPORTIONS_RESTANT = {
    'stars':         {'note': 9 / 15, 'variation_residu': 2 / 15, 'titu': 2 / 15, 'achat_t1': 2 / 15},
    'valeurs_sures': {'note': 8 / 15, 'variation_residu': 3 / 15, 'titu': 2 / 15, 'achat_t1': 2 / 15},
    'equilibre':     {'note': 7 / 15, 'variation_residu': 2 / 15, 'titu': 3 / 15, 'achat_t1': 3 / 15},
    'pepites':       {'note': 7 / 15, 'variation_residu': 2 / 15, 'titu': 2 / 15, 'achat_t1': 4 / 15},
}


def _colonnes_taille(df, taille_label):
    cfg = TAILLES_LIGUE[taille_label]
    col_enchere = cfg["enchere"] if cfg["enchere"] in df.columns else "Enchere moy"
    col_achat = "% achat T1" if "% achat T1" in df.columns else cfg["achat_t1"]
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
        return pill(val, 'bad')
    if 'Demandé' in val:
        return pill(val, 'good')
    if 'Peu demandé' in val:
        return pill(val, 'warn')
    return dash(val)


def _pill_alerte(val):
    val = '' if pd.isna(val) else str(val).strip()
    if not val:
        return dash()
    return pill(val, 'bad')


def _formater_cellule(col, val):
    if col == 'Demande':
        return _pill_demande(val)
    if col == 'Alerte':
        return _pill_alerte(val)
    if col == 'Joueur':
        return name_cell(val)
    if pd.isna(val):
        return dash()
    if col == 'Cote':
        return f"{val:.0f}"
    if col == 'Enchère moy.':
        return f"{val:.1f}"
    if col == 'Note':
        return f"{val:.2f}"
    if col == 'Buts':
        return f"{val:.0f}"
    if col == '%Titu':
        return f"{val:.0f}%"
    if col == 'Matchs joués':
        return f"{val:.0f}"
    return str(val)


def _table_html(df):
    return table_html(df, _formater_cellule)


def _moyenne_ecart_type_notes(row, cols_journees):
    """Moyenne/écart-type des notes jouées cette saison (mêmes conventions que
    get_stats_joueur_mc). Replie sur la note saison brute (écart-type nul) si
    le joueur n'a encore aucune note exploitable cette saison."""
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
    titu = row['%Titu'] / 100 * 10
    achat_t1 = row['AchatT1_norm'] * 10
    if strategie in ('equilibre', 'pepites'):
        achat_t1 = 10 - achat_t1

    return (
        poids_proba * proba +
        reste * prop['note'] * note +
        reste * prop['variation_residu'] * variation_residu +
        reste * prop['titu'] * titu +
        reste * prop['achat_t1'] * achat_t1
    )


def afficher_mercato(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle):
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

    if col_enchere not in df.columns:
        st.warning(
            "Aucune donnée d'enchères trouvée dans le fichier joueurs chargé. "
            "Vérifie que le fichier joueurs enrichi (avec les colonnes d'enchères) est bien utilisé."
        )
        return

    if taille_choisie != "Toutes tailles" and TAILLES_LIGUE[taille_choisie]["enchere"] not in df.columns:
        st.caption(
            f"Pas de donnée détaillée pour les ligues à {taille_choisie.split()[0]} — "
            f"affichage de l'enchère moyenne toutes tailles confondues."
        )

    base_cols = ['Joueur', 'Poste', 'Cote', 'Var Cote', col_enchere, col_achat,
                 'Note', 'Variation', 'Buts', '%Titu', 'Indispo ?']
    df_mercato = df[base_cols].copy()
    df_mercato = df_mercato.rename(columns={
        col_enchere: 'Enchere',
        col_achat: 'AchatT1',
    })

    for col in ['Cote', 'Var Cote', 'Enchere', 'AchatT1', 'Note', 'Variation', 'Buts', '%Titu']:
        df_mercato[col] = pd.to_numeric(df_mercato[col], errors='coerce')

    df_mercato = df_mercato.dropna(subset=['Cote', 'Note', 'Variation', '%Titu'])
    df_mercato = df_mercato[df_mercato['Cote'] > 0]

    nb_journees = len(cols_journees)
    seuil_matchs = int(nb_journees * 0.40)

    df_mercato['Matchs_joues'] = df.apply(
        lambda row: compter_matchs(row, cols_journees), axis=1)
    df_mercato['Absences_recentes'] = df.apply(
        lambda row: absences_consecutives(row, cols_journees), axis=1)
    df_mercato['Alerte'] = df.apply(
        lambda row: alerte_blessure(row, cols_journees), axis=1)
    df_mercato['Ratio'] = df_mercato['Note'] / df_mercato['Cote']  # gardée pour affichage éventuel, plus utilisée dans les scores

    # Note stabilisée (point 9) : la Note brute d'un joueur à 1-2 matchs joués
    # cette saison n'est pas fiable (un seul bon match suffit à la faire
    # décoller) — on la mélange avec sa Note de saison N-1 selon la même
    # grille progressive (poids_phase) que predire_note_hybride(), mais
    # appliquée à la moyenne de saison plutôt qu'à la prédiction pondérée
    # récente de predire_note() : ça stabilise les petits échantillons sans
    # jamais réintroduire de biais de forme récente (Mercato n'utilise
    # volontairement pas de Forme 6J). Utilisée uniquement dans les formules
    # de score/percentile ci-dessous ; la colonne 'Note' affichée reste la
    # vraie moyenne de saison brute.
    df_mercato['NoteStabilisee'] = df.apply(
        lambda row: stabiliser_note_saison(
            trouver_historique_n1(row['Joueur'], row['Poste'], df_n1),
            row, cols_journees, journee_actuelle
        ),
        axis=1
    )
    df_mercato['NoteStabilisee'] = df_mercato['NoteStabilisee'].fillna(df_mercato['Note'])

    stats_notes = df.apply(lambda row: _moyenne_ecart_type_notes(row, cols_journees), axis=1)
    df_mercato['MoyenneNote'] = stats_notes['MoyenneNote']
    df_mercato['EcartTypeNote'] = stats_notes['EcartTypeNote']
    df_mercato['Regularite'] = df.apply(
        lambda row: taux_regularite([row[col] for col in cols_journees if row[col] > 0]),
        axis=1
    )

    # --- Tension du marché (à partir du % achat T1) ---
    df_mercato['Tension'] = df_mercato['AchatT1'].apply(_tension)

    # --- Rangs percentile Cote/Note par poste (réutilisés par "À éviter" et par les
    # seuils de catégorie plus bas) ---
    df_mercato['Cote_pct'] = df_mercato.groupby('Poste')['Cote'].rank(pct=True)
    df_mercato['Note_pct'] = df_mercato.groupby('Poste')['NoteStabilisee'].rank(pct=True)

    # À éviter — seuil relatif au poste (pas de seuil de Cote universel) : cher pour
    # SON poste (au-delà du 60e percentile) ET décevant pour SON poste (sous la
    # médiane), avant filtres. Calculé en mask pour pouvoir exclure ces joueurs des
    # 4 autres stratégies plus bas (mutuellement exclusif, cf. mask_stars etc.).
    mask_eviter = (
        (df_mercato['Cote_pct'] > 0.60) &
        (df_mercato['Note_pct'] < 0.50)
    )
    df_eviter = df_mercato[mask_eviter].copy()

    # --- ProbaBut / ProbaArret (point 1) : Monte Carlo face aux moyennes de ligne de la ligue ---
    df_mercato['Ligne'] = df_mercato['Poste'].apply(poste_vers_ligne)
    moyennes_lignes = df_mercato.groupby('Ligne')['MoyenneNote'].mean().to_dict()
    for ligne in ['ATT', 'MIL', 'DEF', 'GB']:
        moyennes_lignes.setdefault(ligne, 5.0)

    df_mercato['ProbaBut'] = df_mercato.apply(
        lambda row: simuler_proba_but(
            row['MoyenneNote'], row['EcartTypeNote'], row['Poste'], moyennes_lignes
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
    df_mercato['Fiabilite'] = 0.6 * (df_mercato['%Titu'] / 100) + 0.4 * df_mercato['Regularite']
    df_mercato['Fiabilite_pct'] = df_mercato.groupby('Poste')['Fiabilite'].rank(pct=True)

    # Score pépite : prix bas (rang inversé) + note correcte, re-percentilé par poste
    # pour garantir un palier "top X%" exact (la combinaison brute n'est pas uniforme).
    score_pepite = 0.6 * (1 - df_mercato['Cote_pct']) + 0.4 * df_mercato['Note_pct']
    df_mercato['Score_pepite_pct'] = score_pepite.groupby(df_mercato['Poste']).rank(pct=True)

    mask_stars = (
        (df_mercato['Cote_pct'] >= 0.85) &
        (df_mercato['Note_pct'] >= 0.75) &
        (df_mercato['%Titu'] >= 60) &
        (df_mercato['Tension'] != "Très peu demandé") &
        ~mask_eviter
    )
    # Pépites calculé avant Valeurs sûres : en cas de chevauchement (joueur cher-moyen
    # ET fiable ET par ailleurs "pas cher + correct" pour son poste), Pépites prime —
    # son critère de prix est le plus objectif et le plus attendu par un utilisateur
    # qui cherche justement un bon coup pas cher.
    mask_pepites = (
        (df_mercato['Score_pepite_pct'] >= 0.85) &
        (df_mercato['%Titu'] >= 50) &
        ~mask_eviter
    )
    mask_valeurs = (
        (df_mercato['Cote_pct'] >= 0.50) & (df_mercato['Cote_pct'] < 0.85) &
        (df_mercato['Fiabilite_pct'] >= 0.60) &
        (df_mercato['%Titu'] >= 60) &
        ~mask_eviter &
        ~mask_pepites
    )
    # Équilibre = tout le reste (catégorie résiduelle, aucun critère propre) : garantit
    # structurellement qu'aucun joueur n'est absent des 4 stratégies combinées. "À
    # éviter" en est explicitement exclu aussi (catégories mutuellement exclusives :
    # un joueur "à éviter" n'apparaît nulle part ailleurs).
    mask_equilibre = ~mask_stars & ~mask_valeurs & ~mask_pepites & ~mask_eviter

    df_stars = df_mercato[mask_stars].copy()
    df_valeurs = df_mercato[mask_valeurs].copy()
    df_pepites = df_mercato[mask_pepites].copy()
    df_equilibre = df_mercato[mask_equilibre].copy()

    separateur("STRATÉGIE MERCATO")
    # Sélection stratégie
    strategie_choisie = st.radio(
        "Stratégie mercato :",
        ["Stars", "Valeurs sûres", "Équilibre", "Pépites", "À éviter"],
        horizontal=True,
        key="mercato_strategie",
        label_visibility="collapsed"
    )

    with st.expander("🏥 Légende blessures"):
        st.markdown("""
|  | Statut |
|---|---|
| 🚑 | Blessé — 8+ matchs manqués |
| 🩹 | Blessé — moins de 8 matchs manqués |
| 🏥 | Retour de blessure — 8+ matchs d'absence |
| 🐢 | Retour de blessure — 4 à 7 matchs d'absence |
""")

    cols_affichage = ['Joueur', 'Poste', 'Cote', 'Enchere', 'Tension',
                       'Note', 'Buts', '%Titu', 'Matchs_joues', 'Alerte']

    strategie_map = {
        "Stars": ('stars', df_stars),
        "Valeurs sûres": ('valeurs_sures', df_valeurs),
        "Équilibre": ('equilibre', df_equilibre),
        "Pépites": ('pepites', df_pepites),
    }

    if strategie_choisie == "À éviter":
        st.markdown(
            '<div style="font-family:\'Oswald\',sans-serif; font-weight:700; '
            'font-size:1.05rem; letter-spacing:0.04em; text-transform:uppercase; '
            'color:#c8a84b; margin:0.4rem 0 0.8rem;">Joueurs chers mais décevants</div>',
            unsafe_allow_html=True
        )
        df_eviter['Raison'] = df_eviter.apply(lambda row:
            "Cher + peu de matchs" if row['Matchs_joues'] < seuil_matchs
            else "Cher + note décevante", axis=1
        )
        st.markdown(
            _table_html(
                df_eviter[['Joueur', 'Poste', 'Cote', 'Enchere', 'Tension',
                           'Note', 'Matchs_joues', '%Titu', 'Alerte', 'Raison']
                           ].rename(columns={'Enchere': 'Enchère moy.', 'Tension': 'Demande', 'Matchs_joues': 'Matchs joués'}).reset_index(drop=True)
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

                top = df_poste.sort_values(
                    f'Score_{strategie_key}', ascending=False
                ).head(10).copy()
                nom_colonne_proba = 'Proba arrêt' if code == 'G' else 'Proba but'
                top['ProbaBut'] = top['ProbaBut'].apply(lambda x: f"{x*100:.0f}%")

                if len(top) > 0:
                    st.markdown(
                        _table_html(
                            top[cols_affichage + ['ProbaBut']
                                ].rename(columns={
                                    'Enchere': 'Enchère moy.', 'Tension': 'Demande',
                                    'Matchs_joues': 'Matchs joués', 'ProbaBut': nom_colonne_proba,
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
