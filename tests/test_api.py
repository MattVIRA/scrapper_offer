"""Tests de l'accès à Business France (vie/api.py), sans réseau."""

import copy

import pytest
import requests

from vie import api

# Adresse de config.yaml, copiée ici pour que le test ne dépende pas
# des réglages du moment.
URL_CONFIG = (
    "https://mon-vie-via.businessfrance.fr/offres/recherche?query=&specializationsIds=243"
    "&specializationsIds=210&specializationsIds=212&specializationsIds=59"
    "&specializationsIds=255&specializationsIds=24&geographicZones=2&geographicZones=3"
    "&geographicZones=4&geographicZones=6&geographicZones=5&studiesLevelId=4"
    "&teletravail=0&porteEnv=0"
)


class FausseReponse:
    """Réponse HTTP minimale, comme celles de requests."""

    def __init__(self, status_code=200, texte="", donnees=None):
        self.status_code = status_code
        self.text = texte
        self.donnees = donnees

    def json(self):
        return self.donnees

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"code {self.status_code}")


class FausseSession:
    """Session qui renvoie des réponses préparées et garde les requêtes reçues.

    reponses : liste de FausseReponse ou d'exceptions, rendues dans l'ordre.
    """

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.requetes = []

    def _repondre(self):
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    def get(self, url, **options):
        self.requetes.append(("GET", url, options))
        return self._repondre()

    def post(self, url, **options):
        self.requetes.append(("POST", url, options))
        return self._repondre()


@pytest.fixture(autouse=True)
def sans_pause(monkeypatch):
    """Les tests n'attendent pas entre deux pages."""
    monkeypatch.setattr(api, "PAUSE_SECONDES", 0)


def fabriquer_offres(modele, nombre):
    """Renvoie `nombre` copies de l'offre modèle, avec des id différents."""
    offres = []
    for numero in range(nombre):
        offre = copy.deepcopy(modele)
        offre["id"] = 900000 + numero
        offre["reference"] = f"VIE{900000 + numero}"
        offres.append(offre)
    return offres


def pages_api(pages, total):
    """Une réponse d'API par page, avec le total annoncé."""
    return [FausseReponse(donnees={"result": page, "count": total}) for page in pages]


# --- lire_cle_api -------------------------------------------------------------


def test_lire_cle_api_lit_et_decode_la_cle(page_business_france):
    session = FausseSession([FausseReponse(texte=page_business_france)])
    assert api.lire_cle_api(session) == "fausse/cle+test="
    methode, url, _ = session.requetes[0]
    assert (methode, url) == ("GET", api.URL_PAGE_RECHERCHE)


def test_lire_cle_api_erreur_si_cle_absente():
    session = FausseSession([FausseReponse(texte="<html>rien ici</html>")])
    with pytest.raises(api.ErreurApi, match="introuvable"):
        api.lire_cle_api(session)


def test_lire_cle_api_erreur_si_page_en_erreur():
    session = FausseSession([FausseReponse(status_code=503)])
    with pytest.raises(api.ErreurApi, match="Impossible d'ouvrir"):
        api.lire_cle_api(session)


def test_lire_cle_api_erreur_si_site_injoignable():
    session = FausseSession([requests.ConnectionError("pas de réseau")])
    with pytest.raises(api.ErreurApi, match="Impossible d'ouvrir"):
        api.lire_cle_api(session)


# --- filtres_depuis_url -------------------------------------------------------


def test_filtres_depuis_url_avec_l_adresse_de_config():
    assert api.filtres_depuis_url(URL_CONFIG) == {
        "query": "",
        "specializationsIds": ["243", "210", "212", "59", "255", "24"],
        "geographicZones": ["2", "3", "4", "6", "5"],
        "studiesLevelId": ["4"],
        "teletravail": ["0"],
        "porteEnv": ["0"],
    }


def test_filtres_depuis_url_accepte_les_valeurs_separees_par_virgule():
    filtres = api.filtres_depuis_url(f"{api.URL_PAGE_RECHERCHE}?countriesIds=1,2&countriesIds=3")
    assert filtres["countriesIds"] == ["1", "2", "3"]


def test_filtres_depuis_url_ignore_les_parametres_inconnus_et_vides():
    filtres = api.filtres_depuis_url(
        f"{api.URL_PAGE_RECHERCHE}?query=data&tri=date&page=2&countriesIds="
    )
    assert filtres == {"query": "data", "countriesIds": []}


def test_filtres_depuis_url_sans_parametres():
    assert api.filtres_depuis_url(api.URL_PAGE_RECHERCHE) == {"query": ""}


# --- chercher_offres ----------------------------------------------------------


def test_chercher_offres_lit_toutes_les_pages(monkeypatch, recherche_business_france):
    monkeypatch.setattr(api, "TAILLE_PAGE", 2)
    offres = recherche_business_france["result"]
    session = FausseSession(pages_api([offres[0:2], offres[2:4], offres[4:5]], total=5))

    resultat = api.chercher_offres(session, "cle", {"query": "data", "countriesIds": ["1"]})

    assert [o["id"] for o in resultat] == [o["id"] for o in offres]
    corps = [options["json"] for _, _, options in session.requetes]
    assert [c["skip"] for c in corps] == [0, 2, 4]
    assert all(c["limit"] == 2 for c in corps)
    assert all(c["query"] == "data" and c["countriesIds"] == ["1"] for c in corps)
    assert all(options["headers"] == {"X-API-KEY": "cle"} for _, _, options in session.requetes)
    assert all(url == api.URL_API for _, url, _ in session.requetes)


def test_chercher_offres_sans_filtres(recherche_business_france):
    offres = recherche_business_france["result"]
    session = FausseSession(pages_api([offres], total=len(offres)))
    assert len(api.chercher_offres(session, "cle")) == len(offres)
    assert session.requetes[0][2]["json"] == {"limit": api.TAILLE_PAGE, "skip": 0, "query": ""}


def test_chercher_offres_enleve_les_doublons_entre_pages(monkeypatch, recherche_business_france):
    # Une offre a glissé d'une page à l'autre pendant la lecture :
    # elle est lue deux fois, et une autre n'est jamais lue (19 sur 20,
    # donc dans la tolérance de 95 %).
    monkeypatch.setattr(api, "TAILLE_PAGE", 10)
    offres = fabriquer_offres(recherche_business_france["result"][0], 20)
    session = FausseSession(pages_api([offres[0:10], offres[9:19]], total=20))

    resultat = api.chercher_offres(session, "cle")

    ids = [o["id"] for o in resultat]
    assert len(ids) == len(set(ids)) == 19


def test_chercher_offres_s_arrete_sur_une_page_vide(monkeypatch, recherche_business_france):
    monkeypatch.setattr(api, "TAILLE_PAGE", 5)
    offres = recherche_business_france["result"]
    # Le site annonce 6 offres mais la 2e page est vide : 5 sur 6 < 95 %.
    session = FausseSession(pages_api([offres, []], total=6))

    with pytest.raises(api.ErreurApi, match="5 offres lues sur 6"):
        api.chercher_offres(session, "cle")
    assert len(session.requetes) == 2


def test_chercher_offres_aucune_offre():
    session = FausseSession(pages_api([[]], total=0))
    assert api.chercher_offres(session, "cle") == []


def test_chercher_offres_erreur_si_lecture_incomplete(monkeypatch, recherche_business_france):
    monkeypatch.setattr(api, "TAILLE_PAGE", 10)
    offres = fabriquer_offres(recherche_business_france["result"][0], 20)
    # 18 offres différentes sur 20 annoncées : sous les 95 %.
    session = FausseSession(pages_api([offres[0:10], offres[8:18]], total=20))
    with pytest.raises(api.ErreurApi, match="Lecture incomplète : 18 offres lues sur 20"):
        api.chercher_offres(session, "cle")


def test_chercher_offres_erreur_si_code_http_different_de_200():
    session = FausseSession([FausseReponse(status_code=401, texte="clé refusée")])
    with pytest.raises(api.ErreurApi, match=r"code 401.*clé refusée"):
        api.chercher_offres(session, "cle")


def test_chercher_offres_erreur_si_site_injoignable():
    session = FausseSession([requests.Timeout("trop long")])
    with pytest.raises(api.ErreurApi, match="ne répond pas"):
        api.chercher_offres(session, "cle")


# --- reference et lien --------------------------------------------------------


def test_reference_lue_dans_l_offre(recherche_business_france):
    for offre in recherche_business_france["result"]:
        assert api.reference(offre) == offre["reference"]


def test_reference_construite_si_absente():
    assert api.reference({"id": 246803}) == "VIE246803"
    assert api.reference({"id": 246803, "reference": ""}) == "VIE246803"


def test_lien(recherche_business_france):
    offre = recherche_business_france["result"][0]
    assert api.lien(offre) == f"https://mon-vie-via.businessfrance.fr/offres/{offre['id']}"
