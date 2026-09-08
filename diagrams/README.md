# Diagrams

Five diagrams, each rendered as PNG and SVG under [`rendered/`](rendered/). The articles embed the
wide variants; the `*-narrow` ones are kept for a single-column layout.

| Diagram | What it shows |
| --- | --- |
| [`build-and-serve`](rendered/build-and-serve.png) | The two halves of the platform: what build writes and what serve reads. Start here. |
| [`governance-boundary`](rendered/governance-boundary.png) | Where Unity Catalog stops governing, and what the index does not inherit. |
| [`acl-flow`](rendered/acl-flow.png) | How the ACL resolves on one request, and where each branch ends. |
| [`architecture`](rendered/architecture.png) | The whole system on one page: identity, build, serve. |
| [`decision-tree`](rendered/decision-tree.png) | Which enforcement path to use, and the host constraint that follows. |

Alongside them, [`chat-response.png`](rendered/chat-response.png) shows the same question answered
for two callers on different projects — [`chat-response.md`](chat-response.md) explains what the
exchange demonstrates.

## Wide and narrow

Each diagram exists in two shapes.

The **wide** version keeps the lanes side by side, which is how the argument reads best: identity
above build above serve, each as one horizontal band. Its type used to be sized for a slide — 10px
on a 2464px canvas, which lands near 3px once the image is fitted to an article column — so the
type has been scaled up against the canvas and the boxes given the vertical room that needs. The
articles reference these.

The **narrow** version (`*-narrow`) stacks the lanes into a single column instead. It is legible at
any column width but much taller, so it suits a phone or a one-column layout rather than the page.

## Two colour rules, and they never disagree

All five follow the Databricks brand system, which has one rule at its centre:

> **Lava `#FF5F46` marks Databricks. Oat `#D9D7CE` marks everything that is not.**

On top of that, they use **border colour to say who enforces access control** — which is the
argument the article makes, rendered as a visual convention:

| Border | Meaning |
| --- | --- |
| **Green** `#00A972` | **Unity Catalog enforces.** Per caller, platform-side, gives notice when it goes wrong. |
| **Lava** `#FF5F46` | **Your code enforces.** Only as good as you wrote it. |
| **Deep lava** `#FF3621` | **Nothing enforces.** The security plane does not reach here. |
| **Oat** `#D9D7CE` | Outside Databricks entirely. |

Read the architecture diagram by border colour before you read it by arrow. Every silent failure
described in the article sits on a lava or deep-lava border — that is not decoration, it is the
whole point.

## Icons and typography

Every icon is official vendor artwork, embedded rather than fetched. The brand font is
[DM Sans](https://fonts.google.com/specimen/DM+Sans).

| Source | Used for |
| --- | --- |
| Databricks architecture icons | AI Search, Unity Catalog, ABAC, Genie, Model Serving, Databricks Apps, SQL Warehouse, Lakebase, Agent Bricks |
| Microsoft 365 content icons (Teams Purple) | the front end, the person mark |
| Azure Public Service Icons V24 | App Registrations, for the token exchange |

Two notes on what is deliberately absent. There is no plain "Entra ID" mark in the Azure V24 set,
so the RFC 8693 exchange is drawn with **App Registrations** — which is more accurate anyway, since
an app registration is exactly what the federation policy trusts. And the front-end box is labelled
"Front end · web UI, Teams, …" but still drawn with the Teams mark, because a recognisable product
reads faster than a generic client glyph. Teams is only an example of what sits there: a custom web
UI takes the same position and needs the same Entra token federation to get a Databricks token.

The Databricks artwork comes from the community-maintained
[databricks-architecture-icons](https://github.com/oieduardorabelo/databricks-architecture-icons)
collection, which repackages official SVGs without redrawing them. That set is **unofficial** —
Databricks neither sponsors nor endorses it. Databricks, the Databricks logo and the product names
are trademarks of Databricks, Inc. Microsoft, Teams, Azure and Entra are trademarks of Microsoft
Corporation. Check both vendors' brand guidelines before commercial use.
