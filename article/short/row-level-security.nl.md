# Row-level security in een Databricks RAG-agent

*Sven Relijveld, OneDNA, september 2026*

**📖 [Lees de lange versie](../row-level-security.nl.md)** · **🇬🇧 [Read this article in English](row-level-security.md)**

---

Twee collega's stellen dezelfde chatbot dezelfde vraag. Horen ze hetzelfde antwoord te krijgen, of
een verschillend antwoord omdat ze verschillende dingen mogen zien? Elke organisatie die een
AI-assistent op haar eigen documenten zet, loopt hier vroeg of laat tegenaan.

Zo'n systeem hebben we op Databricks gebouwd: een RAG-keten over een beheerd corpus, bereikbaar
vanuit applicaties buiten Databricks, met toegangscontrole per gebruiker. RAG op de native AI Search
(voorheen Vector Search) heeft geen voorziening voor row-level security, dus hebben we het zelf
gebouwd. Het vertrekpunt was [Mastering RAG Chatbot Security: ACL and Metadata Filtering with Mosaic
AI Vector
Search](https://community.databricks.com/t5/technical-blog/mastering-rag-chatbot-security-acl-and-metadata-filtering-with/ba-p/101946),
dat chunks tagt met een metadatakolom en een bijpassende waarde als queryfilter meegeeft. Die post
geeft die waarde met de hand mee; wat wij eraan moesten toevoegen was hem uit de aanroeper afleiden.

## AI RAG-agent en indexontwikkeling

Het systeem bestaat uit twee delen. **Build** is waar data wordt voorbereid en agents worden
ontwikkeld: het draait op een schema en schrijft de index. Documenten komen binnen vanuit
SharePoint, en een pipeline parset, chunkt, verrijkt en embedt ze, met één beheerd Unity
Catalog-artefact per stap. **Serve** is waar agents en indexen worden uitgerold en aangeroepen
— een live requestpad dat alleen leest.

![AI RAG-agent en indexontwikkeling](../../diagrams/rendered/build-and-serve.png)

We willen rechten op querymoment afdwingen, binnen in de agent, en ze niet inbakken in wat er
geïndexeerd wordt. Dat betekent dat je geen aparte indexen nodig hebt voor verschillende
doelgroepen. De ruil is dat de toegangsbeslissing nu plaatsvindt in code die jij hebt geschreven aan
de serve-kant, tegen metadatakolommen die je aan de build-kant hebt gekozen.

## Row-level security op tabellen

Hang een row filter en een column mask aan een tabel en iedere lezer krijgt zijn eigen beeld ervan.
Het filter is een UDF die per query draait en kijkt naar wie de vraag stelt.

```sql
CREATE FUNCTION project_group_filter(project_group STRING)
RETURN is_account_group_member('group-water-delta') AND project_group = 'water-delta'
    OR is_account_group_member('group-projects-all');

ALTER TABLE project_hours SET ROW FILTER project_group_filter ON (project_group);
```

We hebben bevestigd dat het naar de aanroeper kijkt en niet naar de tabeleigenaar, en het daarna
getest: de body vervangen door `RETURN project_group = 'NON_EXISTING_GROUP'` — een groep die geen
enkele rij draagt — moet iedereen niets teruggeven, en dat deed het. Met het origineel terug kwamen
de rijen weer. Een filter dat eraan hangt, is niet per se een filter dat draait. `DESCRIBE TABLE
EXTENDED` vertelt je dát het bestaat; het veranderen vertelt je dat het wérkt.

Op een beheerde tabel stapelen vier mechanismen, en het helpt om te weten welke vraag elk ervan
beantwoordt:

| Mechanisme | De vraag die het beantwoordt |
| --- | --- |
| Object privileges | mag je deze tabel überhaupt aanraken? |
| ABAC-policy | welke regel geldt hier, op tag, over de hele catalog? |
| Row filter | welke rijen krijg jij terug? |
| Column mask | welke waarden daarin mag jij lezen? |

Attribute-based access control is sinds april 2026 GA en schaalt dit: tag de data, hang een policy
aan een catalog of schema, en elk object met die tag valt eronder — inclusief tabellen die volgende
maand worden aangemaakt door iemand die niet weet dat de policy bestaat. Het patroon dat we nu
overal gebruiken is standaard alles op catalogniveau taggen met `classification: unverified` en een
policy schrijven die alles met die tag weigert, zodat nieuwe tabellen dicht zijn tot iemand ze
classificeert.

## De index neemt de filters niet over

Een AI Search-index is een Unity Catalog-object met grants, dus je kunt bevragen toestaan of
weigeren. Er zitten geen row filters en geen column masks op. Een index filteren is een parameter
die je vanuit applicatiecode meegeeft.

![Governance-grens: tabel naar index](../../diagrams/rendered/governance-boundary.png)

Een document gaat op weg naar de index door parsing, chunking en embedding, en de security-context
bereikt de index niet. Een embedding is een rij floats. Wat aankomt, is wat je bewust in
metadatakolommen ernaast hebt weggeschreven — dus je ACL kan nooit expressiever zijn dan de kolommen
die je bij het indexeren hebt meegenomen. Kies je dat verkeerd, dan is de reparatie een rebuild in
plaats van een grant.

Die kolommen zijn ook een randvoorwaarde voor de build-kant en niet iets van de retrieval. Hun
waarden komen meestal uit het bronsysteem, dus de pipeline moet erbij kunnen voordat de serve-kant
ergens op kan filteren. Bij Witteveen+Bos haalden we de SharePoint-metadata als aparte stap over de
Graph API op en joinden die later op de chunks; de Databricks SharePoint-connector stelt inmiddels
`_sharepoint_metadata` direct beschikbaar, waarmee die join verdwijnt. Dat vereist DBR 18 LTS: op
17.3 slaagt de read nog steeds, maar zonder metadatavelden.

Het bijbehorende probleem is dat metadata content **is**. Als je `created_by_email` of `web_url` als
ophaalbare kolom indexeert, zijn die waarden zichtbaar voor iedereen die de index mag bevragen, of
ze de chunktekst nu mogen lezen of niet. De ACL moet toeslaan vóórdat welke kolom dan ook terugkomt,
niet alleen vóór de chunktekst.

> [!WARNING]
> **Een filter dat een kolom noemt die de index niet heeft, wordt genegeerd.** Geen error, geen
> waarschuwing — het beperkt gewoon niets meer, en de query geeft nog steeds een plausibel aantal
> rijen. Daarom toetsen we elke filtersleutel aan de kolommen die de index echt heeft.

## De ACL bouwen: vier beslissingen

De ACL wordt per request opgelost uit het token van de aanroeper zelf, met groepen uit SCIM met zijn
credentials. Een veertig regels, misschien.

![ACL-resolutie per request](../../diagrams/rendered/acl-flow.png)

De groepen komen uit één call, met het token van de aanroeper zelf in de header:

```python
def groups_for(token: str) -> list[str]:
    # Vraag Databricks wie de aanroeper is, als de aanroeper.
    req = urllib.request.Request(
        f"{WORKSPACE}/api/2.0/preview/scim/v2/Me",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    return [g["display"] for g in body.get("groups", [])]
```

Het token van de aanroeper gebruiken in plaats van dat van het endpoint is waar het om draait:
niemand kan een lidmaatschap claimen dat hij niet heeft, omdat hij niet degene is die de vraag
beantwoordt. Een 401 is hier een routinegebeurtenis — een verlopen token — dus wat deze functie bij
een fout doet, bepaalt wat een fout verleent. Wij geven niets terug.

> [!NOTE]
> `/Me` geeft directe lidmaatschappen terug. Een workspace-lokale groep kan een Entra-groep als lid
> hebben, dus iemand kan transitief lid zijn van een groep die deze call niet noemt.

- **Leeg betekent niets, niet alles.** Een aanroeper zonder gemapte groepen haalt niets op, en een
  deployment waar niemand de mapping heeft ingevuld serveert niets aan iedereen.
- **Een kapotte configuratie raist.** Een mapping die niet parset stopt het request in plaats van
  naar leeg te degraderen, zodat de twee toestanden uit elkaar te houden zijn.
- **Een aanroeper zonder rechten bereikt het model nooit.** Die krijgt een expliciete weigering, en
  geen antwoord dat uit de algemene kennis van het model is samengesteld.
- **Waar rechten uit komen is een schaalbeslissing.** Een naamconventie werkt, en het is wat we bij
  Witteveen+Bos hebben opgeleverd. Zodra de toegang van een aanroeper een combinatie van kolommen
  is, is een gedeclareerde tabel het mechanisme dat meeschaalt.

Van elk daarvan bestaat een alternatief dat toegang geeft in plaats van weigert. Een permissieve
default serveert het hele corpus zodra iemand een variabele vergeet. Een kapotte mapping die naar
leeg degradeert lijkt precies op een terecht lege. Een groepsnaam los interpreteren geeft toegang
weg aan iedereen die een groep mag aanmaken — gemeten tegen echte workspace-groepen maakte dat van
een beheergroep een claim op een bronsysteem.

Twee gewoonten kwamen uit het twee keer bouwen hiervan. Merge het rechtenfilter van de aanroeper
óver eventuele filters die de aanroeper zelf meegeeft in plaats van eronder, en wikkel een
meegegeven boolean in een `and`; anders kan een aanroeper zijn eigen ACL verbreden door een filter
mee te geven, en ziet het gelukkige pad er in beide gevallen hetzelfde uit. Houd het token in de
`Authorization`-header en niet in de request body, zodat niets dat payloads logt hem kan opvangen,
inference tables inbegrepen.

## On-behalf-of: welke identiteit Unity Catalog bereikt

Dat alles gaat ervan uit dat de agent weet wie het vraagt. De agent draait ergens — een serving
endpoint, een app, een container — en dat ding heeft een eigen identiteit. On-behalf-of draagt de
identiteit van de aanroeper naar Unity Catalog in plaats van die van de deployer.

Twee hosts kunnen de keten draaien, en één verschil bepaalt welke:

| | Databricks Apps | Model Serving |
| --- | --- | --- |
| Token komt binnen als | `x-forwarded-access-token`-header | in handen van de serving runtime |
| Code haalt het op via | de header lezen | `ModelServingUserCredentials()` |
| Bereikt | de breedste scope, inclusief UC Volumes | index, warehouses, tabellen, Genie — **niet** Volumes |

Zodra de keten een bestand aanraakt, moet Apps de host zijn. Schrijf de keten zo dat hij niet weet
op welke host hij draait, en dan blijft dat een configuratiewijziging.

Vóór beide hosts zit wat de gebruiker opent, en geen daarvan is Databricks. Teams levert helemaal
geen Databricks-token: de Bot Framework OAuth-prompt geeft een **Entra**-token terug, dat Databricks
op workspace-API's weigert, dus wisselt de bot het in op `/oidc/v1/token` (RFC 8693) en roept het
endpoint aan met het resultaat. Die exchange vereist een federatiebeleid op accountniveau dat de
issuer en audience vertrouwt, plus vier Entra-instellingen: `preferred_username` als optionele
access-token-claim, `requestedAccessTokenVersion` 2, een `access_as_user`-scope, en de Bot
Framework-redirect-URI.

> [!WARNING]
> Elke voorwaarde hier faalt zonder foutmelding: onder `mlflow` 2.22.1 staat OBO standaard uit, en
> een ontbrekende `databricks-ai-bridge` in de *gelogde* requirements laat de agent terugvallen op
> zijn eigen identiteit. Assert dus op de identiteit die het antwoord opleverde.

We hebben het gemeten: dezelfde gebruiker, dezelfde vraag, dezelfde modelversie, met de
groepsmapping als enige variabele. Gemapt op de echte groep van de aanroeper gaf retrieval rijen en
een onderbouwd antwoord terug. Gemapt op een groep waar niemand in zit: nul rijen en een uitgelegde
weigering, en het model werd nooit aangeroepen. `obo_active` gaf in beide runs `True`, wat het
rechtenfilter isoleert van het identiteitsloodwerk — zonder die vlag kan een nul "terecht geweigerd"
of "identiteit kapot" betekenen, en is er geen manier om te zien welke van de twee.

De run mét rechten leverde ook iets op waar we niet op testten. Gevraagd wat het corpus over een
bepaalde ontwerpvraag besluit, antwoordde de agent dat de documenten dat niet besluiten en noemde de
vraag onbeslist, in plaats van er een te verzinnen. Dat is alleen te controleren tegen een echt
corpus met echte gaten erin, want synthetische testdata beantwoordt elke vraag die je bedacht toen
je hem schreef.

## Genie als tweede retrieval-pad

Vraag hoeveel uren er per projectgroep zijn geboekt en een similarity search over proza geeft
passages terug, en geen enkel aantal passages telt op tot een totaal. Daarom heeft de agent een
tweede retrieval-pad: prozavragen gaan naar similarity search, aantallen en totalen naar een
Genie-space die SQL genereert tegen beheerde tabellen. Beide draaien op de credentials van de
aanroeper.

![Row-level security in een Databricks RAG-pipeline](../../diagrams/rendered/architecture.png)

Wat verschilt, is wie handhaaft. Op de prozatak is dat onze gedeclareerde grants, en de reden dat je
een passage krijgt is "een van jouw groepen liet hem toe". Op de datatak is het Unity Catalog, en de
reden is "Unity Catalog heeft jou gecontroleerd", met de gegenereerde SQL en een statement-id als
bewijs.

We hebben getest of de identiteit van de aanroeper standhoudt over de hops naar Genie, en dat doet
hij op elk pad dat we konden bouwen. Query history schrijft het statement toe aan de mens op het
interactieve pad, via de agent onder OBO, en vanuit Teams — dat een derde hop toevoegt via Entra en
de token-exchange. In elk geval noemt `executed_as_user_name` de persoon, en niet de service
principal van het endpoint.

> [!WARNING]
> Op een niet-interactief pad ís de service principal je volledige toegangscontrole: iedere mens die
> via die integratie belt, ziet de vereniging van waar hij recht op heeft. Een review van dit pad
> moet dus de grants van die service principal nagaan.

Er is een configuratieroute naar hetzelfde punt. Databricks documenteert dat een service principal
toegang geven tot een Genie-space ook vereist dat je de onderliggende tabellen en warehouse
verleent. Volg die richtlijn voor een agent en het endpoint houdt een staande grant op de data, dus
ziet iedere aanroeper de vereniging van wat het endpoint mag lezen. Onder user authorization heb je
die grants niet nodig; voeg ze niet toe.

## Aanbevelingen

Weet aan welke kant van de grens je zit. Een beheerde tabel wordt door het platform gehandhaafd en
een vectorindex door jou, en die verdienen een verschillende mate van vertrouwen.

Welk pad je krijgt volgt uit twee vragen — of de content gestructureerd is, en of je ACL past op de
kolommen die je mee de index in kunt nemen:

![Keuze van het handhavingspad](../../diagrams/rendered/decision-tree.png)

Test daarna elke control tegen een geval waarin hij moet weigeren. Richt het filter op een waarde
die geen enkele rij draagt en controleer of het niets oplevert. Trek de grant in en controleer of
het antwoord verdwijnt. Zet de groep op eentje waar niemand in zit en controleer of het aantal rijen
naar nul gaat. Een control die je alleen hebt zien slagen, is een control die je niet hebt getest.

Row-level security over een RAG-agent is een reeks kleine ontwerpbeslissingen die allemaal soepel
samen moeten werken, en geen feature die je aanzet. Neem de tijd om uit te tekenen hoe je wilt dat je
agent zich bij elke stap gedraagt. En bouw grondige validaties in je testcyclus.

---

De [lange versie](../row-level-security.nl.md) bevat de metingen, de tabel met token-hops voor OBO,
de Unity Catalog-ontwerpvragen die we hebben uitgezocht, en de platformfeatures die nog in preview
zijn. De map [`examples/`](../../examples/) bevat uitvoerbare demonstraties van elke fout hierboven.

## Benieuwd hoe andere teams toegangscontrole op AI-toepassingen aanpakken?

We vergelijken graag notities over RAG, Unity Catalog en toegangscontrole per gebruiker op
Databricks. Neem contact op via [onedna.nl](https://onedna.nl) of
[LinkedIn](https://nl.linkedin.com/company/one-dna).

---

<sub>Geschreven door Sven Relijveld bij [OneDNA](https://onedna.nl). Kennisdelen zit in ons DNA.
Gemeten in een Databricks-sandbox in augustus en september 2026; identifiers en groepsnamen zijn
voor publicatie gegeneraliseerd.</sub>
