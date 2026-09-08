"""Failure #1: a filter naming a column the index does not have is IGNORED, with no error.

This is the failure mode the whole article is arranged around, and it is worth reproducing
yourself once, because reading about it does not produce the same alarm as watching it.

When this was measured, filtering on an unknown field on AI Search did not raise and did not
warn. It stopped constraining -- and "more rows than you should see" is indistinguishable from
"a good retrieval".

    $ python 01_index_has_no_rls.py                  # offline, uses a fake index
    $ python 01_index_has_no_rls.py --live           # against a real AI Search index

The offline mode models that behaviour so the demonstration runs anywhere.

MEASURED SINCE (Sep 2026, AWS workspace, STANDARD endpoint, HYBRID index): --live no longer
reproduces it. The typo'd column now comes back as a hard error --

    BadRequest: Columns referenced in filters are not present in index: sensitivty

-- so the platform refuses the predicate instead of ignoring it. That is the better behaviour
and it is the reason this script reports three outcomes rather than two: ignored, rejected, or
something neither the article nor this script predicted. Run it against your own index; the
answer is a property of your backend and its version, not of your code -- and if yours behaves
differently again, that is worth knowing and we would like to hear about it.
"""

from __future__ import annotations

import argparse
import os
import sys


# --------------------------------------------------------------------------------------------
# The offline model: an index that behaves the way AI Search documents itself as behaving.
# --------------------------------------------------------------------------------------------

CORPUS = [
    {"id": "1", "source_system": "docs_a", "sensitivity": "internal", "text": "chunk one"},
    {"id": "2", "source_system": "docs_a", "sensitivity": "confidential", "text": "chunk two"},
    {"id": "3", "source_system": "docs_b", "sensitivity": "internal", "text": "chunk three"},
]

#: The columns the index was actually built with. Anything outside this set is not filterable.
INDEXED_COLUMNS = {"id", "source_system", "sensitivity", "text"}


def fake_similarity_search(filters: dict[str, list[str]] | None) -> list[dict]:
    """Model AI Search's filtering, including the part that should frighten you.

    The single important line is the ``continue``: a predicate naming a column the index does
    not have is skipped, not rejected. Everything else here is ordinary filtering.
    """
    rows = CORPUS
    for column, allowed in (filters or {}).items():
        if column not in INDEXED_COLUMNS:
            # >>> THE BUG SURFACE <<<
            # No exception. No warning. The predicate simply stops existing, and every row
            # that it would have excluded is now returned.
            continue
        rows = [r for r in rows if r.get(column) in allowed]
    return rows


#: Returned by :func:`probe` when the backend refused the filter instead of answering it.
REJECTED = -1


def probe(label: str, filters: dict[str, list[str]] | None, search) -> int:
    """Run one probe. Returns the row count, or ``REJECTED`` if the backend refused.

    A refusal is a legitimate outcome, not a crash: it is the *good* behaviour, and on a
    backend that rejects unknown fields it is what the typo probe is expected to produce.
    """
    try:
        rows = search(filters)
    except Exception as exc:  # noqa: BLE001 -- backend exception types vary by client
        if not _is_unknown_column_error(exc):
            raise
        print(f"  {label:<46} REJECTED -- {type(exc).__name__}")
        print(f"  {'':<46} {str(exc).strip()[:88]}")
        return REJECTED
    print(f"  {label:<46} {len(rows)} rows")
    return len(rows)


def _is_unknown_column_error(exc: Exception) -> bool:
    """Is this the backend refusing a filter column it does not have?

    Matched on message text rather than exception class: the AI Search client raises
    ``BadRequest``, pgvector raises a ``ProgrammingError``, and neither is worth importing
    here just to name it. Anything unrecognised is re-raised rather than swallowed -- a
    genuine outage must not be mistaken for a clean refusal.
    """
    text = str(exc).lower()
    return (
        "not present in index" in text
        or "columns referenced in filters" in text
        or ("column" in text and "does not exist" in text)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="run against a real AI Search index")
    args = parser.parse_args()

    if args.live:
        search = _live_search()
        if search is None:
            return 2
    else:
        search = fake_similarity_search
        print("Offline mode: modelling documented AI Search behaviour.\n")

    print("Three probes. The third is the one that makes the first two mean anything.\n")

    unfiltered = probe("no filter at all", None, search)
    real = probe('{"source_system": ["docs_a"]}  (a real column)', {"source_system": ["docs_a"]}, search)
    nonexistent = probe(
        '{"source_system": ["nope"]}    (real column, no match)', {"source_system": ["nope"]}, search
    )

    print()
    typo = probe(
        '{"sensitivty": ["internal"]}   (TYPO -- no such column)',
        {"sensitivty": ["internal"]},
        search,
    )

    print("\n" + "=" * 78)

    # The positive control. Without a predicate you KNOW must match nothing, a filter that is
    # dropped without an error and a filter that is correctly applied can return the same count.
    if nonexistent != 0:
        print("INCONCLUSIVE: the no-match probe returned rows, so filtering is not being applied")
        print("              at all. Fix that before drawing conclusions from anything above.")
        return 1

    print("The no-match probe returned 0, so filtering IS live on known columns.")

    if typo == unfiltered:
        print()
        print(f"  BUT: the typo'd column returned {typo} rows -- the same as NO FILTER.")
        print("  The predicate was accepted and then ignored. A caller restricted to one")
        print("  sensitivity label just received every label, with no error and a plausible count.")
        print()
        print("  This is why assert_enforceable() exists. See 02_assert_enforceable.py.")
        return 0

    if typo == REJECTED:
        print()
        print("  The typo'd column was REJECTED outright -- the query never ran.")
        print("  This backend validates filter keys against the index contract itself, so this")
        print("  particular mistake cannot silently widen access here. Good.")
        print()
        print("  It does not retire the guard in 02, for three reasons:")
        print("    * it is a property of the backend and its version, not of your code, and it")
        print("      is not what AI Search did when this article was measured -- so it can move")
        print("      again, in either direction, without a release note;")
        print("    * a column that EXISTS but was never synced into the index is not this case,")
        print("      and need not refuse so loudly;")
        print("    * a refusal at query time is a 500 to your caller. The guard turns the same")
        print("      mistake into a PermissionError before the request goes out, which is the")
        print("      difference between a refused query and a broken endpoint.")
        print()
        print("  Verify it rather than assume it -- that is the whole point of running this.")
        return 0

    print(f"\n  The typo'd column returned {typo} rows (vs {unfiltered} unfiltered).")
    print("  This index neither ignored the unknown field nor refused it -- an outcome neither")
    print("  the article nor this script predicted. If you see this, the guard in 02 is the only")
    print("  thing standing between you and a filter of unknown effect. We would like to hear")
    print("  about it: https://github.com/OneDNA/blog-databricks-rag-rls/issues")
    return 0


# --------------------------------------------------------------------------------------------
# Live mode
# --------------------------------------------------------------------------------------------


def _live_search():
    """Build a search callable against a real index, or explain why we cannot."""
    index_name = os.environ.get("VS_INDEX")
    endpoint = os.environ.get("VS_ENDPOINT")
    if not index_name or not endpoint:
        print("--live needs VS_INDEX and VS_ENDPOINT set, for example:", file=sys.stderr)
        print("  export VS_ENDPOINT=my-vs-endpoint", file=sys.stderr)
        print("  export VS_INDEX=catalog.schema.my_index", file=sys.stderr)
        return None

    try:
        from databricks.ai_search.client import AISearchClient  # type: ignore
    except ImportError:
        try:
            from databricks.vector_search.client import (  # type: ignore
                VectorSearchClient as AISearchClient,
            )
        except ImportError:
            print("pip install databricks-ai-search", file=sys.stderr)
            return None

    index = AISearchClient().get_index(endpoint_name=endpoint, index_name=index_name)
    query = os.environ.get("VS_QUERY", "design decision")

    def search(filters):
        result = index.similarity_search(
            query_text=query,
            columns=["id"],
            filters=filters or {},
            num_results=100,
        )
        return (result.get("result") or {}).get("data_array") or []

    print(f"Live mode: {index_name} on {endpoint}\n")
    return search


if __name__ == "__main__":
    raise SystemExit(main())
