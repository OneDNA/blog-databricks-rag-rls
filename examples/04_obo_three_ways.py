"""Three OBO mechanisms, side by side -- and how each is switched off with no error.

An ACL keyed on the caller is worthless if the system has lost track of who the caller is. This
file is about that layer: how the caller's identity reaches Databricks, and what it can reach
once it gets there.

    $ python 04_obo_three_ways.py

There is no single "OBO" on Databricks. There are three, they are not interchangeable, and the
differences are load-bearing:

  * Databricks Apps      -- x-forwarded-access-token header. Widest scope set, INCLUDING Volumes.
  * Model Serving        -- ModelServingUserCredentials(). No Volumes, no file operations. At all.
  * External front end   -- an ENTRA token, which Databricks rejects until you exchange it. Any
                            client that is not Databricks (a custom web UI, something like
                            Microsoft Teams) lands here and needs token federation.

The Volumes gap is an architectural constraint worth knowing before you pick a host: the moment
your chain needs to read a file, Model Serving stops being an option.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable


# --------------------------------------------------------------------------------------------
# A credential provider per host. In production these return a WorkspaceClient; here they
# describe themselves, so the comparison is runnable with no Databricks connection.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Mechanism:
    name: str
    token_arrives_as: str
    obtained_via: str
    enabled_by: str
    can_reach: tuple[str, ...]
    cannot_reach: tuple[str, ...]
    silent_failure: str


APPS = Mechanism(
    name="Databricks Apps",
    token_arrives_as="x-forwarded-access-token request header",
    obtained_via="read the header",
    enabled_by="user_api_scopes in the app resource",
    can_reach=("AI Search", "SQL warehouses", "UC tables", "Genie", "UC Volumes", "file ops"),
    cannot_reach=(),
    silent_failure=(
        "`databricks apps deploy` copies ONLY the app directory -- a shared src/ package does "
        "not travel with it. Every unauthenticated request is answered with a 302 OAuth "
        "redirect, so no curl probe triggers the import, and the deploy reports SUCCEEDED."
    ),
)

MODEL_SERVING = Mechanism(
    name="Model Serving",
    token_arrives_as="held by the serving runtime",
    obtained_via="ModelServingUserCredentials()",
    enabled_by="UserAuthPolicy(api_scopes=[...]) at log time",
    can_reach=("AI Search", "SQL warehouses", "UC tables", "Genie", "serving endpoints", "MCP"),
    cannot_reach=("UC Volumes", "any file operation"),
    silent_failure=(
        "Below mlflow 2.22.1 OBO is OFF BY DEFAULT and the agent answers as the endpoint -- no "
        "error. If databricks-ai-bridge is missing from the LOGGED requirements the model loads "
        "and falls back to its own identity -- also no error."
    ),
)

EXTERNAL_FRONT_END = Mechanism(
    name="External front end (web UI, Teams, ...)",
    token_arrives_as="an Entra token (NOT a Databricks token)",
    obtained_via="RFC 8693 exchange at POST /oidc/v1/token",
    enabled_by="token federation: an ACCOUNT-level federation policy",
    can_reach=("whatever the exchanged token allows",),
    cannot_reach=("anything, until the exchange succeeds",),
    silent_failure=(
        "Entra settings the policy depends on, none of which name themselves in the resulting "
        "error: preferred_username as an optional ACCESS TOKEN claim; "
        "requestedAccessTokenVersion 2; a scope the front end can request on the user's behalf."
    ),
)

MECHANISMS = (APPS, MODEL_SERVING, EXTERNAL_FRONT_END)


# --------------------------------------------------------------------------------------------
# The shape the application code actually sees. One interface, three implementations -- which
# is what keeps the chain host-agnostic and makes changing host a config change, not a rewrite.
# --------------------------------------------------------------------------------------------

CredentialProvider = Callable[[], str]


def apps_provider(headers: dict[str, str]) -> CredentialProvider:
    """Databricks Apps: the caller's token arrives in a header the platform sets."""

    def provide() -> str:
        token = headers.get("x-forwarded-access-token")
        if not token:
            # Refuse. Falling back to the app's own identity here is precisely how you
            # build a system that serves every user the deployer's permissions.
            raise PermissionError(
                "no x-forwarded-access-token header: user authorization is not enabled on this "
                "app, or the request did not come through the platform's proxy"
            )
        return token

    return provide


def model_serving_provider() -> CredentialProvider:
    """Model Serving: the runtime holds the caller's credentials."""

    def provide() -> str:
        try:
            from databricks.sdk import WorkspaceClient  # type: ignore
            from databricks.sdk.credentials_provider import (  # type: ignore
                ModelServingUserCredentials,
            )
        except ImportError as err:
            raise PermissionError(
                "databricks-ai-bridge / databricks-sdk missing. Note this must be in the LOGGED "
                "requirements -- if it is absent the model still loads and quietly falls back "
                "to the endpoint's own identity."
            ) from err
        return WorkspaceClient(credentials_strategy=ModelServingUserCredentials()).config.token

    return provide


def federated_provider(entra_token: str, host: str) -> CredentialProvider:
    """External front end: exchange the Entra token for a Databricks one, or fail.

    A client that is not Databricks never yields a Databricks token. Signing the user in with
    Entra yields an Entra token, which Databricks rejects on workspace APIs. This exchange is
    what token federation gives you, and it works the same for a custom web UI or for a
    client like Microsoft Teams.
    """

    def provide() -> str:
        import urllib.parse
        import urllib.request

        body = urllib.parse.urlencode(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": entra_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                "scope": "all-apis",
            }
        ).encode()
        req = urllib.request.Request(f"{host}/oidc/v1/token", data=body)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            import json

            return json.load(resp)["access_token"]

    return provide


def main() -> int:
    print("THE THREE MECHANISMS\n")
    for m in MECHANISMS:
        print(f"  {m.name}")
        print(f"    token arrives as : {m.token_arrives_as}")
        print(f"    obtained via     : {m.obtained_via}")
        print(f"    enabled by       : {m.enabled_by}")
        print(f"    reaches          : {', '.join(m.can_reach)}")
        if m.cannot_reach:
            print(f"    CANNOT reach     : {', '.join(m.cannot_reach)}")
        print()

    print("=" * 92)
    print("\nTHE CONSTRAINT THAT DECIDES YOUR HOST\n")
    print("  Model Serving OBO cannot read Unity Catalog Volumes. Not 'slowly', not 'with extra")
    print("  configuration' -- at all. The moment the chain needs a file operation, Apps is the")
    print("  only option, and anything reaching the agent must reach an app rather than an")
    print("  endpoint. Writing the chain host-agnostically is what makes that a config change.")

    print("\n" + "=" * 92)
    print("\nHOW EACH ONE IS SWITCHED OFF, WITH NO ERROR\n")
    for m in MECHANISMS:
        print(f"  {m.name}:")
        for line in _wrap(m.silent_failure, 84):
            print(f"    {line}")
        print()

    print("=" * 92)
    print("\nTHE ASSERTION THAT CATCHES ALL OF THEM\n")
    print("  Do not assert that an answer came back. Assert on the identity that produced it:\n")
    print("      assert response.custom_outputs['ran_as'] == expected_caller")
    print("      assert response.custom_outputs['obo_active'] is True\n")
    print("  A test that only checks for a response passes just as happily when every caller is")
    print("  being served the deployer's permissions.")

    print("\n" + "=" * 92)
    print("\nLIVE CHECK\n")
    header_token = os.environ.get("X_FORWARDED_ACCESS_TOKEN")
    if header_token:
        print("  x-forwarded-access-token is present: running under Apps user authorization.")
    else:
        try:
            apps_provider({})()
        except PermissionError as err:
            print(f"  Apps provider, no header -> PermissionError (refused)")
            print(f"    {err}")
    return 0


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


if __name__ == "__main__":
    raise SystemExit(main())
