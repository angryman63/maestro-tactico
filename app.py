import streamlit as st
import pandas as pd
import requests
import io
import sys
import os
import time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modele import (
    nettoyer_note, determiner_journee_actuelle, normaliser_recherche,
    trouver_historique_n1, predire_note_hybride, chercher_lignes_joueur,
    mediane_n1_par_poste,
)
from utils.accueil import afficher_accueil
from utils.hebdo import afficher_hebdo
from utils.mercato import afficher_mercato
from utils.adversaire import afficher_adversaire

# ============================================================
# CONFIG PAGE
# ============================================================

st.set_page_config(
    page_title="Maestro Tactico",
    page_icon="⚽",
    layout="wide"
)

# ============================================================
# CSS GLOBAL — IDENTITÉ VISUELLE MAESTRO TACTICO
# ============================================================

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@700&family=Inter:wght@400;500;600&display=swap');

/* Fond général */
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: #141414 !important;
    color: #ffffff !important;
}

[data-testid="stSidebar"] {
    background-color: #0d0d0d !important;
    border-right: 1px solid #c8a84b33;
}

/* Section "Mes joueurs" (sidebar) */
[data-testid="stSidebar"] h3 {
    font-family: 'Oswald', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: #c8a84b !important;
    font-size: 1.05rem !important;
}

[data-testid="stTextAreaRootElement"] {
    background-color: #1a1a1a !important;
    border: 1px solid #333333 !important;
    border-radius: 6px;
}

[data-testid="stTextArea"] textarea {
    color: #f5f5f5 !important;
}

/* Case "Afficher uniquement mes joueurs" */
[data-testid="stCheckbox"] label > div:first-of-type {
    background-color: #1a1a1a !important;
    border: 1px solid rgba(200, 168, 75, 0.5) !important;
    border-radius: 4px !important;
    transition: background-color 0.2s ease, border-color 0.2s ease;
}

[data-testid="stCheckbox"] label[data-selected="true"] > div:first-of-type {
    background-color: #c8a84b !important;
    border-color: #c8a84b !important;
}

[data-testid="stCheckbox"] label[data-selected="true"] > div:first-of-type svg polyline {
    stroke: #0d0d0d !important;
}

[data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p {
    font-family: 'Raleway', sans-serif !important;
    color: #ffffff !important;
}

/* Topbar */
[data-testid="stHeader"] {
    background-color: #0d0d0d !important;
    border-bottom: 1px solid #c8a84b44;
}

/* Navigation principale (Accueil / Conseiller hebdo / Mercato / Simuler le match) —
   st.radio (pas st.tabs) : seul un widget qui renvoie sa valeur sélectionnée à
   Python permet de savoir quelle page est affichée (st.tabs ne le permet pas),
   ce qui est nécessaire pour n'afficher la sidebar "Mes joueurs" que sur
   Conseiller Hebdo. Stylé en pastilles pour reproduire visuellement l'ancienne
   barre d'onglets. */
.st-key-nav_radio [data-testid="stRadioGroup"] {
    background-color: #1a1a1a !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 10px !important;
    padding: 6px !important;
    gap: 6px !important;
}

.st-key-nav_radio [data-testid="stRadioOption"] {
    position: relative !important;
    background-color: transparent !important;
    color: rgba(255, 255, 255, 0.62) !important;
    font-family: 'Oswald', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    /* Padding vertical : sans lui, le libellé (une simple ligne de texte, ~22px de
       haut, contrairement à l'ancien st.tabs() bien plus haut) ne laisse aucune
       place sous le texte pour la barre d'accent ci-dessous — elle traversait alors
       les lettres au lieu de souligner proprement le libellé. */
    padding: 10px 24px !important;
    border-radius: 8px !important;
    cursor: pointer !important;
    transition: color 0.25s ease, background-color 0.25s ease !important;
}

/* Masque le rond radio natif : seul le libellé (pastille pleine) reste visible */
.st-key-nav_radio [data-testid="stRadioOption"] > div > div > div:first-child {
    display: none !important;
}

.st-key-nav_radio [data-testid="stRadioOption"]:hover {
    color: rgba(255, 255, 255, 0.92) !important;
    background-color: #c8a84b14 !important;
}

.st-key-nav_radio [data-testid="stRadioOption"][data-selected="true"] {
    color: #c8a84b !important;
    background-color: #c8a84b22 !important;
    font-weight: 700 !important;
}

.st-key-nav_radio [data-testid="stRadioOption"][data-selected="true"]::after {
    content: "";
    position: absolute;
    left: 16px;
    right: 16px;
    bottom: 2px;
    height: 3px;
    border-radius: 3px;
    background-color: #c8a84b;
}

.st-key-nav_radio [data-testid="stRadioOption"] p {
    font-family: 'Oswald', sans-serif !important;
}

/* DataFrames */
[data-testid="stDataFrame"] {
    background-color: #1a1a1a !important;
    border: 1px solid #333333 !important;
    border-radius: 8px;
}

/* Boutons */
.stButton > button {
    background: linear-gradient(135deg, #c8a84b, #8a6f2e);
    color: #141414;
    font-weight: 700;
    border: none;
    border-radius: 6px;
    font-family: 'Raleway', sans-serif;
}

.stButton > button:hover {
    background: linear-gradient(135deg, #d4b55c, #9a7f3e);
    color: #141414;
}

/* Métriques */
[data-testid="stMetricValue"] {
    color: #c8a84b !important;
    font-family: 'Oswald', sans-serif;
}

/* Selectbox / inputs */
[data-testid="stSelectbox"] > div,
[data-testid="stTextInput"] > div > div {
    background-color: #1a1a1a !important;
    border: 1px solid #333333 !important;
    color: #ffffff !important;
    border-radius: 6px;
}

/* Alerts */
[data-testid="stAlert"] {
    border-radius: 8px;
}

/* Dividers */
hr {
    border-color: #c8a84b44 !important;
}

/* ============================================================
   BANDEAU MAESTRO TACTICO (wordmark, au-dessus des onglets)
   ============================================================ */

.mt-topband {
    text-align: center;
    padding: 18px 16px 12px 16px;
    margin-top: -38px;
}

.mt-topband-wordmark {
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    font-size: 42px;
    color: #c8a84b;
    letter-spacing: 0.35em;
    text-transform: uppercase;
    margin: 0;
}

.mt-topband-line {
    height: 1px;
    background: linear-gradient(to right, transparent, #c8a84b, transparent);
    margin: 0 0 32px 0;
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# TOPBAR / SIDEBAR LOGO
# ============================================================

LOGO_HTML = """
<div style="padding:10px 4px 6px 4px;">
  <div style="font-family:'Oswald',sans-serif; font-weight:700; font-size:16px; color:#c8a84b; letter-spacing:2px; line-height:1;">MT</div>
  <div style="width:100%; height:1px; background:linear-gradient(to right,#c8a84b,transparent); margin:5px 0;"></div>
  <div style="font-family:'Oswald',sans-serif; font-weight:700; font-size:11px; color:#ffffff; letter-spacing:4px; opacity:0.9;">MAESTRO TACTICO</div>
</div>
"""

# ============================================================
# URL GITHUB — FICHIER JOUEURS FUSIONNÉ (saison en cours)
# ============================================================

GITHUB_URL = "https://raw.githubusercontent.com/angryman63/gazon-stats/main/joueurs_fusionne.xlsx"

# ============================================================
# RÉFÉRENCE SAISON N-1 (25-26) — fichier statique, figé, jamais régénéré
# ============================================================

FICHIER_N1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "n1", "joueurs_fusionne_25-26.xlsx")

# ============================================================
# CHARGEMENT AUTOMATIQUE DEPUIS GITHUB
# ============================================================

@st.cache_data(show_spinner=False, ttl=3600)
def charger_depuis_github(url: str):
    """Renvoie (df, heure_recuperation) — l'horodatage est calculé ICI, à
    l'intérieur de la fonction mise en cache (pas à l'appel), pour qu'il soit
    mémorisé avec le DataFrame : tant que le cache est valide (ttl=3600s),
    tous les appels renvoient le MÊME horodatage, celui de la vraie
    récupération réseau — pas l'heure de chaque rerun qui retomberait sur le
    cache. Affiché sur Mercato comme repère de fraîcheur des données."""
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    df = pd.read_excel(io.BytesIO(response.content))
    return df, datetime.now()

@st.cache_data(show_spinner=False)
def charger_reference_n1(chemin: str):
    return pd.read_excel(chemin)

# ============================================================
# LOGIQUE PRINCIPALE
# ============================================================

placeholder = st.empty()
donnees_chargees = "df_joueurs" in st.session_state

if not donnees_chargees:
    with placeholder.container():
        afficher_accueil()
        barre = st.progress(0, text="Connexion à la base joueurs…")
        for i in range(0, 60, 5):
            time.sleep(0.08)
            barre.progress(i, text="Connexion à la base joueurs…")

    try:
        df_raw, derniere_maj = charger_depuis_github(GITHUB_URL)
        st.session_state["df_joueurs"] = df_raw
        st.session_state["derniere_maj"] = derniere_maj
        st.session_state["df_joueurs_n1"] = charger_reference_n1(FICHIER_N1)
    except ValueError as e:
        placeholder.empty()
        st.error(f"Erreur lors de la fusion des fichiers joueurs : {e}")
        st.stop()
    except Exception as e:
        placeholder.empty()
        st.error(f"Impossible de charger la base joueurs depuis GitHub. Vérifiez votre connexion ou contactez le support.")
        st.stop()

    placeholder.empty()

df = st.session_state["df_joueurs"]
df_n1 = st.session_state["df_joueurs_n1"]
derniere_maj = st.session_state.get("derniere_maj")

# ============================================================
# TRAITEMENT DES DONNÉES
# ============================================================

cols_journees = [col for col in df.columns if str(col).startswith('D') and str(col)[1:].isdigit()]
cols_journees = sorted(cols_journees, key=lambda x: int(x[1:]), reverse=True)

for col in cols_journees:
    df[col] = df[col].apply(nettoyer_note)

cols_journees_n1 = [col for col in df_n1.columns if str(col).startswith('D') and str(col)[1:].isdigit()]
cols_journees_n1 = sorted(cols_journees_n1, key=lambda x: int(x[1:]), reverse=True)

for col in cols_journees_n1:
    df_n1[col] = df_n1[col].apply(nettoyer_note)

# Journée calendaire actuelle, déduite des données (jamais codée en dur) :
# servira au plafond J8 et au bandeau du modèle hybride N-1/actuelle (étape suivante).
journee_actuelle = determiner_journee_actuelle(df, cols_journees)

# ============================================================
# SIDEBAR — MES JOUEURS
# ============================================================

def _verifier_noms_joueurs(lignes, df, df_n1, cols_journees, cols_journees_n1, journee_actuelle):
    """Vérifie chaque ligne saisie dans "Mes joueurs" au clic sur Valider (pure
    information, ne change rien à ce qui est affiché par le filtre) :
    - aucune correspondance, même partielle -> introuvable ;
    - correspondance seulement partielle (fragment) -> suggère les noms complets ;
    - nom trouvé (un ou plusieurs homonymes) mais sans Forme 6J exploitable
      (trop peu de matchs cette saison et pas d'historique N-1 fiable, même
      logique que trouver_historique_n1/predire_note_hybride dans Hebdo) ->
      Hebdo l'affiche quand même via un repli sur la médiane N-1 du poste
      (typiquement un promu de Ligue 2, ex. Le Mans/Troyes) : signalé comme
      tel plutôt que comme absent, pour rester cohérent avec ce qui
      s'affiche réellement dans les recommandations ;
    - nom trouvé et éligible -> confirmation discrète.
    Un nom homonyme (plusieurs joueurs réels, ex. postes/clubs différents)
    produit un message par joueur réel trouvé, pas un seul verdict global."""
    # Conservé pour les suggestions par fragment ci-dessous (chercher_lignes_joueur
    # ne couvre que la correspondance exacte) — recalculé une fois pour tout le
    # dataframe plutôt qu'à chaque ligne saisie.
    noms_normalises = df['Joueur'].apply(normaliser_recherche)
    # Même repli ultime que utils/hebdo.py::afficher_hebdo (médiane N-1 du
    # poste, même fonction centralisée modele.py::mediane_n1_par_poste) : un
    # joueur sans Forme 6J exploitable n'est PLUS absent des recommandations
    # depuis ce repli, sauf si le repli lui-même est indisponible (poste
    # totalement absent du fichier N-1).
    note_mediane_poste_n1, note_repli_global_n1 = mediane_n1_par_poste(df_n1, 'Note')
    resultats = []
    for ligne in lignes:
        ligne_norm = normaliser_recherche(ligne)
        if not ligne_norm:
            continue
        # chercher_lignes_joueur (modele.py) : même fonction centralisée de
        # recherche par nom exact (normalisée accents/casse/séparateurs) que
        # Simuler le match, plutôt qu'une correspondance réécrite localement
        # qui pourrait un jour diverger de la logique centrale.
        lignes_exactes = chercher_lignes_joueur(ligne, df)

        if len(lignes_exactes) == 0:
            noms_fragments = df.loc[noms_normalises.str.contains(ligne_norm, regex=False), 'Joueur'].unique().tolist()
            if noms_fragments:
                suggestions = ', '.join(noms_fragments[:8])
                if len(noms_fragments) > 8:
                    suggestions += f", et {len(noms_fragments) - 8} autre(s)"
                resultats.append(('warning', f"« {ligne} » ne correspond à aucun nom exact — vouliez-vous dire : {suggestions} ?"))
            else:
                resultats.append(('error', f"« {ligne} » introuvable dans les données (aucune correspondance, même partielle)."))
            continue

        for _, row in lignes_exactes.iterrows():
            identifiant = f"{row['Joueur']} ({row['Poste']}, {row['Club']})"
            row_n1 = trouver_historique_n1(row['Joueur'], row['Poste'], df_n1)
            note_forme, _ = predire_note_hybride(row_n1, cols_journees_n1, row, cols_journees, journee_actuelle)
            if note_forme is None:
                repli = note_mediane_poste_n1.get(row['Poste'], note_repli_global_n1)
                if pd.isna(repli):
                    resultats.append(('info', f"{identifiant} trouvé mais pas encore assez de données cette saison pour apparaître dans les recommandations."))
                else:
                    resultats.append(('success', f"{identifiant} trouvé et disponible dans les recommandations (estimation prudente basée sur la médiane du poste, faute de données propres cette saison et la saison passée)."))
            else:
                resultats.append(('success', f"{identifiant} trouvé et disponible dans les recommandations."))
    return resultats


def _afficher_pied_de_page():
    """Pied de page (contact + mention RGPD) — identique au texte qui vivait dans
    la sidebar, simplement déplacé en bas de la page principale sur les pages où
    la sidebar "Mes joueurs" n'a plus de raison d'être affichée (voir plus bas)."""
    st.markdown("---")
    st.markdown(
        "<div style='font-family:Raleway,sans-serif; font-size:11px; color:rgba(255,255,255,0.55); "
        "text-align:center; margin-top:8px;'>"
        "maestrotactico.fr<br>contact@maestrotactico.fr"
        "</div>"
        "<div style='font-family:Raleway,sans-serif; font-size:11px; color:rgba(255,255,255,0.65); "
        "text-align:center; margin-top:18px; padding-bottom:8px;'>"
        "Pas de cookies, pas de traçage — juste les infos techniques basiques que l'hébergeur garde par défaut."
        "</div>",
        unsafe_allow_html=True
    )


# ============================================================
# NAVIGATION — rendue AVANT la sidebar : "Mes joueurs" n'a un effet réel que sur
# Conseiller Hebdo (seule page qui reçoit mes_joueurs_input/filtrer), donc n'a de
# sens à afficher que sur cette page — il faut connaître la page sélectionnée
# pour décider quoi mettre dans la sidebar. st.radio (pas st.tabs, qui ne renvoie
# jamais la sélection courante à Python) stylé en pastilles pour un rendu visuel
# identique à l'ancienne barre d'onglets.
# ============================================================

st.markdown(
    """
    <div class="mt-topband">
      <div class="mt-topband-wordmark">MAESTRO TACTICO</div>
    </div>
    <div class="mt-topband-line"></div>
    """,
    unsafe_allow_html=True
)

page_selectionnee = st.radio(
    "Navigation",
    ["Accueil", "Conseiller hebdo", "Mercato", "Simuler le match"],
    horizontal=True,
    key="nav_radio",
    label_visibility="collapsed"
)

# ============================================================
# SIDEBAR — MES JOUEURS (Conseiller Hebdo uniquement — seule page où ce filtre a
# un effet réel). Sur les 3 autres pages, la sidebar est masquée entièrement
# (largeur rendue aux tableaux, notamment les tableaux denses de Mercato) ; le
# logo reste visible via le bandeau haut ci-dessus, et le pied de page est
# affiché en bas du contenu principal via _afficher_pied_de_page().
# ============================================================

filtrer = False

if page_selectionnee == "Conseiller hebdo":
    with st.sidebar:
        st.markdown(LOGO_HTML, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown(
            '### Mes joueurs <span style="font-size:0.6em; opacity:0.5;">(un par ligne)</span>',
            unsafe_allow_html=True
        )

        # Initialisation session state
        if "mes_joueurs_input" not in st.session_state:
            st.session_state["mes_joueurs_input"] = ""

        mes_joueurs_input = st.text_area(
            "Joueurs (un par ligne)",
            value=st.session_state["mes_joueurs_input"],
            height=150,
            key="mes_joueurs_textarea",
            label_visibility="collapsed"
        )

        if st.button("Valider", key="btn_valider_joueurs"):
            st.session_state["mes_joueurs_input"] = st.session_state["mes_joueurs_textarea"]
            lignes = [j.strip() for j in st.session_state["mes_joueurs_input"].split('\n') if j.strip()]
            st.session_state["verification_mes_joueurs"] = _verifier_noms_joueurs(
                lignes, df, df_n1, cols_journees, cols_journees_n1, journee_actuelle
            )
        else:
            st.session_state["mes_joueurs_input"] = mes_joueurs_input

        for niveau, texte in st.session_state.get("verification_mes_joueurs", []):
            if niveau == 'success':
                st.caption(f"✓ {texte}")
            elif niveau == 'error':
                st.error(texte)
            elif niveau == 'warning':
                st.warning(texte)
            elif niveau == 'info':
                st.info(texte)

        filtrer = st.checkbox(
            "Afficher uniquement mes joueurs", value=False, key="filtrer_mes_joueurs"
        )
        st.markdown("---")
        st.markdown(
            "<div style='font-family:Raleway,sans-serif; font-size:11px; color:rgba(255,255,255,0.55); text-align:center;'>"
            "maestrotactico.fr<br>contact@maestrotactico.fr"
            "</div>"
            "<div style='font-family:Raleway,sans-serif; font-size:11px; color:rgba(255,255,255,0.65); "
            "text-align:center; margin-top:18px;'>"
            "Pas de cookies, pas de traçage — juste les infos techniques basiques que l'hébergeur garde par défaut."
            "</div>",
            unsafe_allow_html=True
        )
else:
    st.markdown(
        "<style>"
        "[data-testid='stSidebar'], [data-testid='stSidebarCollapsedControl'] "
        "{ display: none !important; }"
        "</style>",
        unsafe_allow_html=True
    )

# ============================================================
# PAGES
# ============================================================

if page_selectionnee == "Accueil":
    afficher_accueil()
    _afficher_pied_de_page()

elif page_selectionnee == "Conseiller hebdo":
    afficher_hebdo(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle, st.session_state["mes_joueurs_input"], filtrer)

elif page_selectionnee == "Mercato":
    afficher_mercato(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle, derniere_maj)
    _afficher_pied_de_page()

elif page_selectionnee == "Simuler le match":
    afficher_adversaire(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle)
    _afficher_pied_de_page()
