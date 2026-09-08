# Row-level security on a Databricks RAG agent

Two colleagues ask the same chatbot the same question. Should they get the same answer, or
different ones because they are allowed to see different things?

Unity Catalog answers that well for tables — row filters and column masks, evaluated per caller.
It does not answer it for a vector index, which has grants but no row filters, so the access
decision moves out of the platform and into code you write. This is a write-up of building that
access control on Databricks, reachable from a front end outside the platform — a custom web UI or
a client like Microsoft Teams, once token federation is enabled — and of measuring whether it
actually holds.

## The article

Two lengths. The short version is the argument with all five diagrams; the long version adds the
measurements, the OBO token-hop table, the Unity Catalog design questions and the platform features
still in preview.

| | Short · ~6 min | Long · ~21 min |
| --- | --- | --- |
| 🇬🇧 | **[Read it in English](article/short/row-level-security.md)** | [The long version](article/row-level-security.md) |
| 🇳🇱 | **[Lees het in het Nederlands](article/short/row-level-security.nl.md)** | [De lange versie](article/row-level-security.nl.md) |

## What else is here

| Directory | What it holds |
| --- | --- |
| [`examples/`](examples/) | runnable demonstrations of each failure the article describes, including a Unity Catalog RLS fixture with its negative tests |
| [`diagrams/`](diagrams/) | all five diagrams the articles embed, as PNG and SVG, drawn on one brand system |
| [`tests/`](tests/) | the ACL test suite, including the loose group-name matching it rejects |

Run the examples and the tests:

```bash
uv run --with pytest pytest        # 25 tests, no Databricks connection needed
python examples/03_acl_from_groups.py
```

## About

Written by Sven Relijveld at [OneDNA](https://onedna.nl). Sharing knowledge is in our DNA.

Identifiers, group names and project data are generalised for publication. Licensed
[MIT](LICENSE) — lift anything here into your own work.
