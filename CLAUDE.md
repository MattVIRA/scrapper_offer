# scrapper_offer

Récupère les offres VIE de Business France et les range dans un fichier
Excel (`output/offres_vie.xlsx`). Application personnelle, en cours de
refonte : la feuille de route est dans `.claude/LOTS.md`, les tickets
dans `.claude/TICKETS/LOT_<n>/T<n>.<m>.md`.

## Commandes

```bash
pip install -e ".[dev]"   # installer, dans le .venv
python run.py             # lancer : interroge le site et modifie l'Excel
pytest                    # tests, sans réseau
ruff check .              # vérifier le code
```

`python run.py` appelle le vrai site et modifie l'Excel de l'utilisateur :
ne pas le lancer sans accord. Les tests suffisent pour vérifier.

## Style du code

**Langue.**
- Commentaires et docstrings : en anglais, simples et courts.
  Docstring d'une ligne quand ça suffit ; détailler seulement les
  paramètres ou le retour qui ne sont pas évidents.
- Commentaires : expliquer le *pourquoi*, pas le *quoi*.
- Noms (modules, classes, fonctions, variables, tables SQLite,
  sous-commandes) : en anglais. Le code de `vie/` est encore en français ;
  il est traduit au lot 1, pendant son déplacement dans `src/`. Ne pas
  le renommer hors de ce lot.
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
- `ruff format` n'est pas appliqué (voir T0.3) : garder la mise en page
  existante.

**Exceptions.**
- Attraper seulement les exceptions attendues et précises
  (`requests.RequestException`, `OSError`, ...), jamais `except:` ni
  `except Exception:` sans relancer.
- Ne jamais avaler une erreur en silence : la relancer, ou la
  journaliser et le dire dans le bilan.
- Traduire les erreurs techniques en exceptions du projet (`ErreurApi`,
  `ErreurExcel`, puis `ApiError`, `ExcelError` après le lot 1) avec
  `raise ... from err`, pour garder la cause.
- Message d'erreur : ce qui s'est passé et quoi faire, en français.
- Seul le point d'entrée (`run.py`, puis `__main__.py`) attrape les
  exceptions du projet pour les afficher ; les erreurs inattendues
  remontent avec leur trace complète.
- Ne rien modifier sur disque tant qu'une erreur reste possible
  (écriture atomique, vérifications avant d'écrire).

## Règles à ne jamais casser

- Les données saisies par l'utilisateur (Statut, Postulé le, Notes,
  colonnes ajoutées à la main) ne sont jamais modifiées.
- Écriture atomique : fichier temporaire, puis remplacement.
- Sauvegarde dans `backup/` avant chaque modification.
- Lecture incomplète d'une source (< 95 % du total annoncé) : on s'arrête
  sans rien modifier.
- Une offre n'est marquée « Plus en ligne » que si la source donne la
  liste complète de ses offres.

`tests/test_excel.py` vérifie ces règles. Si l'instantané
(`tests/fixtures/excel_attendu.json`) change, c'est que le comportement
change : ne le régénérer que si c'est voulu par le ticket.

## Façon de travailler

- Un ticket à la fois : `/ticket T<n>.<m>`.
- Ne rien modifier hors du périmètre du ticket ; noter dans ses « Notes »
  ce qui est découvert ou décidé.
- Tests à jour et `pytest` vert avant de considérer un ticket terminé.
- L'utilisateur fait lui-même ses commits : proposer un message
  `T<n>.<m> : <titre>`, sans commiter. Pas de tags.

## Données sensibles

Ne pas lire ni versionner `output/`, `profil/` et `lettres/`, sauf si le
ticket le demande. Les fixtures ne contiennent ni vraie clé d'API ni
coordonnées de contact (voir `tests/fixtures/capturer_business_france.py`).
