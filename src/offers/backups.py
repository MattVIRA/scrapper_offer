"""Backups and atomic writes of the user's files (database, config.yaml, prompt)."""

import os
import shutil

# Backups kept per kind of file.
BACKUPS_KEPT = 30


def remove_old_backups(backup_dir, pattern, kept=BACKUPS_KEPT):
    """Delete the oldest files of backup_dir matching pattern, keeping the last ones.

    The names must sort from the oldest, as with a date in the name.
    """
    backups = sorted(backup_dir.glob(pattern))
    for old in backups[:-kept]:
        old.unlink()


def copy_to_backup(path, backup_dir, prefix, now):
    """Copy path into backup_dir as <prefix><date><suffix>, keeping the last backups.

    Raise OSError if it cannot be done.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_dir / f"{prefix}{now:%Y-%m-%d_%H%M%S}{path.suffix}")
    remove_old_backups(backup_dir, f"{prefix}*{path.suffix}")


def write_text_atomically(path, text):
    """Write a temporary file, then replace path with it.

    Raise OSError if it fails; path is then unchanged and no temporary file is left.
    """
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
