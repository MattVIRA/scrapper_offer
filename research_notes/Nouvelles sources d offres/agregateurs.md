# Agrégateurs et API de données d'emploi (France / Europe), alertes e-mail et RSS

Contexte : appli Python perso, un utilisateur, collecte quotidienne, SQLite. Une source implémente `collect()` et, idéalement, `online_offers()` (liste complète, pour détecter les offres retirées). Recherche faite le 2026-10-24, 15 appels d'outils. Une bonne partie des sources secondaires vient de JobsPipe (jobspipe.dev), **un fournisseur concurrent** : à recouper.

## Comparaison des options agrégateurs et API (couverture France, prix, auth, limites, champs, description complète, conditions, fraîcheur)

### Takeaway
Les meilleures options gratuites pour une appli perso sont des API d'« éditeur » (publisher/affiliate) : Adzuna (clé gratuite, quotas faibles, description tronquée), Careerjet (`fr_FR` = optioncarriere.com, compte partenaire requis) et Jooble (clé sur formulaire, extrait de description seulement). Aucune ne fournit la description complète, ni une liste complète permettant `online_offers()`. Les wrappers payants (SerpApi Google Jobs, JSearch, Apify, TheirStack, Coresignal) ont des offres gratuites très limitées et coûtent ensuite de 25 à 60 $/mois ou plus.

### Cited Findings

**Adzuna**
- Auth : deux paramètres obligatoires, `app_id` et `app_key`, obtenus à l'inscription. Formats JSON, JSONP, XML, HTML, XLSX — [Adzuna developer overview](https://developer.adzuna.com/overview)
- Endpoint `/v1/api/jobs/{country}/search/{page}` ; le pays est dans le chemin (exemple officiel : `gb`) — [Adzuna docs search](https://developer.adzuna.com/docs/search)
- Champs de réponse dans les exemples officiels : `id`, `redirect_url`, `description`, `created`, `contract_type`, `contract_time`, `title`, `salary_min`, `salary_max`, `location`, `company`, `category`, `latitude`, `longitude` — [Adzuna docs search](https://developer.adzuna.com/docs/search)
- Description tronquée : selon la doc, Adzuna « currently only provide[s] a snipped of the job description » — [Adzuna docs search](https://developer.adzuna.com/docs/search). Une page tierce le confirme, sans donner la longueur — [JobsPipe, Adzuna API](https://jobspipe.dev/blog/adzuna-api)
- Limites par défaut : 25 appels/minute, 250/jour, 1 000/semaine, 2 500/mois. Des limites plus hautes se négocient avec Adzuna (pas de prix public). Il y a 16 pays, avec la meilleure couverture au Royaume-Uni et en Europe de l'Ouest. Inscription gratuite ; essai de 14 jours pour les organisations commerciales, gouvernementales ou académiques, puis licence éventuelle — [JobsPipe, Adzuna API](https://jobspipe.dev/blog/adzuna-api) (source secondaire, concurrent)
- `redirect_url` passe par Adzuna avant d'arriver à l'offre d'origine — [JobsPipe, Adzuna API](https://jobspipe.dev/blog/adzuna-api)
- Endpoints dérivés : histogram, top_companies, categories, geodata, history — [JobsPipe, Adzuna API](https://jobspipe.dev/blog/adzuna-api)

**Careerjet**
- Client Python officiel `careerjet_api_client` (MIT, Careerjet Ltd). Paramètres obligatoires : `affid` (« Requires to open a Careerjet partner account »), `user_ip`, `user_agent`, `url` (page qui affiche les résultats) — [GitHub careerjet-api-client-python](https://github.com/careerjet/careerjet-api-client-python)
- Paramètres facultatifs : `keywords`, `location`, `sort` (relevance/date/salary), `page`, `pagesize`, `contracttype` (`p` CDI, `c` contrat, `t` intérim, `i` formation/stage, `v` bénévolat), `contractperiod` (temps plein ou partiel) — [GitHub careerjet-api-client-python](https://github.com/careerjet/careerjet-api-client-python)
- Locale `fr_FR` = optioncarriere.com ; environ 70 locales, dont `de_DE`, `es_ES`, etc. — [GitHub careerjet-api-client-python](https://github.com/careerjet/careerjet-api-client-python)
- Le README ne documente pas les champs de réponse, les limites ni les CGU de l'API — [GitHub careerjet-api-client-python](https://github.com/careerjet/careerjet-api-client-python)
- Des serveurs MCP tiers embarquent un `affid` par défaut codé en dur ; il vaut mieux créer le sien — [Glama, Careerjet MCPv2](https://glama.ai/mcp/servers/rftsngl/Careerjet_MCPv2)

**Jooble**
- Clé d'API obtenue via un formulaire (nom, poste, e-mail, site web, téléphone). La page ne documente ni endpoints, ni champs, ni quotas, ni pays — [Jooble API about](https://jooble.org/api/about)
- Requête POST en JSON (`keywords`, `location`) vers un endpoint qui contient la clé dans le chemin. Réponse : `totalCount` et un tableau `jobs` (titre, entreprise, lieu, extrait de description, salaire si connu, source, lien) — [JobsPipe, Jooble API](https://jobspipe.dev/blog/jooble-api.md). **Contradiction** : un autre guide décrit un GET avec paramètres — [publicapis.io](https://publicapis.io/jooble-api/)

**Talent.com, WhatJobs, Jobijoba**
- Talent.com : programme éditeur avec API job en libre-service, flux XML et liens d'affiliation ; plus de 30 M d'offres dans 79 pays. Cible : les sites d'emploi qui monétisent du trafic — [Talent.com Publisher Programs](https://employers.talent.com/publishers)
- WhatJobs : programme éditeur avec « FeedAPI » REST (JSON ou XML), plus des widgets — [WhatJobs publisher program](https://www.whatjobs.com/affiliates)
- Jobijoba : aucune documentation d'API publique ou partenaire trouvée ; seules des intégrations côté recruteur (ATS Manatal) existent — [Manatal, intégration Jobijoba](https://www.manatal.com/integrations/jobijoba)

**Google for Jobs via wrappers payants**
- SerpApi : 250 recherches/mois gratuites (une source plus ancienne dit 100, sans doute périmée). Starter à 25 $ pour 1 000 recherches/mois, Developer à 75 $ pour 5 000. Seules les recherches réussies sont facturées — [apiserpent, SerpApi pricing 2026](https://apiserpent.com/blog/serpapi-pricing-explained) ; [scrapegraphai, SerpApi pricing](https://scrapegraphai.com/blog/serpapi-pricing)
- Ces chiffres valent pour les plans SerpApi en général ; aucune source ne donne de tarif propre à Google Jobs — [apiserpent](https://apiserpent.com/blog/serpapi-pricing-explained)
- Autres fournisseurs d'un « Google Jobs SERP API » : DataForSEO, Bright Data — [DataForSEO](https://dataforseo.com/pricing/serp/google-jobs-serp-api) ; [Bright Data](https://brightdata.com/products/serp-api/google-search/jobs)

**RapidAPI / JSearch**
- JSearch a un plan gratuit (Basic sur RapidAPI) avec un petit quota mensuel, sans carte bancaire et avec un plafond dur. La facturation est à la requête, donc la pagination fait vite monter l'usage — [JobsPipe, is JSearch free](https://jobspipe.dev/answers/is-jsearch-api-free) (concurrent ; quota exact non trouvé)

**Apify (actors communautaires)**
- Exemples de prix pour les actors LinkedIn Jobs : à partir de 0,30 $ pour 1 000 offres (meka.im), 0,99 $ (crawlworks), 1 $ (practicaltools), 2,30 $ (truefetch), 5 $ (un autre) — [Apify meka.im](https://apify.com/meka.im/linkedin-jobs-scraper) ; [Apify crawlworks](https://apify.com/crawlworks/linkedin-job-scraper) ; [Apify practicaltools](https://apify.com/practicaltools/linkedin-jobs) ; [Apify truefetch](https://apify.com/truefetch/linkedin-job-search)
- Des actors existent aussi pour Adzuna (avec une option `descriptionMaxLength`), Jooble et Careerjet — [Apify Adzuna scraper](https://apify.com/blackfalcondata/adzuna-scraper) ; [Apify Jooble scraper](https://apify.com/parseforge/jooble-scraper) ; [Apify Careerjet](https://apify.com/nabeelbaghoor/careerjet-job-search-api.md)
- Ce sont des actors tiers, maintenus par la communauté : prix et fiabilité variables. Un utilisateur a signalé un coût de run inattendu — [Apify curious_coder issue](https://beta-securitybyobscurity.apify.com/curious_coder/linkedin-jobs-scraper/issues/this-scheduled-run-u-jhrRIMcQlQwMrhjz7)

**TheirStack**
- API : 200 crédits gratuits par mois ; plans payants dès 59 $/mois pour 1 500 crédits, jusqu'à 1 500 $/mois pour 1 M. Une offre = 1 crédit, une entreprise = 3 crédits ; les crédits expirent après 12 mois — [TheirStack pricing](https://theirstack.com/de/pricing)
- Le prix des offres a été divisé par 3 ; depuis le 4 juin 2025, la liste des technologies n'apparaît plus dans les réponses de recherche d'offres — [TheirStack blog](https://theirstack.com/en/blog/jobs-are-now-up-to-3x-cheaper)

**Coresignal**
- Selon la doc officielle : essai de 7 jours avec 2 000 crédits, 5 requêtes/s. **Contradiction** : la page de prix annonce 200 crédits valables 14 jours. Plan d'entrée à 49 $/mois pour 250 crédits — [Coresignal docs pricing](https://docs.coresignal.com/pricing) ; [Coresignal pricing](https://coresignal.com/pricing)
- Une source tierce indique 1 crédit par offre d'emploi et 10 par fiche employé ou entreprise — [apiserpent, Coresignal pricing](https://apiserpent.com/blog/coresignal-pricing-explained)

### Inferences
- Pour un usage gratuit et quotidien, Adzuna tient dans le quota : environ 10 recherches × 2 à 5 pages par jour, sous la limite de 250/jour et 2 500/mois. Attention, 2 500/mois ≈ 83/jour en moyenne : c'est la limite mensuelle qui contraint, pas la journalière.
- D'après mes connaissances antérieures, **non vérifiées ici** : Adzuna couvre bien la France (`fr`), avec `results_per_page` maximal de 50, et la réponse Careerjet contient `url`, `title`, `description` (extrait), `company`, `locations`, `date`, `salary`. À confirmer avec un appel réel.
- Careerjet exige `user_ip`, `user_agent` et `url` comme pour un site web. Une appli locale doit envoyer des valeurs plausibles ; il faut vérifier que les CGU partenaire l'acceptent.
- Les API d'éditeur (Careerjet, Jooble, Talent.com, WhatJobs) sont faites pour des sites qui redirigent du trafic payé au clic. Un usage personnel sans site public sort peut-être de leur cadre ; à lire dans leurs CGU.
- TheirStack et Coresignal visent la veille commerciale (B2B, technologies des entreprises). Ils sont surdimensionnés et trop chers pour l'usage visé ; 200 crédits TheirStack ≈ 200 offres/mois.
- Apify et les scrapers LinkedIn reviennent à scraper par un intermédiaire : les CGU de LinkedIn restent en jeu, ce que le projet voulait éviter.

### Gaps
- La liste officielle des pays Adzuna, le `results_per_page` maximal et la longueur de l'extrait n'ont pas été lus dans la doc officielle (les pages activedocs et terms n'ont pas été ouvertes).
- Les CGU Adzuna, Careerjet et Jooble pour un usage personnel non commercial n'ont pas été lues.
- Le quota exact du plan gratuit JSearch, et sa couverture de la France, sont introuvables.
- Le crédit gratuit de la plateforme Apify (souvent cité à 5 $/mois) n'a pas été confirmé.
- La fraîcheur des données (délai d'indexation) n'a été trouvée pour aucun agrégateur.
- L'API officielle France Travail (offres d'emploi, francetravail.io) n'a pas été étudiée ici ; elle est probablement couverte par un autre chercheur.

## Identifiants stables, liens vers l'offre d'origine, doublons

### Takeaway
Adzuna fournit un `id` et un `redirect_url` qui passe par Adzuna. Pour Jooble, la source décrit un lien sans confirmer d'identifiant. Aucun agrégateur ne permet de lister toutes ses offres, donc `online_offers()` est irréalisable de façon fiable. Il faudra dédoublonner entre sources, car les mêmes offres reviennent sur plusieurs agrégateurs.

### Cited Findings
- Adzuna : un champ `id` figure dans les exemples de réponse — [Adzuna docs search](https://developer.adzuna.com/docs/search) ; `redirect_url` passe par Adzuna avant l'offre d'origine — [JobsPipe, Adzuna API](https://jobspipe.dev/blog/adzuna-api)
- Jooble : chaque offre a un lien et un nom de source ; aucun champ de date `updated` n'est confirmé — [JobsPipe, Jooble API](https://jobspipe.dev/blog/jooble-api.md)
- JSearch facture à la requête ; paginer sur de nombreuses requêtes coûte cher — [JobsPipe, is JSearch free](https://jobspipe.dev/answers/is-jsearch-api-free)

### Inferences
- Les API sont des recherches paginées, plafonnées par des quotas : on ne voit que les résultats de ses requêtes, jamais tout le catalogue. Il faut donc gérer « Plus en ligne » par l'absence d'une offre pendant N jours, ou ne pas le gérer. La règle du projet n'autorise « Plus en ligne » que si la source donne sa liste complète ; ces sources doivent donc renvoyer « liste incomplète » (pas de `online_offers()`).
- La règle des 95 % (lecture incomplète) peut s'appliquer par requête à partir du total annoncé (`count` chez Adzuna, `totalCount` chez Jooble), mais pas sur l'ensemble de la source.
- Un même poste revient par Adzuna, Jooble, Careerjet et le site d'origine, avec des identifiants différents et des liens de redirection différents. Le dédoublonnage du projet (`duplicates`) devra se faire sur titre + entreprise + ville, pas sur l'URL.
- La stabilité des identifiants Adzuna, Jooble et Careerjet dans le temps n'est pas documentée. Il vaut mieux garder l'identifiant de la source et une clé normalisée de secours.

### Gaps
- Aucune documentation officielle sur la stabilité des identifiants dans le temps.
- Pas de mesure publique du taux de doublons entre agrégateurs.

## Alertes e-mail et flux RSS comme alternative légale au scraping

### Takeaway
Les flux RSS d'Indeed ne sont plus utilisables de façon fiable : des outils tiers signalent qu'Indeed les bloque, sans annonce officielle trouvée. Lire par IMAP les alertes e-mail (LinkedIn, WTTJ, APEC, etc.) est faisable avec `imaplib`, mais il n'existe pas de parseur prêt à l'emploi. Les e-mails ne contiennent que des liens et des résumés, leur HTML change sans préavis, et la détection des offres retirées est impossible.

### Cited Findings
- Indeed : l'auteur d'un plugin WordPress (Go Fetch Jobs) indique qu'Indeed a commencé à bloquer les requêtes vers ses flux et que le plugin affiche désormais un avertissement et propose d'autres fournisseurs (fil non daté) — [WordPress.org support](https://wordpress.org/support/?p=16478097) ; même symptôme chez JobRoller — [AppThemes forum](https://forums.appthemes.com/report-jobroller-bugs/indeed-feed-no-longer-working-23641/)
- Aucune annonce officielle d'Indeed sur la fin des flux RSS n'a été trouvée (même recherche).
- Alertes LinkedIn : un article décrit un filtrage serverless en Python (SES + Lambda) dont la première étape consiste à extraire les URL des offres du HTML de l'e-mail d'alerte — [levelup.gitconnected](https://levelup.gitconnected.com/filtering-linkedin-job-alerts-with-serverless-python-62bdd07cb81d)
- Outils IMAP réutilisables : `email-monitor` (PyPI, IMAP + API Gmail en OAuth2) — [PyPI email-monitor](https://pypi.org/project/email-monitor) ; ApplyPotato (suivi de candidatures via Gmail, pas un parseur d'alertes) — [GitHub apply-potato](https://github.com/coolbrother/apply-potato)
- Des services commerciaux de parsing d'e-mails (Parseur) proposent ce cas d'usage — [Parseur](https://parseur.com/de/anwendungsfall/jobsuche-automatisierung-mit-parseur)
- Exemple de contrainte d'un site d'emploi : deux alertes au plus par adresse e-mail, avec une fréquence choisie (Tanitjobs) — [Tanitjobs aide](https://www.tanitjobs.com/aide-candidat/alertes-emploi/)

### Inferences
- Lire ses propres e-mails est légalement sûr : l'utilisateur reçoit ces alertes. Suivre ensuite les liens pour récupérer la description revient à scraper.
- Mise en œuvre : une boîte dédiée (ou un libellé Gmail), un mot de passe d'application ou OAuth, puis `imaplib` en Python standard et un parseur par expéditeur (LinkedIn, WTTJ, APEC, Indeed, HelloWork...). Chaque parseur casse quand le gabarit de l'e-mail change.
- Inconvénients : seulement le titre, l'entreprise, le lieu et un lien (souvent avec traceur) ; aucune liste complète, donc pas de `online_offers()` ; filtrage limité aux critères de l'alerte ; les identifiants doivent être extraits des URL (l'identifiant d'offre LinkedIn est dans l'URL, à vérifier) ; un accès IMAP demande un identifiant à stocker (sensible).
- Les identifiants IMAP sont des secrets : ils doivent rester hors du dépôt, conformément aux règles « Données sensibles » du projet.

### Gaps
- Fonctionnement et fréquence des alertes Welcome to the Jungle et APEC : rien trouvé dans les sources publiques. Il faut consulter leurs centres d'aide ou un compte candidat.
- Aucun flux RSS officiel actuel n'a été confirmé pour WTTJ, APEC ou HelloWork.
- Les CGU de LinkedIn sur le traitement automatisé de ses e-mails d'alerte n'ont pas été vérifiées.

## Options adaptées au VIE, à l'international et aux jeunes diplômés

### Takeaway
Aucun agrégateur n'a de filtre VIE. Le mieux est de chercher par mots-clés (« VIE », « V.I.E », « graduate », « jeune diplômé », « junior ») sur Adzuna et Careerjet par pays : les deux couvrent plusieurs pays européens, et Careerjet a un filtre `contracttype=i` (formation). Business France reste la seule source complète des VIE.

### Cited Findings
- Careerjet : environ 70 locales, une par site national (`fr_FR`, `de_DE`, `es_ES`...), et un filtre `contracttype` qui inclut `i` (formation) — [GitHub careerjet-api-client-python](https://github.com/careerjet/careerjet-api-client-python)
- Adzuna : 16 pays, meilleure couverture au Royaume-Uni et en Europe de l'Ouest, pays dans le chemin de l'URL — [JobsPipe, Adzuna API](https://jobspipe.dev/blog/adzuna-api)
- Talent.com : 79 pays — [Talent.com Publisher Programs](https://employers.talent.com/publishers)
- Google for Jobs (via SerpApi) agrège les offres indexées par Google, mais 250 recherches gratuites par mois limitent le nombre de requêtes par pays et par mot-clé — [apiserpent](https://apiserpent.com/blog/serpapi-pricing-explained)

### Inferences
- Les VIE sont publiés par Business France (déjà collecté). Les agrégateurs n'en reprendront que les copies diffusées par les entreprises ou les cabinets, d'où des doublons avec la source existante plutôt que des offres nouvelles.
- Pour les offres « similaires » (graduate programmes, postes juniors à l'étranger), une source Adzuna multi-pays (fr, de, gb, nl, be...) avec quelques mots-clés offre le meilleur rapport valeur/coût dans le quota gratuit. Careerjet complète la France via optioncarriere.com.
- Les alertes e-mail LinkedIn et WTTJ ciblées « junior / international » donnent un complément sans scraping, mais sans description complète.

### Gaps
- Aucune source ne mesure la présence des offres VIE ou graduate sur Adzuna, Jooble ou Careerjet.
- Les programmes de type VIE dans d'autres pays (par exemple les graduate programmes de l'UE, EPSO ou Blue Book) n'ont pas été couverts ici.
