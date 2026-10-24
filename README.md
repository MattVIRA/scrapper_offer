# scrapper_offer

Outil personnel de veille et de suivi des offres de **VIE** (Volontariat
International en Entreprise) publiées par **Business France** sur
[mon-vie-via.businessfrance.fr](https://mon-vie-via.businessfrance.fr).

Il interroge vos recherches enregistrées, range les offres dans une base
SQLite locale, leur donne un score selon vos mots-clés, et vous permet de
les trier, de suivre vos candidatures et de générer des lettres de
motivation depuis une interface web locale. Un export Excel est régénéré à
chaque collecte.

> **Source prise en charge :** Business France (VIE) uniquement, pour
> l'instant. L'architecture prévoit d'autres sources (`src/offers/sources/`).

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
  - [Ligne de commande](#ligne-de-commande)
  - [Interface web](#interface-web)
  - [Lettres de motivation](#lettres-de-motivation)
- [Fichiers produits](#fichiers-produits)
- [Sécurité des données](#sécurité-des-données)
- [Développement](#développement)
- [Structure du projet](#structure-du-projet)

---

## Fonctionnalités

- **Collecte** des offres de une ou plusieurs recherches Business France,
  copiées telles quelles depuis la barre d'adresse du site.
- **Base locale SQLite** (`data/offers.db`) : historique des offres, date
  d'apparition, offres retirées du site marquées « Plus en ligne ».
- **Score par mots-clés** : nombre de mots-clés trouvés dans le titre, la
  description et le profil recherché ; mots d'exclusion qui ramènent le
  score à 0.
- **Interface web** (Streamlit) façon messagerie : recherche, filtres,
  fiche détaillée de l'offre, favoris, corbeille, statut de candidature,
  notes.
- **Suivi des candidatures** : statut (Intéressant, Postulé, Refusé, Pas
  pour moi), date de candidature, lettre (À rédiger, Rédigée), notes.
- **Lettres de motivation** générées par Claude Code à partir de votre CV,
  de vos anciennes lettres et de vos consignes, écrites en `.docx`.
- **Export Excel** (`output/offres_vie.xlsx`) pour consulter les offres
  hors de l'application.
- **Détection des doublons** probables (même entreprise, même titre).
- **Sauvegardes automatiques** de la base, de l'Excel et de la
  configuration avant chaque modification.

---

## Prérequis

| Outil | Version | Usage |
|---|---|---|
| macOS | — | Développé et utilisé sur Mac (bouton « Ouvrir dans le Finder ») |
| [Python](https://www.python.org/downloads/) | **3.13** ou plus | Exécution du programme |
| [Git](https://git-scm.com/) | — | Récupération du code |
| [Claude Code](https://docs.claude.com/en/docs/claude-code) | — | *Facultatif* : uniquement pour les lettres de motivation |

---

## Installation

```bash
git clone https://github.com/MattVIRA/scrapper_offer.git
```

```bash
cd scrapper_offer
```

Créer et activer un environnement virtuel :

```bash
python3.13 -m venv .venv
```

```bash
source .venv/bin/activate
```

Installer le projet (et les outils de développement) :

```bash
pip install -e ".[dev]"
```

Vérifier que tout fonctionne (les tests n'appellent aucun site) :

```bash
pytest
```

### Raccourci facultatif

Pour lancer `offers` sans activer le `.venv`, ajouter dans `~/.zshrc` :

```bash
alias offers="$HOME/Documents/CODE/scrapper_offer/.venv/bin/offers"
```

(adapter le chemin à l'emplacement du dépôt).

---

## Configuration

Tous les réglages sont dans [`config.yaml`](config.yaml), à la racine.

### 1. Ajouter vos recherches Business France

1. Faites votre recherche sur
   [mon-vie-via.businessfrance.fr/offres/recherche](https://mon-vie-via.businessfrance.fr/offres/recherche)
   avec les filtres voulus (spécialités, zones géographiques, niveau
   d'études, télétravail…).
2. Copiez l'adresse de la page.
3. Collez-la dans `config.yaml` :

```yaml
sources:
  business_france:
    enabled: true
    searches:
      - name: "Data en Europe"          # libre, affiché dans la colonne « Recherche »
        url: "https://mon-vie-via.businessfrance.fr/offres/recherche?specializationsIds=243&geographicZones=2"
      - name: "Finance Asie"
        url: "https://mon-vie-via.businessfrance.fr/offres/recherche?..."
        enabled: false                  # coupée sans être effacée
```

Une recherche peut aussi être coupée ou rallumée depuis la page
**Collecte** de l'interface.

### 2. Régler le score

```yaml
keywords_include:     # +1 point par mot-clé trouvé
  - python
  - machine learning
  - data
  - sql

keywords_exclude:     # un seul mot trouvé et le score passe à 0
  - stage
```

Majuscules et accents sont ignorés, et seuls les mots entiers comptent
(« ia » est trouvé dans « projet IA », pas dans « média »). Une offre
exclue reste dans la base et dans l'Excel.

### 3. Lettres de motivation (facultatif)

```yaml
letters:
  profile_dir: profil          # votre CV, vos anciennes lettres, vos consignes
  output_dir: lettres          # où les .docx sont écrits
  prompt: prompts/lettre.md    # prompt envoyé à Claude
  # model: sonnet              # facultatif : modèle de Claude
```

Les chemins sont relatifs à `config.yaml`. Voir
[Lettres de motivation](#lettres-de-motivation).

---

## Utilisation

### Ligne de commande

Toutes les commandes se lancent dans le `.venv` activé.

| Commande | Effet |
|---|---|
| `python -m offers collect` | Interroge Business France, met à jour la base, puis régénère l'Excel |
| `python -m offers export` | Régénère l'Excel depuis la base, sans réseau |
| `python -m offers duplicates` | Affiche les doublons probables |
| `python -m offers letters` | Écrit les lettres des offres « À rédiger », après confirmation |
| `offers ui` | Ouvre l'interface sur http://localhost:8501 |

Options communes :

| Option | Défaut | Commandes |
|---|---|---|
| `--db` | `data/offers.db` | toutes |
| `--excel` | `output/offres_vie.xlsx` | `collect`, `export`, `ui` |
| `--config` | `config.yaml` | `collect`, `letters`, `ui` |
| `--yes` | — | `letters` : pas de confirmation |
| `--replace` | — | `letters` : remplace les lettres déjà écrites |

**Premier lancement :** la base est créée par la première collecte.

```bash
python -m offers collect
```

À la fin, un bilan indique les offres trouvées, ajoutées, et celles qui ne
sont plus en ligne.

### Interface web

```bash
offers ui
```

Le navigateur s'ouvre sur http://localhost:8501. `Ctrl+C` dans le
terminal pour l'arrêter. Après une mise à jour du code, relancer la
commande.

| Page | Contenu |
|---|---|
| **Offres** | Liste des offres avec recherche, filtres (statut, pays, score minimum, date d'ajout…) et fiche détaillée : description, profil recherché, lien vers le site, statut, lettre, notes. Actions groupées : marquer comme lu, mettre à la corbeille… |
| **Favoris** | Les offres marquées d'une étoile |
| **Corbeille** | Les offres masquées, que l'on peut restaurer |
| **Lettres** | Offres dont la lettre est « À rédiger », génération des lettres, lettres déjà écrites, modification du prompt |
| **Collecte** | Lancement d'une collecte, activation des recherches, historique des lancements, export de l'Excel |

Une offre n'est jamais supprimée : la corbeille la masque seulement.

### Lettres de motivation

La génération utilise **Claude Code** (commande `claude`) avec votre
abonnement Claude. Claude ne reçoit aucun outil : il lit uniquement le
prompt et renvoie la lettre, que le programme vérifie avant d'écrire le
`.docx`.

**1. Installer Claude Code et s'y connecter** (voir la
[documentation](https://docs.claude.com/en/docs/claude-code)), puis
vérifier que la commande `claude` répond dans le terminal.

**2. Préparer le dossier `profil/`** (jamais versionné) :

```
profil/
├── cv/            # un ou plusieurs CV (.pdf, .docx, .md, .txt)
├── exemples/      # vos anciennes lettres : modèle de style et de structure
└── consignes.md   # facultatif : ton, longueur, points à mettre en avant
```

**3. Choisir les offres :** dans l'interface, passer le champ *Lettre* de
l'offre à **À rédiger**.

**4. Générer**, au choix :
- page **Lettres** → *Générer les lettres* ;
- ou `python -m offers letters`.

Les lettres sont écrites dans `lettres/` (`lettre_<entreprise>.docx`) et
l'offre passe à « Rédigée ». Une lettre existante n'est jamais écrasée,
sauf avec *Remplacer les lettres existantes* (ou `--replace`) ; l'ancienne
est alors copiée dans `lettres/backup/`.

Le prompt ([`prompts/lettre.md`](prompts/lettre.md)) est modifiable depuis
la page Lettres. Relisez toujours une lettre avant de l'envoyer.

---

## Fichiers produits

| Chemin | Contenu | Versionné |
|---|---|---|
| `data/offers.db` | Base des offres et du suivi : **la référence** | Non |
| `data/backup/` | Sauvegardes de la base (30 gardées) et de `config.yaml` | Non |
| `output/offres_vie.xlsx` | Export Excel, offres hors corbeille | Non |
| `output/backup/` | Versions précédentes de l'Excel | Non |
| `lettres/` | Lettres `.docx` générées | Non |
| `profil/` | CV, anciennes lettres, consignes | Non |

> **L'Excel est en lecture seule.** Il est entièrement régénéré depuis la
> base à chaque export : ce qui y est saisi à la main est perdu au suivant.
> Le suivi se fait dans l'interface. Si l'Excel est ouvert pendant une
> collecte, la collecte se fait quand même et seul l'export est sauté.

Colonnes de l'Excel : Réf., Titre, Entreprise, Pays, Ville, Durée,
Publiée le, Ajoutée le, En ligne, Score, Mots trouvés, Lien, Recherche,
Source, Statut, Lettre, Favori, Postulé le, Notes. Les offres apparues le
jour même ont un fond vert.

---

## Sécurité des données

- L'interface n'écoute que sur `localhost` : elle n'est pas accessible
  depuis le réseau local.
- Les données personnelles (`data/`, `output/`, `profil/`, `lettres/`)
  sont exclues de Git par `.gitignore`.
- Écritures atomiques (fichier temporaire puis remplacement) et une
  transaction par écriture dans la base.
- Sauvegarde automatique avant chaque modification.
- Si moins de 95 % des offres annoncées par le site sont lues, la collecte
  s'arrête sans rien modifier.
- La collecte ne touche jamais à votre suivi (statut, favoris, notes…).

---

## Développement

```bash
pytest
```

```bash
ruff check .
```

```bash
ruff format .
```

- Les tests n'appellent ni le réseau ni `claude`, et travaillent sur des
  bases temporaires.
- L'interface se teste avec `streamlit.testing.v1.AppTest`, sans
  navigateur.
- Toute nouvelle source doit passer le contrat de
  [`tests/sources_contract.py`](tests/sources_contract.py).
- Le schéma de la base n'évolue que par une migration ajoutée à la fin
  de `database.MIGRATIONS`.

Conventions de code et de commit : voir [`CLAUDE.md`](CLAUDE.md).

---

## Structure du projet

```
scrapper_offer/
├── config.yaml              # réglages : recherches, mots-clés, lettres
├── prompts/lettre.md        # prompt des lettres de motivation
├── src/offers/
│   ├── __main__.py          # ligne de commande
│   ├── pipeline.py          # orchestration de la collecte
│   ├── sources/             # une classe par source (business_france.py)
│   ├── storage/             # base SQLite, schéma, migrations
│   ├── scoring/             # score par mots-clés
│   ├── exports/             # export Excel
│   ├── letters/             # lecture du profil, prompt, écriture .docx
│   ├── claude_code.py       # appel à claude -p
│   ├── tracking.py          # statuts de suivi
│   ├── browsing.py          # filtres et compteurs des listes
│   ├── summary.py           # textes des bilans
│   ├── backups.py           # sauvegardes, écriture atomique
│   └── ui/                  # interface Streamlit
└── tests/                   # tests pytest, fixtures sans données réelles
```
