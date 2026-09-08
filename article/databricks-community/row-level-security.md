# Row-level security for a RAG agent: what Unity Catalog enforces, and what you have to build

*A OneDNA contribution. Written by Sven Relijveld, reviewed internally before submission.*

---

Two colleagues ask the same chatbot the same question. Should they get the same answer, or
different ones because they are allowed to see different things? Every organisation that puts an AI
assistant on top of its own documents runs into this sooner or later.

Unity Catalog has a good implementation for that on calls to tables. Attach a row filter and a
column mask, and every reader gets their own view of the same object, evaluated against whoever is
asking. It does not have a type of grant for row filters *inside* a vector index. An AI Search
index is a Unity Catalog object with object-level grants, so you can allow or deny querying it, but
it has no row filters and no column masks. Filtering an index is a parameter you pass in the query,
from your own application code.

Databricks documents this.

> "Row and column level permissions are not supported. However, you can implement your own
> application level ACLs using the filter API."
> — [Databricks AI Search documentation](https://docs.databricks.com/aws/en/vector-search/vector-search)

This post is about the implementation of this, and the caveats. We built per-user access control
over a governed corpus at a civil engineering consultancy, reachable from applications outside
Databricks — a custom web UI in that project, though a client like Microsoft Teams works the same
way once token federation is enabled. What follows is the design, the code, and the parts
that surprised us.

The starting point was [Mastering RAG Chatbot Security: ACL and Metadata Filtering with Mosaic AI
Vector
Search](https://community.databricks.com/t5/technical-blog/mastering-rag-chatbot-security-acl-and-metadata-filtering-with/ba-p/101946),
which tags chunks with a metadata column and passes a matching value as a query filter. That post
passes the value in by hand. Resolving it from the caller is the part we had to add.

The AI RAG system consists of two parts: a build part, where data is prepared and agents are
developed, and a serve part, where agents and indexes are deployed and called.

The first is the **build** path. It runs on a schedule and it is a batch pipeline. Documents arrive
from SharePoint or a fileshare where their owners publish them, and the pipeline walks them through
the medallion layers: landed raw, ingested to a table, parsed and chunked and enriched, then
combined and embedded into an index. Each stage writes one governed Unity Catalog artefact.

The second is the **serve** path. It is a live request path and it reads the index at inference
time. A question arrives from a web UI or another external client, the deployed agent resolves who
is asking, narrows retrieval to what that person may see, fetches from the index, and answers.

![AI RAG agent and index development](../../diagrams/rendered/build-and-serve.png)

## What Unity Catalog does for RLS on tables

Unity Catalog has four mechanisms for access on a governed table, and it helps to know which
question each answers:

| Mechanism | The question it answers |
| --- | --- |
| Object privileges | may you touch this table at all? |
| ABAC policy | which rule applies, by tag, across the whole catalog or schema? |
| Row filter | which rows come back for you? |
| Column mask | which values in them are readable by you? |

A row filter is a UDF that runs per query and resolves against the caller:

```sql
CREATE FUNCTION project_group_filter(project_group STRING)
RETURN is_account_group_member('group-water-delta') AND project_group = 'water-delta'
    OR is_account_group_member('group-projects-all');

ALTER TABLE project_hours SET ROW FILTER project_group_filter ON (project_group);
```

It resolves against the caller and not the table owner, and you can test it by replacing the body
with `RETURN project_group = 'NON_EXISTING_GROUP'` — a group no row has, so a working filter has to
return nothing to everybody.

That is important. A filter that is attached is not necessarily a filter that runs. `DESCRIBE TABLE
EXTENDED` tells you it exists; changing it and watching the results verifies that it works.

Attribute-based access control went GA in April 2026 and scales this past table-by-table
maintenance: tag the data, attach a policy to a catalog or schema, and every object with that tag
is covered, including tables created next month by another person.
`MATCH COLUMNS` finds the right column by tag rather than by name, so a table that spells it
`team_code` instead of `project_group` is still covered.

One ABAC pattern you can use for additional security: tag everything `classification: unverified`
by default at the catalog level, then write a policy that refuses anything still tagged that way.
New tables are then closed until somebody classifies them, rather than open until somebody notices.
The beta functionality of tag propagation and auto-tagging will help you implement this quickly.

## AI Search does not have native RLS capabilities

Point an AI Search index at those governed tables and the picture changes. ABAC governs *tables*.
Tag a table, embed its contents, and the index that results can take the grants but not the
row-level security. You need to explicitly add metadata columns to filter on to the source table,
and add filters to the query being sent to the index.

![Governance boundary: table to index](../../diagrams/rendered/governance-boundary.png)

A document travels through parsing, chunking, enrichment and embedding on its way to the index, and
the security context does not reach the index. What arrives is what you deliberately wrote into
metadata columns alongside it, which means your ACL can never be more expressive than the columns
you wrote at index time. Because a schema change leads to recreating the table, you might spend a
lot of tokens on reindexing your entire corpus. Those columns are a build-side prerequisite. Their
values usually come from the source system, so the pipeline has to reach them before the serve side
can filter on anything.

On that project we pulled SharePoint metadata over the Graph API as a separate step and joined it
onto the chunks later. The Databricks SharePoint connector now exposes `_sharepoint_metadata`
directly, which removes that join — it needs DBR 18 LTS, and on older versions the read still
succeeds with every metadata field absent.

A second caveat: metadata **is** content. If you index `created_by_email` or `web_url` as a
retrievable column, those values are visible to anyone who can query the index, whether or not they
can read the chunk text. The ACL has to apply before any column comes back, not just before the
chunk body does.

> [!WARNING]
> **A filter naming a column the index does not have refuses the query.** AI Search rejects an
> unknown filter column — `BadRequest: Columns referenced in filters are not present in index:
> sensitivty` — validating filter keys against the index contract. To check what your own index
> does, query it with a filter naming a column that does not exist and see whether you get rows,
> zero rows or an error.

We assert every filter's keys against the columns the index actually has, before the query goes
out, and raise rather than warn:

```python
def assert_enforceable(filters: dict[str, Any]) -> None:
    unenforceable = sorted(set(filters) - set(ACL_FILTER_COLUMNS))
    if unenforceable:
        raise PermissionError(
            f"filter columns {unenforceable} are not columns of the index source "
            f"{list(ACL_FILTER_COLUMNS)}, so the request cannot be filtered as intended."
        )
```

It lives in the ACL layer rather than the retriever, so every backend inherits it. Both backends
reject an unknown column on their own today, but a rule that only holds on one backend, or on one
month's behaviour, is not much of a rule.

## Resolving the caller

The filter value has to come from the person asking. That means one call, with the caller's own
token in the header:

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

We use the caller's token rather than the endpoint's, so nobody can claim a membership they do not
have, because they are not the one answering the question.

> [!NOTE]
> `/Me` returns direct memberships. A workspace-local group can have an Entra-sourced group as a
> member, so somebody can be a transitive member of a group this call does not list, and removing
> them from the outer group does not demote them.

![ACL resolution per request](../../diagrams/rendered/acl-flow.png)

Four decisions shaped that flow:

- **Empty means nothing, not everything.** A caller with no mapped groups retrieves nothing, and a
deployment where nobody configured the mapping serves nothing to everybody.
- **A malformed configuration raises.** A mapping that will not parse stops the request rather than
  resolving to empty, so the two states are told apart.
- **An unentitled caller never reaches the call to the index.** They get an explicit denial, rather
  than an answer assembled from the model's general knowledge.
- **Where entitlements come from is a scale decision.** A naming convention works and needs no
configuration at all. Once a caller's access is a combination of columns — e.g. a source system
*and* a site *and* a sensitivity — the name has to encode a tuple, and a declared grants table is needed.

Each has an alternative that grants access instead of refusing it, and each of those is a one-line
change. A 401 from SCIM is a routine event — an expired token — so what your error path returns
decides what a routine failure grants. Against real workspace group names, a rule that read an
entitlement out of any group whose name contained a known token turned an administration group into
a claim on a source system.

## Making sure the agent knows who is asking

All of that assumes the caller's identity reaches Unity Catalog rather than the deployer's.
On-behalf-of does that, and two things decide whether it works: which host runs the chain, and how
the token gets in.

| | Databricks Apps | Model Serving |
| --- | --- | --- |
| Token arrives as | `x-forwarded-access-token` header | held by the serving runtime |
| Code obtains it via | read the header | `ModelServingUserCredentials()` |
| Reaches | the widest scope, including UC Volumes | index, warehouses, tables, Genie — **not** Volumes |

The moment the chain touches a file, Apps has to be the host. Write the chain so it does not know
which host it is on and that stays a configuration change.

In front of either host sits whatever the user opens: a custom web UI, something like Microsoft
Teams, any client that is not Databricks. None of them can hold a Databricks token, so they all
need the same thing — **token federation**. Signing the user in with Entra gets you an Entra
token, which Databricks rejects on workspace APIs. Its server-side code exchanges that token at
`/oidc/v1/token`
(RFC 8693) and calls the endpoint with the result.

Enabling that exchange is account and tenant configuration, not code: an account-level federation
policy trusting the issuer and audience, and an Entra app registration that emits what the policy
expects — `preferred_username` as an optional access-token claim, `requestedAccessTokenVersion` 2,
and a scope it can request on the user's behalf.

> [!WARNING]
> Below `mlflow` 2.22.1 OBO is off by default and the agent answers as the endpoint. A
> `databricks-ai-bridge` missing from the *logged* requirements, rather than just the environment,
> drops the agent back to its own identity.

To test, you need to assert on the identity that produced the answer, not on whether an answer
arrived. A test that checks for a response passes identically whether every caller is being served
their own permissions or the deployer's.

## The results

Two colleagues, two projects, the same agent and the same two questions. Alice is on project Water
Delta; David is on Coastal North. Neither is an administrator, and neither is locked out — David
simply holds a grant on other data, which is the ordinary case.

![Same question, two callers](../../diagrams/rendered/chat-response.png)

Ask *how many hours did we book on Water Delta in Q2* and the question is quantitative, so it
routes to Genie and a SQL warehouse. Alice gets 1,240 hours across eight entries. David gets an
empty result, because Unity Catalog evaluated the row filter against his identity and the hours
table holds no Water Delta rows he can read.

Ask *what went wrong on Water Delta, and what did we learn* and the question is qualitative, so it
routes to the AI Search index. Alice gets six chunks and an answer citing the retrospective and the
closeout note. David gets nothing, because our code passed `{"project_group": "coastal-north"}` and
no chunk has that group attached.

Both of David's answers are empty, and while the answers look identical, they are slightly
different in mechanism. On the Genie path the platform decided, and it would have decided the same
way for any caller on any client. On the AI Search path *our filter* decided — and had we passed no
filter at all, he would have received Water Delta chunks with no error and no warning.

`obo_active` reads `true` in all four metadata boxes. Without it a zero could mean "correctly
filtered" or "identity broken", and the two are
indistinguishable from the answer alone. The same holds across hops: query history attributes the
statement to the human on the interactive path, through the agent under OBO, and from an external
front end, which adds a third hop through Entra and the token exchange. In each case
`executed_as_user_name` names the person, not the endpoint's service principal.

The diagram below puts both retrieval branches, and the identity work in front of them, on one
page. Border colour marks who enforces.

![Row-level security in a Databricks RAG pipeline](../../diagrams/rendered/architecture.png)

## Two things that surprised us
**Which tables you add to a Genie Agent (formerly a Genie space) is not a security control.** We
asked four times, across two identities, for a table we had deliberately not added, and Genie
refused every time and generated no SQL. That looks like enforcement, but it is the model declining
to name a table it was never shown, and a model update can change it without a release note.
Databricks does not document it as a limit on what Genie can reach. Rely on Unity Catalog grants
instead.

**A documented configuration path overrules on-behalf-of and takes the SP identity.** Granting a
service principal access to a Genie Agent also requires granting its underlying tables and
warehouse. Follow that for an agent and the endpoint holds a standing grant on the data, so every
caller sees the union of what the endpoint may read. Under user authorisation you do not need those
grants. `SystemAuthPolicy` should declare only the chat model; `UserAuthPolicy` handles the rest.

More generally, on any non-interactive path every caller retrieves what the service principal may
read. Every human calling
through that integration sees the union of what it was granted, with no differentiation. The
platform is behaving correctly and reporting the identity it was given, so the review question asks
what the service principal is granted, whatever row-level security is switched on.

## What we would tell a team starting this

**Understand where access control has to be enforced, and who owns it.** A governed table is
enforced by the platform; a vector index is enforced by whoever writes the retrieval code. That
splits the work between the index creator, who has to put the ACL columns there, and the agent
developer, who has to filter on them.

**Write the ACL columns at index time.** Your ACL can never be more expressive than the metadata
you put alongside the chunks, and adding one later means a rebuild.

**Make your failure modes explicit.** "No entitlement" and "expired token" are different events
that both return zero rows. Give each one its own signal, so you can tell from the answer which
one you are looking at.

**Check what the service principal is granted.** On any non-interactive path every caller
retrieves what the service principal may read.

Which path you land on follows from two questions — whether the content is structured, and whether
your ACL fits the columns you can get into the index:

![Enforcement path selection](../../diagrams/rendered/decision-tree.png)

Then test each control against a case where it has to deny. Point the filter at a value no row has
and check it returns nothing. Revoke the grant and check the answer disappears. Set the group to
one nobody is in and check the row count goes to zero. A control you have only seen succeed is a
control you have not tested.

> [!NOTE]
> **There is another way to do this.** Serve the vectors from pgvector on Lakebase instead of AI
> Search, and the ACL goes back to being a row-level security policy the database evaluates, so
> Postgres applies the filter rather than your retrieval code. It is not a like-for-like swap: a
> storage-optimized AI Search endpoint is documented to a billion embeddings, where pgvector on
> Lakebase is not sized for that. And it does not escape the same class of mistake — our
> `sensitivity` filter once named a column no stage produced, and on pgvector that is a hard
> "column does not exist", as it now is on AI Search. The filter is equally broken on either one,
> and on both you get an error rather than silence.

---

*Written by Sven Relijveld at [OneDNA](https://onedna.nl), a Databricks partner in the Netherlands.
Identifiers, group names and project data are generalised for publication. You can test this out
yourself by looking at the [demo repo](https://github.com/OneDNA/blog-databricks-rag-rls), which has
a runnable demonstration of each failure above, including a Unity Catalog row-filter fixture with
its negative cases.*
