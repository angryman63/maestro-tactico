import streamlit as st
import pandas as pd
import numpy as np
from modele import (get_joueur_info, poste_vers_ligne,
                    monte_carlo_match, get_stats_joueur_mc, calculer_contexte_ligue)
from utils.table_style import inject_style, pill, escape, separateur

def _joueur_vers_mc(j, ligne, df, cols_journees):
    """Convertit un joueur (dict issu de get_joueur_info, avec 'nom'/'note_pred'/'buts')
    au format attendu par monte_carlo_match : moyenne/écart-type calculés sur ses
    vraies notes de la saison si suffisamment de matchs (>=3), sinon repli sur la
    note prédite (note_pred) et l'estimation de buts déjà calculée par ailleurs."""
    row = df[df['Joueur'].str.lower() == j['nom'].lower()]
    if len(row) > 0:
        row = row.iloc[0]
        notes = [row[col] for col in cols_journees if row[col] > 0]
        if len(notes) >= 3:
            buts = pd.to_numeric(row.get('Buts', 0), errors='coerce')
            matchs = len(notes)
            buts_par_match = buts / matchs if matchs > 0 and not pd.isna(buts) else 0
            return {
                'nom': j['nom'],
                'ligne': ligne,
                'moyenne': float(np.mean(notes)),
                'ecart_type': float(np.std(notes)),
                'buts': float(buts_par_match)
            }
    return {
        'nom': j['nom'],
        'ligne': ligne,
        'moyenne': j['note_pred'] or 5.0,
        'ecart_type': 1.0,
        'buts': j['buts']
    }

liste_bonus = [
    "💼 Valise à Nanard — annule 1 but adverse",
    "🪞 Miroir — retourne le bonus adverse",
    "💃 Zahia — +0,5 à tous mes joueurs",
    "🦷 Suarez — -1 au gardien adverse",
    "👊 Tonton Pat' — annule remplacements adverses",
    "💻 Cheat Code — -0.5 à tous joueurs adverses",
    "🍔 Uber Eats — +1 à un joueur choisi",
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
                     moyennes_lignes, notes_mediane_poste, buts_mediane_poste):
    joueurs_info = []
    for nom in [n.strip() for n in noms_joueurs.split('\n') if n.strip()]:
        info = get_joueur_info(
            nom, df, cols_journees, df_n1, cols_n1, journee_actuelle,
            moyennes_lignes, notes_mediane_poste, buts_mediane_poste
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
            note = f"{j['note_pred']:.2f}" if j['note_pred'] else "Données insuffisantes"
            badges = ""
            if j.get('alerte'):
                badges += pill(j['alerte'], 'bad')
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

    moyennes_lignes, notes_mediane_poste, buts_mediane_poste = calculer_contexte_ligue(df, cols_journees)

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
            for i in range(int(nb_regles_remplacement)):
                st.markdown(f"**Remplacement {i + 1}**")
                rc1, rc2, rc3 = st.columns(3)
                with rc1:
                    st.selectbox("Titulaire", noms_mes_titu, key=f"rempl_titu_{i}")
                with rc2:
                    st.number_input(
                        "Seuil de note (remplacement si en dessous)",
                        min_value=0.0, max_value=10.0, value=5.0, step=0.5,
                        key=f"rempl_seuil_{i}"
                    )
                with rc3:
                    st.selectbox("Remplaçant", noms_mes_rempl, key=f"rempl_nom_{i}")

    capitaine_designe = st.selectbox(
        "Capitaine (bonus +0,5 — suit le joueur même s'il est remplacé en cours de simulation)",
        ["Aucun"] + noms_mes_titu,
        key="capitaine_designe"
    )
    capitaine_actif = capitaine_designe if capitaine_designe != "Aucun" else None

    separateur("CONFIGURATION DES BONUS")
    col_b1, col_b2 = st.columns(2)

    with col_b1:
        st.subheader("Bonus disponibles")
        mes_bonus_dispo = st.selectbox(
            "Bonus disponibles",
            ["Aucun"] + liste_bonus,
            key="mes_bonus_dispo",
            label_visibility="collapsed"
        )
        joueur_uber = None
        conflit_capitaine_uber = False
        if "Uber Eats" in mes_bonus_dispo:
            joueur_uber_choisi = st.selectbox(
                "Joueur boosté par Uber Eats :",
                ["Aucun"] + noms_mes_titu,
                key="joueur_uber"
            )
            joueur_uber = joueur_uber_choisi if joueur_uber_choisi != "Aucun" else None
            # Règle réelle : Uber Eats et Capitaine ne peuvent pas cibler LE MÊME
            # joueur (pas d'exclusion globale entre les deux bonus). Si conflit,
            # Uber Eats est simplement ignoré pour ce joueur au moment de lancer
            # la simulation — le Capitaine, lui, continue de s'appliquer.
            conflit_capitaine_uber = bool(
                capitaine_actif and joueur_uber
                and joueur_uber.strip().lower() == capitaine_actif.strip().lower()
            )
            if conflit_capitaine_uber:
                st.error(
                    f"Uber Eats et Capitaine ne peuvent pas cibler le même joueur "
                    f"({capitaine_actif}). Choisissez un autre joueur pour Uber Eats, "
                    f"ou désignez un autre capitaine."
                )
        importance_match = st.radio(
            "Importance du match",
            ["Crucial", "Normal", "Sans enjeu"],
            horizontal=True,
            key="importance"
        )

    with col_b2:
        bonus_adv_estime = st.selectbox(
            "Bonus adverse (estimé)",
            ["Aucun"] + liste_bonus,
            key="bonus_adv_estime"
        )

    separateur("TERRAIN")

    domicile = st.radio(
        "Terrain",
        ["Domicile", "Extérieur"],
        horizontal=True,
        key="domicile",
        label_visibility="collapsed"
    ) == "Domicile"

    if st.button("Lancer la simulation", type="primary"):

        def construire_equipe_noms(noms_titu):
            titu_info = []
            non_trouves = []
            for nom in [n.strip() for n in noms_titu.split('\n') if n.strip()]:
                info = get_joueur_info(
                    nom, df, cols_journees, df_n1, cols_journees_n1, journee_actuelle,
                    moyennes_lignes, notes_mediane_poste, buts_mediane_poste
                )
                if info:
                    titu_info.append(info)
                else:
                    non_trouves.append(nom)
            return titu_info, non_trouves

        # Mon équipe
        titu_moi, non_trouves_moi = construire_equipe_noms(mes_titu)
        equipe_moi = {'GB': [], 'DEF': [], 'MIL': [], 'ATT': []}
        for j in titu_moi:
            equipe_moi[poste_vers_ligne(j['poste'])].append(j)

        # Équipe adverse
        non_trouves_adv = []
        if "précise" in mode_analyse:
            titu_adv, non_trouves_adv = construire_equipe_noms(adv_titu)
            equipe_adv = {'GB': [], 'DEF': [], 'MIL': [], 'ATT': []}
            for j in titu_adv:
                equipe_adv[poste_vers_ligne(j['poste'])].append(j)
        else:
            equipe_adv, _ = meilleure_compo(
                adv_joueurs, df, cols_journees,
                df_n1, cols_journees_n1, journee_actuelle,
                moyennes_lignes, notes_mediane_poste, buts_mediane_poste
            )

        # Alertes joueurs non trouvés
        if non_trouves_moi:
            st.warning(f"Joueurs non trouvés (mon équipe) : {', '.join(non_trouves_moi)}")
        if non_trouves_adv:
            st.warning(f"Joueurs non trouvés (adversaire) : {', '.join(non_trouves_adv)}")

        # Cas résiduel : le joueur Uber Eats vient du sélecteur (limité aux titulaires
        # saisis), mais ce titulaire précis peut malgré tout ne pas avoir été retrouvé
        # dans les données (voir l'avertissement ci-dessus) — avertissement explicite
        # plutôt qu'un bonus qui ne s'applique silencieusement à personne.
        if joueur_uber and not conflit_capitaine_uber:
            noms_trouves_moi = {j['nom'].strip().lower() for j in titu_moi}
            if joueur_uber.strip().lower() not in noms_trouves_moi:
                st.warning(
                    f"Uber Eats : « {joueur_uber} » n'a pas été retrouvé dans les données "
                    f"— le bonus ne s'appliquera à personne pour cette simulation."
                )

        # Convertir en format Monte Carlo
        def equipe_vers_mc(equipe):
            joueurs_mc = []
            for ligne, joueurs in equipe.items():
                for j in joueurs:
                    joueurs_mc.append(_joueur_vers_mc(j, ligne, df, cols_journees))
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
                moyennes_lignes, notes_mediane_poste, buts_mediane_poste
            )
            if not info_rempl:
                continue
            ligne_rempl = poste_vers_ligne(info_rempl['poste'])
            regles_remplacement_mc.append({
                'titulaire': nom_titu_regle,
                'seuil': float(seuil_regle),
                'remplacant': _joueur_vers_mc(info_rempl, ligne_rempl, df, cols_journees)
            })

        bonus_adv_key = bonus_key_map.get(bonus_adv_estime, None)

        # Simulation sans bonus (le Capitaine, structurel, reste actif même ici)
        with st.spinner("Simulation en cours (2000 scénarios)..."):
            res_sb = monte_carlo_match(
                joueurs_moi_mc, joueurs_adv_mc,
                regles_remplacement=regles_remplacement_mc,
                capitaine=capitaine_actif,
                n_simulations=2000,
                domicile=domicile
            )

        separateur("RÉSULTAT")

        col_s1, col_s2, col_s3 = st.columns([2, 1, 2])

        with col_s1:
            st.metric("Victoire", f"{res_sb['victoires']}%")
            st.metric("Nul", f"{res_sb['nuls']}%")
            st.metric("Défaite", f"{res_sb['defaites']}%")

        with col_s2:
            if res_sb['victoires'] > 50:
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

        if mes_bonus_dispo != "Aucun":
            st.markdown("**Impact du bonus sélectionné :**")

            resultats_bonus = {}
            with st.spinner("Test des bonus en cours..."):
                for bonus in [mes_bonus_dispo]:
                    bonus_key = bonus_key_map.get(bonus, None)
                    res_b = monte_carlo_match(
                        joueurs_moi_mc, joueurs_adv_mc,
                        n_simulations=2000,
                        bonus_moi=bonus_key,
                        bonus_adv=bonus_adv_key,
                        regles_remplacement=regles_remplacement_mc,
                        capitaine=capitaine_actif,
                        domicile=domicile,
                        joueur_uber=(None if conflit_capitaine_uber else joueur_uber)
                    )
                    resultats_bonus[bonus] = res_b

            # Mis en avant visuellement (st.metric, comme le résultat principal) au
            # lieu d'un simple texte noyé dans la page — c'est le chiffre que
            # l'utilisateur vient chercher dans cette section.
            res_avec_bonus = resultats_bonus[mes_bonus_dispo]
            gain_metric = round(res_avec_bonus['victoires'] - res_sb['victoires'], 1)
            col_bonus1, col_bonus2 = st.columns(2)
            with col_bonus1:
                st.metric("Victoire (sans bonus)", f"{res_sb['victoires']}%")
            with col_bonus2:
                st.metric(
                    "Victoire (avec bonus)", f"{res_avec_bonus['victoires']}%",
                    delta=f"{gain_metric:+.1f} pts"
                )

            for bonus, res in sorted(
                resultats_bonus.items(),
                key=lambda x: x[1]['victoires'],
                reverse=True
            ):
                nom_bonus = bonus.split('—')[0].strip()
                gain = round(res['victoires'] - res_sb['victoires'], 1)
                gain_str = f"+{gain}%" if gain > 0 else f"{gain}%"
                if res['victoires'] > 50:
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

            meilleur = max(resultats_bonus.items(), key=lambda x: x[1]['victoires'])
            nom_meilleur = meilleur[0].split('—')[0].strip()
            res_meilleur = meilleur[1]

            vic = res_sb['victoires']

            if vic >= 65:
                st.success(f"**Gardez vos bonus** — Largement favori ({vic}%). Économisez pour un match plus serré !")
            elif vic >= 50:
                if importance_match == "Crucial":
                    st.success(f"**Utilisez {nom_meilleur}** — Match crucial, passe à {res_meilleur['victoires']}% de victoire !")
                else:
                    st.success(f"**Gardez vos bonus** — Favori à {vic}%, bonus non indispensable !")
            elif vic >= 40:
                if round(res_meilleur['victoires'] - vic, 1) >= 6:
                    st.warning(f"**Utilisez {nom_meilleur}** — Match serré ({vic}%), le bonus fait passer à {res_meilleur['victoires']}% !")
                else:
                    st.warning(f"**Match très serré ({vic}%)** — Aucun bonus ne change significativement le résultat")
            elif vic >= 30:
                if res_meilleur['victoires'] >= 50:
                    st.warning(f"**Utilisez {nom_meilleur}** — Peut renverser la situation ({vic}% → {res_meilleur['victoires']}%) !")
                else:
                    st.error(f"**Défaite probable ({vic}%)** — Aucun bonus ne suffit. Économisez-les !")
            else:
                st.error(f"**Défaite très probable ({vic}%)** — N'utilisez aucun bonus, gardez-les pour un match gagnable !")

        else:
            vic = res_sb['victoires']
            if vic >= 65:
                st.success(f"Largement favori ({vic}%) — Pas besoin de bonus !")
            elif vic >= 50:
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
        col_eq1, col_eq2 = st.columns(2)

        with col_eq1:
            st.subheader("Mon équipe")
            st.markdown(_roster_html(equipe_moi), unsafe_allow_html=True)

        with col_eq2:
            st.subheader("Équipe adverse")
            def _rotaldo(j):
                return "Rotaldo probable" if not j['note_pred'] or j['note_pred'] < 3 else None
            st.markdown(_roster_html(equipe_adv, extra_badge_fn=_rotaldo), unsafe_allow_html=True)
