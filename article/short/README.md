# Row-level security in a Databricks RAG agent

*Sven Relijveld, OneDNA, september 2026*

**📖 [Read the long version](../README.md)** · **🇳🇱 [Lees dit artikel in het Nederlands](README.nl.md)**

---

Two colleagues ask the same chatbot the same question. Should they get the same answer, or
different ones because they are allowed to see different things? Every organisation that puts an AI
assistant on top of its own documents runs into this sooner or later.

We built such a system on Databricks: a RAG chain over a governed corpus, reachable from
applications outside Databricks, with access control per user. RAG on the native AI Search
(formerly Vector Search) has no feature for row-level security, so we built it ourselves, and
tested it thoroughly.

## AI RAG agent and index development

The system consists of two parts. **Build** is where data is prepared and agents are developed: it
runs on a schedule and writes the index. Documents arrive from SharePoint, and a pipeline parses,
chunks, enriches and embeds them, writing one governed Unity Catalog artefact per stage. **Serve**
is where agents and indexes are deployed and called — a live request path that only reads.

![AI RAG agent and index development](../../diagrams/rendered/build-and-serve.png)

We want to enforce permissions at query time, inside the agent, rather than baking them into what
gets indexed. This means you do not need separate indexes for different audiences. The trade is that
the access decision now happens in code you wrote on the serve side, against metadata columns you
chose on the build side.

## Row-level security on tables

Attach a row filter and a column mask to a table and every reader gets their own view of it. The
filter is a UDF that runs per query and resolves against whoever is asking.

```sql
CREATE FUNCTION project_group_filter(project_group STRING)
RETURN is_account_group_member('group-water-delta') AND project_group = 'water-delta'
    OR is_account_group_member('group-projects-all');

ALTER TABLE project_hours SET ROW FILTER project_group_filter ON (project_group);
```

We confirmed it resolves against the caller and not the table owner, then tested it: replacing the
body with `RETURN project_group = 'NON_EXISTING_GROUP'` — a group no row carries — has to return
nothing to everybody, and it did. Restoring the original brought the rows back. A filter that is
attached is not necessarily a filter that runs. `DESCRIBE TABLE EXTENDED` tells you it exists;
changing it tells you it works.

Attribute-based access control went GA in April 2026 and scales this: tag the data, attach a policy
to a catalog or schema, and every object carrying the tag is covered — including tables created next
month by somebody who does not know the policy exists.

## The index does not inherit the filters

An AI Search index is a Unity Catalog object with grants, so you can allow or deny querying it. It
has no row filters and no column masks. Filtering an index is a parameter you pass from application
code.

![Governance boundary: table to index](../../diagrams/rendered/governance-boundary.png)

A document travels through parsing, chunking and embedding on its way to the index, and the security
context does not reach the index. An embedding is a list of floats. What arrives is what you
deliberately wrote into metadata columns alongside it — so your ACL can never be more expressive
than the columns you carried at index time. Get that wrong and the fix is a rebuild
rather than a grant.

Those columns are also a build-side prerequisite, not a retrieval concern. Their values usually come
from the source system, so the pipeline has to reach them before the serve side can filter on
anything.

> [!WARNING]
> **A filter naming a column the index does not have is ignored.** No error, no warning — it just
> stops constraining, and the query still returns a plausible row count. So we assert every
> filter's keys against the columns the index actually has, and raise rather than warn.

## Building the ACL: four decisions

The ACL resolves per request from the caller's own token, with groups from SCIM using their
credentials. Perhaps forty lines.

![ACL resolution per request](../../diagrams/rendered/acl-flow.png)

- **Empty means nothing, not everything.** A caller with no mapped groups retrieves nothing, and a
  deployment where nobody configured the mapping serves nothing to everybody.
- **A malformed configuration raises.** A mapping that will not parse stops the request rather than
  resolving to empty, so the two states are told apart.
- **An unentitled caller never reaches the model.** They get an explicit denial, rather than an
  answer assembled from the model's general knowledge.
- **Where entitlements come from is a scale decision.** A naming convention works, and it is what we
  shipped at Witteveen+Bos. Once a caller's access is a combination of columns, a declared table is
  the mechanism that scales.

Each has an alternative that grants access instead of refusing it. A permissive default serves the
whole corpus the first time somebody forgets a variable. A malformed mapping degrading to empty
looks exactly like a correctly empty one. Parsing a group's name loosely hands access to anyone who
can create a group — measured against real workspace groups, that turned an administration group
into a claim on a source system.

## On-behalf-of: which identity reaches Unity Catalog

All of that assumes the agent knows who is asking. On-behalf-of carries the caller's identity to
Unity Catalog instead of the deployer's. Databricks Apps receives the token as a header and reaches
the widest scope including Volumes; Model Serving holds it in the runtime and reaches everything
except Volumes. Teams never yields a Databricks token at all — the Bot Framework returns an Entra
token, which the bot exchanges at `/oidc/v1/token` (RFC 8693).

> [!WARNING]
> Every prerequisite here fails with no error message: below `mlflow` 2.22.1 OBO is off by default,
> and `databricks-ai-bridge` missing from the *logged* requirements drops the agent back to its own
> identity. So assert on the identity that produced the answer, not on whether an answer arrived.

We measured it: same user, same question, same model version, with the group mapping as the only
variable. Mapped to the caller's real group, retrieval returned rows and a grounded answer. Mapped
to a group nobody is in, zero rows and an explained denial, and the model was never called.
`obo_active` reported `True` in both runs, which isolates the entitlement filter from the identity
plumbing.

## Genie as a second retrieval path

Asked how many hours were booked per project group, a similarity search over prose returns passages,
and no number of passages adds up to a total. So the agent has a second retrieval path: prose
questions go to similarity search, counts and totals go to a Genie space generating SQL against
governed tables. Both run on the caller's credentials.

![Row-level security in a Databricks RAG pipeline](../../diagrams/rendered/architecture.png)

What differs is who enforces. On the prose branch it is our declared grants, so provenance
means "one of your groups admitted this passage". On the data branch it is Unity Catalog, so
provenance means "Unity Catalog evaluated you", with the generated SQL and a statement id as
evidence.

> [!WARNING]
> On a non-interactive path the service principal is the whole of your access control: every human
> calling through that integration sees the union of what it was granted. So a review of this path
> has to check the service principal's grants.

## Recommendations

Know which side of the boundary you are on. A governed table is enforced by the platform and a
vector index is enforced by you, and those deserve different amounts of confidence.

![Enforcement path selection](../../diagrams/rendered/decision-tree.png)

Then test each control against a case where it has to deny. Point the filter at a value no row
carries and check it returns nothing. Revoke the grant and check the answer disappears. Set the
group to one nobody is in and check the row count goes to zero. A control you have only seen
succeed is a control you have not tested.

Row-level security over a RAG agent is a series of small design decisions that all have to work
together smoothly, rather than a feature you switch on. Take time to map out how you want your agent
to behave at every step. And build thorough validations into your testing cycle.

---

The [long version](../README.md) has the measurements, the OBO token-hop table, the Unity Catalog
design questions we worked through, and the platform features still in preview. The
[`examples/`](../../examples/) directory has runnable demonstrations of each failure above.

## Curious how other teams handle access control on AI applications?

We are always glad to compare notes on RAG, Unity Catalog and per-user access control on
Databricks. Get in touch via [onedna.nl](https://onedna.nl) or
[LinkedIn](https://nl.linkedin.com/company/one-dna).

---

<sub>Written by Sven Relijveld at [OneDNA](https://onedna.nl). Sharing knowledge is in our DNA.
Measured in a Databricks sandbox during August and September 2026; identifiers and group names
generalised for publication.</sub>
