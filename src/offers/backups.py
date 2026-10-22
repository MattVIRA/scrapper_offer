"""Backups of the user's files, shared by the database and config.yaml."""

# Backups kept per kind of file.
BACKUPS_KEPT = 30


def remove_old_backups(backup_dir, pattern, kept=BACKUPS_KEPT):
    """Delete the oldest files of backup_dir matching pattern, keeping the last ones.

    The names must sort from the oldest, as with a date in the name.
    """
    backups = sorted(backup_dir.glob(pattern))
    for old in backups[:-kept]:
        old.unlink()
