import streamlit as st

def afficher_accueil():

    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@700&family=Raleway:wght@400;500;600&display=swap');

.hero-wrap {
    width: 100%;
    text-align: center;
    padding: 48px 0 32px 0;
}
.hero-title {
    font-family: "Oswald", sans-serif; font-size: 16px; font-weight: 700;
    color: #ffffff; line-height: 1.1; margin: 0 0 16px 0;
}
.hero-wrap .hero-title span {
    color: #c8a84b;
    font-family: "Oswald", sans-serif !important;
    font-weight: 700 !important;
}
.hero-subtitle {
    font-family: "Raleway", sans-serif; font-size: 16px; color: #aaaaaa;
    line-height: 1.7; margin: 0 auto 12px auto; text-align: center;
}
.hero-sep {
    width: 120px; height: 1px;
    background: linear-gradient(to right, transparent, #c8a84b, transparent);
    margin: 0 auto 36px auto;
}

/* ── Cartes fonctionnalités ── */
.feat-card {
    background-color: #1e1e1e;
    border: 1px solid rgba(200, 168, 75, 0.2);
    border-radius: 14px; padding: 32px 24px; min-height: 186px;
    box-sizing: border-box;
    transition: border-color 0.2s ease;
}
.feat-card:hover {
    border-color: rgba(200, 168, 75, 0.55);
}
.feat-name {
    font-family: "Oswald", sans-serif; font-size: 15px; font-weight: 700;
    color: #c8a84b; letter-spacing: 0.5px; margin-bottom: 12px;
}
.feat-desc {
    font-family: "Raleway", sans-serif; font-size: 14px;
    color: #888888; line-height: 1.75; margin: 0;
}

/* ── Comment ça marche ── */
.how-wrap {
    max-width: 860px;
    margin: 48px auto 0 auto;
    padding: 0 8px;
}
.how-title {
    font-family: "Oswald", sans-serif; font-size: 18px; font-weight: 700;
    color: #ffffff; letter-spacing: 1px; text-align: center;
    margin-bottom: 28px; text-transform: uppercase;
}
.how-steps {
    display: flex;
    gap: 20px;
    justify-content: center;
}
.how-step {
    flex: 1;
    background-color: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    padding: 24px 20px;
    text-align: center;
}
.how-num {
    font-family: "Oswald", sans-serif; font-size: 28px; font-weight: 700;
    color: #c8a84b; line-height: 1; margin-bottom: 10px;
}
.how-text {
    font-family: "Raleway", sans-serif; font-size: 13px;
    color: #888888; line-height: 1.6;
}

/* ── Bandeau crédibilité ── */
.credibility {
    text-align: center;
    margin: 40px auto 0 auto;
    padding: 16px 24px;
    max-width: 600px;
    border-top: 1px solid #2a2a2a;
}
.credibility p {
    font-family: "Raleway", sans-serif; font-size: 13px;
    color: #555555; line-height: 1.6; margin: 0;
    font-style: italic;
}
</style>

<div class="hero-wrap">
  <div class="hero-title">Le coach que vos adversaires <span>n\'ont pas</span></div>
  <div class="hero-subtitle">Recommandations hebdo, strat\u00e9gie mercato, analyse de vos adversaires.</div>
  <div class="hero-sep"></div>
</div>
""", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
<div class="feat-card">
  <div class="feat-name">Conseiller Hebdo</div>
  <p class="feat-desc">Le bon choix pour aligner les meilleurs joueurs de la semaine.</p>
</div>
""", unsafe_allow_html=True)

    with col2:
        st.markdown("""
<div class="feat-card">
  <div class="feat-name">Conseiller Mercato</div>
  <p class="feat-desc">Le bon joueur, au bon prix.</p>
</div>
""", unsafe_allow_html=True)

    with col3:
        st.markdown("""
<div class="feat-card">
  <div class="feat-name">Simuler le match</div>
  <p class="feat-desc">Pr\u00e9parer chaque match comme un pro.</p>
</div>
""", unsafe_allow_html=True)

    st.markdown("""
<div class="how-wrap">
  <div class="how-title">Comment \u00e7a marche</div>
  <div class="how-steps">
    <div class="how-step">
      <div class="how-num">1</div>
      <div class="how-text">Renseigner ses joueurs dans le panneau gauche</div>
    </div>
    <div class="how-step">
      <div class="how-num">2</div>
      <div class="how-text">Recevoir les recommandations adapt\u00e9es \u00e0 chaque situation</div>
    </div>
    <div class="how-step">
      <div class="how-num">3</div>
      <div class="how-text">Prendre les bonnes d\u00e9cisions et gagner sa ligue</div>
    </div>
  </div>
  <div class="credibility">
    <p>Des analyses bas\u00e9es sur les donn\u00e9es r\u00e9elles de la saison, mises \u00e0 jour chaque semaine.</p>
  </div>
</div>
""", unsafe_allow_html=True)
