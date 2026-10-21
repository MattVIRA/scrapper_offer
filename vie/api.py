"""Accès au site Business France : lecture de la clé et des offres."""

import json
import re
import time
from urllib.parse import parse_qs, urlparse

import requests

URL_SITE = "https://mon-vie-via.businessfrance.fr"
URL_PAGE_RECHERCHE = URL_SITE + "/offres/recherche"
URL_API = "https://civiweb-api-prd.azurewebsites.net/api/Offers/search"

# Nombre d'offres par requête. L'API refuse les valeurs trop grandes.
TAILLE_PAGE = 100
# Petite pause entre deux requêtes, pour ne pas charger le site.
PAUSE_SECONDES = 0.3
DELAI_MAX_SECONDES = 30

# Filtres de l'adresse de recherche que l'API comprend.
# Les autres paramètres de l'adresse sont ignorés.
FILTRES_CONNUS = [
    "specializationsIds",
    "geographicZones",
    "countriesIds",
    "studiesLevelId",
    "activitySectorId",
    "companiesSizes",
    "missionsTypesIds",
    "missionsDurations",
    "entreprisesIds",
    "teletravail",
    "porteEnv",
]


class ErreurApi(Exception):
    """Problème pendant un échange avec le site."""


def creer_session():
    """Prépare une session HTTP réutilisée pour toutes les requêtes."""
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    return session


def lire_cle_api(session):
    """Lit la clé d'API dans la page de recherche du site.

    La clé est publique : elle est écrite dans le code HTML de la page.
    On la relit à chaque lancement, au cas où elle change.
    """
    try:
        reponse = session.get(URL_PAGE_RECHERCHE, timeout=DELAI_MAX_SECONDES)
        reponse.raise_for_status()
    except requests.RequestException as erreur:
        raise ErreurApi(f"Impossible d'ouvrir la page du site : {erreur}")

    trouve = re.search(r'API_KEY:"((?:[^"\\]|\\.)*)"', reponse.text)
    if not trouve:
        raise ErreurApi(
            "Clé d'API introuvable dans la page du site. "
            "Le site a peut-être changé."
        )
    # La clé est écrite avec des codes comme / à la place de "/".
    # json.loads les remet en clair.
    return json.loads('"' + trouve.group(1) + '"')


def filtres_depuis_url(url):
    """Transforme l'adresse d'une recherche du site en filtres pour l'API.

    Les valeurs restent du texte : l'API refuse les nombres.
    """
    parametres = parse_qs(urlparse(url).query, keep_blank_values=True)
    filtres = {"query": parametres.get("query", [""])[0]}
    for nom in FILTRES_CONNUS:
        if nom in parametres:
            # Accepte "a=1&a=2" comme "a=1,2".
            valeurs = ",".join(parametres[nom]).split(",")
            filtres[nom] = [v for v in valeurs if v != ""]
    return filtres


def chercher_offres(session, cle_api, filtres=None):
    """Renvoie toutes les offres qui correspondent aux filtres.

    Sans filtres, renvoie toutes les offres du site.
    Les offres sont lues page par page.
    """
    offres = {}
    position = 0
    while True:
        corps = {"limit": TAILLE_PAGE, "skip": position, "query": ""}
        corps.update(filtres or {})
        try:
            reponse = session.post(
                URL_API,
                json=corps,
                headers={"X-API-KEY": cle_api},
                timeout=DELAI_MAX_SECONDES,
            )
        except requests.RequestException as erreur:
            raise ErreurApi(f"Le site ne répond pas : {erreur}")
        if reponse.status_code != 200:
            raise ErreurApi(
                f"Le site a refusé la requête (code {reponse.status_code}) : "
                f"{reponse.text[:200]}"
            )

        donnees = reponse.json()
        page = donnees.get("result", [])
        total = donnees.get("count", 0)
        for offre in page:
            # Le dictionnaire évite les doublons entre deux pages.
            offres[str(offre["id"])] = offre

        position += TAILLE_PAGE
        if not page or position >= total:
            break
        time.sleep(PAUSE_SECONDES)

    # Une offre peut changer de page pendant la lecture, donc on tolère
    # un petit écart. Un gros écart veut dire que la lecture a échoué.
    if len(offres) < total * 0.95:
        raise ErreurApi(
            f"Lecture incomplète : {len(offres)} offres lues sur {total}."
        )
    return list(offres.values())


def reference(offre):
    """Renvoie la référence de l'offre, par exemple "VIE246803"."""
    return offre.get("reference") or f"VIE{offre['id']}"


def lien(offre):
    """Renvoie l'adresse de la page de l'offre sur le site."""
    return f"{URL_SITE}/offres/{offre['id']}"
