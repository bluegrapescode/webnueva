# -*- coding: utf-8 -*-
r"""The skin emission: ONE srgb->linear encode, bounds kept in the LINEAR band.

2026-08-11 LINEAR RESTORE. This suite began (2026-08-10) as the HDR-band pin
for the 2026-08-09 RAW emission. That raw contract is now SUPERSEDED and this
file moved with it -- a pin that gets deleted is a pin that stops protecting
anything.

Why the reversal: CustomizerData's colour slots are ``FLinearColor``, which UE
consumes LINEAR by definition, so a raw picker fraction written there renders
every mid-tone too bright (the fleet's "washed out / lighter, and only on some
colours" wave, which began the day of the raw flip). The original "one part of
the body goes dark" defect was the STUDIO DOUBLE ENCODE, never the backend
encode. So the wire carries ONE encode of the raw picker fraction:

    v = srgb_to_linear(clamp01(pick))       # <- the ONE encode
    v = v + eps if v <= 1.0 - eps else v - eps
    round(clamp01(v), 6)

The 2026-08-10 bounds discipline is KEPT but now lives in the LINEAR domain:
never exactly 0 (the client's all-zero short-circuit), never at or above 1 (the
native reader's HDR band). ``variation`` is snapped to an EXACT SkinVariation
key {2.0, 8.0, 16.0}, default 8.0 Medium, and is NEVER jittered -- the eps is
for colour channels only. Framework canonical: ``webcore/skin_apply.py``
(:func:`srgb_to_linear`, :func:`_encode_linear`, :func:`variation_key`).

TWO RED CONTROLS, both live in here so no assertion can pass vacuously:
  * the RAW emission (the thing being reverted): 0.5 -> 0.5005, not ~0.2145.
  * the DOUBLE encode (the thing that produced the original dark defect):
    0.5 -> ~0.0376, not ~0.2145.

THIS SUITE RUNS THE REAL BYTES. ``server.py`` cannot be imported here (no
motor/FastAPI/.env in this sandbox), so instead of mirroring the math -- a
mirror would have stayed green for the entire time the bug was live -- it lifts
``SkinPayloadIn.to_command``'s OWN SOURCE **and the module-level
``_srgb_to_linear`` it now calls** out of server.py with ast and executes them
together. A revert in server.py fails this suite; an edit to a copy of the math
cannot make it pass.

Run:  python backend/tests_local/test_skin_emission_float_band.py
Exit: 0 all pass / 1 a check failed / 2 the suite could NOT run (2 is never a
pass -- a suite that did not run is a failed read).
"""
import ast
import builtins
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, ".."))
SERVER_PY = os.path.join(BACKEND, "server.py")

SLOTS = ("body", "markings", "flank", "underbelly", "detail1", "eyes",
         "male_display")

#: the parked-recipe FOLD RECEIPT band -- vault.py / bot dino.py
#: ``_parked_skin_recipe_grade`` grade a markerless parked row as OUR paint when
#: a top RGB channel sits inside it. Duplicated here on purpose: this suite is
#: what proves the emission still lands there.
RECEIPT_LO, RECEIPT_HI = 0.9989, 0.99995

VARIATION_KEYS = (2.0, 8.0, 16.0)
VARIATION_DEFAULT = 8.0

PASS = 0
FAIL = 0
_FAILED = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS %s" % name)
    else:
        FAIL += 1
        _FAILED.append(name)
        print("  FAIL %s %s" % (name, detail))


# ---------------------------------------------------------------------------
# lift the REAL to_command -- and the REAL _srgb_to_linear -- out of server.py
# ---------------------------------------------------------------------------
def load_sources():
    with open(SERVER_PY, "r", encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    lines = src.splitlines()

    def block(node):
        return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))

    cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SkinPayloadIn":
            cls = node
            break
    if cls is None:
        print("CANNOT RUN: server.py has no class SkinPayloadIn")
        sys.exit(2)
    fn = None
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == "to_command":
            fn = node
            break
    if fn is None:
        print("CANNOT RUN: SkinPayloadIn has no to_command")
        sys.exit(2)
    # the transfer function to_command calls. Lifting it (rather than mirroring
    # it here) is what keeps the encode assertions non-vacuous.
    enc = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_srgb_to_linear":
            enc = node
            break
    if enc is None:
        print("CANNOT RUN: server.py has no module-level _srgb_to_linear")
        sys.exit(2)
    return src, block(fn), block(enc)


SRC, TO_COMMAND_SRC, ENCODE_SRC = load_sources()
TO_COMMAND_AST = ast.parse(TO_COMMAND_SRC)
CALLED_NAMES = set()
for _n in ast.walk(TO_COMMAND_AST):
    if isinstance(_n, ast.Call) and isinstance(_n.func, ast.Name):
        CALLED_NAMES.add(_n.func.id)


class _FixedRandom(object):
    """Pins the eps draw so a wire comparison is exact, and COUNTS every call
    so a suite that silently stopped executing the real source says so."""

    def __init__(self, eps):
        self.eps = float(eps)
        self.calls = 0
        self.eps_calls = 0

    def uniform(self, a, b):
        self.calls += 1
        if (a, b) == (1e-4, 1e-3):
            self.eps_calls += 1
            return self.eps
        # any OTHER draw is a jitter this contract forbids; return something
        # unmistakable so it cannot hide inside a plausible value.
        return -12345.0


def compile_to_command(rng):
    """exec the lifted sources with ``import random`` bound to OUR stub, scoped
    to this function only -- the global random module is never touched."""
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "random":
            return rng
        return real_import(name, *a, **kw)

    bi = dict(vars(builtins))
    bi["__import__"] = fake_import
    ns = {"__builtins__": bi}
    exec(compile(ENCODE_SRC, "server.py::_srgb_to_linear", "exec"), ns)
    exec(compile(TO_COMMAND_SRC, "server.py::SkinPayloadIn.to_command", "exec"), ns)
    return ns["to_command"], ns["_srgb_to_linear"]


# the REAL transfer function, lifted from server.py, for expectation arithmetic
S2L = compile_to_command(_FixedRandom(5e-4))[1]


class _RGBA(object):
    def __init__(self, r, g, b, a=1.0):
        self._v = [float(r), float(g), float(b), float(a)]

    def as_list(self):
        return list(self._v)


class _Payload(object):
    def __init__(self, picks, variation=0, pattern=1, female=False,
                 skin_code="LIN-BAND"):
        for slot in SLOTS:
            setattr(self, slot, _RGBA(*picks[slot]))
        self.variation = variation
        self.pattern = pattern
        self.female = female
        self.skin_code = skin_code


def uniform_picks(r, g, b, a=1.0):
    return {slot: (r, g, b, a) for slot in SLOTS}


def emit(picks, eps, **kw):
    rng = _FixedRandom(eps)
    cmd = compile_to_command(rng)[0](_Payload(picks, **kw), "BP_Rex_C_1",
                                     "BP_Rex_C", "76561199000000001")
    return cmd, rng


def expect_linear(c, eps):
    """What the contract says the wire must carry."""
    v = S2L(min(1.0, max(0.0, float(c))))
    v = v + eps if v <= 1.0 - eps else v - eps
    # rails closed on the ROUNDED value -- see server.py::_j
    return min(0.999999, max(0.000001, round(min(1.0, max(0.0, v)), 6)))


def raw_j(c, eps):
    """RED CONTROL 1 -- the 2026-08-10 RAW emission VERBATIM (the thing this
    ship reverts). No encode, no rounding."""
    x = min(1.0, max(0.0, float(c)))
    return x + eps if x <= 1.0 - eps else x - eps


def double_j(c, eps):
    """RED CONTROL 2 -- the DOUBLE encode (a frontend that already encoded,
    feeding a backend that encodes again). This is the original "one part of
    the body goes dark" defect, and 0.5 lands on ~0.0376."""
    v = S2L(S2L(min(1.0, max(0.0, float(c)))))
    v = v + eps if v <= 1.0 - eps else v - eps
    return min(0.999999, max(0.000001, round(min(1.0, max(0.0, v)), 6)))


def channels(cmd):
    out = []
    for slot in SLOTS:
        out.extend(cmd[slot][:3])
    return out


# ---------------------------------------------------------------------------
def main():
    EPS = 5.0e-4
    SEED = 9.0e-4          # the fleet's seeded-triple draw

    print("[A] the ONE encode -- the seeded wire triple the whole fleet ships")
    cmd, rng = emit(uniform_picks(0.5, 0.5, 0.5), SEED)
    ch = channels(cmd)
    check("A1 the eps draw really came from this suite (source was executed)",
          rng.eps_calls == 1 and rng.calls == 1,
          "calls=%d eps_calls=%d" % (rng.calls, rng.eps_calls))
    check("A2 pick 0.5 -> 0.214941 (linear(0.5) + eps), the fleet's seeded value",
          all(abs(c - 0.214941) < 1e-9 for c in ch), repr(sorted(set(ch))))
    sat, _ = emit(uniform_picks(1.0, 1.0, 1.0), SEED)
    check("A3 pick 1.0 -> 0.9991 (just UNDER 1.0)",
          all(abs(c - 0.9991) < 1e-9 for c in channels(sat)),
          repr(sorted(set(channels(sat)))))
    blk, _ = emit(uniform_picks(0.0, 0.0, 0.0), SEED)
    check("A4 pick 0.0 -> 0.0009 (just ABOVE 0.0)",
          all(abs(c - 0.0009) < 1e-9 for c in channels(blk)),
          repr(sorted(set(channels(blk)))))
    check("A5 the wire is stamped linear", cmd.get("color_space") == "linear",
          repr(cmd.get("color_space")))

    print("[B] RED CONTROL 1 -- the retired RAW emission fails every check")
    raw_mid = raw_j(0.5, SEED)
    check("B1 the raw emission puts 0.5 at 0.5009, not ~0.2149",
          abs(raw_mid - 0.5009) < 1e-9, repr(raw_mid))
    check("B2 A2's assertion is non-vacuous -- it rejects the raw value",
          not all(abs(raw_mid - 0.214941) < 1e-9 for _ in ch), repr(raw_mid))
    check("B3 emitted and raw differ by more than a quarter of the range at 0.5",
          abs(ch[0] - raw_mid) > 0.28, "%r vs %r" % (ch[0], raw_mid))
    check("B4 the raw marker is GONE from the wire",
          cmd.get("color_space") != "srgb", repr(cmd.get("color_space")))

    print("[C] RED CONTROL 2 -- the DOUBLE encode is what we must never emit")
    dbl = double_j(0.5, SEED)
    check("C1 a double encode puts 0.5 at 0.0376 + eps (the original dark "
          "defect), a fifth of where the single encode lands",
          abs(S2L(S2L(0.5)) - 0.03764948) < 1e-8
          and abs(dbl - (S2L(S2L(0.5)) + SEED)) < 1e-6, repr(dbl))
    check("C2 the emission is NOT the double encode",
          abs(ch[0] - dbl) > 0.17, "%r vs %r" % (ch[0], dbl))
    check("C3 the three candidates are mutually distinct -- this test can tell "
          "raw / single / double apart", len({round(raw_mid, 6), ch[0], dbl}) == 3,
          repr(sorted({round(raw_mid, 6), ch[0], dbl})))
    dbl_sweep = []
    for i in range(1, 100):
        p = i / 100.0
        got, _ = emit(uniform_picks(p, p, p), EPS)
        if abs(got["body"][0] - double_j(p, EPS)) < 1e-9:
            dbl_sweep.append(p)
    check("C4 99 mid picks: not one of them lands on the double encode",
          not dbl_sweep, repr(dbl_sweep[:3]))

    print("[D] the encode is EXACT -- every 8-bit pick round-trips")
    drift = []
    for n in range(256):
        p = n / 255.0
        got, _ = emit(uniform_picks(p, p, p), EPS)
        if got["body"][0] != expect_linear(p, EPS):
            drift.append((p, got["body"][0], expect_linear(p, EPS)))
    check("D1 all 256 8-bit picks emit exactly srgb_to_linear(pick) +/- eps, 6dp",
          not drift, repr(drift[:3]))
    check("D2 the transfer function really is the IEC curve (lifted from "
          "server.py, not mirrored here)",
          abs(S2L(0.5) - 0.21404114) < 1e-8 and S2L(1.0) == 1.0
          and S2L(0.0) == 0.0, repr((S2L(0.0), S2L(0.5), S2L(1.0))))
    check("D3 the encode DARKENS the mid-tones (that is the whole point)",
          all(expect_linear(p, EPS) < raw_j(p, EPS)
              for p in (0.2, 0.35, 0.5, 0.65, 0.8, 0.95)), "")

    print("[E] bounds discipline, now in the LINEAR domain")
    check("E1 a 0.0 pick floors strictly ABOVE 0.0 (client all-zero sentinel)",
          all(c > 0.0 for c in channels(blk)), repr(blk["body"]))
    check("E2 a 1.0 pick stays strictly BELOW 1.0 (native HDR band)",
          all(c < 1.0 for c in channels(sat)), repr(sat["body"]))
    neg, _ = emit(uniform_picks(-3.0, -3.0, -3.0), EPS)
    check("E3 an out-of-range NEGATIVE pick still clamps up into the band",
          all(0.0 < c < 1.0 for c in channels(neg)), repr(neg["body"]))
    over, _ = emit(uniform_picks(7.5, 7.5, 7.5), EPS)
    check("E4 an out-of-range HIGH pick clamps down into the band, never above",
          all(0.999 <= c < 1.0 for c in channels(over)), repr(over["body"]))
    print("[F] the RAILS are closed on the ROUNDED value, not before it")

    def canonical_no_rail(c, eps):
        """The framework canonical's exact three lines, WITHOUT LIN's rail
        closure -- the RED control for block F. Kept here so the extra clamp in
        server.py can never be 'tidied away' as redundant."""
        v = S2L(min(1.0, max(0.0, float(c))))
        v = v + eps if v <= 1.0 - eps else v - eps
        return round(min(1.0, max(0.0, v)), 6)

    bad = []
    for n in range(0, 901):
        e = 1.0e-4 + (n / 900.0) * (1.0e-3 - 1.0e-4)
        for pick in (1.0, 0.9999, 0.999, 0.5, 0.05, 0.0, -1.0, 2.0):
            got, _ = emit(uniform_picks(pick, pick, pick), e)
            for c in channels(got):
                if not (0.0 < c < 1.0):
                    bad.append((e, pick, c))
    check("F1 901 eps draws x 8 picks x 7 slots: every emitted channel is "
          "strictly inside (0, 1)", not bad, repr(bad[:3]))
    rail_hits = [(round(1.0e-4 + (n / 900.0) * (1.0e-3 - 1.0e-4), 9), p)
                 for n in range(0, 901)
                 for p in (0.9999,)
                 if canonical_no_rail(p, 1.0e-4 + (n / 900.0)
                                      * (1.0e-3 - 1.0e-4)) >= 1.0]
    check("F2 non-vacuous: without the rail closure the SAME sweep puts a "
          "channel back ON 1.0 (the 6dp round is the last step)",
          len(rail_hits) > 0, "rail_hits=%d" % len(rail_hits))
    reachable = [n for n in range(256)
                 for e in (1.0e-4, 5.0e-4, 1.0e-3)
                 if canonical_no_rail(n / 255.0, e) >= 1.0]
    check("F3 ...but NO 8-bit pick can reach that window, so the closure moves "
          "no byte a real player can produce", not reachable, repr(reachable[:5]))
    same = []
    for n in range(256):
        p = n / 255.0
        got, _ = emit(uniform_picks(p, p, p), EPS)
        if got["body"][0] != canonical_no_rail(p, EPS):
            same.append(p)
    check("F4 all 256 8-bit picks are byte-identical to the framework "
          "canonical's own shape", not same, repr(same[:3]))

    print("[G] the FOLD RECEIPT survives -- _parked_skin_recipe_grade still "
          "recognises our own paint")
    check("G1 srgb_to_linear(1.0) is EXACTLY 1.0, so a saturated pick still "
          "emits 1.0 - eps", S2L(1.0) == 1.0 and abs(
              expect_linear(1.0, EPS) - (1.0 - EPS)) < 1e-12,
          repr(expect_linear(1.0, EPS)))
    out_of_band = []
    for n in range(0, 901):
        e = 1.0e-4 + (n / 900.0) * (1.0e-3 - 1.0e-4)
        got, _ = emit(uniform_picks(1.0, 1.0, 1.0), e)
        v = got["body"][0]
        if not (RECEIPT_LO <= v <= RECEIPT_HI):
            out_of_band.append((e, v))
    check("G2 901 eps draws: a saturated pick ALWAYS lands inside the receipt "
          "band [0.9989, 0.99995]", not out_of_band, repr(out_of_band[:3]))
    mids_in_band = [p / 100.0 for p in range(0, 100)
                    if RECEIPT_LO <= expect_linear(p / 100.0, EPS) <= RECEIPT_HI]
    check("G3 the receipt still MEANS saturated -- no mid pick counterfeits it",
          not mids_in_band, repr(mids_in_band[:5]))

    print("[H] 6dp resolution -- the round is real and the dark end survives")
    check("H1 every emitted channel is rounded to exactly 6 places",
          all(round(c, 6) == c for c in channels(cmd) + channels(blk)
              + channels(sat)), repr(ch[0]))
    check("H2 the round is REAL: the unrounded encode carries more digits",
          repr(S2L(0.5) + EPS) != repr(round(S2L(0.5) + EPS, 6)),
          repr(S2L(0.5) + EPS))
    dark = set()
    for n in range(32):
        got, _ = emit(uniform_picks(n / 255.0, 0.0, 0.0), EPS)
        dark.add(got["body"][0])
    check("H3 the 32 darkest 8-bit picks stay 32 DISTINCT values after the "
          "encode + 6dp round", len(dark) == 32, "distinct=%d" % len(dark))

    print("[I] variation = an EXACT SkinVariation key, and NEVER jittered")
    check("I1 the site's default (0) snaps to the game's own default 8.0 Medium",
          cmd.get("variation") == VARIATION_DEFAULT
          and repr(cmd.get("variation")) == repr(8.0), repr(cmd.get("variation")))
    keyed = {k: emit(uniform_picks(0.5, 0.5, 0.5), EPS,
                     variation=k)[0]["variation"] for k in VARIATION_KEYS}
    check("I2 each exact key rides through unchanged (2.0 / 8.0 / 16.0)",
          all(keyed[k] == k and repr(keyed[k]) == repr(k) for k in VARIATION_KEYS),
          repr(keyed))
    offkey = {v: emit(uniform_picks(0.5, 0.5, 0.5), EPS,
                      variation=v)[0]["variation"]
              for v in (1, 3, 5, 2.00694, 7.999, 15.5, -2.0)}
    check("I3 an off-key value (incl. a jittered 2.00694) falls back to 8.0, "
          "never to a value the client cannot map",
          all(v == VARIATION_DEFAULT for v in offkey.values()), repr(offkey))
    vs, cs = set(), set()
    for _ in range(30):
        rng2 = _FixedRandom(EPS)
        fn = compile_to_command(rng2)[0]
        x = fn(_Payload(uniform_picks(0.5, 0.5, 0.5), variation=2), "a", "c", "s")
        vs.add(repr(x["variation"]))
        cs.add(x["body"][0])
    check("I4 30 draws: variation NEVER moves off its key", vs == {repr(2.0)},
          repr(vs))
    # the colour jitter is what makes the engine's struct-property delta fire;
    # proving it still moves is what stops I4 from being satisfied by a dead
    # emitter that stopped drawing at all.
    lo, _ = emit(uniform_picks(0.5, 0.5, 0.5), 1.0e-4)
    hi, _ = emit(uniform_picks(0.5, 0.5, 0.5), 1.0e-3)
    check("I5 ...while the COLOUR still jitters per apply (the delta still fires)",
          lo["body"][0] != hi["body"][0],
          "%r vs %r" % (lo["body"][0], hi["body"][0]))
    zero = [v for v in list(keyed.values()) + list(offkey.values())
            + [cmd["variation"]] if v == 0.0]
    check("I6 this lane NEVER emits variation 0.0 -- exact 0.0 is the glitch "
          "shader's own trigger and belongs to glitch_catalog alone",
          not zero, repr(zero))

    print("[J] ONE choke point, and the rest of the wire is unchanged")
    check("J1 server.py defines exactly one _j converter",
          SRC.count("def _j(") == 1, "count=%d" % SRC.count("def _j("))
    check("J2 the emission CALLS the module-level _srgb_to_linear (AST, not "
          "text)", "_srgb_to_linear" in CALLED_NAMES, repr(sorted(CALLED_NAMES)))
    check("J3 it is called ONCE per channel, not twice",
          TO_COMMAND_SRC.count("_srgb_to_linear(") == 1,
          "count=%d" % TO_COMMAND_SRC.count("_srgb_to_linear("))
    check("J4 the fold is a conditional lift, the framework canonical's shape "
          "(v + eps if v <= 1.0 - eps else v - eps), not a bare clamp",
          any(isinstance(n, ast.IfExp) for n in ast.walk(TO_COMMAND_AST)),
          "no conditional expression in to_command")
    check("J5 all 7 colour regions still land, 4 components each",
          all(isinstance(cmd.get(s), list) and len(cmd[s]) == 4 for s in SLOTS),
          repr(sorted(cmd)))
    alpha, _ = emit({s: (0.5, 0.5, 0.5, 0.25) for s in SLOTS}, EPS)
    check("J6 alpha rides through untouched, never encoded and never folded",
          all(alpha[s][3] == 0.25 for s in SLOTS), repr(alpha["body"]))
    check("J7 skin_code / class / steamid still carried",
          cmd.get("skin_code") == "LIN-BAND" and cmd.get("class") == "BP_Rex_C"
          and cmd.get("steamid") == "76561199000000001", repr(sorted(cmd)))

    print("\n%d passed, %d failed" % (PASS, FAIL))
    if _FAILED:
        print("FAILED: %s" % ", ".join(_FAILED))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
