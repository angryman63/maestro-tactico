import unicodedata

import streamlit as st
import pandas as pd
from modele import (
    nettoyer_note, calculer_clutch, predire_note, alerte_blessure, etiquette_regularite,
    absences_consecutives, predire_note_hybride, get_bandeau_avertissement, trouver_historique_n1,
    compter_matchs, poids_phase, taux_regularite,
)
from utils.table_style import inject_style, pill, dash, name_cell, table_html, separateur


# Ordre de qualité pour le tri de la colonne Régularité (du meilleur au moins bon)
_RANG_REGULARITE = {
    'Métronome': 4,
    'Régulier': 3,
    'Irrégulier': 2,
    'Rotaldo': 1,
}


def _rang_regularite(val):
    val = '' if pd.isna(val) else str(val)
    for label, rang in _RANG_REGULARITE.items():
        if label in val:
            return rang
    return 0


def _normaliser_accents(texte):
    """Retire les accents pour une comparaison alphabétique correcte (sans quoi
    'É', 'À'... se comparent par leur code Unicode et finissent après 'Z')."""
    return ''.join(
        c for c in unicodedata.normalize('NFKD', str(texte))
        if not unicodedata.combining(c)
    )


def _cle_tri(df, colonne):
    """Retourne une Series servant de clé de tri numérique (ou textuelle
    normalisée) pour la colonne donnée, sans modifier les données affichées."""
    if colonne == 'Régularité':
        return df[colonne].apply(_rang_regularite)
    if colonne == '% Titulaire':
        return df[colonne].astype(str).str.rstrip('%').astype(float)
    if colonne == 'Joueur':
        return df[colonne].apply(_normaliser_accents)
    return df[colonne]


def _trier_tableau(df, colonne, croissant):
    cle = _cle_tri(df, colonne)
    return (
        df.assign(_cle_tri=cle)
          .sort_values('_cle_tri', ascending=croissant, kind='mergesort')
          .drop(columns='_cle_tri')
          .reset_index(drop=True)
    )


def _afficher_tableau_triable(df, colonnes_affichage, cell_renderer, key_prefix):
    """Affiche un sélecteur 'Trier par' + croissant/décroissant au-dessus du tableau stylé,
    puis le tableau HTML. Ne modifie ni les noms de colonnes ni les données : seul
    l'ordre des lignes change."""
    col_select, col_ordre = st.columns([3, 1])
    with col_select:
        options = ["Recommandé"] + colonnes_affichage
        colonne_tri = st.selectbox(
            "Trier par", options, index=0, key=f"tri_col_{key_prefix}",
            filter_mode=None
        )
    with col_ordre:
        ordre = st.radio(
            "Ordre", ["↓", "↑"], horizontal=True,
            key=f"tri_ordre_{key_prefix}", label_visibility="hidden"
        )

    croissant = (ordre == "↑")
    if colonne_tri == "Recommandé":
        # Trie sur le score interne _score plutôt que de garder tel quel
        # l'ordre déjà pré-trié (toujours décroissant) passé par l'appelant —
        # sans ça, la flèche de tri n'avait aucun effet sur "Recommandé".
        df_affiche = df.sort_values('_score', ascending=croissant, kind='mergesort')
    else:
        df_affiche = _trier_tableau(df, colonne_tri, croissant)

    st.markdown(
        table_html(df_affiche[colonnes_affichage].reset_index(drop=True), cell_renderer),
        unsafe_allow_html=True
    )


def _pill_regularite(val):
    val = '' if pd.isna(val) else str(val).strip()
    if not val:
        return dash()
    if 'Métronome' in val:
        return pill(val, 'info')
    if 'Régulier' in val:
        return pill(val, 'good')
    if 'Irrégulier' in val:
        return pill(val, 'warn')
    if 'Rotaldo' in val:
        return pill(val, 'bad')
    return pill(val, 'mid')


def _formater_cellule_hebdo(col, val):
    if col == 'Régularité':
        return _pill_regularite(val)
    if col == 'Joueur':
        return name_cell(val)
    if pd.isna(val):
        return dash()
    if col in ('Note saison', 'Forme 6J'):
        return f"{val:.2f}"
    return str(val)


def afficher_hebdo(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle, mes_joueurs_input, filtrer):
    inject_style()

    bandeau = get_bandeau_avertissement(journee_actuelle)
    if bandeau:
        st.warning(bandeau)

    scores = []
    for idx, row in df.iterrows():
        row_n1 = trouver_historique_n1(row['Joueur'], row['Poste'], df_n1)
        note_forme, mode_forme = predire_note_hybride(
            row_n1, cols_journees_n1, row, cols_journees, journee_actuelle
        )
        if note_forme is None:
            continue

        notes_jouees = [row[col] for col in cols_journees if row[col] > 0]
        regularite_brute = taux_regularite(notes_jouees)
        prob_jouer = row['%Titu'] / 100 if '%Titu' in df.columns else 0.8
        moyenne_saison = float(row['Note']) if 'Note' in df.columns else note_forme

        # Pondération dynamique de la formule "Recommandé" en début de saison :
        # t = poids_actuelle (poids_phase) ramène progressivement la formule vers
        # 0.5/0.3/0.1/0.1 (formule de référence, saison mûre) à mesure que t -> 1.
        matchs_joues = compter_matchs(row, cols_journees)
        _, t = poids_phase(matchs_joues, journee_actuelle)
        score = (moyenne_saison * (0.5 * t) + note_forme * (1 - 0.7 * t) +
                 regularite_brute * (0.1 * t) + prob_jouer * (0.1 * t))
        scores.append({
            'Joueur': row['Joueur'],
            'Poste': row['Poste'],
            'Club': row['Club'],
            'Note saison': round(moyenne_saison, 2),
            'Forme 6J': round(float(note_forme), 2),
            '_regularite_brute': regularite_brute,
            '% Titulaire': f"{int(prob_jouer*100)}%",
            '_score': round(float(score), 2)
        })

    df_scores = pd.DataFrame(scores)

    for poste in df_scores['Poste'].unique():
        mask = df_scores['Poste'] == poste
        vals = df_scores.loc[mask, '_regularite_brute']
        q25, q50, q75 = vals.quantile([0.25, 0.5, 0.75])
        note_mediane_poste = df_scores.loc[mask, 'Note saison'].median()
        df_scores.loc[mask, 'Régularité'] = df_scores.loc[mask].apply(
            lambda row: etiquette_regularite(
                row['_regularite_brute'], q25, q50, q75,
                row['Note saison'], note_mediane_poste
            ),
            axis=1
        )

    df_mes_joueurs = df_scores.copy()
    if filtrer and mes_joueurs_input.strip():
        mes_joueurs = [j.strip().lower() for j in mes_joueurs_input.split('\n') if j.strip()]
        df_mes_joueurs = df_scores[df_scores['Joueur'].str.lower().isin(mes_joueurs)]

    with st.expander("🏥 Légende blessures"):
        st.markdown("""
|  | Statut |
|---|---|
| 🚑 | Blessé — 8+ matchs manqués |
| 🩹 | Blessé — moins de 8 matchs manqués |
| 🏥 | Retour de blessure — 8+ matchs d'absence |
| 🐢 | Retour de blessure — 4 à 7 matchs d'absence |
""")

    separateur("RECOMMANDATIONS PAR POSTE")
    colonnes_affichage = ['Joueur', 'Club', 'Note saison', 'Forme 6J', 'Régularité', '% Titulaire']

    if filtrer and mes_joueurs_input.strip():
        tab0, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "Mes joueurs", "Attaquants", "Milieux Off.",
            "Milieux Déf.", "Défenseurs C.", "Défenseurs L.", "Gardiens"
        ], key="hebdo_postes")
        with tab0:
            colonnes_mes_joueurs = ['Joueur', 'Club', 'Poste', 'Note saison', 'Forme 6J', 'Régularité', '% Titulaire']
            top = df_mes_joueurs.sort_values('_score', ascending=False)[colonnes_mes_joueurs + ['_score']]
            if len(top) > 0:
                _afficher_tableau_triable(
                    top.reset_index(drop=True), colonnes_mes_joueurs,
                    _formater_cellule_hebdo, key_prefix="mes_joueurs"
                )
            else:
                st.warning("Aucun joueur trouvé — vérifiez l'orthographe")
    else:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "Attaquants", "Milieux Off.", "Milieux Déf.",
            "Défenseurs C.", "Défenseurs L.", "Gardiens"
        ], key="hebdo_postes")

    postes_tabs = {
        tab1: 'A', tab2: 'MO', tab3: 'MD',
        tab4: 'DC', tab5: 'DL', tab6: 'G'
    }
    for tab, code in postes_tabs.items():
        with tab:
            top = df_scores[df_scores['Poste'] == code].sort_values(
                '_score', ascending=False
            )[colonnes_affichage + ['_score']]
            if len(top) > 0:
                _afficher_tableau_triable(
                    top.reset_index(drop=True), colonnes_affichage,
                    _formater_cellule_hebdo, key_prefix=f"poste_{code}"
                )
            else:
                st.info("Aucun joueur disponible pour ce poste")
