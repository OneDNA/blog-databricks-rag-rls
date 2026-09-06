# Two questions, two enforcement paths

Companion text for [`chat-response.html`](chat-response.html). The HTML is the visual on its own —
two chat windows and the metadata box under each reply, nothing else. Everything explaining it
lives here.

## What the visual shows

The same agent, the same two questions, two callers on different projects. Alice Chen is on Water
Delta; David Park is on Coastal North. Neither is an administrator and neither is unentitled —
David simply holds a grant on other data. That is the ordinary case, and it is the one worth
drawing: access control is usually about colleagues with different scopes rather than insiders and
outsiders.

## Why two questions

The agent routes on the shape of the question, and the two shapes land on opposite sides of the
governance boundary the article draws.

| Question | Shape | Path | Who enforces |
| --- | --- | --- | --- |
| *How many hours did we book on Water Delta in Q2?* | quantitative | Genie → SQL warehouse | **Unity Catalog**, per caller |
| *What went wrong on Water Delta, and what did we learn?* | qualitative | AI Search index | **your own code**, at query time |

A number comes from governed tables, so a row filter resolves against whoever is asking and the
platform decides what comes back. A judgement lives in documents, so the index has no row
filter at all and the entitlement filter your retrieval code passes is the only thing narrowing
the result.

Border colour on each reply and metadata box marks which of the two enforced that exchange, using
the convention from [`README.md`](README.md):

| Border | Meaning |
| --- | --- |
| Green `#00A972` | Unity Catalog enforces. Per caller, platform-side. |
| Lava `#FF5F46` | Your code enforces. Only as good as you wrote it. |

Because each caller crosses both boundaries in a single thread, the colour marks the *exchange*
rather than the person. One caller is green on their first answer and lava on their second.

## The point: David's two zeros have different causes

Both of David's answers come back empty, and from outside they look identical. They are not.

- **On the Genie path**, his query ran. Unity Catalog evaluated the row filter against his identity
  and returned no Water Delta rows. The platform decided, and it would have decided the same way
  for any caller on any client.
- **On the AI Search path**, his entitlement resolved to Coastal North and the filter went out
  scoped to it. The index has no row filter of its own; had our code passed no filter, or a filter
  naming a column the index does not have, he would have received Water Delta chunks with no
  error and no warning.

> [!NOTE]
> `obo_active: true` in every metadata box is what makes either zero readable. Without it, a zero
> could mean "correctly filtered" or "identity broken" — and the two are indistinguishable from
> the answer alone. Assert on the identity that produced the result, not on whether a result
> arrived.

## Reading the metadata boxes

| Field | What it tells you |
| --- | --- |
| `path` | which retrieval route the question took |
| `enforced by` | which side of the governance boundary applied the constraint |
| `executed_as` | the identity Unity Catalog saw — the human, not the endpoint's service principal |
| `filter` | the entitlement filter our code passed to the index |
| `rows` / `chunks` | how much came back |
| `obo_active` | whether on-behalf-of resolved, so a zero can be told apart from broken identity |

## Provenance

Names, groups, figures and the retrospective details are generalised for publication. The
structure of the exchange — two paths, per-caller enforcement on one and application-level
filtering on the other — reflects what we measured; the specific numbers and document names do
not.

Colour tokens follow the Databricks brand system: the semantic green is `#00A972` / `#00875C`, and
the palette has no teal, turquoise or mint. The `.drawio` diagrams in this directory use the same
`#00A972`, set once as `GREEN` in [`build.py`](build.py).
