"""Recherche des mots-clés dans le texte d'une offre."""

import re
import unicodedata

# Champs de l'offre dans lesquels on cherche les mots-clés.
CHAMPS_TEXTE = ["missionTitle", "missionDescription", "missionProfile"]


def simplifier(texte):
    """Met le texte en minuscules et enlève les accents."""
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def contient(texte_simplifie, mot_cle):
    """Dit si le mot-clé est dans le texte, en tant que mot entier.

    "ia" est trouvé dans "projet IA", mais pas dans "media".
    """
    motif = r"(?<!\w)" + re.escape(simplifier(mot_cle)) + r"(?!\w)"
    return re.search(motif, texte_simplifie) is not None


def noter(offre, mots_inclure, mots_exclure):
    """Renvoie le score de l'offre et le texte de la colonne "Mots trouvés".

    Le score est le nombre de mots-clés trouvés.
    Si un mot à exclure est trouvé, le score vaut 0.
    """
    texte = simplifier(" ".join(offre.get(champ) or "" for champ in CHAMPS_TEXTE))

    exclus = [mot for mot in mots_exclure if contient(texte, mot)]
    if exclus:
        return 0, "exclu : " + ", ".join(exclus)

    trouves = [mot for mot in mots_inclure if contient(texte, mot)]
    return len(trouves), ", ".join(trouves)
