import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modele import nettoyer_note, determiner_journee_actuelle
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

/* Onglets de navigation principaux (Accueil / Conseiller hebdo / Mercato / Simuler le match) */
.st-key-nav_tabs .react-aria-SelectionIndicator {
    display: none !important;
}

.st-key-nav_tabs > div > [role="tablist"] {
    background-color: #1a1a1a !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 10px !important;
    padding: 6px !important;
    gap: 6px !important;
}

.st-key-nav_tabs > div > [role="tablist"] > [data-testid="stTab"] {
    position: relative !important;
    background-color: transparent !important;
    color: rgba(255, 255, 255, 0.62) !important;
    font-family: 'Oswald', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    padding: 0 24px !important;
    border-radius: 8px !important;
    border-bottom: none !important;
    transition: color 0.25s ease, background-color 0.25s ease !important;
}

.st-key-nav_tabs > div > [role="tablist"] > [data-testid="stTab"]:hover {
    color: rgba(255, 255, 255, 0.92) !important;
    background-color: #c8a84b14 !important;
}

.st-key-nav_tabs > div > [role="tablist"] > [data-testid="stTab"][aria-selected="true"] {
    color: #c8a84b !important;
    background-color: #c8a84b22 !important;
    font-weight: 700 !important;
}

.st-key-nav_tabs > div > [role="tablist"] > [data-testid="stTab"][aria-selected="true"]::after {
    content: "";
    position: absolute;
    left: 16px;
    right: 16px;
    bottom: 4px;
    height: 3px;
    border-radius: 3px;
    background-color: #c8a84b;
}

.st-key-nav_tabs > div > [role="tablist"] > [data-testid="stTab"] p {
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

with st.sidebar:
    st.markdown(LOGO_HTML, unsafe_allow_html=True)
    st.markdown("---")

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
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    df = pd.read_excel(io.BytesIO(response.content))
    return df

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
        df_raw = charger_depuis_github(GITHUB_URL)
        st.session_state["df_joueurs"] = df_raw
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

with st.sidebar:
    st.markdown("### Mes joueurs")

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
        st.rerun()
    else:
        st.session_state["mes_joueurs_input"] = mes_joueurs_input

    filtrer = st.checkbox("Afficher uniquement mes joueurs", value=False)
    st.markdown("---")
    st.markdown(
        "<div style='font-family:Raleway,sans-serif; font-size:11px; color:rgba(255,255,255,0.55); text-align:center;'>"
        "maestrotactico.fr<br>contact@maestrotactico.fr"
        "</div>",
        unsafe_allow_html=True
    )

# ============================================================
# NAVIGATION — ONGLETS
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

page0, page1, page2, page3 = st.tabs([
    "Accueil",
    "Conseiller hebdo",
    "Mercato",
    "Simuler le match"
], key="nav_tabs")

with page0:
    afficher_accueil()

with page1:
    afficher_hebdo(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle, st.session_state["mes_joueurs_input"], filtrer)

with page2:
    afficher_mercato(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle)

with page3:
    afficher_adversaire(df, cols_journees, df_n1, cols_journees_n1, journee_actuelle)
