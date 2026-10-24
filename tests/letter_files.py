"""Fake profile files for the letter tests: never the user's real profil/."""

import docx

CONTACT = """\
name: "Camille Martin"
address: "1 rue de la Paix, 75002 Paris"
phone: "06 00 00 00 00"
email: "camille@example.com"
city: "Paris"
"""


def write_pdf(path, text):
    """Write a one-page PDF showing text (ASCII only), with a valid xref table."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    content = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(content))
        content += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(content)
    content += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    content += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    content += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    path.write_bytes(content)


def write_docx(path, paragraphs):
    """Write a Word file with these paragraphs."""
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(str(path))


def make_profile(root, contact=CONTACT):
    """Create a complete profile folder in root and return its path."""
    profile = root / "profil"
    (profile / "cv").mkdir(parents=True)
    (profile / "exemples").mkdir()
    write_pdf(profile / "cv" / "cv.pdf", "Camille Martin - Data Scientist - Python")
    write_docx(profile / "exemples" / "lettre_acme.docx", ["Madame, Monsieur,", "Ancien style."])
    (profile / "consignes.md").write_text("Ton direct, une page.\n", encoding="utf-8")
    if contact is not None:
        (profile / "coordonnees.yaml").write_text(contact, encoding="utf-8")
    return profile
