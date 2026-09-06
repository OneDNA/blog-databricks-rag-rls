"""Caller's groups to entitlements, via a declared table.

This is the ACL itself: the layer that decides what one caller may retrieve. It is short.

    $ python 03_acl_from_groups.py

A naming convention is a valid mechanism and needs no configuration at all -- it is what we
shipped at Witteveen+Bos, and it holds as long as one group maps to one thing. A declared table
is what you need once a caller's access is a COMBINATION of metadata columns, because then the
name would have to encode a tuple.

The section worth your attention is LOOSE PARSING, near the bottom: reading an entitlement out of
any group whose name merely CONTAINS a known token. That is the part that hands the ACL to anyone
who can create a group -- not the naming convention itself, which has to be an exact match against
names only your identity process can mint.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


# --------------------------------------------------------------------------------------------
# The grant: what one group entitles you to, on each of three axes.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupGrant:
    """Deliberately additive: two groups each granting one source system give you both.

    Restriction is expressed by NOT granting, never by a negative rule. A deny that has to be
    intersected with grants is the kind of logic that grants everything when one side is empty.
    """

    source_systems: frozenset[str] = field(default_factory=frozenset)
    site_ids: frozenset[str] = field(default_factory=frozenset)
    sensitivity_labels: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def parse(cls, raw: Any) -> "GroupGrant":
        """Accept three shapes, because the common case should not need the verbose one.

            "docs_a"                                     one source system
            ["docs_a", "docs_b"]                         several
            {"source_systems": [...], "site_ids": [...]} the full form
        """
        if isinstance(raw, str):
            return cls(source_systems=frozenset({raw}))
        if isinstance(raw, (list, tuple, set, frozenset)):
            return cls(source_systems=frozenset(str(v) for v in raw))
        if isinstance(raw, Mapping):
            unknown = set(raw) - {"source_systems", "site_ids", "sensitivity_labels"}
            if unknown:
                # Refuse rather than ignore. A typo'd key ("sensitivity" for
                # "sensitivity_labels") would otherwise drop a restriction with no error, and the
                # result reads as a working grant.
                raise ValueError(f"unknown grant keys {sorted(unknown)}")
            return cls(
                source_systems=frozenset(str(v) for v in raw.get("source_systems") or ()),
                site_ids=frozenset(str(v) for v in raw.get("site_ids") or ()),
                sensitivity_labels=frozenset(str(v) for v in raw.get("sensitivity_labels") or ()),
            )
        raise TypeError(f"cannot read a grant from {type(raw).__name__}")


def parse_group_grants(raw: Any) -> dict[str, GroupGrant]:
    """Read the mapping from config -- a dict, or JSON as a string.

    Empty is meaningful and is NOT an error: it means nobody is entitled to anything. That is
    the correct behaviour for a deployment that has not declared its mapping yet, and it is the
    opposite of what a permissive default would do.

    Malformed, however, RAISES. An empty table and a broken table produce the same visible
    symptom -- no results -- so a broken one failing without an error sends you looking at permissions
    instead.
    """
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as err:
            raise ValueError(f"group grants is not valid JSON: {err}") from err
    if not isinstance(raw, Mapping):
        raise TypeError(f"group grants must be a mapping, got {type(raw).__name__}")
    return {str(g): GroupGrant.parse(v) for g, v in raw.items()}


# --------------------------------------------------------------------------------------------
# The entitlements of one caller.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Entitlements:
    """A value object with no ambient state.

    Passed explicitly into every retrieval, so a code path that forgot to supply them cannot
    inherit somebody else's without anything reporting it.
    """

    principal: str
    source_systems: frozenset[str] = field(default_factory=frozenset)
    site_ids: frozenset[str] = field(default_factory=frozenset)
    sensitivity_labels: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_empty(self) -> bool:
        return not self.source_systems

    @classmethod
    def nobody(cls, principal: str = "anonymous") -> "Entitlements":
        """A caller entitled to nothing -- the negative test's subject."""
        return cls(principal=principal)

    @classmethod
    def from_groups(
        cls,
        principal: str,
        groups: Iterable[str],
        grants: Mapping[str, GroupGrant] | None = None,
    ) -> "Entitlements":
        """Derive entitlements from group memberships, via an explicit map.

        An UNMAPPED group grants nothing. That is stricter than it looks: adding a source system
        means adding a row to a reviewed config value, not choosing a group name.
        """
        grants = grants or {}
        sources: set[str] = set()
        sites: set[str] = set()
        labels: set[str] = set()
        for group in groups:
            grant = grants.get(group)
            if grant is None:
                # Not an error: a caller is normally in several groups unrelated to this corpus.
                continue
            sources |= grant.source_systems
            sites |= grant.site_ids
            labels |= grant.sensitivity_labels
        return cls(principal, frozenset(sources), frozenset(sites), frozenset(labels))


def build_filter(entitlements: Entitlements) -> dict[str, list[str]]:
    """Entitlements to an index filter. Raises on empty rather than returning a match-nothing filter.

    Both refuse, but raising makes the caller handle it deliberately -- and the decorator
    below converts it into an empty result, so what the negative test observes is "no rows",
    not an error.
    """
    if entitlements.is_empty:
        raise PermissionError(
            f"{entitlements.principal} has no source system entitlements; nothing is retrievable"
        )
    filters: dict[str, list[str]] = {"source_system": sorted(entitlements.source_systems)}
    if entitlements.site_ids:
        filters["site_id"] = sorted(entitlements.site_ids)
    if entitlements.sensitivity_labels:
        filters["sensitivity"] = sorted(entitlements.sensitivity_labels)
    return filters


# --------------------------------------------------------------------------------------------
# LOOSE PARSING. Kept runnable, because the output is the argument.
# --------------------------------------------------------------------------------------------


def entitlements_from_group_names(groups: Iterable[str]) -> set[str]:
    """Derive the source system from ANY group name's last hyphen-segment.

    This is the loose version, and the loose part is that it accepts every group it is handed.
    A naming convention is fine; matching it exactly against names only your identity process
    can mint is fine. Deriving meaning from arbitrary group names is not -- run it against the
    names a real workspace actually contains and the problem is immediate.
    """
    return {g.rsplit("-", 1)[-1].lower() for g in groups if "-" in g}


# Group names of the kind any Databricks workspace accumulates. Neither was created with any
# intention of granting access to a document corpus.
TYPICAL_WORKSPACE_GROUPS = [
    "rbac-azure-weu-platform-admins",
    "users-clone-2026-01-01-0900-UTC",
]


# --------------------------------------------------------------------------------------------
# TWO ERROR POLICIES: GRANT ON ERROR, OR REFUSE ON ERROR.
#
# The shape below is not hypothetical: it is a pattern we have seen in a production GenAI
# platform, where entitlement resolution returns a permissive sentinel on ANY error, including
# a 401 or 403 from an expired token. Safety then rests on no document holding that sentinel
# string, which nothing enforces.
#
# We are not showing it to score a point. We are showing it because an expired token is a
# ROUTINE event, so this is a widening of access on the ordinary path, not the exceptional one
# -- and because the two implementations are almost indistinguishable in a code review.
# --------------------------------------------------------------------------------------------

OPEN_ACCESS_SENTINEL = "open access"


def resolve_entitlements_granting(principal: str, token: str | None) -> list[str]:
    """The shape to avoid. Note how reasonable the except block looks in isolation."""
    try:
        if not token:
            raise PermissionError("no token")
        return _groups_from_scim(token)
    except Exception:
        # Fallback: open access if invalid token or other API error.
        return [OPEN_ACCESS_SENTINEL]


def resolve_entitlements_refusing(principal: str, token: str | None) -> Entitlements:
    """The same function, with the opposite answer to the same question."""
    try:
        if not token:
            raise PermissionError("no token")
        groups = _groups_from_scim(token)
    except Exception:
        return Entitlements.nobody(principal)
    return Entitlements.from_groups(principal, groups, GRANTS_FOR_DEMO)


def _groups_from_scim(token: str) -> list[str]:
    """Stand-in for a real SCIM /Me call."""
    if token == "valid":
        return ["group-analysts"]
    raise PermissionError("401 from SCIM: token expired")


GRANTS_FOR_DEMO = parse_group_grants({"group-analysts": "docs_a"})


def main() -> int:
    grants = parse_group_grants(
        {
            "group-analysts": "docs_a",
            "group-engineers": ["docs_a", "docs_b"],
            "group-auditors": {
                "source_systems": ["docs_a"],
                "sensitivity_labels": ["internal"],
            },
        }
    )

    print("A declared grants table maps group -> entitlement:\n")
    for name, grant in grants.items():
        axes = [f"source_systems={sorted(grant.source_systems)}"]
        if grant.sensitivity_labels:
            axes.append(f"sensitivity={sorted(grant.sensitivity_labels)}")
        print(f"  {name:<18} {', '.join(axes)}")

    print("\n" + "=" * 82)
    print("\nResolving callers:\n")

    callers = [
        ("an analyst", ["group-analysts", "group-everyone"]),
        ("an engineer", ["group-engineers"]),
        ("both roles (grants are additive)", ["group-analysts", "group-engineers"]),
        ("an auditor (narrowed by label)", ["group-auditors"]),
        ("someone with no mapped groups", ["group-everyone", "group-office-social"]),
        ("someone with no groups at all", []),
    ]

    for label, groups in callers:
        ent = Entitlements.from_groups(label, groups, grants)
        if ent.is_empty:
            print(f"  {label:<34} -> NOTHING RETRIEVABLE (refused)")
        else:
            print(f"  {label:<34} -> {build_filter(ent)}")

    print("\n" + "=" * 82)
    print("\nThe default, which is the one that matters most:\n")
    ent = Entitlements.from_groups("anyone", ["group-analysts"], parse_group_grants(None))
    print(f"  no grants table configured        -> is_empty={ent.is_empty}")
    print("  A permissive default here would serve the whole corpus to everyone the first time")
    print("  somebody forgot the variable -- and it would look exactly like correct operation.")

    print("\n" + "=" * 82)
    print("\nLOOSE PARSING -- run against typical workspace group names:\n")
    derived = entitlements_from_group_names(TYPICAL_WORKSPACE_GROUPS)
    for g in TYPICAL_WORKSPACE_GROUPS:
        print(f"  {g}")
    print(f"\n  derived source systems: {derived}")
    print()
    print("  A workspace ADMINISTRATION group becomes a claim on a source system called 'admins'.")
    print("  It denies access only by luck -- because no document happens to hold that value.")
    print()
    danger = "team-project-docs_a"
    print(f"  Now consider a group named: {danger}")
    print(f"  derived source systems: {entitlements_from_group_names([danger])}")
    print()
    print("  Anyone able to create a group could grant themselves the entire corpus -- which is")
    print("  what loose matching costs you, not the naming convention itself.")
    print("  Under the declared table, that same group grants nothing:")
    print(
        f"    is_empty={Entitlements.from_groups('attacker', [danger], grants).is_empty}"
    )

    print("\n" + "=" * 82)
    print("\n  An ACL must not be a function of a string somebody else controls.")

    print("\n" + "=" * 82)
    print("\nTWO ERROR POLICIES -- the same three inputs:\n")
    print(f"  {'token':<24} {'granting returns':<28} refusing returns")
    print(f"  {'-' * 24} {'-' * 28} {'-' * 24}")
    for label, token in [
        ("valid", "valid"),
        ("expired (401 from SCIM)", "expired"),
        ("absent entirely", None),
    ]:
        opened = resolve_entitlements_granting("user", token)
        closed = resolve_entitlements_refusing("user", token)
        closed_desc = "NOTHING" if closed.is_empty else sorted(closed.source_systems)
        print(f"  {label:<24} {str(opened):<28} {closed_desc}")

    print()
    print("  Rows two and three are the entire argument. An expired token is a ROUTINE event --")
    print("  it happens to real users every day -- and under the granting policy it WIDENS")
    print("  access rather than removing it.")
    print()
    print("  Safety then rests on no document ever holding the sentinel string in its ACL")
    print("  column. Nothing enforces that. It is a convention, one rename away from failing.")
    print()
    print("  Decide what your error paths grant, and write it down. Most systems have never")
    print("  been asked the question, and the answer is whatever the last except block did.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
