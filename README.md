# ⚽ Gazon Stats — Conseiller MPG

Application web d'aide aux managers MPG (Mon Petit Gazon).
URL : https://gazon-stats.streamlit.app/

---

## 🎯 Objectif

Aider les managers MPG à :
1. Choisir leur composition hebdomadaire
2. Optimiser leur mercato
3. Analyser leur prochain adversaire
4. Simuler le score de leur match

Modèle économique : 5€/mois — lancement août 2026 sur Ligue 1

---

## 📊 Modèle prédictif — Résultats validés

### Backtesting sur 5 championnats 2025-2026

| Championnat | Prédictions | Erreur 6J | Erreur moyenne |
|---|---|---|---|
| Ligue 1 | 6 325 | 0.830 | 0.795 |
| Ligue 2 | 6 292 | 0.756 | 0.718 |
| Liga | 8 652 | 0.773 | 0.735 |
| Premier League | 8 439 | 0.776 | 0.755 |
| Serie A | 8 536 | 0.744 | 0.709 |
| Total | ~38 000 | | |

### Formule score hebdomadaire

Score = Note_saison x 0.5 + Moyenne_6J x 0.3 + Régularité x 0.1 + %Titu x 0.1

### Poids modèle 6J

Poids = [0.30, 0.23, 0.18, 0.14, 0.10, 0.05]

### Régularité — Quartiles par poste
- 1 ✅ Valeur sûre
- 2 👌 Fiable
- 3 ⚠️ Capricieux
- 4 🐐 Rotaldo

### Validation simulation match MPG
- 58% de bon vainqueur prédit sur 112 matchs (J7-J34)
- Hasard = 33% — gain de +25 points
- Match nul prédit correctement à 60.8%

---

## 🏗️ Architecture technique

| Outil | Rôle |
|---|---|
| Google Colab | Développement et tests Python |
| GitHub angryman63/gazon-stats | Stockage du code |
| Streamlit Cloud | Déploiement application web |
| MPGStats.fr | Source des données joueurs (.xlsx) |

---

## 📱 Application Streamlit — Fonctionnalités

### Page 1 — Conseiller hebdo
- Upload fichier MPGStats (.xlsx)
- Onglets par poste : ATT / MO / MD / DC / DL / G
- Colonnes : Joueur / Club / Note saison / Forme 6J / Régularité / % Titulaire
- Filtre "Mes joueurs" avec onglet dédié ⭐
- Tri par colonne

### Page 2 — Mercato
- 4 stratégies : ⭐⭐ Stars / ⭐ Valeurs sûres / ⚖️ Équilibre / 🌱 Pépites
- Section ⚠️ À éviter
- Clutch par poste — % matchs avec note >= 7
- Alertes blessures : 🚑 🩹 🏥 🐢

---

## 🛒 Modèle Mercato

### 4 stratégies avec filtres

| Stratégie | Cote | Note min | %Titu min |
|---|---|---|---|
| ⭐⭐ Stars | >= 25M€ | >= 5.5 | >= 60% |
| ⭐ Valeurs sûres | 12-25M€ | >= 5.2 | >= 60% |
| ⚖️ Équilibre | 8-25M€ | >= 5.0 | >= 60% |
| 🌱 Pépites | < 12M€ | >= 5.0 | >= 50% |

Exception DC Stars : Cote >= 20M€, Note >= 5.3

### À éviter
- Cote >= 20M€ ET Note < 5.2
- Cote >= 15M€ ET Note < 5.0
- Cote >= 15M€ ET matchs joués < 40% des journées

### Score mercato

Clutch = % matchs avec note >= 7 — seuil MPG officiel 5.5

Poids Clutch par poste : G=35%, A=30%, MO=20%, DL=15%, MD=10%, DC=10%

Score Stars = Note x 0.40 + Clutch x cp + Variation x 0.15 + Titu x 0.10 + Pop x 0.05

Score Valeurs = Note x 0.35 + Clutch x (cp x 0.8) + Variation x 0.20 + Ratio x 0.15 + Titu x 0.10

Score Equilibre = Note x 0.30 + Ratio x 0.25 + Clutch x (cp x 0.7) + Variation x 0.15 + Titu x 0.10

Score Pepites = Ratio x 0.40 + Note x 0.25 + Clutch x (cp x 0.5) + Variation x 0.15 + Titu x 0.10

### Alertes blessures

| Emoji | Signification |
|---|---|
| 🚑 | Blessé longue durée — Indispo TRUE, 8+ matchs manqués |
| 🩹 | Blessé court — Indispo TRUE, 1-7 matchs manqués |
| 🏥 | Retour longue blessure — Indispo FALSE, 8+ absences récentes |
| 🐢 | Retour courte blessure — Indispo FALSE, 4-7 absences récentes |

---

## ⚽ Simulation Match MPG

### Règles implémentées
- Seuil but MPG : note >= 5.5 (règle officielle MPG)
- Joueur avec but réel non éligible but MPG
- Arrêt MPG gardien : note >= 8 annule 1 but réel adverse
- 3 Rotaldos = 1 CSC adverse
- Avantage domicile : égalité de notes donne le but MPG à l'équipe à domicile

### Lignes à franchir

ATT : DEF adverse (-1.0) puis GB adverse (-0.5)

MIL : MIL adverse (-1.0) puis DEF adverse (-0.5) puis GB adverse (-0.5)

DEF : ATT adverse (-1.0) puis MIL adverse (-0.5) puis DEF adverse (-0.5) puis GB adverse (-0.5)

### Remplacements
- Remplacement tactique : si note < seuil défini le remplaçant entre
- Remplacement automatique : si titulaire absent le meilleur remplaçant disponible entre
- Pool global : si pas de remplaçant au poste on pioche dans tous les remplaçants
- Rotaldo si aucun remplaçant disponible — note 2.5

---

## 🔄 Mise à jour du fichier joueurs (saison 26-27)

**Avant que les 3 exports par taille de ligue (6/8/10 joueurs) ne soient disponibles**,
`joueurs_fusionne.xlsx` est produit à partir d'un unique export MPGStats via :

```
python scripts/charger_fichier_unique.py <export_MPGStats.xlsx>
```

Ce script renomme les colonnes de journée (`D-N` -> `DN`), corrige les noms mal
transcrits, ET détecte/corrige automatiquement le recyclage de la saison N-1
observé sur l'export pré-saison MPGStats (D1-D34/Note/Buts/%Titu/Variation
remplis avec les valeurs 25-26 au lieu de vrais zéros) — en comparant chaque
chargement au fichier N-1 figé (`data/n1/joueurs_fusionne_25-26.xlsx`). Si les
valeurs ne ressemblent plus à un recyclage (vraie saison 26-27 commencée), le
script n'écrase rien et prévient au lieu de corriger à l'aveugle. Relance-le à
chaque nouveau fichier reçu de MPGStats tant que ce cas de figure dure.

**Une fois les 3 exports par taille disponibles** (vraies enchères), bascule
sur `python scripts/fusionner_joueurs.py` (déclenché aussi automatiquement par
le workflow GitHub Actions `.github/workflows/fusion-joueurs.yml` dès qu'un
push touche les 3 fichiers `L1joueurs26-27_{6,8,10}joueurs.xlsx`) — ne
réutilise plus `charger_fichier_unique.py` à ce stade.

---

## 📋 Données

### Fichiers MPGStats nécessaires
- Joueurs 25-26.xlsx — Ligue 1
- Joueurs L2 25-26.xlsx — Ligue 2
- Joueurs liga 25-26.xlsx — Liga
- Joueurs PL 25-26.xlsx — Premier League
- Joueurs serie A 25-26.xlsx — Serie A

### Colonnes utilisées
Joueur, Poste, Club, Cote, Note, Variation, Buts, %Titu, Indispo ?, D1 à D34

---

## ✅ Fait / ❌ À faire

### Fait
- Modèle prédictif validé sur 38 000 prédictions
- App Streamlit déployée
- Page conseiller hebdomadaire
- Page mercato avec 4 stratégies
- Alertes blessures
- Simulation match MPG notes réelles
- Simulation match MPG notes prédites
- Validation 58% bon vainqueur sur mini championnat 8 équipes

### À faire
- Intégrer simulation dans Streamlit page Analyser mon adversaire
- Détection Rotaldos probables chez l adversaire
- Enchères médianes disponibles en août
- Système premium/gratuit
- Gestion des bonus MPG fonctionnalité premium
- Légende des emojis dans l app
- Support multi-championnats L2, PL, Liga, Serie A
- Attendre réponse MPG sur API mail envoyé à hello@mpg.football
- Tester sur données saison 2026-2027 en août

---

## 💰 Stratégie commerciale
- Prix : 5€/mois dès le lancement
- Lancement : août 2026 — Ligue 1 uniquement
- Extensions progressives présentées comme nouveautés
- Cible : 3 000 abonnés = 15 000€/mois
- Marché : 1.8 million joueurs actifs MPG

---

## 📬 Contacts
- MPG API : mail envoyé à hello@mpg.football en juin 2026
- GitHub : github.com/angryman63/gazon-stats
- App : gazon-stats.streamlit.app
