"""Negative tests -- the ones that matter.

A test asserting that an entitled caller gets rows is nearly worthless: it passes just as
happily when the ACL is switched off entirely. The tests below assert that things DO NOT
happen, and several of them target the loose name-matching this design exists to avoid.

    $ pip install pytest && pytest -v

Two of these are marked `anti_pattern`. They run the LOOSE name-matching approach on purpose --
deriving an entitlement from any group name handed to it -- to show the declared table genuinely
rejects what it accepts. A test that passes against the thing it was written to catch is
decoration, not a test.

An exact-match naming convention is a valid mechanism and is not what these target.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

acl = __import__("03_acl_from_groups")
guard = __import__("02_assert_enforceable")
index = __import__("01_index_has_no_rls")

Entitlements = acl.Entitlements
GroupGrant = acl.GroupGrant
parse_group_grants = acl.parse_group_grants
build_filter = acl.build_filter


GRANTS = parse_group_grants(
    {
        "group-analysts": "docs_a",
        "group-engineers": ["docs_a", "docs_b"],
    }
)


# ==============================================================================================
# Fail closed. Every one of these must yield NOTHING, never everything.
# ==============================================================================================


def test_caller_with_no_groups_is_entitled_to_nothing():
    assert Entitlements.from_groups("nobody", [], GRANTS).is_empty


def test_caller_whose_groups_are_all_unmapped_is_entitled_to_nothing():
    ent = Entitlements.from_groups("stranger", ["group-social", "group-everyone"], GRANTS)
    assert ent.is_empty


def test_no_grants_table_entitles_nobody():
    """The default. A permissive default would serve the corpus to everyone on day one."""
    ent = Entitlements.from_groups("analyst", ["group-analysts"], parse_group_grants(None))
    assert ent.is_empty


def test_build_filter_refuses_rather_than_matching_nothing():
    """Raising, not returning a match-nothing filter -- so the caller handles it deliberately."""
    with pytest.raises(PermissionError, match="nothing is retrievable"):
        build_filter(Entitlements.nobody("nobody"))


def test_malformed_grants_table_raises_and_does_not_degrade_to_empty():
    """An empty table and a broken table have the same symptom. One of them must be loud."""
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_group_grants("{not json at all")


def test_unknown_grant_key_is_refused_not_ignored():
    """A typo'd axis name would otherwise drop a restriction with no error."""
    with pytest.raises(ValueError, match="unknown grant keys"):
        GroupGrant.parse({"sensitivity": ["internal"]})  # should be sensitivity_labels


# ==============================================================================================
# Grants are additive, and restriction is expressed by NOT granting.
# ==============================================================================================


def test_grants_are_additive_across_groups():
    ent = Entitlements.from_groups("both", ["group-analysts", "group-engineers"], GRANTS)
    assert ent.source_systems == frozenset({"docs_a", "docs_b"})


def test_unmapped_group_alongside_a_mapped_one_adds_nothing():
    only = Entitlements.from_groups("a", ["group-analysts"], GRANTS)
    plus = Entitlements.from_groups("a", ["group-analysts", "group-random"], GRANTS)
    assert only.source_systems == plus.source_systems


# ==============================================================================================
# assert_enforceable: the filter that would be ignored without an error.
# ==============================================================================================


@pytest.mark.parametrize(
    "filters",
    [
        {"sensitivty": ["internal"]},  # typo
        {"department": ["finance"]},  # never indexed
        {"source": ["docs_a"]},  # renamed upstream
        {"source_system": ["docs_a"], "owner_email": ["x@y.z"]},  # one good, one not
    ],
)
def test_unenforceable_axes_are_refused(filters):
    with pytest.raises(PermissionError, match="ignored without an error"):
        guard.assert_enforceable(filters)


@pytest.mark.parametrize(
    "filters",
    [
        {"source_system": ["docs_a"]},
        {"source_system": ["docs_a"], "site_id": ["s1"], "sensitivity": ["internal"]},
        {},
    ],
)
def test_enforceable_axes_are_allowed(filters):
    guard.assert_enforceable(filters)


def test_the_guard_fails_against_the_unguarded_builder():
    """The guard must catch what the unguarded builder happily produces.

    Without this, `assert_enforceable` could be a no-op and every test above would still pass.
    """
    unsafe = guard.build_filter_unguarded({"source_system": ["docs_a"], "department": ["fin"]})
    assert "department" in unsafe, "the unguarded builder should produce the unsafe filter"
    with pytest.raises(PermissionError):
        guard.assert_enforceable(unsafe)


# ==============================================================================================
# Loose name-matching. These show the declared table rejects what loose derivation accepts.
# ==============================================================================================


@pytest.mark.anti_pattern
def test_typical_workspace_groups_must_entitle_nobody():
    """An administration group must not become an entitlement claim.

    The loose approach returns {'admins', 'utc'} here. The declared table returns nothing.
    """
    derived = acl.entitlements_from_group_names(acl.TYPICAL_WORKSPACE_GROUPS)
    assert derived == {"admins", "utc"}, "loose derivation should still reproduce"

    ent = Entitlements.from_groups("real user", acl.TYPICAL_WORKSPACE_GROUPS, GRANTS)
    assert ent.is_empty, "declared-table ACL must grant nothing for these groups"


@pytest.mark.anti_pattern
def test_a_group_named_after_a_source_system_grants_nothing():
    """Anyone able to create a group could otherwise grant themselves the whole corpus."""
    attacker_group = "team-project-docs_a"

    assert acl.entitlements_from_group_names([attacker_group]) == {"docs_a"}, (
        "loose derivation hands over the corpus"
    )

    ent = Entitlements.from_groups("attacker", [attacker_group], GRANTS)
    assert ent.is_empty, "an ACL must not be a function of a string somebody else controls"


# ==============================================================================================
# Fail open vs fail closed. The error path is the one nobody tests.
# ==============================================================================================


@pytest.mark.parametrize("token", ["expired", None])
def test_a_failed_token_grants_nothing(token):
    """An expired token is routine. It must not widen access."""
    assert acl.resolve_entitlements_fail_closed("user", token).is_empty


def test_a_valid_token_still_resolves_normally():
    """The positive control: fail-closed must not mean fail-always."""
    ent = acl.resolve_entitlements_fail_closed("user", "valid")
    assert ent.source_systems == frozenset({"docs_a"})


@pytest.mark.parametrize("token", ["expired", None])
def test_the_fail_open_variant_widens_access_on_the_routine_path(token):
    """Documents the fail-open pattern, so the contrast is executable rather than asserted.

    If this ever stops holding, the comparison in the article needs revisiting.
    """
    assert acl.resolve_entitlements_fail_open("user", token) == [acl.OPEN_ACCESS_SENTINEL]


# ==============================================================================================
# The index's silent drop, reproduced.
# ==============================================================================================


def test_filter_on_a_missing_column_returns_everything():
    """Documents the behaviour the guard exists to prevent. If this ever fails, celebrate."""
    everything = index.fake_similarity_search(None)
    typo = index.fake_similarity_search({"sensitivty": ["internal"]})
    assert len(typo) == len(everything), "the predicate should have been dropped with no error"


def test_filter_on_a_real_column_actually_constrains():
    """The positive control. Without it, the test above is consistent with no filtering at all."""
    assert len(index.fake_similarity_search({"source_system": ["nope"]})) == 0
    assert len(index.fake_similarity_search({"source_system": ["docs_a"]})) == 2
