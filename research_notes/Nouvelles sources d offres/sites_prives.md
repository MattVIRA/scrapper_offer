# Sites d'emploi privés et pages carrières ATS : accès technique et contraintes juridiques

Contexte : application personnelle Python (un seul utilisateur, une collecte par jour sur macOS, stockage SQLite). Une source doit fournir `collect()`, et si possible `online_offers()` (liste complète pour repérer les offres retirées), plus une étape « détail » facultative. Recherche faite le 24/10/2026, sans lancer de scraper : lecture de pages publiques, robots.txt et documentation seulement. Avertissement général : beaucoup de sources techniques sont des vendeurs de scrapers (Apify, JobsPipe, Scrapfly) ; elles sont citées comme telles et peuvent présenter les choses à leur avantage.

## 1. API officielles, API partenaires, flux RSS/XML ou alertes e-mail, site par site

### Takeaway
Aucun des grands sites d'emploi privés (Indeed, LinkedIn, WTTJ, HelloWork, Jobteaser, Cadremploi, Meteojob, Glassdoor, Monster, Jobijoba) n'offre d'API publique en libre-service pour *lire* les offres. Les seules API ouvertes et documentées sont celles des ATS (Greenhouse, Lever, Teamtailor en RSS, et SmartRecruiters en partie), qui donnent les offres d'une entreprise à la fois.

### Cited Findings
**Indeed**
- L'API Publisher d'Indeed (recherche d'offres) est fermée : arrêt en 2023 selon la plupart des sources, en 2024 selon d'autres. Rien ne la remplace pour lire les données : il reste un widget de recherche en iframe et un programme de partenariat d'entreprise, sous NDA et via les commerciaux. Les API actuelles servent aux employeurs (par ex. Job Sync API, pour *publier* des offres). Sources : [JobsPipe, guide API Indeed](https://jobspipe.dev/blog/indeed-api-guide), [100hires, Indeed API 2026](https://100hires.com/indeed-api.html), [JobsPikr](https://www.jobspikr.com/blog/beyond-indeed-api-discovering-powerful-alternatives-for-job-aggregation). Ce sont des vendeurs concurrents, et je n'ai pas pu vérifier sur la documentation d'Indeed.
- Le robots.txt d'Indeed bloque `/rss` et `/*?rss` pour tous les robots : les anciens flux RSS de recherche ne sont plus utilisables proprement. — [indeed.com/robots.txt](https://www.indeed.com/robots.txt) (consulté le 24/10/2026, version .com ; celle de fr.indeed.com n'a pas été vérifiée)

**LinkedIn**
- LinkedIn n'a pas d'API publique en libre-service pour chercher ou lire des offres ; les « LinkedIn jobs API » de tiers enrobent les pages publiques. — [linkedapi.io, guide 2026](https://linkedapi.io/guides/linkedin-jobs-scraper)
- Je n'ai pas trouvé de source qui confirme une « API Jobs réservée aux partenaires » (pour la *lecture* d'offres). Voir Gaps.

**Welcome to the Jungle (WTTJ) / Welcome Kit**
- L'API de WTTJ (Welcome Kit) passe par un jeton statique délivré par le support de WTTJ, avec des droits fixés à sa création. Lister et lire les offres se fait *par organisation* (droit `jobs_r`). L'action « List All Jobs (Public Job Board) » demande un droit de partenariat (`su_jobs_r`). C'est donc une API côté employeur ou partenaire, pas un accès public. — [StackOne, connecteur Welcome to the Jungle](https://docs.stackone.com/connectors/welcometothejungle)
- Le robots.txt indique un seul sitemap, `https://www.welcometothejungle.com/sitemaps/index.xml.gz` (un index, qui renvoie sans doute à des sitemaps d'offres ; non vérifié). — [welcometothejungle.com/robots.txt](https://www.welcometothejungle.com/robots.txt)

**HelloWork**
- Aucun flux RSS ni API public trouvé. Le robots.txt déclare un sitemap, `https://www.hellowork.com/fr-fr/horizon.xml`, et bloque les pages d'alertes (`/fr-fr/offres/alertes`). — [hellowork.com/robots.txt](https://www.hellowork.com/robots.txt)
- Les alertes e-mail existent sur le site (chemin `/fr-fr/offres/alertes`, même source), mais je n'ai pas vérifié leur format ni leur fréquence.

**Jobteaser**
- Aucune API publique trouvée pour les offres. — [Apify, JobTeaser scrapers (recherche)](https://apify.com/shahidirfan/jobteaser-job-scraper)

**Cadremploi, Meteojob, Jobijoba, Monster, Glassdoor**
- Aucune API ni aucun flux RSS officiel trouvé pour Cadremploi et Meteojob ; il n'existe que des scrapers tiers sur Apify. Ma recherche n'a rien donné pour Jobijoba et Monster. — [Apify, Cadremploi scraper](https://apify.com/unfenced-group/cadremploi-scraper), [Apify, Meteojob scraper](https://apify.com/trev0n/meteojob-scraper.md)

**ATS (pages carrières des entreprises)** : détail au point 4.
- Greenhouse : API Job Board publique et documentée, GET sans authentification. — [Greenhouse Job Board API docs](https://docs.greenhouse.io/job-board.html)
- Teamtailor : flux RSS public documenté (`/jobs.rss`). — [Teamtailor support, RSS feed how-to](https://support.teamtailor.com/en/articles/11171756-rss-feed-how-to-guide)

### Inferences
- Pour Indeed, LinkedIn, WTTJ, HelloWork et les autres, il ne reste que les points d'accès internes du site web (non documentés, fragiles) ou les alertes e-mail lues dans une boîte mail. Les alertes sont plus robustes juridiquement, puisque l'utilisateur les reçoit lui-même, mais elles ne permettent pas `online_offers()`, car elles ne donnent pas la liste complète.
- Les sitemaps XML (WTTJ, HelloWork) sont publiés pour les robots et pourraient servir de liste complète des offres en ligne, donc de base à `online_offers()`, à condition de vérifier qu'ils contiennent bien les URL des offres et qu'ils sont à jour.

### Gaps
- Statut actuel (2026) d'un éventuel programme partenaire LinkedIn pour lire les offres : aucune source primaire trouvée.
- Flux XML ou multidiffusion de HelloWork, Cadremploi, Meteojob et Jobijoba : ils existent sans doute pour recevoir les offres des employeurs, mais je n'ai trouvé aucune documentation publique de lecture.
- CGU complètes de chaque site non lues (voir point 3).
- Contenu exact des sitemaps WTTJ et HelloWork (présence des offres, fréquence de mise à jour) non vérifié, pour ne pas les télécharger.

## 2. Points d'accès JSON internes, protections anti-robots, rendu JavaScript, connexion

### Takeaway
WTTJ (Algolia) et LinkedIn (points d'accès « guest ») peuvent se lire sans connexion, en HTTP simple, mais ce n'est pas documenté. Jobteaser est protégé par DataDome. Indeed, LinkedIn et Glassdoor limitent fortement le débit. Pour un volume personnel (quelques recherches par jour), le risque technique est surtout la casse au premier changement du site.

### Cited Findings
**WTTJ**
- La recherche du site repose sur des requêtes Algolia publiques (XHR/fetch) ; des outils les rejouent pour paginer offres et entreprises. — [browse.sh, skill WTTJ](https://browse.sh/skills/welcometothejungle.com/scrape-job-company-data-yt3gr8)
- Un acteur Apify dit passer par « les mêmes API publiques que le site WTTJ », avec environ 1 000 offres par requête Algolia ; un autre recommande des proxys résidentiels pour la stabilité. — [Apify, blackfalcondata/wttj-scraper](https://apify.com/blackfalcondata/wttj-scraper.md), [Apify, alexmorain WTTJ](https://apify.com/alexmorain/wttj-jobs-scraper)
- Inférence non vérifiée : la clé Algolia de recherche, publique par construction, est visible dans le front-end. Aucune source ne le dit explicitement.

**LinkedIn**
- Points d'accès sans connexion : `/jobs-guest/jobs/api/seeMoreJobPostings/search` (liste) et `/jobs-guest/jobs/api/jobPosting/{id}` (détail). Ils renvoient des fragments HTML, pas du JSON, paginés par `start`, de 25 en 25. — [linkedapi.io](https://linkedapi.io/guides/linkedin-jobs-scraper), [JobsPipe, LinkedIn scraper Python](https://jobspipe.dev/blog/linkedin-job-scraper-python)
- Une source signale des HTTP 429 après une dizaine de pages depuis une même IP. — [linkedapi.io (md)](https://linkedapi.io/guides/linkedin-jobs-scraper.md). JobSpy parle de 429 en rafale, qui se lèvent au bout d'une minute environ. — [JobSpy README](https://github.com/speedyapply/JobSpy)
- Il faut des en-têtes de type navigateur. — [Apify blog, scrape LinkedIn jobs](https://blog.apify.com/scrape-linkedin-jobs/)

**Indeed**
- Le robots.txt bloque `/viewjob`, `/rss`, `/graphql`, `/rpc/`, ainsi que `/*&start=`, sauf `start=0` à `start=90`, explicitement permis, ce qui revient à 10 pages de résultats. Scrapy est entièrement bloqué par nom. — [indeed.com/robots.txt](https://www.indeed.com/robots.txt)
- JobSpy présente Indeed comme son scraper le plus fiable, sans limite de débit signalée. — [JobSpy README](https://github.com/speedyapply/JobSpy)

**Glassdoor**
- Limitation au-delà d'environ 2 requêtes par seconde (selon JobSpy). — [JobSpy README](https://github.com/speedyapply/JobSpy)
- Un exemple de Scrapfly (août 2026) montre une erreur Glassdoor (statut 400, « location not parsed »). — [Scrapfly, best open source job scrapers](https://scrapfly.io/blog/posts/best-open-source-job-scrapers)

**Jobteaser**
- Protégé par DataDome, qui renvoie une page « Security checkup » aux requêtes simples et à celles des centres de données ; un acteur Apify passe par un service payant de contournement (Bright Data Web Unlocker). — [Apify, JobTeaser scrapers](https://apify.com/shahidirfan/jobteaser-job-scraper)
- Je n'ai trouvé aucune information fiable sur l'obligation de se connecter avec un compte école (voir Gaps).

**HelloWork**
- Le robots.txt bloque les pages de recherche (`/fr-fr/emploi/recherche.html`, `/fr-fr/search/`), toute URL contenant `?` (sauf AdsBot-Google), et entièrement de nombreux aspirateurs (Wget, HTTrack, AhrefsBot, etc.). — [hellowork.com/robots.txt](https://www.hellowork.com/robots.txt)
- JobSpy gère HelloWork (France), avec un `location` en ville, code postal ou région. — [JobSpy README](https://github.com/speedyapply/JobSpy)

**WTTJ, robots.txt**
- Sont bloquées les URL `*/jobs?query=*` et, plus largement, `/*?`, donc toute URL avec paramètres. — [welcometothejungle.com/robots.txt](https://www.welcometothejungle.com/robots.txt)

**Cadremploi / Meteojob**
- Des scrapers Apify y accèdent sans clé d'API. Cadremploi compterait plus de 24 000 offres ; un acteur fournit un mode incrémental (NEW / UPDATED / REAPPEARED). — [Apify, unfenced-group Cadremploi](https://apify.com/unfenced-group/cadremploi-scraper), [Apify, blackfalcondata Cadremploi](https://apify.com/blackfalcondata/cadremploi-scraper)

### Inferences
- Indeed : la limite robots.txt à `start=90` (environ 10 pages) suggère qu'une recherche donne au plus une centaine de résultats par requête. `online_offers()` est donc impossible ; seule la détection par recherche l'est.
- LinkedIn « guest » : même limite pratique (429 vers la 10e page). Suffisant pour quelques recherches étroites par jour, pas pour une liste complète.
- WTTJ par Algolia : c'est le plus « propre » techniquement (JSON structuré, pas de rendu JS nécessaire), mais l'index, la clé ou le nom de l'application peuvent changer sans prévenir.
- Les mentions de DataDome, Cloudflare ou PerimeterX pour Indeed, Glassdoor, HelloWork, Cadremploi et Meteojob n'ont pas été confirmées par des sources lues ici.

### Gaps
- Fournisseur anti-robot exact pour Indeed, Glassdoor, Monster, Cadremploi, Meteojob, Jobijoba et HelloWork : non confirmé.
- Rendu JS nécessaire ou non (Next.js `__NEXT_DATA__`, GraphQL) pour HelloWork, Cadremploi, Meteojob, Monster et Jobijoba : non trouvé.
- Jobteaser : je n'ai pas pu confirmer si les offres complètes demandent un compte école (point avancé dans la question), faute de source.

## 3. CGU, robots.txt et cadre juridique (France / UE, comparaison avec les États-Unis) pour un usage personnel non commercial

### Takeaway
Dans l'UE, les CGU qui interdisent l'extraction automatisée sont opposables même quand la base n'est protégée ni par le droit d'auteur ni par le droit sui generis (CJUE, Ryanair, 2015). Pour un usage personnel, à faible volume, sans redistribution et sans données personnelles, le risque pratique est faible, mais il n'est pas nul si les CGU l'interdisent. Les API ATS publiques et les flux RSS sont la voie la plus sûre.

### Cited Findings
- **CJUE, Ryanair c. PR Aviation, C-30/14, 15/01/2015** : une base de données protégée ni par le droit d'auteur ni par le droit sui generis sort de la directive 96/9/CE ; son titulaire peut donc limiter par contrat (CGU) l'usage par des tiers, ici l'interdiction de l'extraction automatisée à des fins commerciales sans licence écrite. — [CMS, « Le titulaire d'une base de données non protégée peut en interdire l'usage commercial »](https://cms.law/fr/fra/legal-updates/le-titulaire-d-une-base-de-donnees-non-protegee-peut-en-interdire-l-usage-commercial), [Gowling WLG, 2015](https://gowlingwlg.com/en/insights-resources/articles/2015/ryanair-flying-high-at-the-cjeu)
- Droit sui generis (art. 7 de la directive 96/9) : il protège les bases qui ont demandé un investissement substantiel pour obtenir, vérifier ou présenter leur contenu. — [CMS (même article)](https://cms.law/fr/fra/legal-updates/le-titulaire-d-une-base-de-donnees-non-protegee-peut-en-interdire-l-usage-commercial)
- **CNIL** (recommandations du 19/06/2025, IA et intérêt légitime) : la collecte par moissonnage de données personnelles repose en général sur l'intérêt légitime, avec des garanties en plus. Les restrictions explicites des sites (CGU, robots.txt, CAPTCHA) jouent contre le traitement : passer outre empêche de rester dans les « attentes raisonnables » des personnes. — [CNIL, focus intérêt légitime et moissonnage](https://www.cnil.fr/fr/focus-interet-legitime-collecte-par-moissonnage), [CNIL, recommandations IA et intérêt légitime](https://cnil.fr/fr/recommandations-developpement-ia-interet-legitime)
- **hiQ c. LinkedIn (États-Unis)** : le jugement du 4/11/2022 donne tort à hiQ pour violation du *User Agreement* de LinkedIn ; hiQ avait gagné sur le CFAA (accès « non autorisé ») pour les données publiques. En décembre 2022, jugement d'accord à 500 000 $ et injonction permanente (arrêt du scraping, suppression du code et des données) ; ces stipulations, convenues entre les parties, ne font pas jurisprudence. — [Proskauer](https://www.proskauer.com/blog/hiq-and-linkedin-reach-proposed-settlement-in-landmark-scraping-case), [ZwillGen](https://www.zwillgen.com/alternative-data/hiq-v-linkedin-wrapped-up-web-scraping-lessons-learned/), [NatLawReview](https://www.natlawreview.com/article/linkedin-s-data-scraping-battle-hiq-labs-ends-proposed-judgment)
- **WTTJ** : les conditions de « WTTJ Solutions » (offre B2B, pas forcément applicables au site d'emploi grand public) exigent que tout accès automatisé respecte le robots.txt et les restrictions techniques sans surcharger les systèmes ; les systèmes d'IA peuvent indexer les contenus publics sous conditions (attribution) ; entraîner des modèles commerciaux demande une licence. — [WTTJ Solutions, Terms of use](https://solutions.welcometothejungle.com/en/terms-of-use)
- **robots.txt** (rappel, détails au point 2) : Indeed bloque `/viewjob`, `/rss`, `/graphql` ; HelloWork bloque la recherche et les URL à paramètres ; WTTJ bloque `/*?`. — [Indeed](https://www.indeed.com/robots.txt), [HelloWork](https://www.hellowork.com/robots.txt), [WTTJ](https://www.welcometothejungle.com/robots.txt)
- Les acteurs Apify pour Jobteaser renvoient eux-mêmes aux CGU et au robots.txt de Jobteaser, à la charge de l'utilisateur. — [Apify, JobTeaser](https://apify.com/shahidirfan/jobteaser-job-scraper)

### Inferences
- L'arrêt Ryanair visait un usage *commercial* ; pour un usage strictement personnel, à quelques requêtes par jour, l'enjeu contractuel est faible en pratique. La violation des CGU reste toutefois un manquement contractuel, et le risque concret est surtout le blocage d'IP ou de compte, pas une action en justice.
- Le droit sui generis interdit l'extraction ou la réutilisation d'une *partie substantielle* de la base ; quelques dizaines d'offres filtrées par jour pour soi ne semblent pas une partie substantielle. Ce n'est pas un avis juridique.
- Les offres contiennent parfois des données personnelles (nom et e-mail d'un recruteur). Ne pas les garder, ou les minimiser, réduit le risque RGPD. C'est déjà la règle du projet pour les fixtures.
- Contourner un dispositif anti-robot (DataDome sur Jobteaser) ou se connecter avec un compte pour récupérer en masse est à la fois le plus risqué juridiquement (CGU, et la CNIL l'interprète contre l'utilisateur) et le plus fragile. À éviter.
- Un accès avec compte (LinkedIn, Jobteaser) expose le compte personnel de l'utilisateur à une suspension : risque propre à un usage personnel.

### Gaps
- Le texte exact des CGU grand public de WTTJ, HelloWork, Indeed France, LinkedIn, Jobteaser, Cadremploi, Meteojob, Jobijoba, Monster et Glassdoor sur l'extraction automatisée n'a pas été lu (je n'ai trouvé que les conditions WTTJ Solutions).
- Jurisprudence française propre aux sites d'emploi (par ex. une affaire d'agrégateur d'offres) : non trouvée avec les requêtes faites.
- Effet de l'exception de fouille de textes et de données (art. 4 de la directive 2019/790, opt-out par robots.txt) sur un usage personnel : non étudié ici.

## 4. API publiques des ATS (Greenhouse, Lever, SmartRecruiters, Workday, Teamtailor, Welcome Kit)

### Takeaway
Greenhouse, Lever et Teamtailor (RSS) donnent sans clé la liste complète des offres publiées d'une entreprise, en JSON ou RSS : idéal pour `collect()` et `online_offers()` (liste complète). Workday passe par un point d'accès JSON non documenté mais stable et très utilisé. SmartRecruiters est ambigu (documentation officielle avec clé, accès sans clé selon des tiers). Welcome Kit demande un jeton employeur ou partenaire.

### Cited Findings
**Greenhouse (documenté, officiel)**
- « Job Board data is publicly available, so authentication is not required for any GET endpoints. » Seule la candidature (`POST .../jobs/{id}`) demande une clé (Basic Auth). — [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)
- Points d'accès : `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs` (avec `content=true`, on obtient description, départements et bureaux), `.../jobs/{job_id}` (`questions=true`, `pay_transparency=true`), `.../offices`, `.../departments`. Aucune limite de débit documentée sur cette page. — [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html)
- `board_token` est le segment d'URL de la page carrières (par ex. `boards.greenhouse.io/stripe`). — [Željko Šević, DEV](https://dev.to/zsevic/integration-with-greenhouse-public-jobs-api-1lj3)
- Certaines entreprises sont sur la région UE : `boards-api.eu.greenhouse.io`, à tenter en second. — [plin-code/job-boards-greenhouse (Packagist)](https://packagist.org/packages/plin-code/job-boards-greenhouse)

**Lever (public, documenté sur GitHub)**
- `GET https://api.lever.co/v0/postings/{site}?mode=json`, sans clé ; hôte UE `api.eu.lever.co`. Pagination `skip`/`limit` ; filtres équipe, département, lieu, `commitment`. Chaque offre a `id`, `text`, `hostedUrl`, `applyUrl`, `categories`, `workplaceType`, `country` et une description en texte. — [DEV, Lever public jobs API](https://dev.to/zsevic/integration-with-lever-public-jobs-api-2mnn), [100hires, Lever API 2026](https://100hires.com/lever-api.html)
- La spécification officielle serait sur github.com/lever/postings-api (cité par un tiers, non ouvert). Certaines entreprises désactivent ce point d'accès ; un tableau vide renvoie 200 avec `[]`. — [Apify, pappy-dev/lever-jobs](https://apify.com/pappy-dev/lever-jobs.md)

**SmartRecruiters (ambigu)**
- Documentation officielle de la « Public Posting API » : « supports both API Key and OAuth 2.0 Client Credentials authentication », avec le droit `internal_postings_read`. — [SmartRecruiters, Posting API](https://developers.smartrecruiters.com/docs/posting-api)
- Selon des tiers, `GET https://api.smartrecruiters.com/v1/companies/{companyId}/postings` répond sans authentification (pagination `limit`/`offset`, détail par `/postings/{id}`) ; l'identifiant, sensible à la casse, est le segment de jobs.smartrecruiters.com ; le flux public est désactivé pour certains forfaits ; limites de débit par IP. — [DEV, devil_scrapes SmartRecruiters](https://dev.to/devil_scrapes/smartrecruiters-jobs-scraper-pull-any-employers-postings-from-one-keyless-api-4hfd), [JobsPipe, SmartRecruiters](https://jobspipe.dev/sources/smartrecruiters)
- Contradiction non tranchée entre la documentation officielle et les tiers (voir Gaps).

**Workday (non documenté)**
- `POST https://<tenant>.<wdN>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs`, corps JSON `{limit, offset, searchText, appliedFacets}` ; tenant, numéro wdN et site se lisent dans l'URL de la page carrières (par ex. `salesforce.wd12` / `External_Career_Site`). — [DEV, Workday jobs scraper](https://dev.to/devil_scrapes/workday-jobs-scraper-how-to-pull-every-posting-from-any-workday-career-site-1dm0), [Apify, Workday scrapers](https://apify.com/crawlerbros/workday-jobs-scraper)
- Pages de 20 au plus (HTTP 400 au-delà) ; le `total` plafonne à 2 000 sur les gros sites ; le détail (`jobPostingInfo` : description HTML, pays, date) demande un GET par offre ; certains employeurs renvoient 403 aux IP de centres de données ; 429/503 et redirections de maintenance possibles. Ce sont des sources vendeurs. — mêmes sources ([Apify, khadinakbar](https://apify.com/khadinakbar/workday-jobs-scraper), [Apify, maydit](https://apify.com/maydit/workday-jobs-scraper))

**Teamtailor (RSS officiel)**
- Ajouter `.rss` à la page des offres (par ex. `https://career.teamtailor.com/jobs.rss`) ; 100 offres par défaut, `offset` et `per_page` pour aller plus loin ; on y trouve titre, description, URL, télétravail, identifiant global, lieux, département, rôle. — [Teamtailor support, RSS feed](https://support.teamtailor.com/en/articles/11171756-rss-feed-how-to-guide)
- L'API Teamtailor demande une clé créée par l'entreprise (Public / Internal / Admin) : inutilisable par un candidat ; le RSS suffit. — [Teamtailor support (FR)](https://support.teamtailor.com/fr/articles/5963369), [getknit.dev](https://getknit.dev/?p=1052)

**Welcome Kit (WTTJ)**
- Jeton statique délivré par le support de WTTJ ; lecture par organisation ; liste multi-entreprises réservée aux partenaires. — [StackOne, connecteur WTTJ](https://docs.stackone.com/connectors/welcometothejungle)

### Inferences
- Pour les ATS, `online_offers()` est naturel : chaque appel renvoie la liste complète des offres publiées de l'entreprise, donc on peut marquer « Plus en ligne » ce qui en disparaît, ce qui respecte la règle du projet. Le contrôle des 95 % peut se faire par le nombre d'éléments (Greenhouse renvoie `meta.total`, à vérifier ; Workday donne `total`, mais plafonné à 2 000).
- Configuration naturelle : une liste d'entreprises cibles `(ats, identifiant)` dans `config.yaml`, puis un filtrage local par mots-clés, pays ou ville, puisque ces API filtrent peu côté serveur (Workday a `searchText`).
- Les pages carrières sur Welcome Kit ou WTTJ sont fréquentes chez les entreprises françaises, mais sans API publique : il faudrait passer par Algolia (point 2) ou le HTML de la page carrières.

### Gaps
- Limites de débit officielles de Greenhouse et Lever : non documentées dans les pages lues.
- SmartRecruiters : le GET sans clé fonctionne-t-il en 2026 ? À vérifier par un seul appel manuel sur une entreprise connue.
- CGU de Workday sur l'usage du point d'accès cxs : non lues.
- Autres ATS fréquents en France (Ashby, Recruitee, Jobvite, Taleo, SAP SuccessFactors, Flatchr, Digitalrecruiters) : hors du périmètre lu ; Ashby a aussi une API publique selon un acteur Apify ([Apify, ATS Job Board Greenhouse/Lever/Ashby](https://apify.com/oddsmith/ats-job-board)), non vérifié.

## 5. Outils Python open source existants (JobSpy, etc.) et leur état

### Takeaway
JobSpy (`python-jobspy`, dépôt speedyapply/JobSpy, licence MIT, environ 4 600 étoiles) est l'outil de référence. Il couvre Indeed, LinkedIn, Glassdoor et HelloWork pour la France, renvoie un DataFrame pandas, plafonne autour de 1 000 offres par recherche et se fait bloquer sans pause entre requêtes ni proxy.

### Cited Findings
- Sites : LinkedIn, Indeed, Glassdoor, ZipRecruiter (États-Unis et Canada), Bayt, BDJobs, Naukri, **HelloWork (France)** ; Google Jobs figure dans les paramètres mais est « currently unavailable ». Pour la France : HelloWork directement, ou `country_indeed="France"` pour Indeed et Glassdoor. — [JobSpy README](https://github.com/speedyapply/JobSpy)
- État : environ 4 600 étoiles, 392 commits, 13 tickets ouverts, 21 PR ouvertes, licence MIT, aucune *release* GitHub ; date du dernier commit non visible. — [JobSpy GitHub](https://github.com/speedyapply/JobSpy)
- Paramètres : `fetch_description` (une requête de plus par offre, pour les descriptions absentes des listes) ; `linkedin_fetch_description`, obsolète, retiré en 2.0 ; `linkedin_company_ids` ; plafond d'environ 1 000 offres par recherche ; la FAQ conseille d'espacer les recherches et d'utiliser `proxies`. — [JobSpy README](https://github.com/speedyapply/JobSpy)
- Python 3.10 ou plus ; Indeed et Glassdoor demandent `country_indeed`. Un article Scrapfly d'août 2026 liste `linkedin, indeed, glassdoor, google, zip_recruiter, bayt, naukri, bdjobs` et montre une erreur Glassdoor dans son exemple. — [Scrapfly](https://scrapfly.io/blog/posts/best-open-source-job-scrapers), [PyPI python-jobspy](https://pypi.org/project/python-jobspy/1.1.54)
- Nombreuses copies (forks) au contenu variable. — [meliani/JobSpy](https://github.com/meliani/JobSpy), [nathan102030/jobspy](https://github.com/nathan102030/jobspy)
- Pour WTTJ, Cadremploi, Meteojob et Jobteaser, l'écosystème visible est fait d'acteurs Apify payants (de 1 à 5 $ pour 1 000 résultats), pas de bibliothèques Python open source repérées. — [Apify Cadremploi](https://apify.com/unfenced-group/cadremploi-scraper), [Apify Meteojob](https://apify.com/trev0n/meteojob-scraper.md), [Apify WTTJ](https://apify.com/nomad-jobs/wttj-scraper)

### Inferences
- JobSpy tire pandas et ses propres modèles ; on peut l'utiliser comme dépendance (adaptateur `Source` qui convertit le DataFrame) ou comme référence de code pour écrire une source ciblée (Indeed, HelloWork). La première option est plus rapide à écrire, mais rend dépendant des versions de JobSpy.
- JobSpy ne fournit pas de liste complète : avec lui, `online_offers()` n'est pas possible, il faut garder la règle « Plus en ligne » désactivée pour ces sources.

### Gaps
- Date de la dernière version PyPI et rythme de maintenance 2026 : non confirmés (aucune release GitHub, page PyPI récente non lue).
- Fiabilité réelle du scraper HelloWork de JobSpy : aucun retour d'expérience trouvé.
- Je n'ai trouvé aucun projet Python open source spécifique à WTTJ ou aux ATS (il en existe sans doute ; recherche non faite).

## 6. Effort et fragilité estimés par site

### Takeaway
Classement par rapport effort/robustesse pour cette application : ATS publics (Greenhouse, Lever, Teamtailor RSS, puis Workday) ≫ WTTJ (Algolia) ≈ Indeed et HelloWork via JobSpy > LinkedIn guest > Cadremploi, Meteojob, Jobijoba, Monster, Glassdoor (inconnus ou fragiles) > Jobteaser (DataDome, compte : à déconseiller).

### Cited Findings
(Synthèse des points 1 à 5 ; chaque ligne s'appuie sur les sources déjà citées.)

| Site | Méthode la plus réaliste | `online_offers()` | Effort | Fragilité / risque | Base |
|---|---|---|---|---|---|
| Greenhouse | API JSON officielle, sans clé | Oui (liste complète par entreprise) | Faible | Faible (API documentée) | [docs](https://docs.greenhouse.io/job-board.html) |
| Lever | API v0 postings, sans clé | Oui | Faible | Faible à moyenne (désactivable par l'entreprise) | [DEV](https://dev.to/zsevic/integration-with-lever-public-jobs-api-2mnn) |
| Teamtailor | RSS `/jobs.rss` | Oui (pagination `offset`/`per_page`) | Faible | Faible (fonction documentée) | [support](https://support.teamtailor.com/en/articles/11171756-rss-feed-how-to-guide) |
| Workday | POST `/wday/cxs/.../jobs` | Oui jusqu'à environ 2 000 offres (`total` plafonné) | Moyen (pages de 20, détail par offre) | Moyenne (non documenté, 403 possibles) | [DEV](https://dev.to/devil_scrapes/workday-jobs-scraper-how-to-pull-every-posting-from-any-workday-career-site-1dm0) |
| SmartRecruiters | GET postings (clé ou non, à vérifier) | Oui si accessible | Faible | Moyenne (statut de l'authentification incertain) | [docs](https://developers.smartrecruiters.com/docs/posting-api) |
| Welcome Kit | Pas d'API publique (jeton partenaire) | — | — | Bloqué | [StackOne](https://docs.stackone.com/connectors/welcometothejungle) |
| WTTJ | Algolia public (rejouer les requêtes du site) | Possible en théorie (index complet), non vérifié | Moyen | Moyenne (clé ou index modifiables ; robots.txt bloque `/*?`) | [browse.sh](https://browse.sh/skills/welcometothejungle.com/scrape-job-company-data-yt3gr8) |
| Indeed | JobSpy (`country_indeed="France"`) | Non (environ 10 pages par recherche) | Faible avec JobSpy | Moyenne (blocages ; CGU et robots défavorables) | [JobSpy](https://github.com/speedyapply/JobSpy), [robots](https://www.indeed.com/robots.txt) |
| HelloWork | JobSpy (site `hellowork`) ou sitemap | Peut-être via le sitemap `horizon.xml` (non vérifié) | Faible avec JobSpy | Moyenne (robots.txt bloque la recherche) | [JobSpy](https://github.com/speedyapply/JobSpy), [robots](https://www.hellowork.com/robots.txt) |
| LinkedIn | Points d'accès `jobs-guest` (HTML), sans connexion | Non | Moyen (analyse HTML) | Élevée (429, CGU strictes, précédent hiQ) | [linkedapi.io](https://linkedapi.io/guides/linkedin-jobs-scraper) |
| Glassdoor | JobSpy | Non | Faible avec JobSpy | Élevée (erreurs 400 constatées, limite de débit) | [Scrapfly](https://scrapfly.io/blog/posts/best-open-source-job-scrapers) |
| Cadremploi, Meteojob | HTML ou JSON interne (non étudié) ; alertes e-mail | Non connu | Moyen à élevé | Inconnue | [Apify Cadremploi](https://apify.com/unfenced-group/cadremploi-scraper) |
| Jobijoba, Monster | Non étudié (aucune source) | Non connu | Inconnu | Inconnue | — |
| Jobteaser | Déconseillé (DataDome, probable compte école) | Non | Élevé (contournement payant) | Très élevée et risque CGU | [Apify JobTeaser](https://apify.com/shahidirfan/jobteaser-job-scraper) |

### Inferences
- Le meilleur gain pour ce projet serait une source « ATS » générique (une classe par ATS, ou une source avec un adaptateur par ATS) qui lit une liste d'entreprises dans `config.yaml` : API stables, légales (prévues pour être lues publiquement), et compatibles avec la règle « Plus en ligne ».
- En second, Indeed et HelloWork via JobSpy, en acceptant que `online_offers()` manque et que la source puisse être bloquée de temps en temps ; la règle « une source en erreur n'arrête pas les autres » du pipeline couvre ce cas.
- WTTJ via Algolia : intéressant pour le marché français (startups, VIE parfois), à prototyper prudemment avec une requête par recherche et par jour.
- Jobijoba est un agrégateur (offres reprises d'autres sites) : faible intérêt s'il y a déjà Indeed et HelloWork. Je n'ai pas cherché de source pour le confirmer.

### Gaps
- Les estimations d'effort sont des jugements faits à partir de la documentation, pas de mesures (aucun prototype lancé, conformément à la consigne).
- Monster, Jobijoba, Cadremploi et Meteojob mériteraient une lecture de leurs CGU et une inspection manuelle (outils de développement du navigateur, une seule page) pour conclure.
