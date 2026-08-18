import streamlit as st
import pandas as pd
from modele import (
    alerte_blessure, etiquette_regularite, predire_note_hybride, get_bandeau_avertissement,
    trouver_historique_n1, compter_matchs, poids_phase, calculer_regularite_brute,
    stabiliser_valeur_saison, mediane_n1_par_poste, normaliser_accents, normaliser_recherche,
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
        table_html(
            df_affiche[colonnes_affichage].reset_index(drop=True), cell_renderer,
            extra_class="gs-table-hebdo"
        ),
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
    # Seule valeur possible désormais : 'Estimé (poste)' — un débutant tardif
    # avec un vrai historique N-1 personnel (ex. Ikoné) n'affiche plus aucun
    # badge : sa note N-1 est une vraie donnée le concernant, pas une
    # estimation à signaler, cohérent avec l'absence de badge pour un joueur
    # aux données actuelles normales.
    val = '' if pd.isna(val) else str(val).strip()
    if not val:
        return dash()
    return pill(
        val, 'warn',
        title="Aucune donnée exploitable cette saison ni la saison passée "
              "(ex. promu de Ligue 2) — Note saison/Forme 6J estimées sur la "
              "médiane du poste plutôt que sur un vrai historique du joueur."
    )


def _pill_alerte(val):
    val = '' if pd.isna(val) else str(val).strip()
    if not val:
        return dash()
    # 🆕 (jamais titulaire cette saison) n'est pas une alerte de blessure —
    # style neutre plutôt que 'bad' (rouge), réservé aux vraies blessures/
    # retours (🚑🩹🏥🐢).
    return pill(val, 'info' if val.startswith('🆕') else 'bad')


def _formater_cellule_hebdo(col, val):
    if col == 'Régularité':
        return _pill_regularite(val)
    if col == 'Source':
        return _pill_fiabilite(val)
    if col == 'Alerte':
        return _pill_alerte(val)
    if col == 'Joueur':
        return name_cell(val)
    if pd.isna(val):
        return dash()
    if col in ('Note saison', 'Forme 6J'):
        return f"{val:.2f}"
    return str(val)


@st.cache_data(show_spinner=False)
def _construire_df_scores_hebdo(df, df_n1, cols_journees, cols_journees_n1, journee_actuelle):
    """Construit df_scores (une ligne par joueur : Note saison/Forme 6J/
    Régularité/% Titulaire/Source/Alerte/_score) — pure fonction de ces 5
    arguments, mise en cache car la boucle df.iterrows() ci-dessous (avec un
    lookup trouver_historique_n1 sur df_n1 à chaque ligne) prend 1-2 secondes
    et ne dépend ni du filtre "mes joueurs" ni de l'onglet poste/tri
    sélectionné — sans cache, elle était recalculée à l'identique à chaque
    interaction sur la page."""
    # Repli ultime pour un joueur sans AUCUNE donnée exploitable, ni cette
    # saison ni en N-1 (predire_note_hybride renvoie alors None) — typiquement
    # un promu de Ligue 2 (ex. Le Mans, Troyes en 26-27), absent du fichier
    # N-1 puisqu'il n'était pas en Ligue 1 la saison passée. Auparavant ces
    # joueurs étaient simplement exclus (`continue`), invisibles sur Hebdo —
    # mieux vaut une estimation prudente (médiane N-1 du poste, même
    # convention que le repli poste déjà utilisé sur Mercato) clairement
    # signalée comme telle (colonne "Source") qu'une absence totale.
    # mediane_n1_par_poste (modele.py) : fonction centralisée, partagée à
    # l'identique par Mercato et app.py::_verifier_noms_joueurs — un seul
    # calcul de médiane N-1 par poste pour les 3, jamais 3 calculs indépendants
    # qui pourraient un jour diverger silencieusement.
    note_mediane_poste_n1, note_repli_global_n1 = mediane_n1_par_poste(df_n1, 'Note')
    # Repli poste pour %Titu, même convention (médiane N-1) que le repli Note
    # ci-dessus et que celui déjà utilisé sur Mercato (stabiliser_valeur_saison).
    titu_mediane_poste_n1, titu_repli_global_n1 = mediane_n1_par_poste(df_n1, '%Titu')

    scores = []
    for idx, row in df.iterrows():
        row_n1 = trouver_historique_n1(row['Joueur'], row['Poste'], df_n1)
        note_forme, _mode_forme = predire_note_hybride(
            row_n1, cols_journees_n1, row, cols_journees, journee_actuelle
        )
        estimation_poste = note_forme is None
        if estimation_poste:
            note_forme = note_mediane_poste_n1.get(row['Poste'], note_repli_global_n1)
            if pd.isna(note_forme):
                # Repli lui-même indisponible (poste totalement absent du N-1,
                # ex. aucun gardien recensé) : rien de crédible à afficher.
                continue

        # Régularité : fonction centralisée (modele.py::calculer_regularite_brute,
        # repli N-1 inclus), désormais partagée à l'identique par Mercato
        # (Fiabilite) et Simuler le match (formule Capitaine) — un joueur fiable
        # en N-1 a la même Régularité sur les 3 pages, jamais 0.0 par construction
        # comme avant sur les deux autres.
        regularite_brute = calculer_regularite_brute(row, cols_journees, row_n1, cols_journees_n1)

        # % Titulaire affiché : stabilisé N-1 (stabiliser_valeur_saison, même
        # fonction et même colonne '%Titu' que Mercato) plutôt que la valeur
        # brute de saison en cours — sans quoi Hebdo et Mercato afficheraient
        # deux chiffres différents pour le même joueur au même moment (0% brut
        # ici, valeur N-1 réelle là-bas). Sert aussi de plancher de fiabilité
        # interne à etiquette_regularite() (%Titu >= 70/50 selon le label) : un
        # seul calcul pour les deux usages désormais.
        titu_repli_poste = titu_mediane_poste_n1.get(row['Poste'], titu_repli_global_n1)
        titu_stabilise = stabiliser_valeur_saison(
            row_n1, cols_journees_n1, row, cols_journees, journee_actuelle,
            '%Titu', titu_repli_poste
        )
        if titu_stabilise is None or pd.isna(titu_stabilise):
            titu_stabilise = 0.0
        prob_jouer = titu_stabilise / 100

        # 'Note saison' reprend le repli dès que le joueur n'a lui-même encore
        # joué aucun match cette saison (matchs_joues == 0, colonne 'Note' brute
        # à 0 par construction, pas une vraie moyenne mesurée) — pas seulement
        # pour les cas "estimation_poste" (aucune donnée nulle part) : un
        # débutant tardif rescapé par predire_note_hybride sur son propre N-1
        # (ex. Ikoné) a lui aussi matchs_joues == 0, et afficherait sinon une
        # 'Note saison' à 0 à côté d'une 'Forme 6J' à 5.98 — les deux colonnes
        # portent alors la même estimation (personnelle N-1, ou poste si
        # vraiment aucune donnée n'existe — signalé par "Source" dans ce
        # seul cas).
        matchs_joues = compter_matchs(row, cols_journees)
        if matchs_joues == 0:
            moyenne_saison = note_forme
        else:
            moyenne_saison = float(row['Note']) if 'Note' in df.columns else note_forme

        # Source : signale UNIQUEMENT le cas où aucune donnée n'existe nulle
        # part (ni cette saison, ni en N-1 — la médiane du poste est une pure
        # supposition, ex. promu de Ligue 2). Un débutant tardif dont le N-1
        # personnel sert de base (estimation_poste == False, note_forme vient
        # de son propre historique) n'affiche plus de badge : sa note N-1 est
        # une vraie donnée le concernant, pas une estimation à signaler — même
        # traitement qu'un joueur aux données actuelles normales, qui n'a lui
        # non plus jamais de badge.
        fiabilite = 'Estimé (poste)' if estimation_poste else ''

        # Alerte blessure/retour : jusqu'ici importée mais jamais utilisée sur
        # Hebdo (contrairement à Mercato et Simuler le match), rendant l'encart
        # "🏥 Légende blessures" orphelin — même fonction, mêmes badges.
        alerte = alerte_blessure(row, cols_journees, journee_actuelle)

        # Pondération dynamique de la formule "Recommandé" en début de saison :
        # t = poids_actuelle (poids_phase) ramène progressivement la formule vers
        # 0.5/0.3/0.1/0.1 (formule de référence, saison mûre) à mesure que t -> 1.
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
            # round() (pas int(), qui tronque) : même convention d'arrondi que
            # Mercato ('% Titu (estimé)', f"{val:.0f}%") pour éviter qu'un même
            # %Titu stabilisé affiche un chiffre différent d'une page à l'autre
            # par simple artefact de virgule flottante (ex. 56.99999999999999).
            '% Titulaire': f"{round(prob_jouer*100)}%",
            'Source': fiabilite,
            'Alerte': alerte,
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
                row['_titu_pct']
            ),
            axis=1
        )

    return df_scores


def afficher_hebdo(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle, mes_joueurs_input, filtrer):
    inject_style()

    bandeau = get_bandeau_avertissement(journee_actuelle)
    if bandeau:
        st.warning(bandeau)

    df_scores = _construire_df_scores_hebdo(df, df_n1, cols_journees, cols_journees_n1, journee_actuelle)

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
| 🆕 | Pas encore titularisé cette saison (n'a jamais joué — distinct d'un retour de blessure) |
""")

    separateur("RECOMMANDATIONS PAR POSTE")
    colonnes_affichage = ['Joueur', 'Club', 'Note saison', 'Forme 6J', 'Régularité', '% Titulaire', 'Source', 'Alerte']

    if filtrer and mes_joueurs_input.strip():
        tab0, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "Mes joueurs", "Attaquants", "Milieux Off.",
            "Milieux Déf.", "Défenseurs C.", "Défenseurs L.", "Gardiens"
        ], key="hebdo_postes")
        with tab0:
            colonnes_mes_joueurs = ['Joueur', 'Club', 'Poste', 'Note saison', 'Forme 6J', 'Régularité', '% Titulaire', 'Source', 'Alerte']
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
