import pandas as pd
import numpy as np

def nettoyer_note(valeur):
    if pd.isna(valeur):
        return 0
    valeur = str(valeur)
    valeur = valeur.replace('*', '').replace('(', '').replace(')', '').replace('J', '').strip()
    try:
        note = float(valeur)
        if 0 <= note <= 10:
            return note
        return 0
    except:
        return 0

def calculer_clutch(row, cols_journees, seuil=7):
    notes = [row[col] for col in cols_journees if col in row.index]
    notes_jouees = [n for n in notes if n > 0]
    if len(notes_jouees) == 0:
        return 0
    return len([n for n in notes_jouees if n >= seuil]) / len(notes_jouees)

def compter_matchs(row, cols_journees):
    return sum(1 for col in cols_journees if row[col] > 0)

def determiner_journee_actuelle(df, cols_journees):
    """Déduit la journée calendaire actuelle directement des données : une
    journée pas encore jouée a sa colonne à 0 pour tous les joueurs, une
    journée déjà jouée a forcément au moins un joueur noté. Recalculée à
    chaque rafraîchissement des données (jamais codée en dur)."""
    journees_jouees = [int(col[1:]) for col in cols_journees if (df[col] > 0).any()]
    return max(journees_jouees) if journees_jouees else 0

def absences_consecutives(row, cols_journees):
    notes = [row[col] for col in cols_journees]
    count = 0
    for n in notes:
        if n == 0:
            count += 1
        else:
            break
    return count

def predire_note(row, cols_journees):
    notes = [row[col] for col in cols_journees if row[col] > 0]
    if len(notes) < 3:
        return None
    poids = [0.20, 0.19, 0.18, 0.16, 0.14, 0.13]
    notes_6 = notes[:6]
    total_poids = sum(poids[:len(notes_6)])
    return round(sum(n * poids[i] for i, n in enumerate(notes_6)) / total_poids, 2)

def alerte_blessure(row, cols_journees):
    indispo = row.get('Indispo ?', False)
    absences = absences_consecutives(row, cols_journees)
    if indispo == True:
        if absences >= 8:
            return f"🚑 Blessé ({absences} matchs)"
        elif absences >= 1:
            return f"🩹 Blessé ({absences} matchs)"
    else:
        if absences >= 8:
            return f"🏥 Retour ({absences} matchs)"
        elif absences >= 4:
            return f"🐢 Retour ({absences} matchs)"
    return ""

def poids_phase(matchs_joues_joueur, journee_calendaire_actuelle):
    """Retourne (poids_saison_n1, poids_saison_actuelle) selon DEUX critères :
    - la position du JOUEUR dans la grille progressive, déterminée par le
      nombre de matchs qu'IL a déjà joués cette saison (et non la journée
      calendaire), pour ne pas pénaliser/avantager à tort un joueur qui a
      manqué des matchs (blessure, retard de transfert, etc.) ;
    - un plafond calendaire dur : au-delà de la journée 8 (journée > 8),
      la pondération N-1 est TOUJOURS nulle, quel que soit le nombre de
      matchs du joueur — même s'il s'agit littéralement de son 1er match
      de la saison, joué tardivement."""
    if journee_calendaire_actuelle > 8:
        return (0.0, 1.0)
    grille = {
        0: (1.0, 0.0),  # aucun match joué -> comme au tout début (grille J1)
        1: (1.0, 0.0),
        2: (0.8, 0.2),
        3: (0.6, 0.4),
        4: (0.4, 0.6),
        5: (0.2, 0.8),
        6: (0.1, 0.9),
    }
    return grille.get(matchs_joues_joueur, (0.0, 1.0))  # 7+ matchs -> 0% N-1

def predire_note_hybride(row_n1, cols_n1, row_actuelle, cols_actuelle, journee_actuelle):
    """
    Version hybride de predire_note() pour la transition de début de saison.
    Réutilise predire_note() sans le modifier : un appel sur les colonnes
    saison N-1, un appel sur les colonnes saison en cours, puis blend selon
    la grille progressive — positionnée par le nombre de matchs déjà joués
    par CE joueur cette saison, plafonnée par la journée calendaire (0% N-1
    forcé au-delà de J8) — avec repondération automatique si une des deux
    sources est indisponible.

    Retourne (note, mode) où note peut être None si aucune prédiction n'est
    possible (aucune donnée exploitable nulle part, ou plafond calendaire
    atteint sans les 3 notes minimum côté saison actuelle).
    """
    matchs_joues = compter_matchs(row_actuelle, cols_actuelle) if row_actuelle is not None else 0
    poids_n1, poids_actuelle = poids_phase(matchs_joues, journee_actuelle)
    plafond_calendaire_actif = journee_actuelle > 8

    note_n1 = predire_note(row_n1, cols_n1) if row_n1 is not None else None
    note_actuelle = predire_note(row_actuelle, cols_actuelle) if row_actuelle is not None else None

    if poids_n1 > 0 and note_n1 is None and poids_actuelle > 0 and note_actuelle is None:
        return None, "aucune_prediction_possible"

    if poids_n1 > 0 and note_n1 is None:
        poids_n1, poids_actuelle = 0.0, 1.0

    # Repli automatique vers N-1 si le joueur n'a pas encore de note exploitable
    # cette saison (ex. blessure) — mais JAMAIS au-delà du plafond calendaire :
    # passé J8, on ne bascule plus vers N-1, on renvoie "aucune_prediction_possible"
    # comme le ferait predire_note() seule (cf. règle du débutant tardif).
    if poids_actuelle > 0 and note_actuelle is None and not plafond_calendaire_actif:
        poids_n1, poids_actuelle = 1.0, 0.0

    if poids_n1 == 1.0:
        return (note_n1, "100%_N-1") if note_n1 is not None else (None, "aucune_prediction_possible")
    if poids_actuelle == 1.0:
        return (note_actuelle, "100%_actuelle") if note_actuelle is not None else (None, "aucune_prediction_possible")

    note = round(poids_n1 * note_n1 + poids_actuelle * note_actuelle, 2)
    return note, f"{int(poids_n1 * 100)}%N-1/{int(poids_actuelle * 100)}%actuelle"

def get_prediction_complete(row_n1, cols_n1, row_actuelle, cols_actuelle, journee_actuelle):
    """
    Assemble predire_note_hybride() (la note pondérée) et alerte_blessure()
    (le statut blessure/retour), SANS modifier ni fusionner leur logique
    interne — les deux fonctions restent indépendantes et réutilisables
    séparément.

    Retourne (note, mode, alerte).
    """
    note, mode = predire_note_hybride(row_n1, cols_n1, row_actuelle, cols_actuelle, journee_actuelle)
    alerte = alerte_blessure(row_actuelle, cols_actuelle) if row_actuelle is not None else ""
    return note, mode, alerte

def get_bandeau_avertissement(journee_actuelle):
    """Retourne le texte du bandeau, ou None à partir de J7.
    Reste basé sur la journée calendaire globale (avertissement collectif
    sur la fiabilité en tout début de saison), indépendamment de la
    logique par-joueur ci-dessus."""
    if journee_actuelle < 7:
        return (
            "⚠️ Moins de 6 journées disputées — les recommandations sont "
            "basées sur la saison précédente et peuvent être moins précises."
        )
    return None

def trouver_historique_n1(nom_joueur, poste, df_n1):
    """Retrouve la ligne d'un joueur dans le dataframe de la saison N-1, en
    matchant sur Nom + Poste. Renvoie None si aucune correspondance ou si
    plusieurs correspondances (homonymes au même poste, ex. "Camara" ou
    "Coulibaly") : mieux vaut traiter ces cas comme "pas de N-1 fiable"
    (repli automatique de predire_note_hybride) que de risquer d'attribuer
    l'historique du mauvais joueur."""
    correspondances = df_n1[
        (df_n1['Joueur'].str.strip().str.lower() == str(nom_joueur).strip().lower()) &
        (df_n1['Poste'] == poste)
    ]
    if len(correspondances) == 1:
        return correspondances.iloc[0]
    return None

def etiquette_regularite(valeur, q25, q50, q75, note_saison=None, note_mediane_poste=None):
    """Classe la régularité brute (1/(1+écart-type), aveugle au niveau) en quartiles
    par poste. Un joueur ne peut accéder à "Métronome" ou "Régulier" que si sa
    Note_saison est aussi au-dessus de la médiane de son poste — sans ce plancher
    de qualité, un joueur constamment médiocre mais très peu variable (ex. toujours
    ~4/10) serait autrement classé "Métronome" à tort. En dessous du plancher, il
    est reclassé en "Irrégulier" (le calcul de la variance elle-même est inchangé)."""
    if valeur >= q75:
        label = "Métronome"
    elif valeur >= q50:
        label = "Régulier"
    elif valeur >= q25:
        label = "Irrégulier"
    else:
        label = "Rotaldo"

    if (
        label in ("Métronome", "Régulier")
        and note_saison is not None
        and note_mediane_poste is not None
        and note_saison < note_mediane_poste
    ):
        return "Irrégulier"
    return label

def poste_vers_ligne(poste):
    mapping = {'G': 'GB', 'DC': 'DEF', 'DL': 'DEF', 'MD': 'MIL', 'MO': 'MIL', 'A': 'ATT'}
    return mapping.get(poste, 'MIL')

def calculer_contexte_ligue(df, cols_journees):
    """Précalcule, une fois pour tout le dataframe chargé, les moyennes de ligne
    (ATT/MIL/DEF/GB) et la note saison médiane par poste. Contexte réutilisé par
    get_joueur_info() pour ProbaBut/ProbaArret (simuler_proba_but) et pour le
    plancher de qualité de la régularité (même principe que etiquette_regularite) :
    évite de recalculer ces agrégats à chaque appel individuel."""
    moyennes_par_ligne = {'ATT': [], 'MIL': [], 'DEF': [], 'GB': []}
    notes_par_poste = {}
    for _, row in df.iterrows():
        notes = [row[c] for c in cols_journees if row[c] > 0]
        poste = row.get('Poste', 'MO')
        if notes:
            moyennes_par_ligne[poste_vers_ligne(poste)].append(np.mean(notes))
        note_saison = pd.to_numeric(row.get('Note', None), errors='coerce')
        if not pd.isna(note_saison):
            notes_par_poste.setdefault(poste, []).append(note_saison)

    moyennes_lignes = {ligne: (np.mean(vals) if vals else 5.0) for ligne, vals in moyennes_par_ligne.items()}
    notes_mediane_poste = {poste: np.median(vals) for poste, vals in notes_par_poste.items()}
    return moyennes_lignes, notes_mediane_poste

def get_joueur_info(nom_joueur, df, cols_journees, df_n1=None, cols_n1=None, journee_actuelle=999,
                     moyennes_lignes=None, notes_mediane_poste=None):
    row = df[df['Joueur'].str.lower() == nom_joueur.strip().lower()]
    if len(row) == 0:
        return None
    row = row.iloc[0]
    poste = row.get('Poste', 'MO')

    row_n1 = trouver_historique_n1(row['Joueur'], poste, df_n1) if df_n1 is not None else None
    note_pred, _ = predire_note_hybride(
        row_n1, cols_n1 if cols_n1 is not None else cols_journees,
        row, cols_journees, journee_actuelle
    )

    buts_moy = pd.to_numeric(row.get('Buts', 0), errors='coerce')
    matchs = compter_matchs(row, cols_journees)
    buts_par_match = (buts_moy / matchs) if matchs > 0 and not pd.isna(buts_moy) else 0

    notes_jouees = [row[col] for col in cols_journees if row[col] > 0]
    moyenne_notes = np.mean(notes_jouees) if notes_jouees else (note_pred if note_pred is not None else 5.0)
    ecart_type_notes = np.std(notes_jouees) if notes_jouees else 0.0
    proba_but = (
        simuler_proba_but(moyenne_notes, ecart_type_notes, poste, moyennes_lignes)
        if moyennes_lignes is not None else 0.0
    )

    # Régularité : même plancher de qualité relatif au poste que etiquette_regularite()
    # (modele.py) — un joueur constamment médiocre (Note saison sous la médiane de son
    # poste) ne peut pas être considéré "régulier", quelle que soit sa faible variance.
    regularite = 1 / (1 + ecart_type_notes) if notes_jouees else 0
    note_saison = pd.to_numeric(row.get('Note', None), errors='coerce')
    if (
        notes_mediane_poste is not None and poste in notes_mediane_poste
        and not pd.isna(note_saison) and note_saison < notes_mediane_poste[poste]
    ):
        regularite = 0.0

    return {
        'nom': row['Joueur'],
        'poste': poste,
        'note_pred': note_pred,
        'buts': buts_par_match,
        'proba_but': proba_but,
        'regularite': regularite,
        'alerte': alerte_blessure(row, cols_journees)
    }

def simuler_buts_mpg(equipe_att, equipe_def, domicile=True):
    buts_mpg = []
    moy_att = np.mean([j['note_pred'] for j in equipe_def.get('ATT', []) if j['note_pred']] or [5])
    moy_mil = np.mean([j['note_pred'] for j in equipe_def.get('MIL', []) if j['note_pred']] or [5])
    moy_def = np.mean([j['note_pred'] for j in equipe_def.get('DEF', []) if j['note_pred']] or [5])
    note_gb = equipe_def['GB'][0]['note_pred'] if equipe_def.get('GB') and equipe_def['GB'][0]['note_pred'] else 5

    for ligne, joueurs in equipe_att.items():
        if ligne == 'GB':
            continue
        for j in joueurs:
            note = j['note_pred']
            if note is None or note < 5.5 or j.get('buts', 0) > 0:
                continue
            note_courante = note
            if ligne == 'ATT':
                lignes = [(moy_def, -1.0), (note_gb, -0.5)]
            elif ligne == 'MIL':
                lignes = [(moy_mil, -1.0), (moy_def, -0.5), (note_gb, -0.5)]
            elif ligne == 'DEF':
                lignes = [(moy_att, -1.0), (moy_mil, -0.5), (moy_def, -0.5), (note_gb, -0.5)]
            but = True
            for moy, malus in lignes:
                passe = note_courante >= moy if domicile else note_courante > moy
                if not passe:
                    but = False
                    break
                note_courante += malus
            if but:
                buts_mpg.append(j['nom'])
    return buts_mpg


def simuler_proba_but(moyenne, ecart_type, poste, moyennes_lignes, n_simulations=1000):
    """
    Simule par Monte Carlo la probabilité qu'un joueur marque un but MPG
    (ProbaBut, joueurs de champ) ou réalise un arrêt MPG (ProbaArret,
    gardiens : note simulée >= 8), à partir de sa moyenne/écart-type de
    notes. Reprend les mêmes règles de franchissement de lignes que
    simuler_buts_mpg()/monte_carlo_match() (seuil de départ note >= 5,
    puis lignes à franchir avec malus cumulatif), mais face aux moyennes
    de ligne DE LA LIGUE (moyennes_lignes), pour une métrique de qualité
    intrinsèque du joueur, indépendante d'un adversaire précis.
    """
    ligne = poste_vers_ligne(poste)

    if ecart_type <= 0:
        notes = np.full(n_simulations, moyenne)
    else:
        notes = np.random.normal(moyenne, ecart_type, n_simulations)
    notes = np.clip(notes, 0, 10)

    if ligne == 'GB':
        return float(np.mean(notes >= 8))

    if ligne == 'ATT':
        lignes = [(moyennes_lignes['DEF'], -1.0), (moyennes_lignes['GB'], -0.5)]
    elif ligne == 'MIL':
        lignes = [(moyennes_lignes['MIL'], -1.0), (moyennes_lignes['DEF'], -0.5),
                  (moyennes_lignes['GB'], -0.5)]
    elif ligne == 'DEF':
        lignes = [(moyennes_lignes['ATT'], -1.0), (moyennes_lignes['MIL'], -0.5),
                  (moyennes_lignes['DEF'], -0.5), (moyennes_lignes['GB'], -0.5)]
    else:
        return 0.0

    reussite = notes >= 5
    note_courante = notes.copy()
    for moy_adverse, malus in lignes:
        reussite &= (note_courante >= moy_adverse)
        note_courante = note_courante + malus

    return float(np.mean(reussite))


def monte_carlo_match(joueurs_moi, joueurs_adv, n_simulations=500,
                      bonus_moi=None, bonus_adv=None,
                      domicile=True, joueur_uber=None):
    victoires = 0
    nuls = 0
    defaites = 0
    scores_moi = []
    scores_adv = []

    for _ in range(n_simulations):
        notes_moi = {}
        for j in joueurs_moi:
            note = np.random.normal(j['moyenne'], j['ecart_type'])
            note = max(0, min(10, note))
            notes_moi[j['nom']] = {'note': note, 'ligne': j['ligne'], 'buts': j['buts']}

        notes_adv = {}
        for j in joueurs_adv:
            note = np.random.normal(j['moyenne'], j['ecart_type'])
            note = max(0, min(10, note))
            notes_adv[j['nom']] = {'note': note, 'ligne': j['ligne'], 'buts': j['buts']}

        if bonus_moi == 'zahia':
            for k in notes_moi:
                if notes_moi[k]['ligne'] != 'GB':
                    notes_moi[k]['note'] = min(10, notes_moi[k]['note'] + 1)
        elif bonus_moi == 'suarez':
            for k in notes_adv:
                if notes_adv[k]['ligne'] == 'GB':
                    notes_adv[k]['note'] = max(0, notes_adv[k]['note'] - 1)
        elif bonus_moi == 'cheat_code':
            for k in notes_adv:
                if notes_adv[k]['ligne'] != 'GB':
                    notes_adv[k]['note'] = max(0, notes_adv[k]['note'] - 0.5)
        elif bonus_moi == 'uber_eats' and joueur_uber:
            nom_lower = joueur_uber.strip().lower()
            for k in notes_moi:
                if k.lower() == nom_lower:
                    notes_moi[k]['note'] = min(10, notes_moi[k]['note'] + 1)
        elif bonus_moi == 'chapron':
            meilleur_nom = None
            meilleur_note = -1
            for k, v in notes_moi.items():
                if v['ligne'] != 'GB' and v['note'] > meilleur_note:
                    meilleur_note = v['note']
                    meilleur_nom = k
            if meilleur_nom:
                notes_adv[meilleur_nom]['note'] = 2.5

        if bonus_adv == 'zahia':
            for k in notes_adv:
                if notes_adv[k]['ligne'] != 'GB':
                    notes_adv[k]['note'] = min(10, notes_adv[k]['note'] + 1)
        elif bonus_adv == 'suarez':
            for k in notes_moi:
                if notes_moi[k]['ligne'] == 'GB':
                    notes_moi[k]['note'] = max(0, notes_moi[k]['note'] - 1)
        elif bonus_adv == 'cheat_code':
            for k in notes_moi:
                if notes_moi[k]['ligne'] != 'GB':
                    notes_moi[k]['note'] = max(0, notes_moi[k]['note'] - 0.5)
        elif bonus_adv == 'chapron':
            meilleur_nom = None
            meilleur_note = -1
            for k, v in notes_adv.items():
                if v['ligne'] != 'GB' and v['note'] > meilleur_note:
                    meilleur_note = v['note']
                    meilleur_nom = k
            if meilleur_nom:
                notes_moi[meilleur_nom]['note'] = 2.5

        def moy_ligne(notes, ligne):
            vals = [v['note'] for v in notes.values() if v['ligne'] == ligne]
            return np.mean(vals) if vals else 5.0

        moy_def_adv = moy_ligne(notes_adv, 'DEF')
        moy_mil_adv = moy_ligne(notes_adv, 'MIL')
        moy_att_adv = moy_ligne(notes_adv, 'ATT')
        note_gb_adv = next((v['note'] for v in notes_adv.values() if v['ligne'] == 'GB'), 5.0)

        moy_def_moi = moy_ligne(notes_moi, 'DEF')
        moy_mil_moi = moy_ligne(notes_moi, 'MIL')
        moy_att_moi = moy_ligne(notes_moi, 'ATT')
        note_gb_moi = next((v['note'] for v in notes_moi.values() if v['ligne'] == 'GB'), 5.0)

        # Buts réels : loi de Poisson (0, 1, 2+ buts possibles), pas un tirage
        # plafonné à 0/1 qui devenait une certitude dès que buts_par_match > 1.
        # Plusieurs buts réels comptent bien plusieurs fois dans le score (règle MPG).
        score_moi = sum(int(np.random.poisson(v['buts'])) for v in notes_moi.values() if v['buts'] > 0)
        score_adv = sum(int(np.random.poisson(v['buts'])) for v in notes_adv.values() if v['buts'] > 0)

        if note_gb_moi >= 8:
            score_adv = max(0, score_adv - 1)
        if note_gb_adv >= 8:
            score_moi = max(0, score_moi - 1)

        for nom, j in notes_moi.items():
            if j['note'] < 5.5 or j['buts'] > 0:
                continue
            note_c = j['note']
            if j['ligne'] == 'ATT':
                lignes = [(moy_def_adv, -1.0), (note_gb_adv, -0.5)]
            elif j['ligne'] == 'MIL':
                lignes = [(moy_mil_adv, -1.0), (moy_def_adv, -0.5), (note_gb_adv, -0.5)]
            elif j['ligne'] == 'DEF':
                lignes = [(moy_att_adv, -1.0), (moy_mil_adv, -0.5),
                          (moy_def_adv, -0.5), (note_gb_adv, -0.5)]
            else:
                continue
            but = True
            for moy, malus in lignes:
                passe = note_c >= moy if domicile else note_c > moy
                if not passe:
                    but = False
                    break
                note_c += malus
            if but:
                score_moi += 1

        for nom, j in notes_adv.items():
            if j['note'] < 5.5 or j['buts'] > 0:
                continue
            note_c = j['note']
            if j['ligne'] == 'ATT':
                lignes = [(moy_def_moi, -1.0), (note_gb_moi, -0.5)]
            elif j['ligne'] == 'MIL':
                lignes = [(moy_mil_moi, -1.0), (moy_def_moi, -0.5), (note_gb_moi, -0.5)]
            elif j['ligne'] == 'DEF':
                lignes = [(moy_att_moi, -1.0), (moy_mil_moi, -0.5),
                          (moy_def_moi, -0.5), (note_gb_moi, -0.5)]
            else:
                continue
            but = True
            for moy, malus in lignes:
                passe = note_c >= moy if not domicile else note_c > moy
                if not passe:
                    but = False
                    break
                note_c += malus
            if but:
                score_adv += 1

        if bonus_moi == 'valise':
            score_adv = max(0, score_adv - 1)
        if bonus_adv == 'valise':
            score_moi = max(0, score_moi - 1)

        scores_moi.append(score_moi)
        scores_adv.append(score_adv)

        if score_moi > score_adv:
            victoires += 1
        elif score_moi < score_adv:
            defaites += 1
        else:
            nuls += 1

    return {
        'victoires': round(victoires / n_simulations * 100, 1),
        'nuls': round(nuls / n_simulations * 100, 1),
        'defaites': round(defaites / n_simulations * 100, 1),
        'score_moy_moi': round(np.mean(scores_moi), 1),
        'score_moy_adv': round(np.mean(scores_adv), 1),
    }


def get_stats_joueur_mc(info_joueur, cols_journees, df):
    nom = info_joueur['nom']
    row = df[df['Joueur'].str.lower() == nom.lower()]
    if len(row) == 0:
        return None
    row = row.iloc[0]
    notes = [row[col] for col in cols_journees if row[col] > 0]
    if len(notes) < 3:
        return None
    buts = pd.to_numeric(row.get('Buts', 0), errors='coerce')
    matchs = len(notes)
    buts_par_match = buts / matchs if matchs > 0 and not pd.isna(buts) else 0
    return {
        'nom': nom,
        'ligne': poste_vers_ligne(info_joueur['poste']),
        'moyenne': np.mean(notes),
        'ecart_type': np.std(notes),
        'buts': buts_par_match
    }
