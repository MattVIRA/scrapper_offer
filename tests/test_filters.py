"""Tests de la recherche des mots-clés (vie/filters.py)."""

from vie import filters


def test_simplifier_met_en_minuscules():
    assert filters.simplifier("Python SQL") == "python sql"


def test_simplifier_enleve_les_accents():
    assert filters.simplifier("Ingénieur Données À Pékin") == "ingenieur donnees a pekin"


def test_contient_trouve_un_mot_entier():
    assert filters.contient("projet ia et data", "ia")


def test_contient_ignore_un_mot_dans_un_autre():
    # "ia" ne doit pas être trouvé dans "media".
    assert not filters.contient("agence media", "ia")


def test_contient_accepte_la_ponctuation_autour():
    assert filters.contient("(python), sql.", "python")
    assert filters.contient("(python), sql.", "sql")


def test_contient_trouve_un_mot_compose():
    assert filters.contient("experience en machine learning", "machine learning")
    assert not filters.contient("machine de learning", "machine learning")


def test_contient_simplifie_le_mot_cle():
    # Le texte est déjà simplifié, le mot-clé ne l'est pas.
    assert filters.contient("analyse de donnees", "Données")


def test_noter_compte_les_mots_trouves():
    offre = {
        "missionTitle": "Data Analyst",
        "missionDescription": "Projets IA en Python.",
        "missionProfile": "Bonne maîtrise de SQL.",
    }
    score, mots = filters.noter(offre, ["python", "sql", "data", "java"], [])
    assert score == 3
    assert mots == "python, sql, data"


def test_noter_compte_un_mot_une_seule_fois():
    offre = {"missionTitle": "Python", "missionDescription": "python, python"}
    assert filters.noter(offre, ["python"], []) == (1, "python")


def test_noter_cherche_seulement_dans_les_champs_texte():
    offre = {"missionTitle": "Commercial", "organizationName": "Python Corp"}
    assert filters.noter(offre, ["python"], []) == (0, "")


def test_noter_met_zero_si_un_mot_a_exclure_est_trouve():
    offre = {"missionTitle": "Data Analyst stage", "missionDescription": "Python"}
    score, mots = filters.noter(offre, ["python", "data"], ["stage", "alternance"])
    assert score == 0
    assert mots == "exclu : stage"


def test_noter_liste_tous_les_mots_exclus():
    offre = {"missionTitle": "Stage en alternance"}
    assert filters.noter(offre, [], ["stage", "alternance"]) == (0, "exclu : stage, alternance")


def test_noter_accepte_des_champs_vides_ou_absents():
    offre = {"missionTitle": None, "missionDescription": ""}
    assert filters.noter(offre, ["python"], []) == (0, "")
    assert filters.noter({}, ["python"], ["stage"]) == (0, "")
