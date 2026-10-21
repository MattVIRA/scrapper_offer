"""Données communes aux tests."""

import json
import os

import pytest

DOSSIER_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def lire_fixture(nom):
    """Renvoie le texte d'un fichier de tests/fixtures."""
    with open(os.path.join(DOSSIER_FIXTURES, nom), encoding="utf-8") as fichier:
        return fichier.read()


@pytest.fixture
def recherche_business_france():
    """Vraie réponse de l'API Business France : {"result": [...], "count": ...}."""
    return json.loads(lire_fixture("business_france_recherche.json"))


@pytest.fixture
def page_business_france():
    """Extrait de la page de recherche du site, avec une fausse clé d'API."""
    return lire_fixture("business_france_page.html")
