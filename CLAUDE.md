# scrapper_offer

Récupère des offres d'emploi (pour l'instant les VIE de Business France),
les range dans une base SQLite (`data/offers.db`) et les exporte dans un
fichier Excel (`output/offres_vie.xlsx`).
Application personnelle, en cours de refonte : la feuille de route est
dans `.claude/LOTS.md`, les tickets dans `.claude/TICKETS/LOT_<n>/T<n>.<m>.md`.

Code dans `src/offers/` : `sources/` (une classe par source, contrat
dans `sources/base.py`), `storage/` (`database.py`, seul module qui parle
à SQLite, `schema.sql`, `migrations/`), `scoring/`, `exports/`,
`tracking.py` (statuts de suivi), `browsing.py` (filtres, compteurs,
pastilles des listes, sans Streamlit), `pipeline.py` (orchestrateur),
`summary.py` (textes du bilan de collecte), `backups.py`,
`__main__.py` (ligne de commande) et `ui/`, l'interface Streamlit :
- `app.py` : point d'entrée, navigation, erreurs du projet affichées ;
- `app_pages/` : une page par script (Offres, Favoris, Corbeille,
  Collecte), qui ne fait qu'appeler les modules ci-dessous ;
- `offer_table.py` : liste commune aux pages Offres, Favoris et
  Corbeille (`PageSettings`) ; `offer_card.py` : fiche d'une offre ;
- `collect_job.py` : collecte dans un fil de fond ; `session.py` :
  chemins et ouverture de la base ; `labels.py` : choix de statut et de
  lettre.

## Commandes

```bash
pip install -e ".[dev]"         # installer, dans le .venv
python -m offers collect        # interroge les sites, met à jour la base puis régénère l'Excel
python -m offers export         # régénère l'Excel à partir de la base, sans réseau
python -m offers duplicates     # affiche les doublons probables
offers ui                       # ouvre l'interface sur http://localhost:8501 (Ctrl+C pour l'arrêter)
pytest                          # tests, sans réseau
ruff check .                    # vérifier le code
ruff format .                   # mettre en forme (ruff format --check . pour vérifier)
```

Options : `--db` (défaut `data/offers.db`) et `--excel` (défaut
`output/offres_vie.xlsx`) ; `collect` et `ui` prennent aussi `--config`.
`ui` passe les trois chemins à l'interface, qui peut lancer une collecte
(page Collecte, dans un fil de fond) et exporter l'Excel.

`offers ui` (ou `python -m offers ui`) marche dans le `.venv` activé.
Pour la lancer sans l'activer, alias facultatif dans `~/.zshrc` :
`alias offers="$HOME/Documents/CODE/scrapper_offer/.venv/bin/offers"`.
L'interface n'écoute que sur `localhost` (option passée par `offers ui`
et `.streamlit/config.toml`). Après une mise à jour du code, relancer
`offers ui` : Streamlit relit les pages, mais garde en mémoire les
modules déjà importés.

`collect`, `export` et `ui` modifient la base, l'Excel ou `config.yaml`
de l'utilisateur (et `collect` appelle les vrais sites) : ne pas les
lancer sans accord sur ses fichiers. Les tests suffisent pour vérifier.

**Tester l'interface.** `AppTest` (`streamlit.testing.v1`), sans
navigateur, sur une base dans `tmp_path`, jamais la vraie (ne pas lancer
l'app sans `--db`). `AppTest` ne sait ni cocher une case ni changer une
cellule d'un `st.data_editor`, ni cliquer un `ButtonColumn` : les offres
cochées sont dans `st.session_state["<page>_selected"]`, la fiche
ouverte dans `"<page>_card"` (les tests les remplissent), et les
modifications du tableau passent par `offer_table.apply_table_changes`,
testée avec pytest. Ces gestes sont à faire vérifier par l'utilisateur.
La logique sans Streamlit (`browsing.py`, `summary.py`) se teste avec
pytest seul.

## Style du code

**Langue.**
- Commentaires et docstrings : en anglais, simples et courts.
  Docstring d'une ligne quand ça suffit ; détailler seulement les
  paramètres ou le retour qui ne sont pas évidents.
- Commentaires : expliquer le *pourquoi*, pas le *quoi*.
- Noms (modules, classes, fonctions, variables, tables SQLite,
  sous-commandes) : en anglais.
- Restent en français, car ce sont des sorties pour l'utilisateur :
  messages affichés (erreurs, bilans), titres des colonnes Excel
  (« Réf. », « En ligne », ...), valeurs comme « Plus en ligne » ou les
  choix de « Statut ».

**Code maintenable.**
- Fonctions courtes, une seule responsabilité, noms explicites.
- Pas de duplication : factoriser dès qu'un même bloc apparaît deux fois.
- Pas de valeur magique : constantes nommées en haut du module.
- Pas de dépendance cachée : passer ce dont une fonction a besoin en
  paramètre plutôt que lire un état global.
- Tout comportement nouveau ou modifié est couvert par un test.
- Mise en page : `ruff format` (décidé en T1.9). Un tableau compact plus
  lisible sur quelques lignes peut être protégé par `# fmt: off` /
  `# fmt: on`, comme `SCRIPT_COLUMNS` et `WIDTHS` dans `exports/excel.py`.

**Exceptions.**
- Attraper seulement les exceptions attendues et précises
  (`requests.RequestException`, `OSError`, ...), jamais `except:` ni
  `except Exception:` sans relancer.
- Ne jamais avaler une erreur en silence : la relancer, ou la
  journaliser et le dire dans le bilan.
- Traduire les erreurs techniques en exceptions du projet, qui héritent
  de `OffersError` (`ConfigError`, `ApiError`, `ExcelError`,
  `StorageError`), avec
  `raise ... from err`, pour garder la cause.
- Une source en erreur n'arrête pas les autres : le pipeline garde son
  erreur et l'affiche dans le bilan.
- Message d'erreur : ce qui s'est passé et quoi faire, en français.
- Seuls les points d'entrée (`__main__.py`, `ui/app.py`) attrapent les
  exceptions du projet pour les afficher ; les erreurs inattendues
  remontent avec leur trace complète. Exception : une action de
  l'interface (export de l'Excel, interrupteur d'une recherche) affiche
  son erreur à côté du bouton, pour que le reste de la page reste
  utilisable.
- Ne rien modifier sur disque tant qu'une erreur reste possible
  (écriture atomique, vérifications avant d'écrire).

## Règles à ne jamais casser

- La base est la référence des offres ; l'Excel en est un export.
- L'Excel ne sert qu'à consulter : il est régénéré entièrement depuis
  la base à chaque export (offres hors corbeille, suivi compris), et rien
  n'y est jamais lu. Ce qui y est tapé à la main est perdu à l'export
  suivant (sauf dans `output/backup/`).
- La table `tracking` (statut, lettre, favori, lecture, corbeille, date
  de candidature, notes) n'est écrite que par l'interface, à partir des
  saisies de l'utilisateur ; la collecte n'y touche jamais.
- Une offre n'est jamais supprimée : la corbeille la masque
  (`tracking.hidden`), et l'on peut la restaurer.
- L'interface n'écoute que sur `localhost`, jamais sur le réseau local.
- Excel ouvert pendant une collecte : la collecte se fait quand même,
  seul l'export est sauté et signalé dans le bilan. Les textes du bilan
  sont dans `summary.py`, partagés par la ligne de commande et
  l'interface.
- Écriture atomique : fichier temporaire, puis remplacement (Excel) ;
  une transaction par écriture (base, via `database.transaction`).
- Sauvegarde avant chaque modification : l'Excel dans `output/backup/`,
  la base dans `data/backup/` avant chaque lancement (30 gardées).
- Lecture incomplète d'une source (< 95 % du total annoncé) : on s'arrête
  sans rien modifier.
- Une offre n'est marquée « Plus en ligne » que si sa source donne la
  liste complète de ses offres ; chaque source le fait pour ses offres,
  même si une autre est en erreur.
- `config.yaml` n'est modifié par le programme que pour couper ou
  rallumer une recherche (page Collecte, `config.set_search_enabled`) :
  avec `ruamel.yaml`, qui garde commentaires et mise en page, après une
  copie dans `data/backup/`, et par écriture atomique.
- Le schéma évolue seulement par une nouvelle migration ajoutée à la fin
  de `database.MIGRATIONS` (version dans `PRAGMA user_version`).

`tests/test_excel_export.py` vérifie ces règles. Si l'instantané
(`tests/fixtures/excel_expected.json`) change, c'est que le comportement
change : ne le régénérer (`UPDATE_SNAPSHOT=1`) que si c'est voulu par le
ticket.

Toute nouvelle source passe le contrat de `tests/sources_contract.py`.

## Façon de travailler

- Un ticket à la fois : `/ticket T<n>.<m>`.
- Ne rien modifier hors du périmètre du ticket ; noter dans ses « Notes »
  ce qui est découvert ou décidé.
- Tests à jour et `pytest` vert avant de considérer un ticket terminé.
- Un ticket = un commit (décidé au lot 3) : à la fin de chaque ticket,
  proposer son message.
- L'utilisateur fait lui-même ses commits : proposer un message (voir
  « Messages de commit »), sans commiter. Pas de tags.

## Messages de commit

Format : `type(portée): description`, en français, en une ligne.

- `type` : ce que fait le commit.
  - `add` : nouvelle fonctionnalité, nouveau fichier ou nouvelle commande ;
  - `update` : changement d'un comportement existant ;
  - `fix` : correction d'un bug ;
  - `remove` : suppression de code, de fichiers ou d'une fonctionnalité ;
  - `refactor` : réorganisation du code sans changement de comportement ;
  - `test` : tests seuls ;
  - `docs` : documentation seule (`CLAUDE.md`, docstrings, ...).
- `portée` : la partie du code concernée, en anglais comme les noms du
  code (`storage`, `excel`, `pipeline`, `cli`, `business_france`,
  `config`, ...).
- `description` : ce qui change, à l'infinitif ou en phrase nominale,
  sans point final. Finir par le ticket ou le lot entre parenthèses,
  par exemple `(T2.4)` ou `(lot 2)`.

Exemples :
`add(storage): import unique de l'Excel dans la base (T2.4)`,
`fix(excel): garder le fond vert des offres du jour (T1.7)`.

## Données sensibles

Ne pas lire ni versionner `output/`, `data/`, `profil/` et `lettres/`,
sauf si le ticket le demande. Les fixtures ne contiennent ni vraie clé d'API ni
coordonnées de contact (voir `tests/fixtures/capture_business_france.py`).
