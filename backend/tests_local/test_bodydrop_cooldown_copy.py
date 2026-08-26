# -*- coding: utf-8 -*-
"""Body Drop cooldown 10-min gate - Lua constant + web copy stay in lockstep.

Pure source scan (no imports of vault.py, which needs motor/env). Asserts the
repo Lua mod constant CORPSE_COOLDOWN is 600 with all four paired fallbacks,
no orphaned 900 fallback remains, and the Spanish web copy says 10 minutos.

Run: py -3.12 backend/tests_local/test_bodydrop_cooldown_copy.py
"""
import os
import re
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..")
REPO = os.path.abspath(os.path.join(BACKEND, "..", ".."))
LUA = os.path.join(REPO, "mod", "lua", "LaIslaNublarDataMod", "Scripts", "main.full.lua")
VAULT = os.path.join(BACKEND, "vault.py")
VAULT_JSX = os.path.join(REPO, "web", "frontend", "src", "components", "inventory", "VaultSection.jsx")

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


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


lua = read(LUA)
vault_src = read(VAULT)
jsx = read(VAULT_JSX)

print("[lua constant]")
decls = re.findall(r"^local CORPSE_COOLDOWN = (\d+)", lua, re.M)
check("exactly one declaration", len(decls) == 1, str(decls))
check("declaration is 600", decls == ["600"], str(decls))
fallbacks_600 = lua.count("(tonumber(CORPSE_COOLDOWN) or 600)")
fallbacks_900 = lua.count("(tonumber(CORPSE_COOLDOWN) or 900)")
check("four paired 600 fallbacks", fallbacks_600 == 4, str(fallbacks_600))
check("zero stale 900 fallbacks", fallbacks_900 == 0, str(fallbacks_900))
check("comment says 10 minutes", "600  -- 10 minutes per SteamID Deino" in lua)
check("lease comment says 10 min", "(10 min), so reconnect/repossess churn" in lua)
check("no stale 15-min lease comment", "(15 min), so reconnect" not in lua)

print("[web copy]")
DIEZ = "espera de 10 minutos"
check("vault.py refusal says 10 minutos", DIEZ in vault_src)
check("vault.py refusal no longer says 15", "espera de 15 minutos" not in vault_src)
check("vault.py comment says 10-min lease", "10-min per-SteamID feeder lease" in vault_src)
check("VaultSection modal says cada 10 minutos", "un Body Drop cada 10 minutos" in jsx)
check("VaultSection modal no longer says cada 15", "cada 15 minutos" not in jsx)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
