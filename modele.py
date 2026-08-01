import unicodedata

import pandas as pd
import numpy as np

# Lettres qui ne sont PAS des combinaisons lettre+diacritique combinant au
# sens Unicode, mais des caractères à part entière : unicodedata.normalize
# ('NFKD', ...) ne les décompose donc jamais (contrairement à é, ï, ñ, ć, ń,
# ý, š... qui restent gérés par la décomposition Unicode standard plus bas,
# inchangée). Traitées manuellement, EN PLUS de cette décomposition — pas à
# sa place. Complète au besoin si d'autres lettres de ce type apparaissent
# dans de futures données (un futur cas = une ligne ici).
CORRESPONDANCE_MANUELLE_ACCENTS = {
    'ø': 'o', 'Ø': 'O',
    'ł': 'l', 'Ł': 'L',
    'đ': 'd', 'Đ': 'D',
    'ß': 'ss',
}

def normaliser_accents(texte):
    """Retire les accents pour une comparaison alphabétique/textuelle correcte
    (sans quoi 'É', 'À'... se comparent par leur code Unicode et finissent
    après 'Z', ou ne matchent pas un texte saisi sans accent). Deux étapes :
    1) CORRESPONDANCE_MANUELLE_ACCENTS pour les lettres non décomposables
       automatiquement (ø, ł, đ, ß...) ;
    2) la décomposition Unicode standard (inchangée) pour tous les autres
       accents."""
    texte = str(texte)
    for original, remplacement in CORRESPONDANCE_MANUELLE_ACCENTS.items():
        texte = texte.replace(original, remplacement)
    return ''.join(
        c for c in unicodedata.normalize('NFKD', texte)
        if not unicodedata.combining(c)
    )

def normaliser_recherche(texte):
    """Normalise un nom pour une comparaison de CORRESPONDANCE (recherche/filtre/
    désambiguïsation) tolérante aux accents ET aux séparateurs : en plus de
    normaliser_accents(), retire espaces, tirets et apostrophes (droite ' ou courbe ’,
    équivalentes) des deux côtés de la comparaison — "Saint-Maximin", "Saint Maximin" et
    "SaintMaximin" doivent être reconnus comme un seul et même nom, quel que soit le
    séparateur tapé par l'utilisateur (l'export MPGStats lui-même n'est pas toujours
    cohérent : certains noms composés utilisent un tiret, d'autres un espace, ex.
    "Zaïre-Emery" vs "Nuno Mendes"). L'apostrophe est ajoutée à titre préventif : aucun
    joueur actuel n'en a dans son nom, mais un futur "N'Diaye" ou "M'Bappé" tapé avec
    l'apostrophe droite du clavier alors que la donnée source utilise la courbe (ou
    l'inverse) ne doit pas se retrouver introuvable, même logique que
    CORRESPONDANCE_MANUELLE_ACCENTS plus haut. Volontairement DISTINCTE de
    normaliser_accents() : cette dernière sert aussi de clé de TRI alphabétique
    (utils/hebdo.py::_cle_tri) où retirer ces caractères changerait l'ordre
    d'affichage — seule la comparaison de correspondance doit les ignorer, jamais le
    tri."""
    return (
        normaliser_accents(texte).lower().strip()
        .replace('-', '').replace(' ', '').replace("'", '').replace('’', '')
    )

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

def poids_phase(matchs_joues_joueur, journee_calendaire_actuelle, plafond_calendaire=True):
    """Retourne (poids_saison_n1, poids_saison_actuelle) selon DEUX critères :
    - la position du JOUEUR dans la grille progressive, déterminée par le
      nombre de matchs qu'IL a déjà joués cette saison (et non la journée
      calendaire), pour ne pas pénaliser/avantager à tort un joueur qui a
      manqué des matchs (blessure, retard de transfert, etc.) ;
    - un plafond calendaire dur (si plafond_calendaire=True, le comportement
      par défaut, utilisé par predire_note_hybride pour la prédiction de
      forme) : au-delà de la journée 8 (journée > 8), la pondération N-1 est
      TOUJOURS nulle, quel que soit le nombre de matchs du joueur — même
      s'il s'agit littéralement de son 1er match de la saison, joué
      tardivement. plafond_calendaire=False désactive ce plafond (utile pour
      stabiliser un agrégat de saison comme la Note Mercato, où un joueur à
      1-2 matchs reste un petit échantillon à stabiliser quelle que soit la
      journée calendaire, contrairement à une prédiction de forme hebdomadaire)."""
    if plafond_calendaire and journee_calendaire_actuelle > 8:
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

def stabiliser_note_saison(row_n1, cols_n1, row_actuelle, cols_actuelle, journee_actuelle,
                            note_repli_poste=None):
    """Stabilise la colonne 'Note' de saison brute (moyenne simple sur tous les
    matchs joués, PAS la version pondérée récente de predire_note()) pour les
    petits échantillons, en la mélangeant avec la Note de saison N-1 du joueur.

    Réutilise la même grille progressive que predire_note_hybride() (poids_phase,
    basée sur le nombre de matchs déjà joués par CE joueur), mais SANS son
    plafond calendaire à J8 (plafond_calendaire=False) : ce plafond a été conçu
    pour une prédiction de forme hebdomadaire (un débutant tardif ne doit plus
    profiter de son N-1, périmé, une fois la saison bien entamée), alors qu'ici
    on stabilise un agrégat de saison pour un score de classement — un joueur
    à 1-2 matchs reste un petit échantillon à stabiliser quelle que soit la
    journée calendaire. Appliquée à la moyenne de saison brute plutôt qu'à
    predire_note() (pondération récente sur les 6 derniers matchs) :
    predire_note_hybride() ne converge jamais vers la Note brute de saison
    même une fois le joueur installé (il reste construit sur les 6 derniers
    matchs, un tout autre signal, cf. "Forme 6J" de Conseiller Hebdo), alors
    qu'ici on veut au contraire retrouver EXACTEMENT la Note de saison brute
    une fois assez de matchs joués, sans jamais introduire de biais de forme
    récente (Mercato n'utilise volontairement pas de Forme 6J).

    Fiabilité à double sens : un historique N-1 trouvé (row_n1 non None) mais
    lui-même bâti sur peu de matchs (ex. joueur qui a très peu joué la saison
    dernière aussi) n'est pas transféré tel quel — sa propre Note N-1 est
    d'abord mélangée avec note_repli_poste (médiane du poste, calculée par
    l'appelant sur les joueurs à échantillon fiable) selon la même grille
    poids_phase(), positionnée cette fois par le nombre de matchs N-1
    disponibles plutôt que par la saison en cours. Sans quoi le problème de
    petit échantillon réapparaîtrait à l'identique, simplement transféré sur
    les données N-1 au lieu des données actuelles."""
    matchs_joues = compter_matchs(row_actuelle, cols_actuelle) if row_actuelle is not None else 0
    poids_n1, poids_actuelle = poids_phase(matchs_joues, journee_actuelle, plafond_calendaire=False)

    def _note_brute(row):
        if row is None:
            return None
        note = pd.to_numeric(row.get('Note', None), errors='coerce')
        return None if pd.isna(note) else float(note)

    note_actuelle = _note_brute(row_actuelle)
    note_n1 = _note_brute(row_n1)

    if note_n1 is not None and note_repli_poste is not None:
        matchs_n1 = compter_matchs(row_n1, cols_n1) if cols_n1 else 0
        poids_repli_n1, poids_propre_n1 = poids_phase(matchs_n1, journee_actuelle, plafond_calendaire=False)
        if poids_repli_n1 > 0:
            note_n1 = poids_repli_n1 * note_repli_poste + poids_propre_n1 * note_n1

    if poids_n1 > 0 and note_n1 is None:
        poids_n1, poids_actuelle = 0.0, 1.0
    if poids_actuelle > 0 and note_actuelle is None:
        poids_n1, poids_actuelle = 1.0, 0.0

    if poids_actuelle == 1.0:
        return note_actuelle
    if poids_n1 == 1.0:
        return note_n1
    if note_actuelle is None and note_n1 is None:
        return None
    return round(poids_n1 * note_n1 + poids_actuelle * note_actuelle, 2)

def stabiliser_stats_proba_but(row_n1, cols_n1, row_actuelle, cols_actuelle, journee_actuelle,
                                moyenne_repli, ecart_type_repli):
    """Stabilise la moyenne ET l'écart-type de notes utilisés par
    simuler_proba_but() (tirage Monte Carlo de ProbaBut/ProbaArret) pour les
    petits échantillons — même principe que stabiliser_note_saison() : mélange
    les stats de la saison en cours avec celles de la saison N-1 du joueur,
    mêmes poids progressifs poids_phase() (sans plafond calendaire), même
    correspondance N-1 (trouver_historique_n1, appelée par l'appelant).

    Avec très peu de matchs joués (poids_actuelle proche de 0), le résultat
    est dominé par le repli (N-1, ou moyenne_repli/ecart_type_repli — les
    médianes du poste, calculées par l'appelant sur les joueurs à échantillon
    fiable — si aucun historique N-1 fiable n'existe) : un joueur à 1 seul
    match n'est PAS traité comme si sa note isolée était représentative avec
    juste une variance élargie autour — il est presque entièrement recentré
    sur un profil de référence crédible (N-1 ou moyenne/écart-type du poste),
    la seule façon d'éviter un ProbaBut extrême (proche de 0% ou 100%) basé
    sur un échantillon d'un seul match.

    Fiabilité à double sens : si l'historique N-1 trouvé (row_n1 non None)
    repose lui-même sur peu de matchs, moyenne_n1/ecart_type_n1 sont à leur
    tour mélangés avec moyenne_repli/ecart_type_repli selon la même grille
    poids_phase(), positionnée cette fois par le nombre de matchs N-1
    disponibles — sinon le problème de petit échantillon réapparaîtrait à
    l'identique, simplement transféré sur les données N-1."""
    matchs_joues = compter_matchs(row_actuelle, cols_actuelle) if row_actuelle is not None else 0
    poids_n1, poids_actuelle = poids_phase(matchs_joues, journee_actuelle, plafond_calendaire=False)

    notes_actuelle = [row_actuelle[col] for col in cols_actuelle if row_actuelle[col] > 0] if row_actuelle is not None else []
    moyenne_actuelle = float(np.mean(notes_actuelle)) if notes_actuelle else moyenne_repli
    ecart_type_actuelle = float(np.std(notes_actuelle)) if notes_actuelle else 0.0

    moyenne_n1, ecart_type_n1 = None, None
    matchs_n1 = 0
    if row_n1 is not None:
        notes_n1 = [row_n1[col] for col in cols_n1 if row_n1[col] > 0]
        matchs_n1 = len(notes_n1)
        if notes_n1:
            moyenne_n1 = float(np.mean(notes_n1))
            ecart_type_n1 = float(np.std(notes_n1))
    if moyenne_n1 is None:
        moyenne_n1 = moyenne_repli
    if ecart_type_n1 is None:
        ecart_type_n1 = ecart_type_repli
    if matchs_n1 > 0:
        poids_repli_n1, poids_propre_n1 = poids_phase(matchs_n1, journee_actuelle, plafond_calendaire=False)
        if poids_repli_n1 > 0:
            moyenne_n1 = poids_repli_n1 * moyenne_repli + poids_propre_n1 * moyenne_n1
            ecart_type_n1 = poids_repli_n1 * ecart_type_repli + poids_propre_n1 * ecart_type_n1

    if poids_n1 == 1.0:
        return moyenne_n1, ecart_type_n1
    if poids_actuelle == 1.0:
        return moyenne_actuelle, ecart_type_actuelle
    moyenne = poids_n1 * moyenne_n1 + poids_actuelle * moyenne_actuelle
    ecart_type = poids_n1 * ecart_type_n1 + poids_actuelle * ecart_type_actuelle
    return moyenne, ecart_type

def calculer_repli_stabilisation(df, cols_journees):
    """Précalcule, une fois pour tout le dataframe chargé, les valeurs de repli
    par poste utilisées par stabiliser_stats_proba_but() — mêmes conventions que
    utils/mercato.py::afficher_mercato (médiane de la moyenne/écart-type de notes
    jouées cette saison, calculée UNIQUEMENT sur les joueurs à échantillon fiable,
    >= 3 matchs joués, pour ne pas être elles-mêmes biaisées par les petits
    échantillons qu'elles sont censées corriger). Renvoie (moyenne_mediane_poste,
    moyenne_repli_global, ecart_type_mediane_poste, ecart_type_repli_global)."""
    def _stats_ligne(row):
        notes = [row[c] for c in cols_journees if row[c] > 0]
        return pd.Series({
            'matchs': len(notes),
            'moyenne': float(np.mean(notes)) if notes else np.nan,
            'ecart_type': float(np.std(notes)) if notes else np.nan,
            'poste': row.get('Poste', 'MO'),
        })

    stats = df.apply(_stats_ligne, axis=1)
    fiable = stats[stats['matchs'] >= 3]

    moyenne_mediane_poste = fiable.groupby('poste')['moyenne'].median().to_dict()
    ecart_type_mediane_poste = fiable.groupby('poste')['ecart_type'].median().to_dict()
    moyenne_repli_global = fiable['moyenne'].median()
    ecart_type_repli_global = fiable['ecart_type'].median()

    return (moyenne_mediane_poste, moyenne_repli_global,
            ecart_type_mediane_poste, ecart_type_repli_global)

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

def taux_regularite(notes_jouees, n_matchs=6):
    """Taux de fiabilité basé sur le "flop" : proportion des n_matchs derniers
    matchs joués (notes_jouees déjà trié du plus récent au plus ancien, comme
    cols_journees) où la note est en dessous de 5.0, quel que soit le poste
    (les médianes de note par poste sont assez proches — 4,87 à 5,34 — pour ne
    pas justifier un seuil différencié). Remplace l'ancienne variance brute
    (1/(1+écart-type)) : un joueur irrégulier au sens statistique mais qui ne
    "floppe" jamais (ex. alterne 6/10 et 8/10) n'est pas vraiment un problème
    de fiabilité, contrairement à un joueur qui multiplie les notes < 5.0."""
    six_derniers = notes_jouees[:n_matchs]
    if not six_derniers:
        return 0.0
    nb_flops = sum(1 for note in six_derniers if note < 5.0)
    return 1 - (nb_flops / len(six_derniers))

_SEUILS_TITU_REGULARITE = {"Métronome": 70, "Régulier": 50}


def etiquette_regularite(valeur, q25, q50, q75, note_saison=None, note_mediane_poste=None, titu_pct=None):
    """Classe la régularité brute (1/(1+écart-type), aveugle au niveau) en quartiles
    par poste. Un joueur ne peut accéder à "Métronome" ou "Régulier" que si sa
    Note_saison est aussi au-dessus de la médiane de son poste — sans ce plancher
    de qualité, un joueur constamment médiocre mais très peu variable (ex. toujours
    ~4/10) serait autrement classé "Métronome" à tort. En dessous du plancher, il
    est reclassé en "Irrégulier" (le calcul de la variance elle-même est inchangé).

    Second plancher, sur le %Titu cette fois : un joueur quasiment jamais titulaire
    (ex. 0% de titularisation) peut malgré tout avoir un taux de flop très bas sur
    ses rares apparitions, et se retrouver "Métronome" à tort alors qu'il n'a pas
    l'échantillon de titularisations qui justifierait cette étiquette de fiabilité.
    Métronome exige %Titu >= 70 (titulaire quasi indiscutable), Régulier exige
    %Titu >= 50 — en dessous, reclassé en "Irrégulier" quel que soit le taux de
    flop calculé."""
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

    if (
        label in _SEUILS_TITU_REGULARITE
        and titu_pct is not None
        and titu_pct < _SEUILS_TITU_REGULARITE[label]
    ):
        return "Irrégulier"

    return label

def poste_vers_ligne(poste):
    mapping = {'G': 'GB', 'DC': 'DEF', 'DL': 'DEF', 'MD': 'MIL', 'MO': 'MIL', 'A': 'ATT'}
    return mapping.get(poste, 'MIL')

def calculer_contexte_ligue(df, cols_journees):
    """Précalcule, une fois pour tout le dataframe chargé, les moyennes de ligne
    (ATT/MIL/DEF/GB), la note saison médiane par poste et la médiane de buts/match
    par poste. Contexte réutilisé par get_joueur_info() pour ProbaBut/ProbaArret
    (simuler_proba_but), pour le plancher de qualité de la régularité (même
    principe que etiquette_regularite), et comme valeur de repli de buts_par_match
    avant qu'un joueur ait disputé son premier match cette saison : évite de
    recalculer ces agrégats à chaque appel individuel."""
    moyennes_par_ligne = {'ATT': [], 'MIL': [], 'DEF': [], 'GB': []}
    notes_par_poste = {}
    buts_par_match_par_poste = {}
    for _, row in df.iterrows():
        notes = [row[c] for c in cols_journees if row[c] > 0]
        poste = row.get('Poste', 'MO')
        if notes:
            moyennes_par_ligne[poste_vers_ligne(poste)].append(np.mean(notes))
        note_saison = pd.to_numeric(row.get('Note', None), errors='coerce')
        if not pd.isna(note_saison):
            notes_par_poste.setdefault(poste, []).append(note_saison)
        matchs = len(notes)
        buts = pd.to_numeric(row.get('Buts', 0), errors='coerce')
        if matchs > 0 and not pd.isna(buts):
            buts_par_match_par_poste.setdefault(poste, []).append(buts / matchs)

    moyennes_lignes = {ligne: (np.mean(vals) if vals else 5.0) for ligne, vals in moyennes_par_ligne.items()}
    notes_mediane_poste = {poste: np.median(vals) for poste, vals in notes_par_poste.items()}
    buts_mediane_poste = {poste: np.median(vals) for poste, vals in buts_par_match_par_poste.items()}
    return moyennes_lignes, notes_mediane_poste, buts_mediane_poste

def chercher_lignes_joueur(nom_joueur, df, club=None):
    """Cherche les lignes de df dont 'Joueur' correspond à nom_joueur, en tolérant accents/casse
    ET séparateurs (normaliser_recherche, même standard que Mercato/Hebdo — "Saint-Maximin",
    "Saint Maximin" et "SaintMaximin" sont équivalents) — et, si club est fourni, restreint
    aux lignes de ce club (même tolérance), pour lever un homonyme (ex. "Diallo" correspond à
    4 joueurs réels : Metz, Nice, Strasbourg, Lens). Retourne un DataFrame de 0, 1 ou plusieurs
    lignes : ne tranche JAMAIS silencieusement un homonyme, à l'appelant de décider
    (get_joueur_info garde l'ancien comportement de compatibilité — 1ère ligne — pour tous les
    appels existants ; Simuler le match, lui, bloque tant que ce n'est pas exactement 1 ligne)."""
    noms_normalises = df['Joueur'].apply(normaliser_recherche)
    nom_norm = normaliser_recherche(nom_joueur)
    lignes = df[noms_normalises == nom_norm]
    if club is not None and len(lignes) > 0:
        club_norm = normaliser_recherche(club)
        clubs_normalises = lignes['Club'].apply(normaliser_recherche)
        lignes = lignes[clubs_normalises == club_norm]
    return lignes


def get_joueur_info(nom_joueur, df, cols_journees, df_n1=None, cols_n1=None, journee_actuelle=999,
                     moyennes_lignes=None, notes_mediane_poste=None, buts_mediane_poste=None, club=None):
    row = chercher_lignes_joueur(nom_joueur, df, club)
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
    if matchs > 0 and not pd.isna(buts_moy):
        buts_par_match = buts_moy / matchs
    else:
        # Avant le 1er match de la saison : d'abord le propre taux de but/match
        # du JOUEUR en N-1 (row_n1, même correspondance fiable que pour la note
        # hybride) — un titulaire confirmé qui marquait beaucoup en N-1 garde un
        # repli élevé même sans historique cette saison, distinct d'un remplaçant.
        # Seulement si aucun N-1 fiable (vraie recrue, homonyme ambigu) : repli
        # sur la MÉDIANE (pas la moyenne) de buts/match des joueurs du même poste
        # — la distribution est très asymétrique (la plupart des défenseurs ne
        # marquent jamais, une minorité aux coups de pied arrêtés tire la moyenne
        # vers le haut).
        buts_n1 = pd.to_numeric(row_n1.get('Buts', 0), errors='coerce') if row_n1 is not None else None
        matchs_n1 = (
            compter_matchs(row_n1, cols_n1 if cols_n1 is not None else cols_journees)
            if row_n1 is not None else 0
        )
        if row_n1 is not None and matchs_n1 > 0 and not pd.isna(buts_n1):
            buts_par_match = buts_n1 / matchs_n1
        else:
            buts_par_match = (
                buts_mediane_poste.get(poste, 0) if buts_mediane_poste is not None else 0
            )

    notes_jouees = [row[col] for col in cols_journees if row[col] > 0]
    moyenne_notes = np.mean(notes_jouees) if notes_jouees else (note_pred if note_pred is not None else 5.0)
    ecart_type_notes = np.std(notes_jouees) if notes_jouees else 0.0
    proba_but = (
        simuler_proba_but(moyenne_notes, ecart_type_notes, poste, moyennes_lignes)
        if moyennes_lignes is not None else 0.0
    )

    # Régularité : taux de fiabilité basé sur le "flop" (taux_regularite), même
    # plancher de qualité relatif au poste que etiquette_regularite() (modele.py)
    # — un joueur constamment médiocre (Note saison sous la médiane de son
    # poste) ne peut pas être considéré "régulier", quel que soit son taux de flop.
    regularite = taux_regularite(notes_jouees)
    note_saison = pd.to_numeric(row.get('Note', None), errors='coerce')
    if (
        notes_mediane_poste is not None and poste in notes_mediane_poste
        and not pd.isna(note_saison) and note_saison < notes_mediane_poste[poste]
    ):
        regularite = 0.0

    titu_pct = pd.to_numeric(row.get('%Titu', 0), errors='coerce')

    return {
        'nom': row['Joueur'],
        'poste': poste,
        'note_pred': note_pred,
        'buts': buts_par_match,
        'proba_but': proba_but,
        'regularite': regularite,
        'titu': 0.0 if pd.isna(titu_pct) else float(titu_pct),
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


def bonus_dispositif_def(nb_defenseurs):
    """Bonus MPG lié au dispositif tactique : une défense à 4 (4-4-2, 4-3-3...)
    donne +0,5 à chaque défenseur titulaire au coup d'envoi, une défense à 5
    (5-3-2, 5-4-1...) donne +1. Moins de 4 défenseurs : pas de bonus."""
    if nb_defenseurs >= 5:
        return 1.0
    if nb_defenseurs == 4:
        return 0.5
    return 0.0


def monte_carlo_match(joueurs_moi, joueurs_adv, n_simulations=2000,
                      bonus_moi=None, bonus_adv=None,
                      domicile=True, joueur_uber=None,
                      regles_remplacement=None, capitaine=None, seed=None):
    """seed : nombres aléatoires communs (variance reduction) — appeler avec la
    même graine pour la simulation de référence et chaque simulation "avec
    bonus" d'un même match garantit que les DEUX tirent exactement les mêmes
    notes/buts avant application du bonus (l'ordre des tirages ne dépend que
    des joueurs et de n_simulations, jamais du bonus lui-même, qui n'intervient
    qu'après). Toute différence observée entre les deux résultats reflète alors
    uniquement l'effet mécanique du bonus, jamais du bruit d'échantillonnage
    entre deux séries de tirages indépendantes. seed=None (par défaut) conserve
    le comportement précédent (tirages indépendants à chaque appel)."""
    rng = np.random.default_rng(seed)
    victoires = 0
    nuls = 0
    defaites = 0
    scores_moi = []
    scores_adv = []

    # Dispositif tactique : déduit du nombre de défenseurs (ligne 'DEF') dans
    # la compo TITULAIRE de départ, fixe pour tout le match (indépendant des
    # remplacements déclenchés en cours de simulation ci-dessous).
    bonus_def_moi = bonus_dispositif_def(sum(1 for j in joueurs_moi if j['ligne'] == 'DEF'))
    bonus_def_adv = bonus_dispositif_def(sum(1 for j in joueurs_adv if j['ligne'] == 'DEF'))

    # Remplacements configurés par l'utilisateur (mon équipe uniquement) :
    # {nom du titulaire -> {'seuil': ..., 'remplacant': {'nom','ligne','moyenne','ecart_type','buts'}}}
    # Clé normalisée (accents/casse/séparateurs) : le nom du titulaire vient tel que
    # saisi par l'utilisateur (regle['titulaire']), alors que j['nom'] est le nom
    # canonique du dataframe (get_joueur_info) — une différence de casse, d'accent
    # ou de séparateur entre les deux (ex. "Dembele" saisi vs "Dembélé" en base, ou
    # "Zaire Emery" vs "Zaïre-Emery") ferait sinon échouer la correspondance
    # silencieusement, sans jamais déclencher le remplacement même si la note tirée
    # passe sous le seuil.
    def _cle_nom(nom):
        return normaliser_recherche(nom)

    regles_par_titulaire = {_cle_nom(r['titulaire']): r for r in (regles_remplacement or [])}

    for _ in range(n_simulations):
        notes_moi = {}
        for j in joueurs_moi:
            note = rng.normal(j['moyenne'], j['ecart_type'])
            note = max(0, min(10, note))
            ligne, buts = j['ligne'], j['buts']
            substitue = False

            regle = regles_par_titulaire.get(_cle_nom(j['nom']))
            if regle and note < regle['seuil']:
                rempl = regle['remplacant']
                note = rng.normal(rempl['moyenne'], rempl['ecart_type'])
                note = max(0, min(10, note))
                ligne, buts = rempl['ligne'], rempl['buts']
                substitue = True

            if ligne == 'DEF':
                note = min(10, note + bonus_def_moi)

            notes_moi[j['nom']] = {'note': note, 'ligne': ligne, 'buts': buts, 'substitue': substitue}

        notes_adv = {}
        for j in joueurs_adv:
            note = rng.normal(j['moyenne'], j['ecart_type'])
            note = max(0, min(10, note))
            if j['ligne'] == 'DEF':
                note = min(10, note + bonus_def_adv)
            notes_adv[j['nom']] = {'note': note, 'ligne': j['ligne'], 'buts': j['buts']}

        if bonus_moi == 'zahia':
            # Règle confirmée : les joueurs entrants (remplacement déclenché cette
            # simulation) n'ont pas le bonus Zahia, réservé aux vrais titulaires.
            for k in notes_moi:
                if notes_moi[k]['ligne'] != 'GB' and not notes_moi[k]['substitue']:
                    notes_moi[k]['note'] = min(10, notes_moi[k]['note'] + 0.5)
        elif bonus_moi == 'suarez':
            for k in notes_adv:
                if notes_adv[k]['ligne'] == 'GB':
                    notes_adv[k]['note'] = max(0, notes_adv[k]['note'] - 1)
        elif bonus_moi == 'cheat_code':
            for k in notes_adv:
                if notes_adv[k]['ligne'] != 'GB':
                    notes_adv[k]['note'] = max(0, notes_adv[k]['note'] - 0.5)
        elif bonus_moi == 'uber_eats' and joueur_uber:
            # Règle confirmée : si le joueur désigné a été remplacé cette simulation,
            # le bonus est perdu pour cette simulation — pas transféré au remplaçant.
            nom_lower = joueur_uber.strip().lower()
            for k in notes_moi:
                if k.lower() == nom_lower and not notes_moi[k]['substitue']:
                    notes_moi[k]['note'] = min(10, notes_moi[k]['note'] + 1)

        if bonus_adv == 'zahia':
            for k in notes_adv:
                if notes_adv[k]['ligne'] != 'GB':
                    notes_adv[k]['note'] = min(10, notes_adv[k]['note'] + 0.5)
        elif bonus_adv == 'suarez':
            for k in notes_moi:
                if notes_moi[k]['ligne'] == 'GB':
                    notes_moi[k]['note'] = max(0, notes_moi[k]['note'] - 1)
        elif bonus_adv == 'cheat_code':
            for k in notes_moi:
                if notes_moi[k]['ligne'] != 'GB':
                    notes_moi[k]['note'] = max(0, notes_moi[k]['note'] - 0.5)

        # Bonus Capitaine (+0,5) : contrairement à Zahia/Uber Eats, il SUIT le
        # joueur désigné même s'il devient remplaçant en cours de simulation —
        # aucune exclusion sur le flag 'substitue' ici, volontairement.
        if capitaine and capitaine in notes_moi:
            notes_moi[capitaine]['note'] = min(10, notes_moi[capitaine]['note'] + 0.5)

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
        # Le tirage est conservé PAR JOUEUR (buts_reels_moi/adv) : le mécanisme du
        # but MPG virtuel plus bas doit exclure un joueur seulement s'IL a réellement
        # marqué dans CETTE simulation précise, pas simplement parce que son taux
        # moyen de buts/match (j['buts']) est non nul.
        buts_reels_moi = {nom: int(rng.poisson(v['buts'])) if v['buts'] > 0 else 0
                          for nom, v in notes_moi.items()}
        buts_reels_adv = {nom: int(rng.poisson(v['buts'])) if v['buts'] > 0 else 0
                          for nom, v in notes_adv.items()}
        score_moi = sum(buts_reels_moi.values())
        score_adv = sum(buts_reels_adv.values())

        if note_gb_moi >= 8:
            score_adv = max(0, score_adv - 1)
        if note_gb_adv >= 8:
            score_moi = max(0, score_moi - 1)

        for nom, j in notes_moi.items():
            if j['note'] < 5.5 or buts_reels_moi[nom] > 0:
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
            if j['note'] < 5.5 or buts_reels_adv[nom] > 0:
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
