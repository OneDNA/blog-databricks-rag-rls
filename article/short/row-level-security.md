# Row-level security in a Databricks RAG agent

*Sven Relijveld, OneDNA, september 2026*

**📖 [Read the long version](../row-level-security.md)** · **🇳🇱 [Lees dit artikel in het Nederlands](row-level-security.nl.md)**

---

Two colleagues ask the same chatbot the same question. Should they get the same answer, or
different ones because they are allowed to see different things? Every organisation that puts an AI
assistant on top of its own documents runs into this sooner or later.

We built such a system on Databricks: a RAG chain over a governed corpus, reachable from
applications outside Databricks, with access control per user. RAG on the native AI Search (formerly
Vector Search) has no feature for row-level security, so we built it ourselves. The starting point
was [Mastering RAG Chatbot Security: ACL and Metadata Filtering with Mosaic AI Vector
Search](https://community.databricks.com/t5/technical-blog/mastering-rag-chatbot-security-acl-and-metadata-filtering-with/ba-p/101946),
which tags chunks with a metadata column and passes a matching value as a query filter. That post
passes the value in by hand; the piece we had to add was resolving it from the caller.

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

Four mechanisms stack on a governed table, and it helps to know which question each answers:

| Mechanism | The question it answers |
| --- | --- |
| Object privileges | may you touch this table at all? |
| ABAC policy | which rule applies, by tag, across the whole catalog? |
| Row filter | which rows come back for you? |
| Column mask | which values in them are readable by you? |

Attribute-based access control went GA in April 2026 and scales this: tag the data, attach a policy
to a catalog or schema, and every object carrying the tag is covered — including tables created next
month by somebody who does not know the policy exists. The pattern we now use everywhere is to tag
everything `classification: unverified` at the catalog level and write a policy refusing anything
still carrying that tag, so new tables are closed until somebody classifies them.

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
anything. At Witteveen+Bos we pulled the SharePoint metadata over the Graph API as a separate step
and joined it onto the chunks later; the Databricks SharePoint connector now exposes
`_sharepoint_metadata` directly, which removes that join. It needs DBR 18 LTS: on 17.3 the read
still succeeds, with every metadata field absent.

The related problem is that metadata **is** content. If you index `created_by_email` or `web_url` as
a retrievable column, those values are visible to anyone who can query the index, whether or not
they can read the chunk text. The ACL has to apply before any column comes back, not just before the
chunk body does.

> [!WARNING]
> **A filter naming a column the index does not have is ignored.** No error, no warning — it just
> stops constraining, and the query still returns a plausible row count. So we assert every
> filter's keys against the columns the index actually has, and raise rather than warn.

## Building the ACL: four decisions

The ACL resolves per request from the caller's own token, with groups from SCIM using their
credentials. Perhaps forty lines.

![ACL resolution per request](../../diagrams/rendered/acl-flow.png)

The groups come from one call, with the caller's own token in the header:

```python
def groups_for(token: str) -> list[str]:
    # Ask Databricks who the caller is, as the caller.
    req = urllib.request.Request(
        f"{WORKSPACE}/api/2.0/preview/scim/v2/Me",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    return [g["display"] for g in body.get("groups", [])]
```

Using the caller's token rather than the endpoint's is the whole point: nobody can claim a
membership they do not have, because they are not the one answering the question. A 401 here is a
routine event — an expired token — so what this function does on failure decides what an error
grants. We return nothing.

> [!NOTE]
> `/Me` returns direct memberships. A workspace-local group can have an Entra-sourced group as a
> member, so somebody can be a transitive member of a group this call does not list.

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

Two habits came out of building this twice. Merge the caller's entitlement filter over any
caller-supplied filters rather than under them, and wrap a caller-supplied boolean in an `and`;
otherwise a caller can widen their own ACL by passing a filter, and the happy path looks identical
either way. Keep the token in the `Authorization` header rather than the request body, so nothing
that logs payloads can capture it, inference tables included.

## On-behalf-of: which identity reaches Unity Catalog

All of that assumes the agent knows who is asking. The agent runs somewhere — a serving endpoint,
an app, a container — and that thing has an identity of its own. On-behalf-of carries the caller's
identity to Unity Catalog instead of the deployer's.

Two hosts can run the chain, and one difference settles which:

| | Databricks Apps | Model Serving |
| --- | --- | --- |
| Token arrives as | `x-forwarded-access-token` header | held by the serving runtime |
| Code obtains it via | read the header | `ModelServingUserCredentials()` |
| Reaches | the widest scope, including UC Volumes | index, warehouses, tables, Genie — **not** Volumes |

The moment the chain touches a file, Apps has to be the host. Write the chain so it does not know
which host it is on and that stays a configuration change.

In front of either host sits whatever the user opens, and none of those are Databricks. Teams never
yields a Databricks token: the Bot Framework OAuth prompt returns an **Entra** token, which
Databricks rejects on workspace APIs, so the bot exchanges it at `/oidc/v1/token` (RFC 8693) and
calls the endpoint with the result. That exchange needs an account-level federation policy trusting
the issuer and audience, plus four Entra settings — `preferred_username` as an optional
access-token claim, `requestedAccessTokenVersion` 2, an `access_as_user` scope, and the Bot
Framework redirect URI.

> [!WARNING]
> Every prerequisite here fails with no error message: below `mlflow` 2.22.1 OBO is off by default,
> and `databricks-ai-bridge` missing from the *logged* requirements drops the agent back to its own
> identity. So assert on the identity that produced the answer, not on whether an answer arrived.

We measured it: same user, same question, same model version, with the group mapping as the only
variable. Mapped to the caller's real group, retrieval returned rows and a grounded answer. Mapped
to a group nobody is in, zero rows and an explained denial, and the model was never called.
`obo_active` reported `True` in both runs, which isolates the entitlement filter from the identity
plumbing — without that flag a zero could mean "correctly denied" or "identity broken", and there
would be no way to tell which.

The entitled run also told us something we were not testing for. Asked what the corpus decides about
a particular design question, the agent answered that the documents do not decide it and called the
question unresolved, rather than inventing one. That is only checkable against a real corpus with
real gaps in it, because synthetic test data answers every question you thought to ask when you
wrote it.

## Genie as a second retrieval path

Asked how many hours were booked per project group, a similarity search over prose returns passages,
and no number of passages adds up to a total. So the agent has a second retrieval path: prose
questions go to similarity search, counts and totals go to a Genie space generating SQL against
governed tables. Both run on the caller's credentials.

![Row-level security in a Databricks RAG pipeline](../../diagrams/rendered/architecture.png)

What differs is who enforces. On the prose branch it is our declared grants, so the reason you got
a passage is "one of your groups allowed it". On the data branch it is Unity Catalog, so the reason
is "Unity Catalog checked you", with the generated SQL and a statement id as evidence.

We tested whether the caller's identity holds across the hops into Genie, and it does on every path
we could construct. Query history attributes the statement to the human on the interactive path,
through the agent under OBO, and from Teams — which adds a third hop through Entra and the token
exchange. In each case `executed_as_user_name` names the person, not the endpoint's service
principal.

> [!WARNING]
> On a non-interactive path the service principal is the whole of your access control: every human
> calling through that integration sees the union of what it was granted. So a review of this path
> has to check the service principal's grants.

There is a configuration route to the same place. Databricks documents that granting a service
principal access to a Genie space also requires granting its underlying tables and warehouse. Follow
that guidance for an agent and the endpoint holds a standing grant on the data, so every caller sees
the union of what the endpoint may read. Under user authorisation you do not need those grants; do
not add them.

## Recommendations

**Know which side of the boundary you are on.** A governed table is enforced by the platform and a
vector index is enforced by you, and those deserve different amounts of confidence.

**Carry the columns at index time.** Your ACL can never be more expressive than the metadata you
wrote alongside the chunks, and adding one later means a rebuild.

**Deny on error.** Make "no entitlement" and "something broke" tell themselves apart, so a zero row
count is diagnosable.

**Check the service principal, not the feature.** On any non-interactive path the SP is the whole
of your access control, whatever row-level security is switched on.

Which path you land on follows from two questions — whether the content is structured, and whether
your ACL fits the columns you can carry into the index:

![Enforcement path selection](../../diagrams/rendered/decision-tree.png)

Then test each control against a case where it has to deny. Point the filter at a value no row
carries and check it returns nothing. Revoke the grant and check the answer disappears. Set the
group to one nobody is in and check the row count goes to zero. A control you have only seen
succeed is a control you have not tested.

Row-level security over a RAG agent is a series of small design decisions that all have to work
together smoothly, rather than a feature you switch on. Take time to map out how you want your agent
to behave at every step. And build thorough validations into your testing cycle.

---

The [long version](../row-level-security.md) has the measurements, the OBO token-hop table, the
Unity Catalog design questions we worked through, and the platform features still in preview. The
[`examples/`](../../examples/) directory has runnable demonstrations of each failure above.

## Curious how other teams handle access control on AI applications?

We are always glad to compare notes on RAG, Unity Catalog and per-user access control on
Databricks. Get in touch via [onedna.nl](https://onedna.nl) or
[LinkedIn](https://nl.linkedin.com/company/one-dna).

---

<sub>Written by Sven Relijveld at [OneDNA](https://onedna.nl). Sharing knowledge is in our DNA.
Measured in a Databricks sandbox during August and September 2026; identifiers and group names
generalised for publication.</sub>
