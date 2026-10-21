"""Enregistre de vraies réponses de Business France pour les tests.

À lancer à la main, jamais par pytest :
    python tests/fixtures/capturer_business_france.py

Écrit à côté de ce fichier :
- business_france_recherche.json : une page de l'API (quelques offres) ;
- business_france_page.html : un extrait de la page de recherche,
  avec une fausse clé d'API à la place de la vraie.
"""

import json
import os
import re

from vie import api

DOSSIER = os.path.dirname(os.path.abspath(__file__))
NOMBRE_OFFRES = 5
# Texte gardé de chaque côté de la clé dans l'extrait de la page.
MARGE_EXTRAIT = 60
# Fausse clé, écrite dans la page avec des codes comme la vraie
# ("/" devient barre oblique inverse + "u002F").
FAUSSE_CLE = "fausse/cle+test="
# Champs de l'offre qui peuvent désigner une personne : remplacés.
CHAMPS_CONTACT = {
    "contactCivility": "",
    "contactFirstName": "",
    "contactLastName": "",
    "contactName": "Contact Test",
    "contactEmail": "contact@example.com",
    "contactURL": "",
}


def encoder(texte):
    """Écrit les caractères spéciaux avec des codes, comme la page du site."""
    return "".join(c if c.isalnum() or c == "=" else "\\u%04X" % ord(c) for c in texte)


def anonymiser(offre):
    """Remplace les coordonnées du contact par des valeurs factices."""
    for champ, valeur in CHAMPS_CONTACT.items():
        if champ in offre:
            offre[champ] = valeur
    return offre


def capturer_page(session):
    """Enregistre l'extrait de page autour de la clé, avec la fausse clé."""
    reponse = session.get(api.URL_PAGE_RECHERCHE, timeout=api.DELAI_MAX_SECONDES)
    reponse.raise_for_status()
    trouve = re.search(r'API_KEY:"((?:[^"\\]|\\.)*)"', reponse.text)
    if not trouve:
        raise api.ErreurApi("Clé d'API introuvable dans la page du site.")

    debut = max(trouve.start() - MARGE_EXTRAIT, 0)
    fin = trouve.end() + MARGE_EXTRAIT
    extrait = (
        reponse.text[debut:trouve.start(1)]
        + encoder(FAUSSE_CLE)
        + reponse.text[trouve.end(1):fin]
    )
    with open(os.path.join(DOSSIER, "business_france_page.html"), "w",
              encoding="utf-8") as fichier:
        fichier.write(extrait + "\n")
    return json.loads('"' + trouve.group(1) + '"')


def capturer_recherche(session, cle_api):
    """Enregistre une page de l'API, réduite à quelques offres."""
    reponse = session.post(
        api.URL_API,
        json={"limit": NOMBRE_OFFRES, "skip": 0, "query": ""},
        headers={"X-API-KEY": cle_api},
        timeout=api.DELAI_MAX_SECONDES,
    )
    reponse.raise_for_status()
    donnees = reponse.json()
    donnees["result"] = [anonymiser(offre) for offre in donnees["result"]]
    with open(os.path.join(DOSSIER, "business_france_recherche.json"), "w",
              encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2)
        fichier.write("\n")


def main():
    session = api.creer_session()
    cle_api = capturer_page(session)
    capturer_recherche(session, cle_api)
    print(f"Fixtures écrites dans {DOSSIER}")


if __name__ == "__main__":
    main()
