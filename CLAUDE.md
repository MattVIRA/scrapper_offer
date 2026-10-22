# scrapper_offer

Récupère des offres d'emploi (pour l'instant les VIE de Business France),
les range dans une base SQLite (`data/offers.db`) et les exporte dans un
fichier Excel (`output/offres_vie.xlsx`).
Application personnelle, en cours de refonte : la feuille de route est
dans `.claude/LOTS.md`, les tickets dans `.claude/TICKETS/LOT_<n>/T<n>.<m>.md`.

Code dans `src/offers/` : `sources/` (une classe par source, contrat
dans `sources/base.py`), `storage/` (`database.py`, seul module qui parle
à SQLite, `schema.sql`, `excel_import.py`), `scoring/`, `exports/`,
`tracking.py` (statuts de suivi), `pipeline.py` (orchestrateur),
`__main__.py` (ligne de commande).

## Commandes

```bash
pip install -e ".[dev]"         # installer, dans le .venv
python -m offers collect        # interroge les sites, met à jour la base puis l'Excel
python -m offers import-excel   # une seule fois : offres et suivi de l'Excel vers la base
python -m offers export         # met à jour l'Excel à partir de la base, sans réseau
python -m offers duplicates     # affiche les doublons probables
pytest                          # tests, sans réseau
ruff check .                    # vérifier le code
ruff format .                   # mettre en forme (ruff format --check . pour vérifier)
```

Options : `--db` (défaut `data/offers.db`) et `--excel` (défaut
`output/offres_vie.xlsx`) ; `collect` prend aussi `--config`.

`collect`, `import-excel` et `export` modifient la base ou l'Excel de
l'utilisateur (et `collect` appelle les vrais sites) : ne pas les lancer
sans accord sur ses fichiers. Les tests suffisent pour vérifier.

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
- Seul le point d'entrée (`__main__.py`) attrape les
  exceptions du projet pour les afficher ; les erreurs inattendues
  remontent avec leur trace complète.
- Ne rien modifier sur disque tant qu'une erreur reste possible
  (écriture atomique, vérifications avant d'écrire).

## Règles à ne jamais casser

- La base est la référence des offres ; l'Excel en est un export.
- Les données saisies par l'utilisateur (Statut, Postulé le, Notes,
  colonnes ajoutées à la main) ne sont jamais modifiées.
- La table `tracking` n'est écrite qu'à partir des saisies de
  l'utilisateur. Jusqu'au lot 3, il les fait dans l'Excel, et
  `sync_tracking` les recopie dans la base à chaque collecte ; l'export
  n'écrit jamais les colonnes de l'utilisateur.
- Écriture atomique : fichier temporaire, puis remplacement (Excel) ;
  une transaction par écriture (base, via `database.transaction`).
- Sauvegarde avant chaque modification : l'Excel dans `output/backup/`,
  la base dans `data/backup/` avant chaque lancement (30 gardées).
- Lecture incomplète d'une source (< 95 % du total annoncé) : on s'arrête
  sans rien modifier.
- Une offre n'est marquée « Plus en ligne » que si sa source donne la
  liste complète de ses offres ; chaque source le fait pour ses offres,
  même si une autre est en erreur.
- Le schéma évolue seulement par une nouvelle migration ajoutée à la fin
  de `database.MIGRATIONS` (version dans `PRAGMA user_version`).

`tests/test_excel_export.py` vérifie ces règles. Si l'instantané
(`tests/fixtures/excel_expected.json`) change, c'est que le comportement
change : ne le régénérer (`UPDATE_SNAPSHOT=1`) que si c'est voulu par le
ticket. `excel_attendu.json` est l'instantané de l'ancien code (T0.5) :
ne jamais le régénérer ; hors colonne « Source » et liste déroulante
« Statut », le fichier produit doit lui rester identique.

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
