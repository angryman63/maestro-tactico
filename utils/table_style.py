import html as _html
import streamlit as st
THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Raleway:wght@400;500;600&display=swap');

div[data-testid="stRadio"] > div {
    background-color: #1a1a1a;
    padding: 10px 14px;
    border-radius: 10px;
    border: 1px solid rgba(200, 168, 75, 0.35);
}
div[data-testid="stRadio"] label p {
    color: #ffffff !important;
}

/* ── Police par défaut : base site-wide — Raleway pour tout ce qui n'est pas
   un titre/sous-titre de section (labels de champ, texte de contenu,
   boutons, menus), Oswald réservé aux titres/sous-titres ── */
[data-testid="stWidgetLabel"] p {
    font-family: 'Raleway', sans-serif !important;
}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stMarkdownContainer"] li {
    font-family: 'Raleway', sans-serif !important;
}
[data-testid="stSelectbox"] input[role="combobox"],
[data-testid="stTextArea"] textarea,
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    font-family: 'Raleway', sans-serif !important;
}
div[data-testid="stButton"] button,
div[data-testid="stButton"] button p {
    font-family: 'Raleway', sans-serif !important;
}
/* Filet de sécurité : tout titre markdown ("### ...") passe par un wrapper
   stHeadingWithActionElements avec un span interne qui hérite sinon de la
   police par défaut de Streamlit malgré une règle posée sur le h1-h6 lui-même. */
[data-testid="stHeadingWithActionElements"] h1,
[data-testid="stHeadingWithActionElements"] h2,
[data-testid="stHeadingWithActionElements"] h3,
[data-testid="stHeadingWithActionElements"] h4,
[data-testid="stHeadingWithActionElements"] span,
[data-testid="stHeadingWithActionElements"] p {
    font-family: 'Oswald', sans-serif !important;
    font-weight: 700 !important;
}

/* ── Sélecteurs en pilules or (Mercato + Simuler le match) ── */
.st-key-mercato_taille_ligue [data-testid="stRadioGroup"],
.st-key-mercato_strategie [data-testid="stRadioGroup"],
.st-key-mode_analyse [data-testid="stRadioGroup"],
.st-key-importance [data-testid="stRadioGroup"],
.st-key-domicile [data-testid="stRadioGroup"] {
    gap: 6px;
}
.st-key-mercato_taille_ligue [data-testid="stRadioOption"],
.st-key-mercato_strategie [data-testid="stRadioOption"],
.st-key-mode_analyse [data-testid="stRadioOption"],
.st-key-importance [data-testid="stRadioOption"],
.st-key-domicile [data-testid="stRadioOption"] {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 6px 16px;
    transition: background-color 0.2s ease, border-color 0.2s ease;
}
.st-key-mercato_taille_ligue [data-testid="stRadioOption"]:hover,
.st-key-mercato_strategie [data-testid="stRadioOption"]:hover,
.st-key-mode_analyse [data-testid="stRadioOption"]:hover,
.st-key-importance [data-testid="stRadioOption"]:hover,
.st-key-domicile [data-testid="stRadioOption"]:hover {
    background-color: rgba(200, 168, 75, 0.08);
}
.st-key-mercato_taille_ligue [data-testid="stRadioOption"][data-selected="true"],
.st-key-mercato_strategie [data-testid="stRadioOption"][data-selected="true"],
.st-key-mode_analyse [data-testid="stRadioOption"][data-selected="true"],
.st-key-importance [data-testid="stRadioOption"][data-selected="true"],
.st-key-domicile [data-testid="stRadioOption"][data-selected="true"] {
    background-color: rgba(200, 168, 75, 0.18);
    border-color: #c8a84b;
}
.st-key-mercato_taille_ligue [data-testid="stRadioOption"] > div > div > div:first-child,
.st-key-mercato_strategie [data-testid="stRadioOption"] > div > div > div:first-child,
.st-key-mode_analyse [data-testid="stRadioOption"] > div > div > div:first-child,
.st-key-importance [data-testid="stRadioOption"] > div > div > div:first-child,
.st-key-domicile [data-testid="stRadioOption"] > div > div > div:first-child {
    display: none;
}
.st-key-mercato_taille_ligue [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] p,
.st-key-mercato_strategie [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] p,
.st-key-mode_analyse [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] p,
.st-key-importance [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] p,
.st-key-domicile [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] p {
    font-family: 'Oswald', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.03em;
    color: rgba(255, 255, 255, 0.75) !important;
    margin: 0 !important;
    transition: color 0.2s ease;
}
.st-key-mercato_taille_ligue [data-testid="stRadioOption"][data-selected="true"] [data-testid="stMarkdownContainer"] p,
.st-key-mercato_strategie [data-testid="stRadioOption"][data-selected="true"] [data-testid="stMarkdownContainer"] p,
.st-key-mode_analyse [data-testid="stRadioOption"][data-selected="true"] [data-testid="stMarkdownContainer"] p,
.st-key-importance [data-testid="stRadioOption"][data-selected="true"] [data-testid="stMarkdownContainer"] p,
.st-key-domicile [data-testid="stRadioOption"][data-selected="true"] [data-testid="stMarkdownContainer"] p {
    color: #c8a84b !important;
    font-weight: 700 !important;
}

/* ── Zones de texte "Simuler le match" : Titulaires / Remplaçants / Joueurs adverses ── */
.st-key-mes_titu label[data-testid="stWidgetLabel"],
.st-key-mes_rempl label[data-testid="stWidgetLabel"],
.st-key-adv_titu label[data-testid="stWidgetLabel"],
.st-key-adv_rempl label[data-testid="stWidgetLabel"],
.st-key-adv_joueurs label[data-testid="stWidgetLabel"] {
    background: none !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    padding: 0 !important;
}
.st-key-mes_titu label[data-testid="stWidgetLabel"] p,
.st-key-mes_rempl label[data-testid="stWidgetLabel"] p,
.st-key-adv_titu label[data-testid="stWidgetLabel"] p,
.st-key-adv_rempl label[data-testid="stWidgetLabel"] p,
.st-key-adv_joueurs label[data-testid="stWidgetLabel"] p {
    font-family: 'Raleway', sans-serif !important;
    color: #ffffff !important;
}
.st-key-mes_titu [data-testid="stTextAreaRootElement"],
.st-key-mes_rempl [data-testid="stTextAreaRootElement"],
.st-key-adv_titu [data-testid="stTextAreaRootElement"],
.st-key-adv_rempl [data-testid="stTextAreaRootElement"],
.st-key-adv_joueurs [data-testid="stTextAreaRootElement"] {
    background-color: #161616 !important;
    border: 1px solid rgba(200, 168, 75, 0.4) !important;
    border-radius: 8px !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.st-key-mes_titu [data-testid="stTextAreaRootElement"]:focus-within,
.st-key-mes_rempl [data-testid="stTextAreaRootElement"]:focus-within,
.st-key-adv_titu [data-testid="stTextAreaRootElement"]:focus-within,
.st-key-adv_rempl [data-testid="stTextAreaRootElement"]:focus-within,
.st-key-adv_joueurs [data-testid="stTextAreaRootElement"]:focus-within {
    border-color: #c8a84b !important;
    box-shadow: 0 0 0 2px rgba(200, 168, 75, 0.15);
}

/* ── Labels des champs à accent or (Simuler le match) : groupes en pilules ── */
.st-key-mode_analyse label[data-testid="stWidgetLabel"] p,
.st-key-domicile label[data-testid="stWidgetLabel"] p,
.st-key-importance label[data-testid="stWidgetLabel"] p {
    font-family: 'Oswald', sans-serif !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    letter-spacing: 0.04em !important;
    text-transform: none !important;
    color: #c8a84b !important;
}

/* ── Sous-titres h3 (Simuler le match) : équipes + bonus disponibles/adverse ── */
h3#mon-equipe,
h3#equipe-adverse,
h3#bonus-disponibles,
h3#bonus-adverse-estime {
    font-family: 'Oswald', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    letter-spacing: 0.04em !important;
    text-transform: none !important;
    color: #c8a84b !important;
}

/* ── Labels de champ (Simuler le match) : Titulaires / Remplaçants /
   Joueurs adverses disponibles / Capitaine — niveau "label de champ",
   clairement en dessous des sous-titres h3 (1rem) et des bandeaux dorés
   (1.35rem), aligné sur la taille par défaut des autres labels de champ
   du site (Titulaire/Remplaçant/Seuil de note/Nombre de remplacements). ── */
.st-key-mes_titu label[data-testid="stWidgetLabel"] p,
.st-key-mes_rempl label[data-testid="stWidgetLabel"] p,
.st-key-adv_titu label[data-testid="stWidgetLabel"] p,
.st-key-adv_rempl label[data-testid="stWidgetLabel"] p,
.st-key-adv_joueurs label[data-testid="stWidgetLabel"] p,
.st-key-capitaine_designe label[data-testid="stWidgetLabel"] p {
    font-size: 0.875rem !important;
}

/* ── Menu déroulant "Bonus adverse (estimé)" (Simuler le match) ── */
.st-key-bonus_adv_estime input[role="combobox"] {
    font-family: 'Raleway', sans-serif !important;
}

/* ── Textes d'aide (st.caption) : plus petits et discrets que le texte courant ── */
[data-testid="stCaptionContainer"] p {
    font-family: 'Raleway', sans-serif !important;
    font-size: 0.8rem !important;
    color: rgba(255, 255, 255, 0.55) !important;
}

/* ── Onglets de poste (Mercato + Conseiller Hebdo) : Attaquants / Milieux / ... ── */
.st-key-mercato_postes .react-aria-SelectionIndicator,
.st-key-hebdo_postes .react-aria-SelectionIndicator {
    display: none !important;
}
.st-key-mercato_postes > div > [role="tablist"],
.st-key-hebdo_postes > div > [role="tablist"] {
    background-color: #1a1a1a !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 10px !important;
    padding: 6px !important;
    gap: 6px !important;
}
.st-key-mercato_postes > div > [role="tablist"] > [data-testid="stTab"],
.st-key-hebdo_postes > div > [role="tablist"] > [data-testid="stTab"] {
    position: relative !important;
    background-color: transparent !important;
    color: rgba(255, 255, 255, 0.62) !important;
    font-family: 'Oswald', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    padding: 0 18px !important;
    border-radius: 8px !important;
    border-bottom: none !important;
    transition: color 0.25s ease, background-color 0.25s ease !important;
}
.st-key-mercato_postes > div > [role="tablist"] > [data-testid="stTab"]:hover,
.st-key-hebdo_postes > div > [role="tablist"] > [data-testid="stTab"]:hover {
    color: rgba(255, 255, 255, 0.92) !important;
    background-color: rgba(200, 168, 75, 0.08) !important;
}
.st-key-mercato_postes > div > [role="tablist"] > [data-testid="stTab"][aria-selected="true"],
.st-key-hebdo_postes > div > [role="tablist"] > [data-testid="stTab"][aria-selected="true"] {
    color: #c8a84b !important;
    background-color: rgba(200, 168, 75, 0.13) !important;
    font-weight: 700 !important;
}
.st-key-mercato_postes > div > [role="tablist"] > [data-testid="stTab"][aria-selected="true"]::after,
.st-key-hebdo_postes > div > [role="tablist"] > [data-testid="stTab"][aria-selected="true"]::after {
    content: "";
    position: absolute;
    left: 12px;
    right: 12px;
    bottom: 4px;
    height: 2px;
    border-radius: 2px;
    background-color: #c8a84b;
}
.st-key-mercato_postes > div > [role="tablist"] > [data-testid="stTab"] p,
.st-key-hebdo_postes > div > [role="tablist"] > [data-testid="stTab"] p {
    font-family: 'Oswald', sans-serif !important;
}

/* ── Sélecteur "Trier par" : texte en Raleway (valeur affichée + options du menu) ── */
[class*="st-key-tri_col_"] [data-testid="stSelectbox"] * {
    font-family: 'Raleway', sans-serif !important;
}
[role="listbox"] [role="option"] {
    font-family: 'Raleway', sans-serif !important;
}
[role="listbox"] [role="option"] [data-item-hl] {
    background-color: transparent !important;
    border-radius: 6px;
    transition: background-color 0.15s ease;
}
[role="listbox"] [role="option"]:hover [data-item-hl],
[role="listbox"] [role="option"][data-focused="true"] [data-item-hl] {
    background-color: rgba(200, 168, 75, 0.18) !important;
}
[role="listbox"] [role="option"][aria-selected="true"] [data-item-hl] {
    color: #ffffff !important;
}
[class*="st-key-tri_col_"] label[data-testid="stWidgetLabel"] p {
    font-family: 'Oswald', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: rgba(200, 168, 75, 0.75) !important;
}

/* ── Sélecteur d'ordre de tri (↓ / ↑) à côté de "Trier par" ── */
[class*="st-key-tri_ordre_"] [data-testid="stRadioGroup"] {
    gap: 4px;
}
[class*="st-key-tri_ordre_"] [data-testid="stRadioOption"] {
    background-color: transparent;
    border: 1px solid rgba(200, 168, 75, 0.25);
    border-radius: 6px;
    padding: 4px 10px;
    transition: background-color 0.2s ease, border-color 0.2s ease;
}
[class*="st-key-tri_ordre_"] [data-testid="stRadioOption"]:hover {
    background-color: rgba(200, 168, 75, 0.08);
}
[class*="st-key-tri_ordre_"] [data-testid="stRadioOption"][data-selected="true"] {
    background-color: rgba(200, 168, 75, 0.18);
    border-color: #c8a84b;
}
[class*="st-key-tri_ordre_"] [data-testid="stRadioOption"] > div > div > div:first-child {
    display: none;
}
[class*="st-key-tri_ordre_"] [data-testid="stMarkdownContainer"] p {
    color: rgba(255, 255, 255, 0.7) !important;
    font-family: 'Oswald', sans-serif !important;
    font-weight: 700 !important;
    margin: 0 !important;
    transition: color 0.2s ease;
}
[class*="st-key-tri_ordre_"] [data-testid="stRadioOption"][data-selected="true"] [data-testid="stMarkdownContainer"] p {
    color: #c8a84b !important;
}

/* ── Expander "Légende blessures" ── */
[data-testid="stExpander"] details {
    background-color: #161616 !important;
    border: 1px solid rgba(200, 168, 75, 0.25) !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary {
    border-radius: 10px;
    transition: background-color 0.2s ease;
}
[data-testid="stExpander"] summary:hover {
    background-color: rgba(200, 168, 75, 0.06) !important;
}
[data-testid="stExpander"] [data-testid="stIconMaterial"] {
    color: #c8a84b !important;
}
[data-testid="stExpander"] summary p {
    font-family: 'Oswald', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em;
    color: #c8a84b !important;
}
[data-testid="stExpander"] table {
    font-family: 'Raleway', sans-serif !important;
}
.gs-table-wrap {
    max-height: 440px;
    overflow-y: auto;
    border-radius: 10px;
    border: 1px solid rgba(200, 168, 75, 0.25);
    margin-bottom: 8px;
}
.gs-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'Raleway', sans-serif;
    font-size: 0.87em;
}
.gs-table thead th {
    position: sticky;
    top: 0;
    background-color: #0d0d0d;
    color: #c8a84b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-family: 'Oswald', sans-serif;
    font-size: 0.72em;
    font-weight: 700;
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid rgba(200, 168, 75, 0.35);
    white-space: nowrap;
}
.gs-table tbody td {
    padding: 9px 14px;
    color: #e8e8e8;
    border-bottom: 1px solid #232323;
    white-space: nowrap;
}
/* ── Réglage largeur de colonnes (Conseiller Hebdo uniquement) : moins de
   colonnes et plus étroites que Mercato (8-9 vs 12), donc sur mobile
   (viewport forcé, cf. app.py) la largeur totale du tableau tombait par
   coïncidence quasi pile sur la largeur visible (sidebar présente sur cette
   page, contrairement à Mercato) — la colonne coupée n'affichait qu'un
   filet de quelques pixels, imperceptible une fois le zoom arrière du
   navigateur appliqué, et donnait l'impression à tort que le tableau
   s'arrêtait là. Padding cellules élargi pour que la colonne coupée montre
   toujours une part substantielle d'elle-même (comme sur Mercato), signal
   visuel clair qu'il faut faire défiler horizontalement. ── */
.gs-table-hebdo thead th,
.gs-table-hebdo tbody td {
    padding-left: 20px;
    padding-right: 20px;
}

.gs-table tbody tr:nth-child(odd) { background-color: #161616; }
.gs-table tbody tr:nth-child(even) { background-color: #202020; }
.gs-table tbody tr:hover { background-color: #2a2412; }
.gs-table .gs-name { color: #ffffff; font-weight: 600; }
.gs-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-family: 'Raleway', sans-serif;
    font-size: 0.92em;
    font-weight: 600;
    white-space: nowrap;
}
.gs-pill[title] {
    cursor: help;
}
.gs-pill-bad        { background-color: #3d1f1f; color: #ff6b6b; }
.gs-pill-warn       { background-color: #3a2a12; color: #e8a33d; }
.gs-pill-good       { background-color: #1e3a24; color: #6fd18c; }
.gs-pill-good-dark  { background-color: #0d2414; color: #3da85e; }
.gs-pill-mid        { background-color: #2a2a2a; color: #c8a84b; }
.gs-pill-info       { background-color: #14262e; color: #6ec6d9; }
.gs-pill-neutral    { background-color: #262626; color: #8a8a8a; }
.gs-page-title {
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    font-size: 2.1em;
    color: #ffffff;
    letter-spacing: 0.5px;
    margin: 0 0 18px 0;
    padding-bottom: 10px;
    border-bottom: 2px solid #c8a84b;
    display: inline-block;
}
.gs-dash { color: #555555; }

/* ── Séparateur or ── */
.gs-sep {
    display: flex;
    align-items: center;
    gap: 14px;
    margin: 1rem 0 0.8rem;
}
.gs-sep-line-l {
    flex: 1;
    height: 2px;
    background: linear-gradient(to right, transparent, #c8a84b66);
}
.gs-sep-line-r {
    flex: 1;
    height: 2px;
    background: linear-gradient(to left, transparent, #c8a84b66);
}
.gs-sep-label {
    font-family: 'Oswald', sans-serif;
    font-size: 1.35rem;
    font-weight: 600;
    letter-spacing: 0.18em;
    color: #c8a84b;
    white-space: nowrap;
    text-transform: uppercase;
}
/* Priorité renforcée : le span .gs-sep-label est rendu à l'intérieur d'un
   stMarkdownContainer (via st.markdown), donc la règle globale
   [data-testid="stMarkdownContainer"] span (Raleway !important, plus
   spécifique que .gs-sep-label seul) l'emporterait sinon sur ce
   font-family Oswald. */
.gs-sep .gs-sep-label {
    font-family: 'Oswald', sans-serif !important;
}

/* ── Cards équipes ── */
.gs-equipe-card {
    background-color: #141414;
    border-radius: 6px;
    padding: 16px 20px;
    border-top: 2px solid;
    margin-bottom: 12px;
}
.gs-equipe-card.moi { border-color: #c8a84b; }
.gs-equipe-card.adv { border-color: #333333; }
.gs-equipe-title {
    font-family: 'Oswald', sans-serif;
    font-size: 0.72rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 10px;
}
.gs-equipe-title.or  { color: #c8a84b; }
.gs-equipe-title.gris { color: #555555; }

/* ── Bouton simulation ── */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #c8a84b, #8a6f2e) !important;
    color: #0d0d0d !important;
    font-family: 'Raleway', sans-serif !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 0.75rem 2.5rem !important;
    transition: opacity 0.2s !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    opacity: 0.85 !important;
}

/* ── Bouton "Valider" (sidebar) — même typographie que le bouton de simulation ── */
.st-key-btn_valider_joueurs button {
    font-family: 'Raleway', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
}

.gs-roster {
    display: flex;
    flex-direction: column;
    gap: 6px;
}
.gs-roster-row {
    display: flex;
    align-items: center;
    gap: 10px;
    background-color: #161616;
    border: 1px solid #232323;
    border-radius: 8px;
    padding: 8px 12px;
}
.gs-roster-ligne {
    color: #c8a84b;
    font-size: 0.72em;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    width: 42px;
    flex-shrink: 0;
}
.gs-roster-row .gs-roster-ligne {
    font-family: 'Oswald', sans-serif !important;
}
.gs-roster-nom {
    color: #ffffff;
    font-weight: 600;
    flex-grow: 1;
}
.gs-roster-row .gs-roster-nom {
    font-family: 'Raleway', sans-serif !important;
}
.gs-roster-note {
    color: #c8a84b;
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    min-width: 48px;
    text-align: right;
    flex-shrink: 0;
    white-space: nowrap;
}
.gs-roster-row .gs-roster-note {
    font-family: 'Oswald', sans-serif !important;
}

/* "Select all" (multiselect, ex. "Bonus disponibles") : injecté par Streamlit
   dans le menu déroulant, texte codé en dur dans le bundle JS compilé — aucun
   paramètre Python ne permet de le traduire. Contourné en masquant le texte
   d'origine (font-size:0, pas display:none, pour ne pas perturber l'ARIA) et
   en affichant le français via un pseudo-élément. Toujours la 1ère option du
   menu (":first-child" parmi les li[role="option"] frères), quel que soit le
   multiselect concerné — pas de dépendance aux classes emotion-cache
   (générées, non stables d'une version de Streamlit à l'autre). */
ul[data-testid="stSelectboxVirtualDropdown"] li[role="option"]:first-child [data-testid="stTooltipHoverTarget"] > div {
    font-size: 0 !important;
    position: relative;
}
ul[data-testid="stSelectboxVirtualDropdown"] li[role="option"]:first-child [data-testid="stTooltipHoverTarget"] > div::before {
    content: "Tout sélectionner";
    font-size: 0.875rem;
    font-family: 'Raleway', sans-serif;
}

/* "No results" (multiselect/selectbox, quand le filtre tapé ne matche aucune
   option) : même situation que "Select all" ci-dessus — texte codé en dur côté
   frontend, testid stable (stSelectboxVirtualDropdownEmpty) ciblé plutôt que
   des classes générées. */
ul[data-testid="stSelectboxVirtualDropdownEmpty"] li {
    font-size: 0 !important;
    position: relative;
}
ul[data-testid="stSelectboxVirtualDropdownEmpty"] li::before {
    content: "Aucun résultat";
    font-size: 0.875rem;
    font-family: 'Raleway', sans-serif;
    color: rgba(255, 255, 255, 0.6);
}

/* ── Bandeau titre de page (Mercato / Simuler le match) : logo/marque +
   titre + repère contextuel — même identité que le mini-logo sidebar
   (app.py::LOGO_HTML), en version horizontale compacte. ── */
.gs-page-header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
    padding: 18px 22px;
    margin-bottom: 22px;
    background-color: #1a1a1a;
    border: 1px solid rgba(200, 168, 75, 0.25);
    border-radius: 12px;
}
.gs-page-header-logo {
    flex-shrink: 0;
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 10px;
    background: linear-gradient(135deg, #c8a84b, #8a6f2e);
    color: #141414;
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    font-size: 1rem;
    letter-spacing: 0.05em;
}
.gs-page-header-text {
    flex-grow: 1;
    min-width: 180px;
}
.gs-page-header-title {
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    font-size: 1.5rem;
    color: #ffffff;
    letter-spacing: 0.02em;
    line-height: 1.25;
}
.gs-page-header-tagline {
    font-family: 'Raleway', sans-serif;
    font-size: 0.85rem;
    color: #888888;
    margin-top: 2px;
}
.gs-page-header-context {
    flex-shrink: 0;
    font-family: 'Raleway', sans-serif;
    font-weight: 600;
    font-size: 0.78rem;
    color: #c8a84b;
    background-color: rgba(200, 168, 75, 0.12);
    border: 1px solid rgba(200, 168, 75, 0.35);
    border-radius: 20px;
    padding: 6px 16px;
    white-space: nowrap;
}

/* ── Cartouches chiffres clés (Mercato) ── */
.gs-kpi-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin-bottom: 26px;
}
.gs-kpi-card {
    background-color: #161616;
    border: 1px solid #262626;
    border-radius: 10px;
    padding: 16px 18px;
    min-width: 0;
    transition: border-color 0.2s ease;
}
.gs-kpi-card:hover {
    border-color: rgba(200, 168, 75, 0.45);
}
.gs-kpi-label {
    font-family: 'Oswald', sans-serif;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #888888;
    margin-bottom: 8px;
}
.gs-kpi-value {
    font-family: 'Oswald', sans-serif;
    font-size: 1.3rem;
    font-weight: 700;
    color: #c8a84b;
    line-height: 1.25;
    overflow-wrap: anywhere;
}
.gs-kpi-sub {
    font-family: 'Raleway', sans-serif;
    font-size: 0.78rem;
    color: #666666;
    margin-top: 4px;
}

/* ── Cartouches étapes (Simuler le match) — statiques, pas de calcul ── */
.gs-step-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin-bottom: 26px;
}
.gs-step-card {
    display: flex;
    align-items: center;
    gap: 14px;
    background-color: #161616;
    border: 1px solid #262626;
    border-radius: 10px;
    padding: 16px 18px;
}
.gs-step-num {
    flex-shrink: 0;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background-color: rgba(200, 168, 75, 0.15);
    color: #c8a84b;
    font-family: 'Oswald', sans-serif;
    font-weight: 700;
    font-size: 0.95rem;
}
.gs-step-text {
    font-family: 'Raleway', sans-serif;
    font-size: 0.85rem;
    color: #cccccc;
    line-height: 1.4;
}

@media (max-width: 900px) {
    .gs-kpi-row, .gs-step-row { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 560px) {
    .gs-kpi-row, .gs-step-row { grid-template-columns: 1fr; }
}

/* ── Largeur de page plafonnée (Mercato) : la sidebar est masquée sur cette
   page (app.py), ce qui libère toute la largeur de l'écran — sans plafond,
   le bandeau/cartouches/tableau s'étalent sur grand écran au détriment de
   la lisibilité. st.container(key="mercato_page_wrap") plutôt qu'un simple
   <div> HTML : seul un vrai conteneur Streamlit englobe correctement tous
   les widgets natifs rendus à l'intérieur (radios, tableaux...), un <div>
   ouvert dans un st.markdown ne "contiendrait" pas les st.* suivants. ── */
.st-key-mercato_page_wrap {
    max-width: 1180px;
    margin: 0 auto;
}
</style>
"""
def inject_style():
    st.markdown(THEME_CSS, unsafe_allow_html=True)

def separateur(titre):
    st.markdown(f"""
    <div class="gs-sep">
        <div class="gs-sep-line-l"></div>
        <span class="gs-sep-label">{titre}</span>
        <div class="gs-sep-line-r"></div>
    </div>
    """, unsafe_allow_html=True)

def escape(val):
    return _html.escape(str(val))
def pill(text, kind='mid', title=None):
    """kind: bad | warn | good | good-dark | mid | info | neutral
    title: texte d'info-bulle optionnel (attribut HTML title, tooltip natif au survol)."""
    title_attr = f' title="{escape(title)}"' if title else ''
    return f'<span class="gs-pill gs-pill-{kind}"{title_attr}>{escape(text)}</span>'
def dash(symbol='—'):
    return f'<span class="gs-dash">{symbol}</span>'
def name_cell(val):
    return f'<span class="gs-name">{escape(val)}</span>'
def table_html(df, cell_renderer, extra_class=None):
    """Construit un tableau HTML stylé.
    cell_renderer(col, val) -> str (html à insérer dans la cellule).
    extra_class : classe CSS additionnelle sur <table>, pour un réglage propre
    à une page précise (ex. largeur de colonnes) sans affecter .gs-table
    partout où elle est réutilisée."""
    colonnes = list(df.columns)
    entetes = ''.join(f'<th>{escape(c)}</th>' for c in colonnes)
    lignes = []
    for _, row in df.iterrows():
        cellules = ''.join(f'<td>{cell_renderer(c, row[c])}</td>' for c in colonnes)
        lignes.append(f'<tr>{cellules}</tr>')
    corps = ''.join(lignes)
    classes_table = 'gs-table' + (f' {extra_class}' if extra_class else '')
    return (
        '<div class="gs-table-wrap">'
        f'<table class="{classes_table}">'
        f'<thead><tr>{entetes}</tr></thead><tbody>{corps}</tbody>'
        '</table></div>'
    )
