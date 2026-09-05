"""The guard that turns failure #1 into a raised error.

``assert_enforceable`` refuses to hand back a filter the index cannot apply. It is four lines of
logic, and it prevents the failure an ACL must never have: a predicate that is accepted and then
ignored.

    $ python 02_assert_enforceable.py

Three design choices are demonstrated below, and each is a decision rather than a detail:

1. It RAISES rather than warns. A warning in a serving container is a log line nobody reads.
2. It lives in the ACL layer, not the retriever, so every backend inherits it. pgvector would
   have raised "column does not exist" on its own; AI Search will not. A rule that only holds
   on the backend that gives notice is not a rule.
3. It asserts against a DECLARED contract rather than introspecting the index at runtime, so
   the check works offline, in tests, and before the index exists.
"""

from __future__ import annotations


# --------------------------------------------------------------------------------------------
# The contract. This is the set of columns the index was built with, declared once, in code.
# Changing the index without changing this is exactly the drift the guard is here to catch.
# --------------------------------------------------------------------------------------------

ACL_FILTER_COLUMNS: tuple[str, ...] = ("source_system", "site_id", "sensitivity")


def assert_enforceable(filters: dict[str, object]) -> None:
    """Refuse a filter whose keys the index cannot actually apply.

    Raises PermissionError -- deliberately, rather than ValueError. This is a security control
    refusing the request, and the exception type should say so to anyone reading a traceback.
    """
    unenforceable = sorted(set(filters) - set(ACL_FILTER_COLUMNS))
    if unenforceable:
        raise PermissionError(
            f"entitlement axes {unenforceable} are not columns of the index source "
            f"{list(ACL_FILTER_COLUMNS)}, so filtering on them would be ignored without an error. "
            "Add the column to the index (a rebuild) or stop emitting the predicate; "
            "serving unfiltered results is not an option."
        )


# --------------------------------------------------------------------------------------------
# The two implementations, side by side. The point of keeping the old one is that a regression
# test which passes against the bug it was written for is decoration -- so we run both.
# --------------------------------------------------------------------------------------------


def build_filter_unguarded(entitlements: dict[str, list[str]]) -> dict[str, list[str]]:
    """What we had before. Correct-looking, and quietly unsafe."""
    return {axis: sorted(values) for axis, values in entitlements.items() if values}


def build_filter_guarded(entitlements: dict[str, list[str]]) -> dict[str, list[str]]:
    """What we have now. Identical, plus one line that cannot be forgotten."""
    filters = {axis: sorted(values) for axis, values in entitlements.items() if values}
    assert_enforceable(filters)
    return filters


CASES: list[tuple[str, dict[str, list[str]], bool]] = [
    (
        "a normal entitlement",
        {"source_system": ["docs_a"]},
        True,
    ),
    (
        "all three axes",
        {"source_system": ["docs_a"], "site_id": ["site-1"], "sensitivity": ["internal"]},
        True,
    ),
    (
        "a typo: 'sensitivty'",
        {"source_system": ["docs_a"], "sensitivty": ["internal"]},
        False,
    ),
    (
        "an axis nobody added to the index",
        {"source_system": ["docs_a"], "department": ["finance"]},
        False,
    ),
    (
        "renamed upstream: 'source' not 'source_system'",
        {"source": ["docs_a"]},
        False,
    ),
]


def main() -> int:
    print("Each case is built twice: once without the guard, once with it.\n")
    print(f"  Index contract: {list(ACL_FILTER_COLUMNS)}\n")
    print(f"  {'case':<44} {'unguarded':<22} guarded")
    print(f"  {'-' * 44} {'-' * 22} {'-' * 24}")

    failures = 0
    for label, entitlement, should_pass in CASES:
        # Unguarded: builds a filter regardless. The danger is that this NEVER fails.
        unguarded = build_filter_unguarded(entitlement)
        bad_axes = sorted(set(unguarded) - set(ACL_FILTER_COLUMNS))
        unguarded_note = "built (unsafe, and it does not raise)" if bad_axes else "built"

        try:
            build_filter_guarded(entitlement)
            guarded_note = "built"
            passed = True
        except PermissionError:
            guarded_note = "PermissionError <-- refused"
            passed = False

        print(f"  {label:<44} {unguarded_note:<22} {guarded_note}")

        if passed is not should_pass:
            failures += 1
            print(f"      ^^ UNEXPECTED: expected {'pass' if should_pass else 'refusal'}")

    print()
    print("=" * 92)
    print()
    print("Read the middle column. The unguarded builder never fails -- it happily returns a")
    print("filter containing an axis the index will ignore, and the query then succeeds, returns")
    print("a plausible number of rows, and serves content the caller is not entitled to.")
    print()
    print("That is the whole argument for the guard: the unsafe path has no symptom.")
    print()

    # The check that matters: does the guard actually reject what it should? A guard verified
    # only against inputs it accepts is a guard you are hoping about.
    refused = sum(1 for _, e, ok in CASES if not ok and not _accepts(e))
    expected = sum(1 for _, _, ok in CASES if not ok)
    print(f"Guard refused {refused}/{expected} of the cases that must be refused.")

    if failures:
        print(f"\n{failures} case(s) behaved unexpectedly.")
        return 1
    return 0


def _accepts(entitlement: dict[str, list[str]]) -> bool:
    try:
        build_filter_guarded(entitlement)
        return True
    except PermissionError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
