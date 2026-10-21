"""Récupère les offres VIE et met à jour le fichier Excel.

Lancement : python run.py
Réglages : config.yaml
"""

import os
import sys

import yaml

from vie import api, excel, filters

DOSSIER = os.path.dirname(os.path.abspath(__file__))
CHEMIN_CONFIG = os.path.join(DOSSIER, "config.yaml")
CHEMIN_EXCEL = os.path.join(DOSSIER, "output", "offres_vie.xlsx")


def lire_config():
    """Lit config.yaml."""
    with open(CHEMIN_CONFIG, encoding="utf-8") as fichier:
        return yaml.safe_load(fichier)


def main():
    config = lire_config()
    mots_inclure = config.get("keywords_include") or []
    mots_exclure = config.get("keywords_exclude") or []

    # Inutile d'interroger le site si le fichier ne peut pas être modifié.
    excel.verifier_fichier_ferme(CHEMIN_EXCEL)

    session = api.creer_session()
    cle_api = api.lire_cle_api(session)

    # 1) Toutes les offres du site, sans filtre.
    #    Sert à savoir si les offres du fichier sont encore en ligne,
    #    même si les recherches de config.yaml ont changé.
    print("Lecture de toutes les offres du site...")
    offres_site = {api.reference(o): o for o in api.chercher_offres(session, cle_api)}
    if not offres_site:
        raise api.ErreurApi("Le site ne renvoie aucune offre. Rien n'est modifié.")

    # 2) Les offres de chaque recherche. Seules celles-ci sont ajoutées.
    offres_recherches = []
    for recherche in config.get("searches") or []:
        print(f"Recherche « {recherche['name']} »...")
        filtres = api.filtres_depuis_url(recherche["url"])
        for offre in api.chercher_offres(session, cle_api, filtres):
            offres_recherches.append((offre, recherche["name"]))

    def noter(offre):
        return filters.noter(offre, mots_inclure, mots_exclure)

    bilan = excel.mettre_a_jour(CHEMIN_EXCEL, offres_site, offres_recherches, noter)

    en_ligne = len({api.reference(offre) for offre, _ in offres_recherches})
    print(
        f"{en_ligne} offres en ligne, "
        f"{bilan['ajoutees']} nouvelles ajoutées ({bilan['pertinentes']} pertinentes), "
        f"{bilan['retirees']} passées « plus en ligne »."
    )
    print(f"Fichier : {CHEMIN_EXCEL}")


if __name__ == "__main__":
    try:
        main()
    except (api.ErreurApi, excel.ErreurExcel) as erreur:
        print(f"Erreur : {erreur}")
        sys.exit(1)
