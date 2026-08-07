import streamlit as st
import pandas as pd
from modele import (
    nettoyer_note, calculer_clutch, predire_note, alerte_blessure, etiquette_regularite,
    absences_consecutives, predire_note_hybride, get_bandeau_avertissement, trouver_historique_n1,
    compter_matchs, poids_phase, taux_regularite, normaliser_accents, normaliser_recherche,
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


def _cle_tri(df, colonne):
    """Retourne une Series servant de clé de tri numérique (ou textuelle
    normalisée) pour la colonne donnée, sans modifier les données affichées."""
    if colonne == 'Régularité':
        return df[colonne].apply(_rang_regularite)
    if colonne == '% Titulaire':
        return df[colonne].astype(str).str.rstrip('%').astype(float)
    if colonne == 'Joueur':
        return df[colonne].apply(normaliser_accents)
    return df[colonne]


def _trier_tableau(df, colonne, croissant):
    cle = _cle_tri(df, colonne)
    return (
        df.assign(_cle_tri=cle)
          .sort_values('_cle_tri', ascending=croissant, kind='mergesort')
          .drop(columns='_cle_tri')
          .reset_index(drop=True)
    )


def _synchroniser_tri(col_key, ordre_key):
    """Callback on_change : mémorise le dernier choix de tri fait par l'utilisateur
    (peu importe l'onglet), pour que _afficher_tableau_triable() puisse le
    reproduire dans les autres onglets au prochain rendu (point 3)."""
    st.session_state['hebdo_dernier_tri_col'] = st.session_state[col_key]
    st.session_state['hebdo_dernier_tri_ordre'] = st.session_state[ordre_key]


def _afficher_tableau_triable(df, colonnes_affichage, cell_renderer, key_prefix):
    """Affiche un sélecteur 'Trier par' + croissant/décroissant au-dessus du tableau stylé,
    puis le tableau HTML. Ne modifie ni les noms de colonnes ni les données : seul
    l'ordre des lignes change."""
    options = ["Recommandé"] + colonnes_affichage
    col_key = f"tri_col_{key_prefix}"
    ordre_key = f"tri_ordre_{key_prefix}"

    # Persistance du tri entre onglets (point 3) : Streamlit impose une clé de
    # widget distincte par onglet (les 7 onglets sont tous instanciés à chaque
    # rendu), donc chaque onglet est réaligné ici sur le dernier choix fait
    # n'importe où — sans ça, changer de tri sur un onglet ne changeait rien
    # aux autres, qui retombaient sur leur propre défaut "Recommandé".
    dernier_col = st.session_state.get('hebdo_dernier_tri_col', "Recommandé")
    st.session_state[col_key] = dernier_col if dernier_col in options else "Recommandé"
    st.session_state[ordre_key] = st.session_state.get('hebdo_dernier_tri_ordre', "↓")

    col_select, col_ordre = st.columns([3, 1])
    with col_select:
        colonne_tri = st.selectbox(
            "Trier par", options, key=col_key, filter_mode=None,
            on_change=_synchroniser_tri, args=(col_key, ordre_key)
        )
    with col_ordre:
        ordre = st.radio(
            "Ordre", ["↓", "↑"], horizontal=True,
            key=ordre_key, label_visibility="hidden",
            on_change=_synchroniser_tri, args=(col_key, ordre_key)
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


def _pill_fiabilite(val):
    val = '' if pd.isna(val) else str(val).strip()
    if not val:
        return dash()
    return pill(
        val, 'warn',
        title="Aucune donnée exploitable cette saison ni la saison passée "
              "(ex. promu de Ligue 2) — Note saison/Forme 6J estimées sur la "
              "médiane du poste plutôt que sur un vrai historique du joueur."
    )


def _formater_cellule_hebdo(col, val):
    if col == 'Régularité':
        return _pill_regularite(val)
    if col == 'Fiabilité':
        return _pill_fiabilite(val)
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

    # Repli ultime pour un joueur sans AUCUNE donnée exploitable, ni cette
    # saison ni en N-1 (predire_note_hybride renvoie alors None) — typiquement
    # un promu de Ligue 2 (ex. Le Mans, Troyes en 26-27), absent du fichier
    # N-1 puisqu'il n'était pas en Ligue 1 la saison passée. Auparavant ces
    # joueurs étaient simplement exclus (`continue`), invisibles sur Hebdo —
    # mieux vaut une estimation prudente (médiane N-1 du poste, même
    # convention que le repli poste déjà utilisé sur Mercato) clairement
    # signalée comme telle (colonne "Fiabilité") qu'une absence totale.
    note_mediane_poste_n1 = df_n1.groupby('Poste')['Note'].median().to_dict()
    note_repli_global_n1 = df_n1['Note'].median()

    scores = []
    for idx, row in df.iterrows():
        row_n1 = trouver_historique_n1(row['Joueur'], row['Poste'], df_n1)
        note_forme, mode_forme = predire_note_hybride(
            row_n1, cols_journees_n1, row, cols_journees, journee_actuelle
        )
        estimation_poste = note_forme is None
        if estimation_poste:
            note_forme = note_mediane_poste_n1.get(row['Poste'], note_repli_global_n1)
            if pd.isna(note_forme):
                # Repli lui-même indisponible (poste totalement absent du N-1,
                # ex. aucun gardien recensé) : rien de crédible à afficher.
                continue

        notes_jouees = [row[col] for col in cols_journees if row[col] > 0]
        # Repli N-1 (même principe que Note/%Titu/ProbaBut sur Mercato) :
        # taux_regularite([]) retombe sur 0.0 quand la saison en cours n'a
        # encore aucune note exploitable (systématique en pré-saison) — et
        # comme q25/q50/q75 sont alors aussi tous à 0.0 (calculés sur la même
        # valeur uniforme pour tout le poste), etiquette_regularite() reclasse
        # tout le monde en "Irrégulier" par construction, sans refléter le
        # moindre vrai profil. Si un historique N-1 fiable existe, le taux de
        # flop est calculé sur les derniers matchs RÉELS de la saison 25-26 à
        # la place. Sans historique N-1 (vraie recrue/inconnu) : comportement
        # inchangé (0.0, comme avant).
        if notes_jouees:
            regularite_brute = taux_regularite(notes_jouees)
        elif row_n1 is not None:
            notes_jouees_n1 = [row_n1[col] for col in cols_journees_n1 if row_n1[col] > 0]
            regularite_brute = taux_regularite(notes_jouees_n1)
        else:
            regularite_brute = taux_regularite(notes_jouees)

        prob_jouer = row['%Titu'] / 100 if '%Titu' in df.columns else 0.8
        # %Titu de repli réservé au plancher de fiabilité de
        # etiquette_regularite() (%Titu >= 70/50 selon le label) : sans lui,
        # ce plancher reclasserait "Irrégulier" même un joueur dont le vrai
        # taux de flop N-1 ci-dessus est excellent, puisque son %Titu BRUT de
        # saison en cours reste à 0 tant qu'il n'a rejoué aucun match.
        # N'affecte QUE ce plancher interne — la colonne "% Titulaire"
        # affichée reste la vraie valeur brute de saison en cours, inchangée.
        if notes_jouees:
            titu_pct_gate = round(prob_jouer * 100, 1)
        elif row_n1 is not None and pd.notna(row_n1.get('%Titu')):
            titu_pct_gate = float(row_n1['%Titu'])
        else:
            titu_pct_gate = round(prob_jouer * 100, 1)

        # 'Note saison' reprend elle aussi le repli poste pour ces joueurs :
        # la laisser à sa valeur brute (0, sans historique) à côté d'une
        # 'Forme 6J' déjà repliée sur la médiane du poste afficherait deux
        # chiffres incohérents pour le même joueur (l'un honnête à 0, l'autre
        # estimé) — les deux colonnes portent la même estimation prudente,
        # signalée une seule fois via "Fiabilité".
        if estimation_poste:
            moyenne_saison = note_forme
        else:
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
            '_titu_pct': round(prob_jouer * 100, 1),
            '_titu_pct_gate': titu_pct_gate,
            '% Titulaire': f"{int(prob_jouer*100)}%",
            'Fiabilité': 'Estimé (poste)' if estimation_poste else '',
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
                row['Note saison'], note_mediane_poste,
                row['_titu_pct_gate']
            ),
            axis=1
        )

    df_mes_joueurs = df_scores.copy()
    if filtrer and mes_joueurs_input.strip():
        # Comparaison normalisée (accents + casse + séparateurs), cohérente avec la
        # validation au clic sur "Valider" (app.py::_verifier_noms_joueurs) : sans
        # quoi un nom tapé sans accent (ex. "Said" au lieu de "Saïd") ou avec le
        # mauvais séparateur (ex. "Saint Maximin" au lieu de "Saint-Maximin") était
        # validé comme trouvé mais silencieusement absent du filtre "Mes joueurs".
        mes_joueurs = [normaliser_recherche(j) for j in mes_joueurs_input.split('\n') if j.strip()]
        noms_normalises = df_scores['Joueur'].apply(normaliser_recherche)
        df_mes_joueurs = df_scores[noms_normalises.isin(mes_joueurs)]

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
    colonnes_affichage = ['Joueur', 'Club', 'Note saison', 'Forme 6J', 'Régularité', '% Titulaire', 'Fiabilité']

    if filtrer and mes_joueurs_input.strip():
        tab0, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "Mes joueurs", "Attaquants", "Milieux Off.",
            "Milieux Déf.", "Défenseurs C.", "Défenseurs L.", "Gardiens"
        ], key="hebdo_postes")
        with tab0:
            colonnes_mes_joueurs = ['Joueur', 'Club', 'Poste', 'Note saison', 'Forme 6J', 'Régularité', '% Titulaire', 'Fiabilité']
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

    # "Afficher uniquement mes joueurs" doit aussi filtrer les onglets par poste,
    # pas seulement conditionner l'existence de l'onglet "Mes joueurs" — sans
    # cette ligne, Attaquants/Milieux Off./etc. affichaient toujours TOUS les
    # joueurs du poste, case cochée ou non (bug : la case n'avait aucun effet
    # visible sur ces onglets-là).
    df_source_postes = df_mes_joueurs if (filtrer and mes_joueurs_input.strip()) else df_scores

    postes_tabs = {
        tab1: 'A', tab2: 'MO', tab3: 'MD',
        tab4: 'DC', tab5: 'DL', tab6: 'G'
    }
    for tab, code in postes_tabs.items():
        with tab:
            top = df_source_postes[df_source_postes['Poste'] == code].sort_values(
                '_score', ascending=False
            )[colonnes_affichage + ['_score']]
            if len(top) > 0:
                _afficher_tableau_triable(
                    top.reset_index(drop=True), colonnes_affichage,
                    _formater_cellule_hebdo, key_prefix=f"poste_{code}"
                )
            else:
                st.info("Aucun joueur disponible pour ce poste")
