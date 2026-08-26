"""Patreon apply-gate — decision + frontend contract parity.

Standalone mirror (this sandbox has no motor/.env, so server.py cannot be imported —
same convention as test_me_state_contract.py). Mirrors backend/server.py's
`_parse_patreon_roles`, `_tier_from_roles` and the decision core of `_patreon_access`
(the DB-persist side effect is exercised in prod, not here), then asserts:

  1. decision matrix: admin / tier-role holder / active patron / stale-grant fallback /
     merely-linked-patreon / nobody.
  2. contract parity: every key frontend/src/pages/SkinEditor.jsx reads off the
     /api/patreon-access payload (and off the /api/apply 403 detail.access) exists:
       access.allowed, access.via, access.tier, access.tier_roles,
       access.discord.{linked, username, in_guild, tier_role, checked},
       access.patreon.{linked, active, tier_name}

Run: python backend/tests_local/test_patreon_apply_gate.py  (or pytest)
"""
import sys

# ---- mirrors of backend/server.py ----

def _parse_patreon_roles(raw):
    out = {}
    for part in (raw or '').split(','):
        part = part.strip()
        if not part:
            continue
        rid, _, label = part.partition(':')
        rid = rid.strip()
        if rid.isdigit():
            out[rid] = label.strip() or rid
    return out


ROLES_ENV = ("1523183010575286283:Apex,1523182777342759022:Elder,1523182644764999790:Adult,"
             "1523181589457141922:Sub Adult,1523181427640762468:Juvie")
DISCORD_PATREON_ROLES = _parse_patreon_roles(ROLES_ENV)


def _tier_from_roles(roles):
    if not roles:
        return None
    held = set(roles)
    for rid, label in DISCORD_PATREON_ROLES.items():
        if rid in held:
            return label
    return None


def patreon_access_decide(user, member_info):
    """Mirror of server.py::_patreon_access with the live fetch injected as
    `member_info` = (in_guild, roles) and the users-collection write dropped."""
    u = user or {}
    pat_active = u.get("patreon_patron_status") == "active_patron"
    out = {
        "allowed": False, "via": None, "tier": None,
        "discord": {
            "linked": bool(u.get("discord_id")),
            "username": u.get("discord_username") or None,
            "in_guild": None,
            "tier_role": None,
            "checked": False,
        },
        "patreon": {
            "linked": bool(u.get("patreon_id")),
            "active": pat_active,
            "tier_name": u.get("patreon_tier_name") if pat_active else None,
        },
        "tier_roles": list(DISCORD_PATREON_ROLES.values()),
    }
    if u.get("role") == "admin":
        out.update(allowed=True, via="admin")
        return out
    tier = None
    if u.get("discord_id") and DISCORD_PATREON_ROLES:
        in_guild, roles = member_info
        out["discord"]["in_guild"] = in_guild
        out["discord"]["checked"] = in_guild is not None
        if in_guild is None:
            tier = u.get("discord_tier_role") or None
            out["discord"]["in_guild"] = u.get("discord_in_guild") if tier else None
        else:
            tier = _tier_from_roles(roles)
    out["discord"]["tier_role"] = tier
    if tier:
        out.update(allowed=True, via="discord_role", tier=tier)
    elif pat_active:
        out.update(allowed=True, via="patreon", tier=None)  # server maps patreon tier separately
    return out


APEX = "1523183010575286283"
JUVIE = "1523181427640762468"

# Keys SkinEditor.jsx reads (grepped from the file: PatreonGateBody + banner + applyToLive).
FRONTEND_KEYS = {
    "top": ["allowed", "via", "tier", "tier_roles", "discord", "patreon"],
    "discord": ["linked", "username", "in_guild", "tier_role", "checked"],
    "patreon": ["linked", "active", "tier_name"],
}


def check(name, cond):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}")
    return cond


def test_patreon_apply_gate():
    ok = True

    # role parsing
    ok &= check("5 tier roles parsed, order preserved",
                list(DISCORD_PATREON_ROLES.values()) == ["Apex", "Elder", "Adult", "Sub Adult", "Juvie"])
    ok &= check("precedence: Apex+Juvie -> Apex", _tier_from_roles([JUVIE, APEX]) == "Apex")

    # decision matrix
    r = patreon_access_decide({"role": "admin"}, (None, None))
    ok &= check("admin allowed via admin", r["allowed"] and r["via"] == "admin")

    r = patreon_access_decide({"id": "u1", "discord_id": "5", "discord_username": "x"}, (True, [APEX, "999"]))
    ok &= check("Apex role holder allowed near-instant", r["allowed"] and r["via"] == "discord_role" and r["tier"] == "Apex")

    r = patreon_access_decide({"id": "u2", "discord_id": "5", "patreon_id": "p1"}, (True, ["999"]))
    ok &= check("in guild, no tier role, patreon merely LINKED -> denied",
                not r["allowed"] and r["discord"]["in_guild"] is True and r["discord"]["tier_role"] is None)

    r = patreon_access_decide({"id": "u3", "discord_id": "5", "discord_tier_role": "Elder", "discord_in_guild": True}, (None, None))
    ok &= check("Discord API down + previously-verified holder -> stale grant", r["allowed"] and r["tier"] == "Elder")

    r = patreon_access_decide({"id": "u4", "discord_id": "5"}, (None, None))
    ok &= check("Discord API down + unknown -> stays locked", not r["allowed"] and r["discord"]["checked"] is False)

    r = patreon_access_decide({"id": "u5", "patreon_id": "p", "patreon_patron_status": "active_patron",
                               "patreon_tier_name": "Apex Tier"}, (None, None))
    ok &= check("active patron without Discord allowed via patreon", r["allowed"] and r["via"] == "patreon")

    r = patreon_access_decide({"id": "u6", "discord_id": "5"}, (False, []))
    ok &= check("not in guild -> denied with in_guild False", not r["allowed"] and r["discord"]["in_guild"] is False)

    # frontend contract parity (on a denied payload — the shape the gate panel renders)
    for k in FRONTEND_KEYS["top"]:
        ok &= check(f"payload has top-level '{k}'", k in r)
    for k in FRONTEND_KEYS["discord"]:
        ok &= check(f"payload.discord has '{k}'", k in r["discord"])
    for k in FRONTEND_KEYS["patreon"]:
        ok &= check(f"payload.patreon has '{k}'", k in r["patreon"])

    assert ok, "patreon apply-gate mirror checks failed"


if __name__ == "__main__":
    test_patreon_apply_gate()
    print("ALL PASS")
    sys.exit(0)
