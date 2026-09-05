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
gebouwd, en grondig getest.

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

Attribute-based access control is sinds april 2026 GA en schaalt dit: tag de data, hang een policy
aan een catalog of schema, en elk object met die tag valt eronder — inclusief tabellen die volgende
maand worden aangemaakt door iemand die niet weet dat de policy bestaat.

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
ergens op kan filteren.

> [!WARNING]
> **Een filter dat een kolom noemt die de index niet heeft, wordt genegeerd.** Geen error, geen
> waarschuwing — het beperkt gewoon niets meer, en de query geeft nog steeds een plausibel aantal
> rijen. Daarom toetsen we elke filtersleutel aan de kolommen die de index echt heeft.

## De ACL bouwen: vier beslissingen

De ACL wordt per request opgelost uit het token van de aanroeper zelf, met groepen uit SCIM met zijn
credentials. Een veertig regels, misschien.

![ACL-resolutie per request](../../diagrams/rendered/acl-flow.png)

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
default
serveert het hele corpus zodra iemand een variabele vergeet. Een kapotte mapping die naar leeg
degradeert lijkt precies op een terecht lege. Een groepsnaam los interpreteren geeft toegang weg aan
iedereen die een groep mag aanmaken — gemeten tegen echte workspace-groepen maakte dat van een
beheergroep een claim op een bronsysteem.

## On-behalf-of: welke identiteit Unity Catalog bereikt

Dat alles gaat ervan uit dat de agent weet wie het vraagt. On-behalf-of draagt de identiteit van de
aanroeper naar Unity Catalog in plaats van die van de deployer. Databricks Apps krijgt het token als
header binnen en bereikt de breedste scope inclusief Volumes; Model Serving houdt het in de runtime
en bereikt alles behalve Volumes. Teams levert helemaal geen Databricks-token — de Bot Framework
geeft een Entra-token terug, dat de bot inwisselt op `/oidc/v1/token` (RFC 8693).

> [!WARNING]
> Elke voorwaarde hier faalt zonder foutmelding: onder `mlflow` 2.22.1 staat OBO standaard uit, en
> een ontbrekende `databricks-ai-bridge` in de *gelogde* requirements laat de agent terugvallen op
> zijn eigen identiteit. Assert dus op de identiteit die het antwoord opleverde.

We hebben het gemeten: dezelfde gebruiker, dezelfde vraag, dezelfde modelversie, met de
groepsmapping als enige variabele. Gemapt op de echte groep van de aanroeper gaf retrieval rijen en
een onderbouwd antwoord terug. Gemapt op een groep waar niemand in zit: nul rijen en een uitgelegde
weigering, en het model werd nooit aangeroepen. `obo_active` gaf in beide runs `True`, wat het
rechtenfilter isoleert van het identiteitsloodwerk.

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

> [!WARNING]
> Op een niet-interactief pad ís de service principal je volledige toegangscontrole: iedere mens die
> via die integratie belt, ziet de vereniging van waar hij recht op heeft. Een review van dit pad
> moet dus de grants van die service principal nagaan.

## Aanbevelingen

Weet aan welke kant van de grens je zit. Een beheerde tabel wordt door het platform gehandhaafd en
een vectorindex door jou, en die verdienen een verschillende mate van vertrouwen.

![Keuze van het handhavingspad](../../diagrams/rendered/decision-tree.png)

Test daarna elke control tegen een geval waarin hij moet weigeren. Richt het filter op een waarde
die geen enkele rij draagt en controleer of het niets oplevert. Trek de grant in en controleer of
het antwoord verdwijnt. Zet de groep op eentje waar niemand in zit en controleer of het aantal rijen
naar nul gaat. Een control die je alleen hebt zien slagen, is een control die je niet hebt getest.

Row-level security over een RAG-agent is een reeks kleine ontwerpbeslissingen die allemaal soepel
samen moeten werken, en geen feature die je aanzet. Neem de tijd om uit te tekenen hoe je wilt dat je
agent zich bij elke stap gedraagt. En bouw grondige validaties in je testcyclus.

---

De [lange versie](../row-level-security.nl.md) bevat de metingen, de tabel met token-hops voor OBO, de Unity
Catalog-ontwerpvragen die we hebben uitgezocht, en de platformfeatures die nog in preview zijn. De
map [`examples/`](../../examples/) bevat uitvoerbare demonstraties van elke fout hierboven.

## Benieuwd hoe andere teams toegangscontrole op AI-toepassingen aanpakken?

We vergelijken graag notities over RAG, Unity Catalog en toegangscontrole per gebruiker op
Databricks. Neem contact op via [onedna.nl](https://onedna.nl) of
[LinkedIn](https://nl.linkedin.com/company/one-dna).

---

<sub>Geschreven door Sven Relijveld bij [OneDNA](https://onedna.nl). Kennisdelen zit in ons DNA.
Gemeten in een Databricks-sandbox in augustus en september 2026; identifiers en groepsnamen zijn
voor publicatie gegeneraliseerd.</sub>
