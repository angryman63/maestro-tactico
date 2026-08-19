import re
import streamlit as st
import pandas as pd
import numpy as np
from modele import (get_joueur_info, chercher_lignes_joueur, poste_vers_ligne, trouver_historique_n1,
                    stabiliser_stats_proba_but, calculer_repli_stabilisation,
                    monte_carlo_match, calculer_contexte_ligue, mediane_n1_par_poste,
                    construire_distribution_n1_par_poste)
from utils.table_style import inject_style, pill, escape, separateur

_MOTIF_NOM_CLUB = re.compile(r'^(.*?)\s*\(([^)]+)\)\s*$')

# calculer_contexte_ligue/calculer_repli_stabilisation (modele.py) sont pures
# fonctions de (df, cols_journees) mais itèrent tout le dataframe — mises en
# cache ici (pas dans modele.py, qui reste volontairement sans dépendance à
# Streamlit) pour ne pas être recalculées à chaque interaction sur la page
# (changement de mode d'analyse, saisie des compos...) qui ne change ni df ni
# cols_journees.
@st.cache_data(show_spinner=False)
def _calculer_contexte_ligue_cache(df, cols_journees):
    return calculer_contexte_ligue(df, cols_journees)


@st.cache_data(show_spinner=False)
def _calculer_repli_stabilisation_cache(df, cols_journees, df_n1, cols_journees_n1):
    (moyenne_mediane_poste, moyenne_repli_global,
     ecart_type_mediane_poste, ecart_type_repli_global) = calculer_repli_stabilisation(df, cols_journees)

    # Repli ultime sur la saison N-1 : en tout début de saison, aucun joueur
    # n'a encore >= 3 matchs cette saison, donc le repli "saison en cours"
    # calculé ci-dessus est vide (dicts vides + médianes globales NaN) pour
    # tout le monde. Sans repli supplémentaire, un joueur sans note actuelle
    # ET sans historique N-1 personnel (row_n1 = None dans
    # stabiliser_stats_proba_but, ex. transfert sans passage en Ligue 1 la
    # saison passée, type Openda) fait renvoyer (None, None) à
    # stabiliser_stats_proba_but(), qui plante float(None) dans
    # _joueur_vers_mc() — Simuler le match n'a alors plus aucun repli du
    # tout, contrairement à Mercato (repli neutre 5.0/1.0 câblé en dur côté
    # appelant). La saison N-1, elle, est terminée : toujours assez de
    # joueurs à >= 3 matchs pour fournir un repli par poste crédible — {**a,
    # **b} pour que le repli saison en cours (déjà calculé) prime poste par
    # poste dès qu'il existe, le N-1 ne comblant que les postes manquants.
    if pd.isna(moyenne_repli_global) or pd.isna(ecart_type_repli_global) or not moyenne_mediane_poste:
        (moyenne_mediane_poste_n1, moyenne_repli_global_n1,
         ecart_type_mediane_poste_n1, ecart_type_repli_global_n1) = calculer_repli_stabilisation(
            df_n1, cols_journees_n1
        )
        moyenne_mediane_poste = {**moyenne_mediane_poste_n1, **moyenne_mediane_poste}
        ecart_type_mediane_poste = {**ecart_type_mediane_poste_n1, **ecart_type_mediane_poste}
        if pd.isna(moyenne_repli_global):
            moyenne_repli_global = moyenne_repli_global_n1
        if pd.isna(ecart_type_repli_global):
            ecart_type_repli_global = ecart_type_repli_global_n1

    return (moyenne_mediane_poste, moyenne_repli_global,
            ecart_type_mediane_poste, ecart_type_repli_global)


# Même repli médiane N-1 par poste que Conseiller Hebdo/Mercato pour note_pred
# (get_joueur_info) — mise en cache pour la même raison que les deux fonctions
# ci-dessus (pas dans modele.py, sans dépendance Streamlit). Conservé comme
# repli ultime (cf. _cote_pct_par_poste_cache/_distribution_n1_par_poste_cache
# ci-dessous, le repli principal désormais utilisé par get_joueur_info) pour
# les cas où le percentile de Cote du joueur est indisponible.
@st.cache_data(show_spinner=False)
def _mediane_n1_par_poste_cache(df_n1, colonne):
    return mediane_n1_par_poste(df_n1, colonne)


# Percentile de Cote (saison en cours) de chaque joueur parmi les joueurs de
# son poste — même convention que utils/mercato.py (Cote_pct,
# groupby('Poste')['Cote'].rank(pct=True)) — utilisé par get_joueur_info()
# pour lire la Note de repli au même percentile dans la distribution N-1 du
# poste (note_percentile_n1) plutôt qu'une médiane plate partagée par tout le
# poste. Mis en cache ici pour la même raison que les fonctions ci-dessus.
@st.cache_data(show_spinner=False)
def _cote_pct_par_poste_cache(df):
    cote = pd.to_numeric(df['Cote'], errors='coerce')
    return cote.groupby(df['Poste']).rank(pct=True)


# Distribution N-1 complète de Note par poste (pas seulement sa médiane) pour
# l'interpolation continue par percentile de get_joueur_info() — mise en cache
# pour la même raison que les fonctions ci-dessus.
@st.cache_data(show_spinner=False)
def _distribution_n1_par_poste_cache(df_n1, colonne):
    return construire_distribution_n1_par_poste(df_n1, colonne)


# Seuil de significativité du gain de bonus (points de %) — au-delà duquel un gain
# est jugé assez important pour recommander d'utiliser le bonus plutôt que de
# l'économiser. Variable selon l'enjeu réel du match : un match Crucial justifie
# d'utiliser un bonus pour un gain modeste, un match Sans enjeu ne justifie
# d'utiliser un bonus que pour un gain très important (pourquoi le dépenser sinon).
SEUIL_SIGNIFICATIVITE_GAIN = {"Crucial": 3, "Normal": 8, "Sans enjeu": 15}


def _est_favori(res):
    """'Favori' = Victoire est le résultat le plus probable des trois (Victoire/Nul/
    Défaite) — PAS un seuil absolu à 50% : à 48,8% Victoire / 21,4% Nul / 29,8%
    Défaite, Victoire est bien le résultat le plus probable malgré un chiffre sous
    50%. Utilisée à la fois par le bandeau du haut et par la recommandation, pour
    que les deux zones de la page tranchent "favori ou pas" de la même façon."""
    return res['victoires'] > max(res['nuls'], res['defaites'])


def _metrique_secondaire(label, valeur):
    """Variante réduite de st.metric (HTML) — même structure label au-dessus/valeur en
    gros en dessous, mais à une taille plus modeste qu'un vrai st.metric. Utilisée pour
    Nul/Défaite (moins prioritaires que Victoire pour la décision) : reste confortablement
    lisible, contrairement à un st.caption gris minuscule."""
    return (
        '<div style="margin-bottom:0.6rem;">'
        f'<div style="font-size:0.875rem; color:rgba(255,255,255,0.6);">{escape(label)}</div>'
        f'<div style="font-size:1.5rem; font-weight:600; color:#ffffff; line-height:1.3;">{escape(valeur)}</div>'
        '</div>'
    )


def _detail_configuration(label, valeur, delta=None):
    """Une ligne du détail des 2 configurations testées ("Impact de vos bonus
    disponibles") — plus grande et plus contrastée qu'un st.caption (qui rendait ce
    contexte peu lisible), mais nettement plus petite que la grande st.metric
    "Victoire avec [mon bonus]" au-dessus : garde la hiérarchie visuelle sans
    sacrifier la lisibilité."""
    delta_html = (
        f' <span style="font-size:0.9rem; color:rgba(255,255,255,0.6);">({escape(delta)})</span>'
        if delta else ''
    )
    return (
        '<div style="font-size:1.05rem; color:rgba(255,255,255,0.9); margin-bottom:4px;">'
        f'{escape(label)} : <strong style="color:#e8c76b;">{escape(valeur)}</strong>{delta_html}'
        '</div>'
    )


def _poste_du_nom(nom_ligne, df):
    """Résout le Poste d'une ligne "Nom" ou "Nom (Club)" (même syntaxe de
    désambiguïsation que _analyser_lignes_joueurs ci-dessous) — None si le nom
    est introuvable ou encore ambigu (homonyme non levé). Utilisée pour filtrer
    le menu "Remplaçant" de "Configurer les remplacements" au même poste que le
    titulaire choisi (un gardien ne doit pas pouvoir remplacer un attaquant)."""
    m = _MOTIF_NOM_CLUB.match(nom_ligne)
    nom, club = (m.group(1).strip(), m.group(2).strip()) if m else (nom_ligne, None)
    candidats = chercher_lignes_joueur(nom, df, club)
    if len(candidats) == 1:
        return candidats.iloc[0]['Poste']
    return None


def _analyser_lignes_joueurs(texte, df, exiger_onze):
    """Analyse les lignes saisies dans un champ Titulaires/Remplaçants de Simuler le match —
    adapté de app.py::_verifier_noms_joueurs (même standard normaliser_recherche, via
    chercher_lignes_joueur), mais avec un
    verdict par ligne à 3 états stricts (introuvable / ambigu / ok) : contrairement à
    Mercato/Hebdo, Simuler le match doit résoudre CHAQUE ligne à un joueur UNIQUE (impossible de
    simuler un match avec un joueur "peut-être Untel, peut-être Untel bis"). Accepte la syntaxe
    "Nom (Club)" pour lever une ambiguïté (ex. "Diallo (Metz)" — 4 joueurs différents s'appellent
    Diallo dans les données : Metz, Nice, Strasbourg, Lens).
    Retourne (ok, lignes_ok, messages) où lignes_ok est la liste des (nom_exact, club_exact)
    résolus sans ambiguïté (à utiliser tel quel pour construire l'équipe, sans reparser le
    texte), et ok signifie "aucune erreur ET (pas d'exigence de 11 OU exactement 11)"."""
    lignes = [l.strip() for l in texte.split('\n') if l.strip()]
    lignes_ok = []
    messages = []
    for ligne in lignes:
        m = _MOTIF_NOM_CLUB.match(ligne)
        nom, club = (m.group(1).strip(), m.group(2).strip()) if m else (ligne, None)
        candidats = chercher_lignes_joueur(nom, df, club)
        if len(candidats) == 0:
            messages.append(('error', f"« {ligne} » introuvable dans les données."))
        elif len(candidats) > 1:
            clubs = candidats['Club'].unique().tolist()
            messages.append((
                'error',
                f"« {ligne} » est ambigu ({len(candidats)} joueurs correspondent : "
                f"{', '.join(clubs)}) — précisez le club, ex. « {nom} ({clubs[0]}) »."
            ))
        else:
            row = candidats.iloc[0]
            lignes_ok.append((row['Joueur'], row['Club']))
    ok = len(messages) == 0 and (not exiger_onze or len(lignes_ok) == 11)
    return ok, lignes_ok, messages


def _afficher_messages_effectif(label, lignes_ok, messages, exiger_onze):
    for niveau, texte in messages:
        getattr(st, niveau)(f"{label} — {texte}")
    if not exiger_onze:
        return
    if len(lignes_ok) == 11 and not messages:
        return
    if not lignes_ok and not messages:
        st.caption(f"{label} — en attente de saisie (0/11).")
    else:
        st.error(f"{label} — {len(lignes_ok)}/11 titulaires reconnus (il en faut exactement 11).")

def _joueur_vers_mc(j, ligne, df, cols_journees, df_n1, cols_journees_n1, journee_actuelle,
                     moyenne_mediane_poste, moyenne_repli_global,
                     ecart_type_mediane_poste, ecart_type_repli_global):
    """Convertit un joueur (dict issu de get_joueur_info, avec 'nom'/'poste'/'note_pred'/'buts')
    au format attendu par monte_carlo_match : moyenne/écart-type stabilisés via
    stabiliser_stats_proba_but() — même principe que Mercato (utils/mercato.py) :
    mélange avec l'historique N-1 selon poids_phase(), pour ne pas traiter la
    moyenne/variance d'un joueur à 1-2 matchs comme représentative (l'ancien seuil
    dur ">= 3 matchs sinon note_pred" traitait tout échantillon en dessous de 3 de
    façon binaire, sans le mélange progressif que permet la stabilisation).
    'buts' réutilise directement j['buts'], déjà stabilisé par get_joueur_info()
    (repli sur N-1 puis médiane du poste)."""
    row = df[df['Joueur'].str.lower() == j['nom'].lower()]
    if len(row) == 0:
        return {
            'nom': j['nom'],
            'ligne': ligne,
            'moyenne': j['note_pred'] or 5.0,
            'ecart_type': 1.0,
            'buts': j['buts']
        }
    row = row.iloc[0]
    poste = row.get('Poste', j.get('poste', 'MO'))
    row_n1 = trouver_historique_n1(row['Joueur'], poste, df_n1) if df_n1 is not None else None
    moyenne, ecart_type = stabiliser_stats_proba_but(
        row_n1, cols_journees_n1, row, cols_journees, journee_actuelle,
        moyenne_mediane_poste.get(poste, moyenne_repli_global),
        ecart_type_mediane_poste.get(poste, ecart_type_repli_global)
    )
    return {
        'nom': j['nom'],
        'ligne': ligne,
        'moyenne': float(moyenne),
        'ecart_type': float(ecart_type),
        'buts': j['buts']
    }

liste_bonus = [
    "💼 Valise à Nanard — annule 1 but adverse",
    "💃 Zahia — +0,5 à tous mes joueurs",
    "🦷 Suarez — -1 au gardien adverse",
    "💻 Cheat Code — -0.5 à tous joueurs adverses",
    "🍔 Uber Eats — +1 à un joueur choisi",
]

# Retirés des menus pour la bêta : sans aucun effet actuellement dans
# monte_carlo_match (bonus_moi/bonus_adv == 'miroir'/'tonton' n'y est jamais
# géré) — les laisser sélectionnables induirait l'utilisateur en erreur.
# Remettre dans liste_bonus ci-dessus une fois leur logique implémentée.
liste_bonus_non_implementes = [
    "🪞 Miroir — retourne le bonus adverse",
    "👊 Tonton Pat' — annule remplacements adverses",
]

bonus_key_map = {
    "💼 Valise à Nanard — annule 1 but adverse": "valise",
    "🪞 Miroir — retourne le bonus adverse": "miroir",
    "💃 Zahia — +0,5 à tous mes joueurs": "zahia",
    "🦷 Suarez — -1 au gardien adverse": "suarez",
    "👊 Tonton Pat' — annule remplacements adverses": "tonton",
    "💻 Cheat Code — -0.5 à tous joueurs adverses": "cheat_code",
    "🍔 Uber Eats — +1 à un joueur choisi": "uber_eats",
    "Aucun": None,
}

def meilleure_compo(noms_joueurs, df, cols_journees, df_n1, cols_n1, journee_actuelle,
                     moyennes_lignes, notes_mediane_poste, buts_mediane_poste,
                     moyenne_mediane_poste=None, moyenne_repli_global=None,
                     ecart_type_mediane_poste=None, ecart_type_repli_global=None,
                     note_mediane_poste_n1=None, note_repli_global_n1=None,
                     cote_pct_par_joueur=None, distribution_note_n1_par_poste=None,
                     distribution_note_n1_globale=None):
    joueurs_info = []
    for nom in [n.strip() for n in noms_joueurs.split('\n') if n.strip()]:
        info = get_joueur_info(
            nom, df, cols_journees, df_n1, cols_n1, journee_actuelle,
            moyennes_lignes, notes_mediane_poste, buts_mediane_poste,
            moyenne_mediane_poste=moyenne_mediane_poste, moyenne_repli_global=moyenne_repli_global,
            ecart_type_mediane_poste=ecart_type_mediane_poste, ecart_type_repli_global=ecart_type_repli_global,
            note_mediane_poste_n1=note_mediane_poste_n1, note_repli_global_n1=note_repli_global_n1,
            cote_pct_par_joueur=cote_pct_par_joueur,
            distribution_note_n1_par_poste=distribution_note_n1_par_poste,
            distribution_note_n1_globale=distribution_note_n1_globale
        )
        if info and info['note_pred'] is not None:
            joueurs_info.append(info)

    # Score combiné = 0.75 × %Titu_percentile(par poste) + 0.25 × Note_percentile
    # (par poste) — même méthode de normalisation en rang percentile par poste que
    # le reste de Mercato (utils/mercato.py : groupby('Poste')...rank(pct=True)),
    # plutôt qu'un tri brut sur un seul critère : un joueur très titulaire mais
    # avec de très mauvaises stats peut ainsi être dépassé par un joueur un peu
    # moins titulaire mais nettement meilleur sur le plan de la note.
    #
    # Le critère secondaire est fixe (Note prédite), quel que soit le contexte
    # d'appel : la compo adverse reconstituée ici est censée approcher le onze
    # RÉEL que l'entraîneur adverse alignerait, ce qui ne dépend évidemment pas
    # d'une préférence de jeu (offensive/défensive/équilibrée) propre à
    # l'utilisateur de l'app — l'adversaire n'a aucune idée de ce choix. La Note
    # est le seul des 3 anciens critères pertinent pour TOUS les postes (Régularité
    # fait déjà doublon avec %Titu — un joueur régulier a presque toujours un
    # %Titu élevé — et Proba but n'a de sens que pour les attaquants/gardiens).
    if joueurs_info:
        df_pool = pd.DataFrame(joueurs_info)
        df_pool['titu_pct'] = df_pool.groupby('poste')['titu'].rank(pct=True)
        df_pool['note_pct'] = df_pool.groupby('poste')['note_pred'].rank(pct=True)
        scores = 0.75 * df_pool['titu_pct'] + 0.25 * df_pool['note_pct']
        for info, score in zip(joueurs_info, scores):
            info['score_compo'] = float(score)
        joueurs_info.sort(key=lambda x: x['score_compo'], reverse=True)

    equipe = {'GB': [], 'DEF': [], 'MIL': [], 'ATT': []}
    limites = {'GB': 1, 'DEF': 4, 'MIL': 4, 'ATT': 2}
    remplacants = {'GB': [], 'DEF': [], 'MIL': [], 'ATT': []}

    for j in joueurs_info:
        ligne = poste_vers_ligne(j['poste'])
        if len(equipe[ligne]) < limites[ligne]:
            equipe[ligne].append(j)
        elif len(remplacants[ligne]) < 2:
            remplacants[ligne].append(j)

    return equipe, remplacants

def _roster_html(equipe, extra_badge_fn=None):
    lignes_html = []
    for ligne in ['GB', 'DEF', 'MIL', 'ATT']:
        for j in equipe.get(ligne, []):
            if j['note_pred'] is None:
                note = "Données insuffisantes"
            elif j.get('note_estimee'):
                # Même convention que Mercato (astérisque + infobulle intégrés à la
                # valeur plutôt qu'une colonne dédiée) pour une note qui ne vient
                # d'aucune donnée exploitable du joueur (ni cette saison ni en
                # N-1) mais de la médiane de son poste — pas une vraie prédiction,
                # à ne pas confondre avec les autres notes de la compo.
                note = (
                    f'<span title="Aucune donnée exploitable cette saison ni la '
                    f'saison passée (ex. transfert sans historique Ligue 1) — Note '
                    f'estimée à partir de la Cote du joueur (percentile dans son '
                    f'poste) plutôt que sur un vrai historique du joueur." '
                    f'style="cursor:help;">{j["note_pred"]:.2f}'
                    f'<sup style="color:#c8a84b;"> *</sup></span>'
                )
            else:
                note = f"{j['note_pred']:.2f}"
            badges = ""
            if j.get('alerte'):
                # 🆕 (jamais titulaire cette saison) n'est pas une alerte de
                # blessure — style neutre plutôt que 'bad' (rouge), même
                # convention que Hebdo/Mercato.
                badges += pill(j['alerte'], 'info' if j['alerte'].startswith('🆕') else 'bad')
            if j.get('proba_but') is not None:
                label = "Arrêt" if j.get('poste') == 'G' else "But"
                badges += pill(
                    f"Proba {label} MPG {j['proba_but']*100:.0f}%", 'mid',
                    title="Probabilité de but MPG virtuel (franchissement de lignes), "
                          "pas une probabilité de but réel inscrit sur le terrain."
                )
            if extra_badge_fn:
                extra = extra_badge_fn(j)
                if extra:
                    badges += pill(extra, 'warn')
            lignes_html.append(
                '<div class="gs-roster-row">'
                f'<span class="gs-roster-ligne">{escape(ligne)}</span>'
                f'<span class="gs-roster-nom">{escape(j["nom"])}</span>'
                f'{badges}'
                f'<span class="gs-roster-note">{note}</span>'
                '</div>'
            )
    return f'<div class="gs-roster">{"".join(lignes_html)}</div>'


def afficher_adversaire(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle):
    inject_style()

    # ============================================================
    # BANDEAU TITRE + REPÈRES D'ÉTAPES — pur habillage, ne touche à aucune
    # logique du formulaire ci-dessous (radio mode d'analyse, zones de texte,
    # validation des effectifs) : juste inséré au-dessus.
    # ============================================================
    st.markdown(
        """
        <div class="gs-page-header">
          <div class="gs-page-header-logo">MT</div>
          <div class="gs-page-header-text">
            <div class="gs-page-header-title">Simuler le match</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown(
        """
        <div class="gs-step-row">
          <div class="gs-step-card">
            <div class="gs-step-num">1</div>
            <div class="gs-step-text">Choisir le mode d'analyse</div>
          </div>
          <div class="gs-step-card">
            <div class="gs-step-num">2</div>
            <div class="gs-step-text">Renseigner les deux compos</div>
          </div>
          <div class="gs-step-card">
            <div class="gs-step-num">3</div>
            <div class="gs-step-text">Configurer les bonus</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    moyennes_lignes, notes_mediane_poste, buts_mediane_poste = _calculer_contexte_ligue_cache(df, cols_journees)
    (moyenne_mediane_poste, moyenne_repli_global,
     ecart_type_mediane_poste, ecart_type_repli_global) = _calculer_repli_stabilisation_cache(
        df, cols_journees, df_n1, cols_journees_n1
    )
    note_mediane_poste_n1, note_repli_global_n1 = _mediane_n1_par_poste_cache(df_n1, 'Note')
    cote_pct_par_joueur = _cote_pct_par_poste_cache(df)
    distribution_note_n1_par_poste, distribution_note_n1_globale = _distribution_n1_par_poste_cache(df_n1, 'Note')

    separateur("MODE D'ANALYSE")
    mode_analyse = st.radio(
        "Mode d'analyse",
        ["Analyse préventive (avant match)", "Analyse précise (compo connue)"],
        horizontal=True,
        key="mode_analyse"
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Mon équipe")
        mes_titu = st.text_area(
            "Titulaires (un par ligne)",
            height=250,
            key="mes_titu"
        )
        mes_remplacants = st.text_area(
            "Remplaçants (un par ligne)",
            height=150,
            key="mes_rempl"
        )

    with col2:
        st.subheader("Équipe adverse")
        if "précise" in mode_analyse:
            adv_titu = st.text_area(
                "Titulaires adverses (un par ligne)",
                height=250,
                key="adv_titu"
            )
            adv_remplacants = st.text_area(
                "Remplaçants adverses (un par ligne)",
                height=150,
                key="adv_rempl"
            )
        else:
            adv_joueurs = st.text_area(
                "Joueurs adverses disponibles (un par ligne)",
                height=400,
                key="adv_joueurs"
            )
            st.caption(
                "La compo adverse est reconstituée automatiquement à partir de cette liste "
                "(%Titu + critère de la stratégie choisie) — une estimation, pas une certitude."
            )

    noms_mes_titu = [n.strip() for n in mes_titu.split('\n') if n.strip()]
    noms_mes_rempl = [n.strip() for n in mes_remplacants.split('\n') if n.strip()]

    # Vérification des effectifs — bloque le lancement de la simulation tant que
    # les Titulaires ne sont pas EXACTEMENT 11 joueurs reconnus sans ambiguïté de
    # chaque côté requis (Mon équipe toujours ; Équipe adverse seulement en mode
    # "Analyse précise", la seule où elle a un onze fixe — le pool "Analyse
    # préventive" a une sémantique différente, alimenté par meilleure_compo(),
    # et n'est pas concerné par cette exigence). Les Remplaçants reçoivent la même
    # détection introuvable/ambigu (messages informatifs) mais ne bloquent jamais
    # le bouton — seuls les points 1 et 2 de la demande visent les Titulaires.
    ok_moi, lignes_ok_moi, messages_moi = _analyser_lignes_joueurs(mes_titu, df, exiger_onze=True)
    _afficher_messages_effectif("Mon équipe (titulaires)", lignes_ok_moi, messages_moi, exiger_onze=True)
    if noms_mes_rempl:
        _, _, messages_moi_rempl = _analyser_lignes_joueurs(mes_remplacants, df, exiger_onze=False)
        _afficher_messages_effectif("Mon équipe (remplaçants)", [], messages_moi_rempl, exiger_onze=False)

    ok_adv, lignes_ok_adv = True, []
    if "précise" in mode_analyse:
        ok_adv, lignes_ok_adv, messages_adv = _analyser_lignes_joueurs(adv_titu, df, exiger_onze=True)
        _afficher_messages_effectif("Équipe adverse (titulaires)", lignes_ok_adv, messages_adv, exiger_onze=True)
        if adv_remplacants.strip():
            _, _, messages_adv_rempl = _analyser_lignes_joueurs(adv_remplacants, df, exiger_onze=False)
            _afficher_messages_effectif("Équipe adverse (remplaçants)", [], messages_adv_rempl, exiger_onze=False)

    with st.expander("Configurer les remplacements"):
        if not noms_mes_titu:
            st.caption("Renseignez d'abord vos titulaires ci-dessus.")
        elif not noms_mes_rempl:
            st.caption("Renseignez d'abord vos remplaçants ci-dessus.")
        else:
            nb_regles_remplacement = st.number_input(
                "Nombre de remplacements à configurer",
                min_value=0, max_value=len(noms_mes_titu), value=0, step=1,
                key="nb_regles_remplacement"
            )
            # Postes résolus une fois pour tous les remplaçants (pas les titulaires,
            # dont le poste dépend du titulaire choisi par règle, donc résolu à la
            # volée ci-dessous) — utilisés pour ne proposer, dans "Remplaçant", que
            # les joueurs du même poste que le titulaire sélectionné : sans ce
            # filtre, rien n'empêchait de faire entrer un gardien à la place d'un
            # attaquant.
            poste_par_rempl = {nom: _poste_du_nom(nom, df) for nom in noms_mes_rempl}
            for i in range(int(nb_regles_remplacement)):
                st.markdown(f"**Remplacement {i + 1}**")
                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    titu_choisi = st.selectbox("Titulaire", noms_mes_titu, key=f"rempl_titu_{i}")
                with rc2:
                    st.number_input(
                        "Seuil de note (remplacement si en dessous)",
                        min_value=0.0, max_value=10.0, value=5.0, step=0.5,
                        key=f"rempl_seuil_{i}"
                    )
                with rc3:
                    poste_titu = _poste_du_nom(titu_choisi, df) if titu_choisi else None
                    if poste_titu is None:
                        # Titulaire introuvable/ambigu (ex. homonyme non levé) :
                        # aucun poste de référence pour filtrer — repli sur la
                        # liste complète plutôt que de bloquer la sélection.
                        remplacants_du_poste = noms_mes_rempl
                    else:
                        remplacants_du_poste = [
                            n for n in noms_mes_rempl if poste_par_rempl.get(n) == poste_titu
                        ]
                    # Auto-corrige la valeur mémorisée si elle ne correspond plus aux
                    # options courantes (ex. Titulaire changé de poste depuis le
                    # dernier choix de Remplaçant) — sans ça, Streamlit lève une
                    # exception dès que la valeur en session_state n'est plus dans
                    # la liste filtrée (même défaut que Capitaine ci-dessous).
                    if st.session_state.get(f"rempl_nom_{i}") not in remplacants_du_poste:
                        st.session_state[f"rempl_nom_{i}"] = (
                            remplacants_du_poste[0] if remplacants_du_poste else None
                        )
                    if remplacants_du_poste:
                        st.selectbox("Remplaçant", remplacants_du_poste, key=f"rempl_nom_{i}")
                    else:
                        st.selectbox("Remplaçant", [], key=f"rempl_nom_{i}",
                                      placeholder=f"Aucun remplaçant au poste {poste_titu}")

    # Auto-corrige la valeur mémorisée si elle ne correspond plus à un titulaire
    # actuel (ex. liste encore vide au tout premier rendu, puis remplie ensuite, ou
    # capitaine retiré des Titulaires) — sans ça, Streamlit garde la sélection
    # "vide" du tout premier rendu (options=[]) même une fois la liste remplie, et
    # affiche le placeholder anglais par défaut ("Choose an option") au lieu de
    # revenir sur le premier titulaire disponible.
    if noms_mes_titu and st.session_state.get("capitaine_designe") not in noms_mes_titu:
        st.session_state["capitaine_designe"] = noms_mes_titu[0]

    capitaine_actif = st.selectbox(
        "Capitaine (bonus +0,5 — suit le joueur même s'il est remplacé en cours de simulation)",
        noms_mes_titu,
        key="capitaine_designe",
        placeholder="Renseignez d'abord vos titulaires ci-dessus"
    )

    separateur("CONFIGURATION DES BONUS")
    col_b1, col_b2 = st.columns(2)

    with col_b1:
        st.subheader("Bonus disponibles")
        mes_bonus_dispo_liste = st.multiselect(
            "Bonus disponibles",
            liste_bonus,
            key="mes_bonus_dispo",
            label_visibility="collapsed",
            placeholder="Aucun bonus sélectionné",
            help="Coche tous les bonus encore en réserve — chacun est testé séparément "
                 "(jamais cumulés, un seul bonus utilisable par match en vrai MPG)."
        )
        if any("Uber Eats" in b for b in mes_bonus_dispo_liste):
            st.caption(
                "🍔 Uber Eats : la meilleure cible est déterminée automatiquement "
                "ci-dessous (testée sur chaque titulaire) — inutile de la choisir "
                "à l'aveugle avant de voir l'effet."
            )
        importance_match = st.radio(
            "Importance du match",
            ["Crucial", "Normal", "Sans enjeu"],
            horizontal=True,
            key="importance"
        )

    with col_b2:
        st.subheader("Bonus adverse (estimé)")
        bonus_adv_estime = st.selectbox(
            "Bonus adverse (estimé)",
            ["Aucun"] + liste_bonus,
            key="bonus_adv_estime",
            label_visibility="collapsed"
        )

    separateur("TERRAIN")

    domicile = st.radio(
        "Terrain",
        ["Domicile", "Extérieur"],
        horizontal=True,
        key="domicile",
        label_visibility="collapsed"
    ) == "Domicile"

    if st.button("Lancer la simulation", type="primary", disabled=not (ok_moi and ok_adv)):

        # Construction à partir des lignes déjà résolues par _analyser_lignes_joueurs
        # ci-dessus (nom exact + club exact), PAS en reparsant le texte brut : le
        # bouton n'est cliquable que si ok_moi/ok_adv valent True, donc ces lignes
        # sont garanties 11/11 et non-ambiguës — réutiliser le club déjà déterminé
        # (via get_joueur_info(..., club=...)) assure que la simulation porte
        # exactement sur le même joueur que celui confirmé par la vérification,
        # plutôt que de redéclencher un homonyme non résolu.
        def construire_equipe_depuis_lignes_ok(lignes_ok):
            titu_info = []
            non_trouves = []
            for nom, club in lignes_ok:
                info = get_joueur_info(
                    nom, df, cols_journees, df_n1, cols_journees_n1, journee_actuelle,
                    moyennes_lignes, notes_mediane_poste, buts_mediane_poste, club=club,
                    moyenne_mediane_poste=moyenne_mediane_poste, moyenne_repli_global=moyenne_repli_global,
                    ecart_type_mediane_poste=ecart_type_mediane_poste, ecart_type_repli_global=ecart_type_repli_global,
                    note_mediane_poste_n1=note_mediane_poste_n1, note_repli_global_n1=note_repli_global_n1,
                    cote_pct_par_joueur=cote_pct_par_joueur,
                    distribution_note_n1_par_poste=distribution_note_n1_par_poste,
                    distribution_note_n1_globale=distribution_note_n1_globale
                )
                if info:
                    titu_info.append(info)
                else:
                    non_trouves.append(nom)
            return titu_info, non_trouves

        # Mon équipe
        titu_moi, non_trouves_moi = construire_equipe_depuis_lignes_ok(lignes_ok_moi)
        equipe_moi = {'GB': [], 'DEF': [], 'MIL': [], 'ATT': []}
        for j in titu_moi:
            equipe_moi[poste_vers_ligne(j['poste'])].append(j)

        # Équipe adverse
        non_trouves_adv = []
        if "précise" in mode_analyse:
            titu_adv, non_trouves_adv = construire_equipe_depuis_lignes_ok(lignes_ok_adv)
            equipe_adv = {'GB': [], 'DEF': [], 'MIL': [], 'ATT': []}
            for j in titu_adv:
                equipe_adv[poste_vers_ligne(j['poste'])].append(j)
        else:
            equipe_adv, _ = meilleure_compo(
                adv_joueurs, df, cols_journees,
                df_n1, cols_journees_n1, journee_actuelle,
                moyennes_lignes, notes_mediane_poste, buts_mediane_poste,
                moyenne_mediane_poste=moyenne_mediane_poste, moyenne_repli_global=moyenne_repli_global,
                ecart_type_mediane_poste=ecart_type_mediane_poste, ecart_type_repli_global=ecart_type_repli_global,
                note_mediane_poste_n1=note_mediane_poste_n1, note_repli_global_n1=note_repli_global_n1,
                cote_pct_par_joueur=cote_pct_par_joueur,
                distribution_note_n1_par_poste=distribution_note_n1_par_poste,
                distribution_note_n1_globale=distribution_note_n1_globale
            )

        # Alertes joueurs non trouvés
        if non_trouves_moi:
            st.warning(f"Joueurs non trouvés (mon équipe) : {', '.join(non_trouves_moi)}")
        if non_trouves_adv:
            st.warning(f"Joueurs non trouvés (adversaire) : {', '.join(non_trouves_adv)}")

        # Convertir en format Monte Carlo
        def joueur_vers_mc(j, ligne):
            return _joueur_vers_mc(
                j, ligne, df, cols_journees, df_n1, cols_journees_n1, journee_actuelle,
                moyenne_mediane_poste, moyenne_repli_global,
                ecart_type_mediane_poste, ecart_type_repli_global
            )

        def equipe_vers_mc(equipe):
            joueurs_mc = []
            for ligne, joueurs in equipe.items():
                for j in joueurs:
                    joueurs_mc.append(joueur_vers_mc(j, ligne))
            return joueurs_mc

        joueurs_moi_mc = equipe_vers_mc(equipe_moi)
        joueurs_adv_mc = equipe_vers_mc(equipe_adv)

        # Remplacements configurés (mon équipe uniquement) : convertit chaque
        # règle (titulaire, seuil, remplaçant) en infos exploitables par
        # monte_carlo_match, en réutilisant get_joueur_info pour le remplaçant
        # (même logique de prédiction/repli que pour un titulaire).
        regles_remplacement_mc = []
        nb_regles_remplacement = st.session_state.get("nb_regles_remplacement", 0)
        for i in range(int(nb_regles_remplacement)):
            nom_titu_regle = st.session_state.get(f"rempl_titu_{i}")
            seuil_regle = st.session_state.get(f"rempl_seuil_{i}")
            nom_rempl_regle = st.session_state.get(f"rempl_nom_{i}")
            if not (nom_titu_regle and nom_rempl_regle and seuil_regle is not None):
                continue
            info_rempl = get_joueur_info(
                nom_rempl_regle, df, cols_journees, df_n1, cols_journees_n1, journee_actuelle,
                moyennes_lignes, notes_mediane_poste, buts_mediane_poste,
                moyenne_mediane_poste=moyenne_mediane_poste, moyenne_repli_global=moyenne_repli_global,
                ecart_type_mediane_poste=ecart_type_mediane_poste, ecart_type_repli_global=ecart_type_repli_global,
                note_mediane_poste_n1=note_mediane_poste_n1, note_repli_global_n1=note_repli_global_n1,
                cote_pct_par_joueur=cote_pct_par_joueur,
                distribution_note_n1_par_poste=distribution_note_n1_par_poste,
                distribution_note_n1_globale=distribution_note_n1_globale
            )
            if not info_rempl:
                continue
            ligne_rempl = poste_vers_ligne(info_rempl['poste'])
            regles_remplacement_mc.append({
                'titulaire': nom_titu_regle,
                'seuil': float(seuil_regle),
                'remplacant': joueur_vers_mc(info_rempl, ligne_rempl)
            })

        bonus_adv_key = bonus_key_map.get(bonus_adv_estime, None)

        # Nombres aléatoires communs (réduction de variance) : la simulation de
        # référence et chaque simulation "avec bonus" ci-dessous partagent la
        # même graine — les DEUX tirent alors exactement les mêmes notes/buts
        # avant application du bonus, si bien que toute différence observée
        # reflète uniquement l'effet mécanique du bonus, jamais du bruit
        # d'échantillonnage entre deux séries de tirages indépendantes (ce qui
        # pouvait faire apparaître un gain négatif sur un bonus qui ne peut
        # mécaniquement jamais nuire, ex. Suarez, Valise à Nanard).
        seed_commun = int(np.random.randint(0, 2**31 - 1))

        # Simulation "sans MON bonus" (le Capitaine, structurel, reste actif même
        # ici) — bonus_adv est appliqué ICI AUSSI, identique à chaque simulation
        # "avec mon bonus" ci-dessous : seul bonus_moi doit varier entre les deux
        # simulations comparées. Avant ce correctif, bonus_adv n'était PAS passé
        # à cette référence (implicitement None) alors qu'il l'était dans chaque
        # test "avec bonus" — le delta affiché mesurait donc l'effet COMBINÉ
        # (mon bonus + bonus adverse) au lieu de l'effet isolé de mon bonus,
        # faisant paraître négatif un bonus pourtant mécaniquement neutre/positif
        # dès que le bonus adverse estimé était pénalisant pour moi (ex. Cheat
        # Code, Valise à Nanard adverse).
        with st.spinner("Simulation en cours (2000 scénarios)..."):
            res_sb = monte_carlo_match(
                joueurs_moi_mc, joueurs_adv_mc,
                bonus_adv=bonus_adv_key,
                regles_remplacement=regles_remplacement_mc,
                capitaine=capitaine_actif,
                n_simulations=2000,
                domicile=domicile,
                seed=seed_commun
            )

        separateur("RÉSULTAT")

        col_s1, col_s2, col_s3 = st.columns([2, 1, 2])

        with col_s1:
            # Victoire en st.metric (grande, priorité visuelle) — Nul/Défaite en
            # taille réduite (_metrique_secondaire) mais lisible, pas juste un
            # st.caption gris minuscule : même principe de hiérarchie que "Impact
            # de vos bonus disponibles" (le chiffre qui compte pour décider ressort,
            # le reste sert de contexte sans être illisible).
            st.metric("Victoire", f"{res_sb['victoires']}%")
            st.markdown(_metrique_secondaire("Nul", f"{res_sb['nuls']}%"), unsafe_allow_html=True)
            st.markdown(_metrique_secondaire("Défaite", f"{res_sb['defaites']}%"), unsafe_allow_html=True)

        with col_s2:
            if _est_favori(res_sb):
                st.markdown("### Favori")
            elif res_sb['victoires'] > 40:
                st.markdown("### Serré")
            else:
                st.markdown("### Outsider")

        with col_s3:
            st.metric("Score moyen prévu",
                     f"{res_sb['score_moy_moi']} - {res_sb['score_moy_adv']}")

        separateur("RECOMMANDATION CAPITAINE")
        candidats_cap = []
        for ligne, joueurs in equipe_moi.items():
            if ligne == 'GB':
                continue
            for j in joueurs:
                if j['note_pred'] is not None:
                    # Formule fixe (note + régularité + proba but), même pondération
                    # équilibrée quel que soit le contexte d'appel — cette recommandation
                    # reste une simple suggestion, l'utilisateur choisit son propre
                    # capitaine via le sélecteur "Capitaine" ci-dessus.
                    score_cap = (j['note_pred']/10)*0.5 + j['regularite']*0.3 + j['proba_but']*0.2
                    candidats_cap.append((j['nom'], j['poste'], j['note_pred'], score_cap))

        if equipe_moi.get('GB') and equipe_moi['GB']:
            gb = equipe_moi['GB'][0]
            if gb.get('proba_but', 0) >= 0.10:
                candidats_cap.append((gb['nom'], 'G', gb['note_pred'], 999))

        if candidats_cap:
            meilleur_cap = max(candidats_cap, key=lambda x: x[3])
            st.success(f"**{meilleur_cap[0]}** ({meilleur_cap[1]}) — Note prédite : {meilleur_cap[2]}")

        separateur("RECOMMANDATION MAESTRO TACTICO")

        if mes_bonus_dispo_liste:
            st.markdown("**Impact de vos bonus disponibles :**")

            # Chaque bonus coché est testé SÉPARÉMENT (une simulation dédiée par
            # bonus, bonus_moi=<un seul à la fois>) — jamais cumulés entre eux,
            # conformément à la règle réelle MPG (un seul bonus utilisable par
            # match). bonus_adv (l'estimation adverse) reste, lui, constant sur
            # toutes ces simulations ET SUR LA RÉFÉRENCE res_sb ci-dessus : c'est
            # un contexte de match, pas un choix de l'utilisateur qui varie d'un
            # test à l'autre — seul bonus_moi doit varier entre res_sb et res_b.
            resultats_bonus = {}
            cibles_uber = {}
            with st.spinner("Test des bonus en cours..."):
                for bonus in mes_bonus_dispo_liste:
                    bonus_key = bonus_key_map.get(bonus, None)
                    if bonus_key == 'uber_eats':
                        # Recommandation automatique, même principe que le reste de
                        # "Impact de vos bonus disponibles" : l'app conseille, l'utilisateur
                        # n'a pas à deviner la cible avant même d'en voir l'effet. Teste
                        # Uber Eats sur CHAQUE titulaire (le Capitaine est exclu — règle
                        # réelle : les deux bonus ne peuvent pas cibler le même joueur, le
                        # tester serait équivalent à ne pas utiliser Uber Eats du tout) et
                        # retient la meilleure cible trouvée.
                        candidats_uber = [j['nom'] for j in titu_moi if j['nom'] != capitaine_actif]
                        res_b, meilleure_cible = None, None
                        for candidat in candidats_uber:
                            res_candidat = monte_carlo_match(
                                joueurs_moi_mc, joueurs_adv_mc,
                                n_simulations=2000,
                                bonus_moi=bonus_key,
                                bonus_adv=bonus_adv_key,
                                regles_remplacement=regles_remplacement_mc,
                                capitaine=capitaine_actif,
                                domicile=domicile,
                                joueur_uber=candidat,
                                seed=seed_commun
                            )
                            if res_b is None or res_candidat['victoires'] > res_b['victoires']:
                                res_b, meilleure_cible = res_candidat, candidat
                        cibles_uber[bonus] = meilleure_cible
                    else:
                        res_b = monte_carlo_match(
                            joueurs_moi_mc, joueurs_adv_mc,
                            n_simulations=2000,
                            bonus_moi=bonus_key,
                            bonus_adv=bonus_adv_key,
                            regles_remplacement=regles_remplacement_mc,
                            capitaine=capitaine_actif,
                            domicile=domicile,
                            seed=seed_commun
                        )
                    resultats_bonus[bonus] = res_b

            def _label_bonus(bonus):
                nom = bonus.split('—')[0].strip()
                cible = cibles_uber.get(bonus)
                return f"{nom} ({cible})" if cible else nom

            meilleur = max(resultats_bonus.items(), key=lambda x: x[1]['victoires'])
            nom_meilleur = _label_bonus(meilleur[0])
            res_meilleur = meilleur[1]
            gain_meilleur = round(res_meilleur['victoires'] - res_sb['victoires'], 1)

            # Mise en avant : LA valeur qui compte pour décider ("avec mon bonus", le
            # bonus adverse estimé étant déjà pris en compte dans cette même valeur ET
            # dans sa référence res_sb) — seule grande st.metric, pas "aucun bonus" ni
            # "bonus adverse seul" qui ne sont pas ce que l'utilisateur s'apprête à
            # vivre (l'adversaire, lui, a déjà décidé). Le delta reste la valeur
            # marginale de MA décision par rapport à res_sb (bonus adverse déjà inclus).
            st.metric(
                f"Victoire avec {nom_meilleur}", f"{res_meilleur['victoires']}%",
                delta=f"{gain_meilleur:+.1f} pts"
            )

            # Détail des 2 configurations qui comptent réellement pour LA décision de
            # l'utilisateur (utiliser mon bonus ou pas, sachant que l'adversaire utilise
            # déjà le sien) — texte HTML dimensionné via _detail_configuration, pas
            # st.metric, pour rester visuellement secondaire par rapport à la valeur
            # mise en avant ci-dessus. "Aucun bonus" retiré : ce n'est pas une situation
            # que l'utilisateur peut choisir (l'adversaire a déjà décidé d'utiliser le
            # sien), cette 3e référence n'aidait donc pas la décision et compliquait la
            # lecture sans raison.
            st.markdown(
                '<div style="font-size:0.95rem; color:rgba(255,255,255,0.75); '
                'margin:6px 0 6px;">Détail des 2 configurations testées (% de victoire) :</div>',
                unsafe_allow_html=True
            )
            col_bonus1, col_bonus2 = st.columns(2)
            with col_bonus1:
                st.markdown(_detail_configuration("Bonus adverse seul", f"{res_sb['victoires']}%"), unsafe_allow_html=True)
            with col_bonus2:
                st.markdown(
                    _detail_configuration(f"Avec {nom_meilleur}", f"{res_meilleur['victoires']}%", f"{gain_meilleur:+.1f} pts"),
                    unsafe_allow_html=True
                )

            for bonus, res in sorted(
                resultats_bonus.items(),
                key=lambda x: x[1]['victoires'],
                reverse=True
            ):
                nom_bonus = _label_bonus(bonus)
                gain = round(res['victoires'] - res_sb['victoires'], 1)
                gain_str = f"+{gain}%" if gain > 0 else f"{gain}%"
                if _est_favori(res):
                    indicateur = "+"
                elif res['victoires'] > 40:
                    indicateur = "~"
                else:
                    indicateur = "-"
                st.write(
                    f"{indicateur} **{nom_bonus}** → "
                    f"{res['victoires']}% victoire ({gain_str}) | "
                    f"Score: {res['score_moy_moi']}-{res['score_moy_adv']}"
                )

            # Recommandation finale — UNE SEULE, par palier de victoire (vic),
            # tenant compte de l'importance du match et du gain du meilleur bonus
            # (seuil de significativité variable selon l'enjeu — voir
            # SEUIL_SIGNIFICATIVITE_GAIN : 3 pts en Crucial, 8 en Normal, 15 en
            # Sans enjeu, au lieu d'un seuil fixe de 6 pts quel que soit l'enjeu).
            # Avant ce correctif, un second bloc de recommandation générique
            # (uniquement basé sur gain_meilleur >= 6, ignorant vic/importance)
            # s'affichait EN PLUS de cette logique par palier, produisant deux
            # messages simultanés qui pouvaient se contredire (ex. "Utilisez X"
            # et "Gardez vos bonus" en même temps avec Importance = Normal/Sans
            # enjeu). "Favori" (paliers vic>=50 et res_meilleur>=50 remplacés)
            # utilise _est_favori (Victoire = résultat le plus probable des
            # trois), pas un seuil absolu à 50% — même définition que le
            # bandeau du haut, pour rester cohérent avec lui.
            vic = res_sb['victoires']
            seuil_gain = SEUIL_SIGNIFICATIVITE_GAIN.get(importance_match, 8)

            if vic >= 65:
                st.success(f"**Gardez vos bonus** — Largement favori ({vic}%). Économisez pour un match plus serré !")
            elif _est_favori(res_sb):
                if importance_match == "Crucial":
                    st.success(f"**Utilisez {nom_meilleur}** — Match crucial, passe à {res_meilleur['victoires']}% de victoire !")
                else:
                    st.success(f"**Gardez vos bonus** — Favori à {vic}%, bonus non indispensable !")
            elif vic >= 40:
                if round(res_meilleur['victoires'] - vic, 1) >= seuil_gain:
                    st.warning(f"**Utilisez {nom_meilleur}** — Match serré ({vic}%), le bonus fait passer à {res_meilleur['victoires']}% !")
                else:
                    st.warning(f"**Match très serré ({vic}%)** — Aucun bonus ne change significativement le résultat")
            elif vic >= 30:
                if _est_favori(res_meilleur):
                    st.warning(f"**Utilisez {nom_meilleur}** — Peut renverser la situation ({vic}% → {res_meilleur['victoires']}%) !")
                else:
                    st.error(f"**Défaite probable ({vic}%)** — Aucun bonus ne suffit. Économisez-les !")
            else:
                st.error(f"**Défaite très probable ({vic}%)** — N'utilisez aucun bonus, gardez-les pour un match gagnable !")

        else:
            vic = res_sb['victoires']
            if vic >= 65:
                st.success(f"Largement favori ({vic}%) — Pas besoin de bonus !")
            elif _est_favori(res_sb):
                st.success(f"Favori ({vic}%) — Victoire probable !")
            elif vic >= 40:
                st.warning(f"Match serré ({vic}%) — Envisagez d'utiliser un bonus !")
            elif vic >= 30:
                st.error(f"Outsider ({vic}%) — Utilisez un bonus si disponible !")
            else:
                st.error(f"Très outsider ({vic}%) — Économisez vos bonus !")

        if "Miroir" in bonus_adv_estime:
            st.warning("**L'adversaire a le Miroir !** — Si vous utilisez un bonus, il peut le retourner contre vous !")

        separateur("DÉTAILS DES ÉQUIPES")
        st.caption(
            "Notes de base, hors bonus — calculées une seule fois avant simulation, "
            "elles ne varient donc pas selon le bonus sélectionné ci-dessus."
        )
        col_eq1, col_eq2 = st.columns(2)

        with col_eq1:
            st.subheader("Mon équipe")
            st.markdown(_roster_html(equipe_moi), unsafe_allow_html=True)

        with col_eq2:
            st.subheader("Équipe adverse")
            def _rotaldo(j):
                return "Rotaldo probable" if not j['note_pred'] or j['note_pred'] < 3 else None
            st.markdown(_roster_html(equipe_adv, extra_badge_fn=_rotaldo), unsafe_allow_html=True)
