"""Texts of the collection summary, shared by the command line and the interface."""

from offers.sources import source_label


def collect_summary(report, excel_path):
    """Return the lines of the summary of a CollectReport."""
    lines = [source_summary(source) for source in report.sources]
    if report.excel is None:
        lines.append(excel_skipped_summary(report.excel_error))
    else:
        lines.append(excel_summary(report.excel, excel_path))
    if report.duplicates:
        lines.append(duplicates_summary(report.duplicates))
    return lines


def source_summary(source):
    """Return the summary line of one source (a SourceReport)."""
    label = source_label(source.name)
    if source.error:
        return f"{label} : en erreur, ses offres ne changent pas. {source.error}"
    saved = source.saved
    return (
        f"{label} : {saved.found} offres trouvées, "
        f"{saved.added} nouvelles ajoutées ({saved.relevant} pertinentes), "
        f"{saved.removed} passées « plus en ligne »."
    )


def excel_summary(report, path):
    """Return the summary line of the Excel export."""
    return f"Excel régénéré : {report.rows} offres (hors corbeille). Fichier : {path}"


def excel_skipped_summary(error):
    """Return the summary line of an export that could not be done."""
    return (
        f"Export Excel non fait, la collecte est enregistrée. {error} "
        "Ensuite : bouton « Exporter l'Excel » ou python -m offers export."
    )


def duplicates_summary(count):
    return f"{count} doublons probables : python -m offers duplicates pour les voir."
