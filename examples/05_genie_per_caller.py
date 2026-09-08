"""The contrast: a path where Unity Catalog does the enforcing, and the problem inside it.

Everything in examples 01-04 is about the index path, where YOU enforce. This is the other
branch of the same agent -- a Genie space over governed tables, where the platform enforces.

    $ python 05_genie_per_caller.py

Two things are worth taking from this file.

THE GOOD NEWS: Unity Catalog resolves row filters and column masks against the CALLER, on every
path we could construct -- interactive, agent-under-OBO, and an external front end (three hops, via
Entra token federation). Query history attributes the statement to the human, not to the serving
endpoint's service principal.

THE PROBLEM: on a non-interactive path the service principal IS the evaluated identity. Correctly
and honestly. Which means every human calling through that integration sees the union of what
the SP was granted, with no per-caller differentiation at all. The risk is not that identity
gets lost -- it is that a broadly-granted SP OVERRULES on-behalf-of and takes its own.
"""

from __future__ import annotations

from dataclasses import dataclass


# --------------------------------------------------------------------------------------------
# What we measured. Each row is a path we actually ran, with the identity the platform recorded
# in query history -- which is the independent check, not the agent's own self-report.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Path:
    description: str
    caller: str
    evaluated_as: str
    per_caller: bool
    note: str


MEASURED = (
    Path(
        "SQL editor (control)",
        caller="a human",
        evaluated_as="that human",
        per_caller=True,
        note="the baseline every other row is compared against",
    ),
    Path(
        "Genie UI, interactive",
        caller="a human",
        evaluated_as="that human",
        per_caller=True,
        note="matches its control exactly",
    ),
    Path(
        "Agent under OBO -> Genie",
        caller="a human",
        evaluated_as="that human",
        per_caller=True,
        note="two hops; needs the 'genie' OAuth scope in UserAuthPolicy",
    ),
    Path(
        "External front end -> agent -> Genie",
        caller="a human",
        evaluated_as="that human",
        per_caller=True,
        note="three hops, including an RFC 8693 token exchange",
    ),
    Path(
        "Service principal over the API",
        caller="an SP",
        evaluated_as="THE SERVICE PRINCIPAL",
        per_caller=False,
        note="honest, and precisely the problem -- see below",
    ),
)


# --------------------------------------------------------------------------------------------
# The decisive comparison: same space, same question, same generated SQL, two callers.
# --------------------------------------------------------------------------------------------

COMPARISON = (
    ("a caller in the admitted group", 7, "unmasked"),
    ("a caller in no admitted group", 0, "NULL (masked)"),
)


def main() -> int:
    print("WHOSE IDENTITY DOES THE QUERY RUN AS?\n")
    print(f"  {'path':<34} {'evaluated as':<24} per-caller?")
    print(f"  {'-' * 34} {'-' * 24} {'-' * 11}")
    for p in MEASURED:
        mark = "yes" if p.per_caller else "NO"
        print(f"  {p.description:<34} {p.evaluated_as:<24} {mark}")
    print()
    for p in MEASURED:
        print(f"  {p.description}: {p.note}")

    print("\n" + "=" * 88)
    print("\nTHE DECISIVE COMPARISON\n")
    print("  Same space. Same question. Byte-identical generated SQL. Only the caller changed.\n")
    print(f"  {'caller':<34} {'rows':<8} masked column")
    print(f"  {'-' * 34} {'-' * 8} {'-' * 14}")
    for who, rows, masked in COMPARISON:
        print(f"  {who:<34} {rows:<8} {masked}")

    print("\n  Row filters AND column masks both resolve per caller. We established this with a")
    print("  negative test -- replacing the filter body with a predicate matching nothing,")
    print("  confirming 0 rows, then restoring it. A filter that is attached is not necessarily")
    print("  a filter that runs; DESCRIBE tells you it exists, and changing it tells you it works.")

    print("\n" + "=" * 88)
    print("\nTHE POSITIVE CONTROL, without which a 0 means nothing\n")
    print("  'No rows' is also what a bad token, a missing grant, or a broken warehouse looks")
    print("  like. So the restricted caller was asked something it COULD answer:\n")
    print("      Q: how many rows are in the table?")
    print("      A: a row containing 0\n")
    print("  A successful execution returning zero is not a failure returning nothing. That is")
    print("  what makes the zero attributable to the row filter rather than to the plumbing.")

    print("\n" + "=" * 88)
    print("\nTHE PROBLEM\n")
    print("  The service principal row preserves identity too -- and that IS the problem.")
    print()
    print("  It is not laundering permissions. It is evaluated honestly, as itself. But on a")
    print("  non-interactive path the SP is the WHOLE of your access control: every human")
    print("  calling through that integration sees the union of what the SP may read.")
    print()
    print("  So the review question is not 'is RLS enabled' -- it is. The question is:")
    print()
    print("      WHAT IS THAT SERVICE PRINCIPAL GRANTED?")

    print("\n" + "=" * 88)
    print("\nTHE CONFIGURATION VERSION OF THE SAME PROBLEM\n")
    print("  Databricks documents that granting an SP access to a Genie space also requires")
    print("  granting its underlying tables and warehouse. Follow that for an agent and you have")
    print("  given the ENDPOINT a standing grant on the data -- so every caller sees the union of")
    print("  what the endpoint may read -- on-behalf-of overruled, by following the docs.")
    print()
    print("  Under user authorization you do not need those downstream grants. Do not add them.")
    print("  Declare only the chat model in SystemAuthPolicy; UserAuthPolicy handles the rest.")

    print("\n" + "=" * 88)
    print("\nAND ONE THING THAT IS *NOT* A BOUNDARY\n")
    print("  A Genie space has a curated table list. It is NOT a security boundary.")
    print()
    print("  We asked four times, two identities, for a table deliberately left off the list.")
    print("  All four refused, generating no SQL at all. That looks like enforcement. It is not.")
    print("  It is the model declining to name a table it was never shown, and a model update")
    print("  can change it without a release note. The Databricks documentation does not promise")
    print("  the list limits what Genie can reach.")
    print()
    print("  Rely on Unity Catalog grants. Never on the curated list.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
