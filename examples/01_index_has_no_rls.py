"""Silent failure #1: a filter naming a column the index does not have is IGNORED.

This is the failure mode the whole article is arranged around, and it is worth reproducing
yourself once, because reading about it does not produce the same alarm as watching it.

On AI Search, filtering on an unknown field does not raise. It does not warn. It stops
constraining -- and "more rows than you should see" is indistinguishable from "a good retrieval".

    $ python 01_index_has_no_rls.py                  # offline, uses a fake index
    $ python 01_index_has_no_rls.py --live           # against a real AI Search index

The offline mode models the documented behaviour so the demonstration runs anywhere. The --live
mode runs the same three probes against a real index; if your index behaves differently, that is
worth knowing and we would like to hear about it.
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
    not carry is skipped, not rejected. Everything else here is ordinary filtering.
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


def probe(label: str, filters: dict[str, list[str]] | None, search) -> int:
    rows = search(filters)
    print(f"  {label:<46} {len(rows)} rows")
    return len(rows)


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
    # silently dropped and a filter that is correctly applied can return the same count.
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

    print(f"\n  The typo'd column returned {typo} rows (vs {unfiltered} unfiltered).")
    print("  This index rejects unknown fields rather than ignoring them -- good, and worth")
    print("  verifying rather than assuming, because the guard in 02 is what makes it safe.")
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
