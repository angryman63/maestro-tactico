import pandas as pd

CLE_FUSION = ['Joueur', 'Poste', 'Club']

# ---------------------------------------------------------------------------
# Corrections de noms (accents/caractères mal transcrits par l'export
# MPGStats) : appliquées automatiquement à chaque fusion hebdomadaire — PAS
# une modification manuelle des fichiers sources, qui serait à refaire à
# chaque nouvel export. Structure volontairement simple (un dict
# nom_source -> nom_corrigé) pour qu'ajouter un futur cas soit trivial : une
# seule ligne à ajouter ci-dessous, aucune autre modification de code requise.
# Un nom absent de ce dict n'est jamais modifié (no-op).
CORRECTIONS_NOMS = {
    # Défensif : les exports actuellement disponibles fournissent déjà
    # "João Neves" avec l'accent, mais un export MPGStats pourrait un jour
    # (re)transcrire ce nom sans accent — corrigé automatiquement si le cas
    # se présente, sans nécessiter de nouvelle intervention.
    "Joao Neves": "João Neves",
    # Vérifiées via Wikipédia :
    "Hrádecky": "Hrádecký",      # Lukáš Hrádecký (Monaco)
    "Sulc": "Šulc",              # Pavel Šulc (Lyon)
    "Bulatovic": "Bulatović",    # Bulatović (Lens)
    "Radakovic": "Radaković",    # Radaković (Nantes)
    "Szymanski": "Szymański",    # Szymański (Rennes)
}


def _corriger_noms(df):
    """Applique CORRECTIONS_NOMS à la colonne 'Joueur' — remplace UNIQUEMENT
    les noms présents dans le dict, aucun effet sur les autres (source déjà
    correcte ou joueur non concerné)."""
    df['Joueur'] = df['Joueur'].replace(CORRECTIONS_NOMS)
    return df


def _colonnes_specifiques(df, taille):
    """Colonnes propres à une taille de ligue, ex: 'Enchere moy/L6', '% achat T1/L6'..."""
    suffixe = f"/L{taille}"
    return [c for c in df.columns if str(c).endswith(suffixe)]


def _verifier_cle_unique(df, nom_fichier):
    doublons = df[df.duplicated(subset=CLE_FUSION, keep=False)]
    if not doublons.empty:
        exemples = doublons[CLE_FUSION].drop_duplicates().head(5).values.tolist()
        raise ValueError(
            f"Le fichier « {nom_fichier} » contient des doublons sur Joueur+Poste+Club "
            f"(ex: {exemples}). Impossible de fusionner sans risquer une erreur d'attribution."
        )


def fusionner_fichiers_joueurs(fichier_6, fichier_8, fichier_10):
    """
    Fusionne les 3 exports MPGStats (ligues à 6, 8 et 10 joueurs) en un seul DataFrame.

    Chaque fichier est censé contenir déjà toutes les colonnes communes (Cote, Note,
    Club, D1-D34, etc.) ainsi que ses colonnes d'enchères spécifiques (suffixe /L6, /L8, /L10).
    Le fichier '6 joueurs' sert de base ; on ne récupère des fichiers 8 et 10 que
    leurs colonnes spécifiques, rattachées via la clé Joueur + Poste + Club.
    """
    df6 = pd.read_excel(fichier_6)
    df8 = pd.read_excel(fichier_8)
    df10 = pd.read_excel(fichier_10)

    for df, nom in [(df6, "6 joueurs"), (df8, "8 joueurs"), (df10, "10 joueurs")]:
        manquantes = [c for c in CLE_FUSION if c not in df.columns]
        if manquantes:
            raise ValueError(
                f"Le fichier « {nom} » ne contient pas les colonnes attendues : {manquantes}. "
                f"Vérifie qu'il s'agit bien d'un export MPGStats standard."
            )
        # Avant la vérification de clé unique et la fusion : si un export
        # orthographie un nom différemment d'un fichier à l'autre (ex. "Joao
        # Neves" dans l'un, "João Neves" dans un autre), la correction aligne
        # les 3 fichiers AVANT la jointure sur Joueur+Poste+Club — sans quoi
        # la fusion échouerait à rattacher les colonnes d'enchères de ce
        # joueur (clé différente = pas de correspondance).
        _corriger_noms(df)
        _verifier_cle_unique(df, nom)

    cols_8 = _colonnes_specifiques(df8, 8)
    cols_10 = _colonnes_specifiques(df10, 10)

    df = df6.merge(df8[CLE_FUSION + cols_8], on=CLE_FUSION, how='left')
    df = df.merge(df10[CLE_FUSION + cols_10], on=CLE_FUSION, how='left')

    return df
