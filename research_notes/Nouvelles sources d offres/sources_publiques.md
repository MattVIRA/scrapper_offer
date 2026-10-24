# Sources publiques d'offres d'emploi (France Travail, APEC, secteur public, EURES)

Contexte : appli perso Python (macOS, SQLite, lancement quotidien), contrat `Source` avec `collect()` et `online_offers()` facultatif ; lot 6 : seconde source + étape « détail » facultative. Recherche faite le 24/10/2026. Plusieurs pages officielles (francetravail.io, apec.fr) sont des applications JS ou renvoient 403 aux robots : elles n'ont pas pu être lues directement, ce qui est signalé à chaque fois.

## 1. France Travail : API « Offres d'emploi v2 » (francetravail.io)

### Takeaway
**Point clé : d'après data.gouv.fr, l'API Offres d'emploi n'est « actuellement plus exposée » sur francetravail.io (accès « restreint », sur demande par formulaire de contact), parce que des solutions d'IA l'utilisaient massivement sans respecter ses conditions.** Le fonctionnement technique (OAuth2 client credentials, scope `api_offresdemploiv2`, pages de 150, plafond d'environ 1 150 résultats par requête) est bien documenté par des tiers. Mais une personne seule ne peut sans doute plus s'inscrire en libre-service. À vérifier avant d'en faire la seconde source du lot 6.

### Cited Findings
- Statut : la fiche data.gouv.fr de l'API porte « Restreint » ; elle dit que l'API « n'est actuellement plus exposée » sur francetravail.io, le temps que France Travail revoie sa diffusion et sa réutilisation. Raison donnée : un usage automatisé massif par certaines solutions d'IA qui ne respectaient pas les conditions et licences de réutilisation. La fiche ne donne ni date de suspension ni date de retour. — [data.gouv.fr, API Offres d'emploi](https://www.data.gouv.fr/dataservices/api-offres-demploi)
- Qui peut demander l'accès : collectivités et administrations, entreprises et associations, particuliers, via « Demander un accès » (francetravail.io/contact). Limite annoncée : 10 appels/seconde. — [data.gouv.fr, API Offres d'emploi](https://www.data.gouv.fr/dataservices/api-offres-demploi)
- La liste des API France Travail sur data.gouv.fr marque « Accès restreint » sur Offres d'emploi (mise à jour quelques jours avant la consultation, donc vers octobre 2026). D'autres API (ROME 4.0, La Bonne Boîte, Marché du travail, ...) n'ont pas cette mention. — [data.gouv.fr, organisation France Travail, dataservices](https://www.data.gouv.fr/organizations/france-travail/dataservices)
- Une recherche web générale n'a trouvé aucun article de presse sur cette suspension. La seule source est la fiche data.gouv.fr (source primaire, publiée par France Travail). — recherche web du 24/10/2026, sans résultat pertinent
- Contenu : l'API renvoie « en temps réel les offres d'emploi actives collectées par France Travail ou que France Travail a reçues de ses partenaires à la condition que ceux-ci aient consenti à leur mise à disposition dans l'API ». Les offres partenaires (agrégées) en font donc partie, mais seulement celles des partenaires qui l'ont accepté. — [data.gouv.fr (résumé de la recherche), jeu « Offres d'emploi diffusées à France Travail »](https://www.data.gouv.fr/datasets/offres-demploi-diffusees-a-france-travail)
- Usage réservé aux « développeurs signataires d'un contrat de licence » (l'accès se fait sous licence, ce n'est pas de l'open data). — [francetravail.fr, cité par la recherche web](https://www.francetravail.fr/employeur/vos-recrutements/informez-vous-sur-vos-services-d/france-travail-donne-plus-de-vis.html)
- Inscription (procédure d'avant la suspension, d'après un blog tiers publié le 01/09/2026 et modifié le 26/09/2026) : compte gratuit sur francetravail.io, déclaration d'une application, abonnement de celle-ci à l'API ; on obtient alors client_id et client_secret. — [JobsPipe blog (éditeur commercial, source secondaire)](https://jobspipe.dev/blog/france-travail-api.md)
- OAuth2 (même source) : `POST https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire`, `grant_type=client_credentials`, `scope=api_offresdemploiv2` (ailleurs souvent avec `o2dsoffre`, non confirmé ici). Jeton Bearer de courte durée. — [JobsPipe blog](https://jobspipe.dev/blog/france-travail-api.md)
- Endpoints (même source) : recherche `GET https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search` ; référentiels sous `/referentiel/` (`communes`, `metiers`, ...). — [JobsPipe blog](https://jobspipe.dev/blog/france-travail-api.md)
- Paramètres de recherche (même source) : `motsCles`, `codeROME`, `commune`, `departement`, `distance`, `typeContrat`, `minCreationDate`/`maxCreationDate` (ISO-8601, par ex. `2026-08-01T00:00:00Z`), `range`. Réponse : `resultats`, `filtresPossibles` (compteurs par facette) ; le total réel est dans l'en-tête `Content-Range`. — [JobsPipe blog](https://jobspipe.dev/blog/france-travail-api.md)
- Pagination : `range` vaut `0-149` par défaut ; 150 résultats au plus par appel ; premier indice ≤ 1000, second ≤ 1149, soit 1 150 offres au plus par requête. Au-delà, il faut découper (par ex. par fenêtres `minCreationDate`/`maxCreationDate`). Le chiffre 3149 n'apparaît dans aucune source consultée. — [JobsPipe blog](https://jobspipe.dev/blog/france-travail-api.md) ; [paquet PyPI api-offres-emploi (documentation citée par la recherche)](https://pypi.org/project/api-offres-emploi)
- Débit : selon les sources, 3 requêtes/s (documentation du paquet `api-offres-emploi`, ancienne) ou 10 appels/s (JobsPipe et data.gouv.fr, plus récents). — [PyPI api-offres-emploi](https://pypi.org/project/api-offres-emploi) ; [data.gouv.fr](https://www.data.gouv.fr/dataservices/api-offres-demploi)
- Client Python : il existe `api-offres-emploi` sur PyPI. La page n'a pas pu être chargée pour voir sa version et sa date ; sa documentation (citée par la recherche) parle encore de 3 req/s. — [PyPI api-offres-emploi](https://pypi.org/project/api-offres-emploi)
- Licence de réutilisation (d'après JobsPipe, non vérifié sur le texte officiel) : obligation d'afficher l'offre complète, logo compris. — [résumé de la recherche web citant JobsPipe](https://jobspipe.dev/blog/france-travail-api)
- Pas de coût mentionné : compte « gratuit » selon JobsPipe. — [JobsPipe blog](https://jobspipe.dev/blog/france-travail-api.md)

### Inferences
- Pour le lot 6, il faut tenir France Travail pour **incertaine** : sans accès accordé sur demande, aucune intégration légale. La démarche : envoyer une demande d'accès par le formulaire de francetravail.io, en présentant un usage personnel et non commercial, puis attendre la réponse.
- Si l'accès est accordé : `collect()` est simple (une requête par recherche, pages de 150). L'étape « détail » est probablement inutile, car le JSON de recherche contient d'habitude `description` ; c'est le cas dans les versions connues de l'API, mais aucune source lue ici ne le confirme. Un endpoint de détail `GET /offres/{id}` existait (connaissance antérieure, non confirmée ici).
- Liste complète pour « Plus en ligne » : faisable seulement si chaque recherche configurée renvoie ≤ 1 150 résultats, ou si on la découpe par fenêtres de dates jusqu'à ce que chaque tranche passe sous le plafond. Le `Content-Range` donne le total annoncé : il permet de garder la règle « < 95 % ⇒ arrêt ». Une liste de toutes les offres de France Travail (plusieurs centaines de milliers) n'est pas réaliste ; `online_offers()` devrait alors couvrir l'union des recherches configurées. Le contrat actuel l'accepte-t-il ? À examiner.
- Ne pas contourner la suspension en lisant le site candidat.francetravail.fr : les raisons données (abus de réutilisation) laissent penser qu'un tel usage serait mal vu. Je n'ai pas lu les CGU du site.
- Effort, si l'accès est obtenu : faible à moyen (OAuth2, renouvellement du jeton, découpage par dates, correspondance des champs), environ 1 à 2 tickets.

### Gaps
- La documentation officielle de francetravail.io (catalogue, CGU de l'API, liste exacte des scopes, endpoints de référentiels, présence de `description` et `origineOffre`/`partenaires` dans les résultats) n'a pas pu être lue : application JS non lisible par l'outil.
- Date exacte de la suspension, sort des comptes existants (les identifiants déjà émis marchent-ils encore ?), délai de réponse aux demandes : non trouvés.
- Version et date du dernier paquet `api-offres-emploi` : page PyPI non chargée. Pas de dépôt GitHub de 2026 consulté pour confirmer le comportement actuel.

## 2. APEC (offres cadres)

### Takeaway
Aucune API officielle ni open data APEC trouvée. Le site s'appuie sur des services JSON internes (recherche et détail) que des scrapers commerciaux (Apify, spider.cloud) utilisent. Ces services sont protégés par DataDome (anti-bot), et `robots.txt` comme les CGU renvoient 403 aux robots. Une source APEC reviendrait à contourner une protection anti-bot : c'est à écarter pour une appli perso qui veut rester légale et robuste.

### Cited Findings
- Aucune documentation d'API publique officielle APEC trouvée ; les résultats sont des acteurs Apify et des services commerciaux. — [recherche web ; ex. Apify studio-amba/apec-scraper](https://apify.com/studio-amba/apec-scraper)
- Un acteur Apify dit lire directement « l'API de recherche JSON d'APEC », à 100 offres par requête, avec une requête de plus par offre pour le détail (description complète, profil, entreprise, compétences, URL de candidature). — [Apify studio-amba/apec-scraper](https://apify.com/studio-amba/apec-scraper)
- Le même acteur signale qu'APEC protège ses API de recherche et de détail par DataDome, et propose une clé Bright Data (proxy) en paramètre. — [Apify studio-amba/apec-scraper](https://apify.com/studio-amba/apec-scraper)
- Format d'URL d'une offre : `https://www.apec.fr/candidat/recherche-emploi/emploi/detail-offre/178910904W`. — [Apify studio-amba/apec-scraper](https://apify.com/studio-amba/apec-scraper)
- Autres scrapers commerciaux du même genre : [Apify khadinakbar](https://apify.com/khadinakbar/apec-jobs-scraper), [Apify blackfalcondata](https://apify.com/blackfalcondata/apec-scraper), [spider.cloud](https://spider.cloud/scrapers/apec-fr-scraper/)
- `https://www.apec.fr/robots.txt` et `https://www.apec.fr/conditions-generales-dutilisation.html` renvoient HTTP 403 à l'outil de lecture : impossible de lire leur contenu. — tentative directe du 24/10/2026
- Choisir le service public envoie ses offres vers d'autres sites, dont APEC (« Multidiffusion (LinkedIn, APEC, DVT …) »). — [CSP Guide Offres (PDF)](https://choisirleservicepublic.gouv.fr/wp-content/uploads/2026/03/CSP-Guide-Offres.pdf)

### Inferences
- La présence de DataDome montre une volonté claire d'APEC de bloquer l'automatisation. Le contourner (proxys, imitation de navigateur) poserait un problème juridique (CGU ; droit sui generis du producteur de bases de données, art. L.342-1 CPI, connaissance générale non vérifiée ici) et rendrait la source fragile au quotidien.
- Si APEC compte vraiment : utiliser à la main les alertes e-mail du site, ou écrire à APEC pour un partenariat. Je n'ai trouvé aucune piste officielle.
- Effort technique (non recommandé) : élevé et instable.

### Gaps
- Texte réel des CGU APEC sur l'extraction automatisée et contenu de `robots.txt` (403).
- URLs exactes des endpoints JSON internes : pas données par les pages consultées.

## 3. Autres sources publiques : Choisir le service public, place-emploi-public, data.gouv.fr, EURES, VIE

### Takeaway
La source publique la plus solide est le jeu data.gouv.fr « Les offres diffusées sur Choisir le Service Public » : open data sous Licence Ouverte 2.0, mis à jour chaque semaine, CSV d'environ 120 Mo, URL stable. Mais il est beaucoup plus pauvre que le site (un utilisateur le dit) et hebdomadaire, pas quotidien. Les autres jeux « France Travail » de data.gouv.fr sont des statistiques trimestrielles ou de petits extraits locaux, inutilisables comme source. EURES n'a pas d'API publique documentée trouvée.

### Cited Findings
**Choisir le service public (CSP)**
- Jeu de données publié par la DGAFP : offres publiées sur CSP (par les employeurs publics ou reçues de sites partenaires), plus les référentiels métiers, domaines et spécialités de diplômes ; « données brutes », mises à jour « à une fréquence hebdomadaire » ; Licence Ouverte 2.0 ; dernière mise à jour du jeu le 19/10/2026. — [data.gouv.fr, Les offres diffusées sur CSP](https://www.data.gouv.fr/datasets/les-offres-diffusees-sur-choisir-le-service-public)
- Fichiers : un CSV courant de 120,7 Mo, plus des CSV annuels (156,4 Mo au 29/12/2025, 160,4 Mo au 30/12/2024, ...) et une documentation PDF/XLSX (avril 2023). Lien de téléchargement stable du dernier CSV : `https://www.data.gouv.fr/api/1/datasets/r/867034a2-2fa1-41b4-bd39-c84691ea618f`. — [data.gouv.fr, Les offres diffusées sur CSP](https://www.data.gouv.fr/datasets/les-offres-diffusees-sur-choisir-le-service-public)
- Limite : un commentaire d'utilisateur dit que les offres du jeu contiennent très peu d'informations par rapport à celles du site, et que le champ des compétences attendues est souvent vide. — [data.gouv.fr, discussions du jeu CSP (résumé de la recherche)](https://www.data.gouv.fr/datasets/les-offres-diffusees-sur-choisir-le-service-public/discussions)
- Aucune API publique ni flux RSS de CSP trouvés. L'export Excel décrit dans le guide sert aux employeurs pour leurs propres offres. CSP renvoie automatiquement ses offres vers France Travail et 1J1S (« Rediffusion automatique (Pôle Emploi & 1J1S) »). — [CSP Guide Offres (PDF, 2026)](https://choisirleservicepublic.gouv.fr/wp-content/uploads/2026/03/CSP-Guide-Offres.pdf)
- Volume : près de 350 000 offres publiées sur CSP en 2024 ; nombre stable en 2025. — [fonction-publique.gouv.fr, 2024](https://www.fonction-publique.gouv.fr/toutes-les-publications/pres-de-350-000-offres-demploi-ont-ete-publiees-sur-le-site-choisir-le-service-public-en-2024) ; [fonction-publique.gouv.fr, 2025](https://www.fonction-publique.gouv.fr/toutes-les-publications/le-nombre-doffres-publiees-sur-le-site-choisir-le-service-public-se-stabilise-en-2025)

**data.gouv.fr, jeux « France Travail »**
- « Offres d'emploi diffusées à France Travail » : mis à jour chaque trimestre (dernière fois le 03/07/2026), un seul fichier XLS de 45,8 Ko. C'est un décompte ou une synthèse, pas une liste d'offres exploitable. — [data.gouv.fr](https://www.data.gouv.fr/datasets/offres-demploi-diffusees-a-france-travail)
- « France Travail - Offres d'emploi » : republié par le Département de Seine-Saint-Denis (data.seinesaintdenis.fr), CSV de 492 Ko, mis à jour le 27/08/2026, Licence Ouverte 2.0. C'est un extrait local, pas une source nationale. — [data.gouv.fr](https://www.data.gouv.fr/datasets/france-travail-offres-demploi)

**EURES**
- Pas de documentation développeur EURES officielle trouvée. Des scrapers tiers disent s'appuyer sur une API REST publique « jv-search » du portail, sans compte, pour environ 3 millions d'offres dans plus de 30 pays. — [Apify nomad-jobs/eures-scraper](https://apify.com/nomad-jobs/eures-scraper) ; [Apify studio-amba/eures-scraper](https://apify.com/studio-amba/eures-scraper)

**Business France / VIE**
- Aucune autre source VIE officielle trouvée au-delà de ce que l'appli utilise déjà (mon-vie-via.businessfrance.fr / Civiweb). Recherche non poussée faute de budget d'appels.

### Inferences
- Source CSP du lot 6 : faisable et légale (Licence Ouverte 2.0 : réutilisation libre, citer la source et la date). `collect()` télécharge le CSV de la semaine (environ 120 Mo) puis filtre localement avec les recherches configurées. Le CSV est probablement une image des offres en ligne (« offres diffusées ») : il donnerait alors naturellement `online_offers()`. Mais la page ne précise pas s'il s'agit d'un instantané ou d'un historique : **à vérifier sur le CSV avant d'activer « Plus en ligne »**. La règle « < 95 % du total annoncé » n'a pas d'équivalent direct (pas de total annoncé) ; on pourrait comparer avec le nombre de lignes de la semaine précédente.
- Étape « détail » : vu la pauvreté du CSV, une étape détail lirait la page de l'offre sur choisirleservicepublic.gouv.fr. Je n'ai pas lu les CGU ni le robots.txt de CSP : à vérifier avant.
- Fraîcheur : hebdomadaire, alors que l'appli tourne chaque jour ; il faut éviter de retélécharger 120 Mo par jour (comparer ETag/Last-Modified, ou la date de mise à jour via l'API data.gouv.fr `/api/1/datasets/<id>/`).
- place-emploi-public.gouv.fr : d'après mes connaissances antérieures (non vérifié dans cette recherche), elle a été fusionnée dans Choisir le service public vers 2022-2023. Ce n'est plus une source séparée.
- EURES : la seule piste est un endpoint non documenté. Statut juridique et stabilité inconnus ; faible priorité.
- Effort estimé : CSP open data, moyen (gros CSV, correspondance des colonnes, filtre local, pas d'auth) ; EURES, moyen à élevé et incertain.

### Gaps
- Colonnes exactes du CSV CSP et sens de l'export (offres en ligne ou cumul) : la documentation PDF/XLSX n'a pas été lue.
- CGU et robots.txt de choisirleservicepublic.gouv.fr pour une éventuelle étape « détail ».
- Statut actuel de place-emploi-public.gouv.fr : pas vérifié en ligne.
- Endpoint et conditions d'usage de l'API EURES : non trouvés de source officielle.
- Autres sources VIE ou internationales publiques : pas étudiées.
