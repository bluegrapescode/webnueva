# -*- coding: utf-8 -*-
"""Admin user directory - /admin/users must be able to find EVERY account.

The 2026-08-09 report ("cant find a lot of users in the web admin"): the route
pulled `db.users.find({}).sort(created_at,-1).to_list(1000)` and then filtered
that page in Python. La Isla Nublar had 1192 accounts, so the 192 OLDEST ones
were unreachable by any search - and an unreachable account looks exactly like
an account that does not exist. The dashboard tile said 1192 the whole time.

This battery proves the replacement WITHOUT a database: the query builder and
the limit clamp are lifted out of server.py by AST (no import of the FastAPI
app, no env), and the produced Mongo `$regex` is executed with Python's own re
against real name samples - Mongo and Python share PCRE-ish semantics for the
plain substring + IGNORECASE case this route uses.

Covered on purpose: the empty needle (must mean EVERYONE, never nobody), regex
metacharacters typed by a human (must be literal, not a pattern that matches
the whole site), the Discord-name lane, and every junk ?limit= value.

Run: py -3.12 backend/tests_local/test_admin_user_directory.py
"""
import ast
import os
import re
import sys
from typing import Optional

BACKEND = os.path.join(os.path.dirname(__file__), "..")
SERVER = os.path.join(BACKEND, "server.py")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def load_source():
    with open(SERVER, "r", encoding="utf-8") as f:
        return f.read()


def lift(src, names):
    """Exec just the named top-level functions/assignments out of server.py."""
    tree = ast.parse(src)
    wanted = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            wanted.append(node)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    wanted.append(node)
    mod = ast.Module(body=wanted, type_ignores=[])
    ns = {"re": re, "Optional": Optional}
    exec(compile(ast.fix_missing_locations(mod), "<lifted>", "exec"), ns)
    return ns


def matches(q, user):
    """Run a built Mongo filter against one user dict, Python-side."""
    if not q:
        return True
    for clause in q["$or"]:
        (field, spec), = clause.items()
        val = user.get(field)
        if not isinstance(val, str):
            continue
        if re.search(spec["$regex"], val, re.IGNORECASE):
            return True
    return False


def main():
    src = load_source()
    ns = lift(src, {"admin_user_search_query", "clamp_admin_user_limit",
                    "ADMIN_USER_LIMIT_DEFAULT", "ADMIN_USER_LIMIT_MAX"})
    build = ns["admin_user_search_query"]
    clamp = ns["clamp_admin_user_limit"]
    DEFAULT = ns["ADMIN_USER_LIMIT_DEFAULT"]
    MAX = ns["ADMIN_USER_LIMIT_MAX"]

    print("empty needle == the whole directory (never a match-nothing query)")
    for needle in (None, "", "   ", "\t\n"):
        q = build(needle)
        check(f"empty {needle!r} -> {{}}", q == {}, f"got {q!r}")

    print("plain needle matches name, steam id and discord name, any case")
    q = build("moon")
    check("three fields searched", set(list(c)[0] for c in q["$or"]) ==
          {"persona_name", "steam_id", "discord_username"}, repr(q))
    check("case-insensitive flag", all(list(c.values())[0]["$options"] == "i" for c in q["$or"]))
    check("matches MoonVeil (name)", matches(q, {"persona_name": "MoonVeil"}))
    check("matches by discord name", matches(q, {"persona_name": "x", "discord_username": "moonlord"}))
    check("does not match unrelated", not matches(q, {"persona_name": "Rexy", "steam_id": "76561198000000001"}))

    q = build("76561198012345678")
    check("full steam id matches", matches(q, {"persona_name": "x", "steam_id": "76561198012345678"}))
    q = build("012345")
    check("steam id substring matches", matches(q, {"persona_name": "x", "steam_id": "76561198012345678"}))

    print("the dangerous direction: a typed metacharacter is a LITERAL")
    everyone = [{"persona_name": "Rexy"}, {"persona_name": "MoonVeil"}, {"persona_name": "Duran"}]
    q = build(".")
    check("'.' does not match everyone", not any(matches(q, u) for u in everyone),
          "a raw regex '.' would have matched all three")
    check("'.' still matches a real dot", matches(build("."), {"persona_name": "mr.duran"}))
    q = build("a|b")
    check("'a|b' is literal, not alternation", not matches(q, {"persona_name": "Rexy"}))
    check("'a|b' matches the literal text", matches(build("a|b"), {"persona_name": "team a|b"}))
    for bad in ("(", "[", "*", "+", "\\", "??", "(?i)"):
        try:
            build(bad)
            check(f"needle {bad!r} builds without raising", True)
        except Exception as e:  # noqa: BLE001
            check(f"needle {bad!r} builds without raising", False, repr(e))

    print("a user missing a field is skipped, not crashed on")
    q = build("moon")
    check("missing persona_name survives", matches(q, {"steam_id": "moon123"}))
    check("None field survives", not matches(q, {"persona_name": None, "steam_id": None}))

    print("limit clamp - junk never 500s and never hands out the collection")
    cases = [(None, DEFAULT), (0, 1), (-5, 1), (1, 1), (50, 50),
             (MAX, MAX), (MAX + 1, MAX), (10 ** 9, MAX),
             ("50", 50), ("abc", DEFAULT), ("", DEFAULT), (3.7, 3), ([], DEFAULT)]
    for raw, want in cases:
        try:
            got = clamp(raw)
        except Exception as e:  # noqa: BLE001
            got = f"raised {e!r}"
        check(f"clamp({raw!r}) == {want}", got == want, f"got {got!r}")
    check("default covers today's site (1192 accounts)", DEFAULT >= 1192, f"default={DEFAULT}")

    print("source contract - the route must query the DB, not a Python page")
    tree = ast.parse(src)
    route = None
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "admin_users":
            route = node
    check("admin_users route exists", route is not None)
    body = ast.get_source_segment(src, route) if route else ""
    check("no 1000-row page left", ".to_list(1000)" not in body, body[:200])
    check("uses the query builder", "admin_user_search_query" in body)
    check("uses the clamp", "clamp_admin_user_limit" in body)
    check("counts the real match total", "count_documents" in body)
    check("reports the total on the wire", "X-Total-Matches" in body)
    check("flags a truncated answer", "X-Truncated" in body)
    check("logs a truncated answer", "TRUNCATED" in body)
    check("no Python-side lowercase filter", ".lower()" not in body, body[:200])
    # ?limit= must arrive as a STRING. Typed int, FastAPI answers 422 for
    # ?limit=abc before clamp_admin_user_limit runs, and the clamp cases above
    # would be promising something the wire does not do (caught on prod by the
    # signed-in HTTP proof, 2026-08-09).
    check("limit is not typed as an int on the route",
          "limit: Optional[int]" not in body and "limit: int" not in body, body[:300])

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
