import React, { useCallback, useEffect, useRef, useState } from "react";
import { Ban, ShieldCheck, Search, X, AlertTriangle, History } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useSound } from "@/context/SoundContext";
import {
  BAN_COPY, fill, opId, displayName, confirmSentence, confirmNote, buildPlaceBody,
  rowFacts, candidateFacts, suggestHint, refusalText, splitHistory,
} from "@/lib/webBans";

// ── Baneos de la página web (owner-only tab, 2026-08-17) ─────────────────────
// ONE BOX -> A DROP-DOWN -> ONE PERSON -> ONE BUTTON -> ONE PLAIN-WORDS CONFIRM.
// Type a name and matching players appear as you type (the site's own users +
// the bot's Discord names); paste a Steam ID and that account appears even if
// nobody here has ever seen it. Pick a person, choose how long, optionally say
// why, press the one button - and a confirm card says, in a sentence, exactly
// what is about to happen before anything does.
//
// NOTHING HERE DECIDES ANYTHING. The server previews and refuses on its own
// gates (you cannot ban yourself, you cannot ban an owner, a shorter ban folds
// into a longer one) and every sentence a refusal produces is shown verbatim.
// The two-step is the SERVER's arm-and-confirm handshake (webban.py): the first
// press arms, the second spends the arm, and a confirm whose payload drifted
// from the preview is refused there, not here.

const inputCls = "w-full glass rounded-lg px-3 py-2.5 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-gold/50";
const dangerBtn = "inline-flex items-center justify-center gap-2 font-bold px-4 py-2.5 rounded-xl transition-all disabled:opacity-50 hover:brightness-110";
const dangerStyle = { background: "rgba(226,74,74,0.14)", border: "1px solid #E24A4A", color: "#E24A4A" };
const ghostBtn = "inline-flex items-center justify-center gap-2 text-sm font-semibold px-4 py-2.5 rounded-xl glass border border-white/10 text-foreground hover:bg-white/5 transition-all disabled:opacity-50";

function Face({ person, size = 32 }) {
  const src = person && person.avatar;
  if (src) return <img src={src} alt="" width={size} height={size} loading="lazy" className="rounded-lg object-cover border border-white/10 shrink-0" style={{ width: size, height: size }} />;
  const letter = (displayName(person).charAt(0) || "?").toUpperCase();
  return (
    <span aria-hidden="true" className="rounded-lg glass border border-white/10 flex items-center justify-center font-display font-bold text-gold shrink-0" style={{ width: size, height: size, fontSize: size * 0.45 }}>{letter}</span>
  );
}

function BanRow({ row, withActions, onLifted }) {
  const { play } = useSound();
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  const facts = rowFacts(row);

  // TWO PRESSES, in place: the first turns the button into the question, the
  // second acts. A misclick on a list of people must cost nothing.
  const press = async () => {
    if (!armed) {
      setArmed(true);
      play("click");
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setArmed(false), 6000);
      return;
    }
    clearTimeout(timer.current);
    setArmed(false);
    setBusy(true);
    try {
      await api.adminBansLift(row.steam_id);
      play("success");
      const done = fill(BAN_COPY.doneUnban, { name: displayName(row) });
      toast.success(done);
      onLifted?.(done);
    } catch (e) {
      play("error");
      toast.error(refusalText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-3 glass rounded-xl p-3" data-testid={`ban-row-${row.steam_id}`}>
      <Face person={row} size={36} />
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-sm truncate">{displayName(row)}</p>
        {facts.length > 0 && <p className="text-[11px] text-muted-foreground truncate">{facts.join(" · ")}</p>}
      </div>
      {withActions && row.state === "active" && (
        <button onClick={press} disabled={busy} data-testid={`ban-unban-${row.steam_id}`}
          className={armed
            ? "text-xs font-bold px-3 py-2 rounded-lg whitespace-nowrap inline-flex items-center gap-1.5 transition-all"
            : "text-xs font-bold px-3 py-2 rounded-lg glass border border-emerald/30 text-emerald hover:bg-emerald/10 transition-all whitespace-nowrap inline-flex items-center gap-1.5"}
          style={armed ? dangerStyle : undefined}>
          <ShieldCheck size={13} /> {busy ? "Un momento…" : armed ? fill(BAN_COPY.unbanConfirm, { name: displayName(row) }) : BAN_COPY.unbanButton}
        </button>
      )}
    </div>
  );
}

function Candidate({ person, onPick }) {
  const facts = candidateFacts(person);
  return (
    <button type="button" role="option" aria-selected="false" onClick={() => onPick(person)} data-testid={`ban-candidate-${person.steam_id}`}
      className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-white/5 focus:bg-white/5 focus:outline-none transition-colors">
      <Face person={person} size={28} />
      <span className="min-w-0 flex-1">
        <b className="block text-sm truncate">{displayName(person)}</b>
        {facts.length > 0 && <span className="block text-[11px] text-muted-foreground truncate">{facts.join(" · ")}</span>}
      </span>
      {person.banned && <span className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase" style={{ color: "#E24A4A", background: "rgba(226,74,74,0.14)", border: "1px solid rgba(226,74,74,0.5)" }}>{BAN_COPY.bannedChip}</span>}
    </button>
  );
}

export function BansTab() {
  const { play } = useSound();
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [people, setPeople] = useState([]);
  const [hint, setHint] = useState("");
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState(null);
  const [mode, setMode] = useState("forever");
  const [days, setDays] = useState(7);
  const [reason, setReason] = useState("");
  const [armed, setArmed] = useState(null);   // { body, preview } between preview and confirm
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const seq = useRef(0);
  const inputRef = useRef(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const { data: d } = await api.adminBansOverview();
      setData(d);
      setLoadError("");
    } catch (e) {
      setLoadError(refusalText(e, BAN_COPY.listFail));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  // The drop-down: debounced, last answer wins.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setPeople([]); setOpen(false); setHint(""); return undefined; }
    const mine = ++seq.current;
    const t = setTimeout(async () => {
      try {
        const { data: d } = await api.adminBansSuggest(q);
        if (mine !== seq.current) return;
        const list = Array.isArray(d?.people) ? d.people : [];
        setPeople(list);
        setOpen(list.length > 0);
        setHint(suggestHint(d?.kind, list.length));
      } catch (e) {
        if (mine !== seq.current) return;
        setPeople([]); setOpen(false);
        setHint(refusalText(e, BAN_COPY.genericFail));
      }
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  const pick = (person) => {
    play("click");
    setPicked(person);
    setArmed(null);
    setMode("forever");
    setDays(7);
    setReason("");
    setQuery("");
    setPeople([]);
    setOpen(false);
    setHint("");
    setError("");
  };

  const clearForm = () => {
    setPicked(null);
    setArmed(null);
    setError("");
    try { inputRef.current?.focus(); } catch (e) { /* nicety */ }
  };

  const preview = async () => {
    if (!picked) return;
    setError("");
    setBusy("preview");
    try {
      const body = buildPlaceBody(picked, { mode, days, reason, opId: opId() });
      const { data: d } = await api.adminBansPlace(body);
      if (!d?.ok || !d?.armed) { setError(BAN_COPY.genericFail); return; }
      setArmed({ body, preview: d.preview || {} });
      play("click");
    } catch (e) {
      play("error");
      setError(refusalText(e));
    } finally {
      setBusy("");
    }
  };

  const confirm = async () => {
    if (!armed) return;
    setError("");
    setBusy("confirm");
    try {
      const { data: d } = await api.adminBansPlace({ ...armed.body, confirm: true });
      if (!d?.ok) { setError(BAN_COPY.genericFail); return; }
      const name = displayName(picked);
      clearForm();
      // Reload FIRST, then say Done - the reload clears the status line as it
      // starts, so the other order wiped the one sentence the flow ends on.
      await load();
      const done = d.folded && d.message ? d.message : fill(BAN_COPY.doneBan, { name });
      setStatus(done);
      play("success");
      toast.success(done);
    } catch (e) {
      play("error");
      setError(refusalText(e));
    } finally {
      setBusy("");
    }
  };

  const onKey = (ev) => {
    if (ev.key === "Escape") { setOpen(false); return; }
    if (ev.key === "Enter" && open && people.length) { ev.preventDefault(); pick(people[0]); }
  };

  const active = Array.isArray(data?.active) ? data.active : [];
  const history = splitHistory(data?.history);
  const unavailable = data && data.available === false;

  return (
    <div className="space-y-6" data-testid="bans-tab">
      <div className="glass rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-1"><Ban size={18} className="text-gold" /><h3 className="font-display font-bold text-xl">{BAN_COPY.title}</h3></div>
        <p className="text-sm text-muted-foreground mb-4">{BAN_COPY.lede}</p>

        {loadError && <p className="text-sm mb-3" style={{ color: "#E24A4A" }} data-testid="bans-load-error">{loadError}</p>}
        {unavailable && <p className="text-sm text-muted-foreground mb-3" data-testid="bans-unavailable">{data.message || BAN_COPY.unavailable}</p>}
        {Number(data?.gate_faults) > 0 && (
          <p className="text-xs mb-3 flex items-start gap-2 rounded-lg p-2.5" style={{ color: "#f59e0b", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.35)" }} data-testid="bans-health">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {BAN_COPY.healthWarning}
          </p>
        )}

        {!unavailable && (
          <div className="relative">
            <label className="block">
              <span className="label-overline text-[10px] text-muted-foreground block mb-1.5">{BAN_COPY.findLabel}</span>
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input ref={inputRef} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey}
                  onFocus={() => people.length && setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
                  role="combobox" aria-expanded={open} aria-autocomplete="list" aria-controls="bans-matches" autoComplete="off"
                  placeholder={BAN_COPY.findPlaceholder} data-testid="bans-find" className={`${inputCls} pl-9`} />
              </div>
            </label>
            {hint && <p className="text-xs text-muted-foreground mt-2" data-testid="bans-find-hint">{hint}</p>}
            {open && people.length > 0 && (
              <div id="bans-matches" role="listbox" data-testid="bans-matches"
                className="absolute left-0 right-0 mt-1 z-30 rounded-xl overflow-hidden bg-[#0c0c0e] border border-white/10 shadow-2xl divide-y divide-white/5">
                {people.map((p) => <Candidate key={p.steam_id} person={p} onPick={pick} />)}
              </div>
            )}
          </div>
        )}

        {picked && (
          <div className="mt-5 rounded-xl p-4 border border-white/10 bg-white/[0.03] space-y-4" data-testid="bans-form">
            <div className="flex items-center gap-3">
              <Face person={picked} size={44} />
              <div className="min-w-0 flex-1">
                <p className="font-display font-bold text-base truncate">{displayName(picked)}</p>
                <p className="text-[11px] text-muted-foreground truncate">
                  {picked.banned ? BAN_COPY.bannedChip : picked.known === false ? BAN_COPY.unknownAccount : (picked.steam_id || "")}
                </p>
              </div>
              <button onClick={clearForm} className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-white/5" aria-label={BAN_COPY.cancel} data-testid="bans-form-close"><X size={16} /></button>
            </div>

            <div>
              <p className="label-overline text-[10px] text-muted-foreground mb-2">{BAN_COPY.howLong}</p>
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <label className="inline-flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="bans-length" checked={mode === "forever"} onChange={() => setMode("forever")} data-testid="bans-length-forever" /> {BAN_COPY.forever}
                </label>
                <label className="inline-flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="bans-length" checked={mode === "days"} onChange={() => setMode("days")} data-testid="bans-length-days" />
                  <input type="number" min={1} max={3650} step={1} value={days} disabled={mode !== "days"}
                    onClick={() => setMode("days")} onChange={(e) => setDays(e.target.value)} data-testid="bans-days"
                    className={`${inputCls} w-24 py-1.5`} /> {BAN_COPY.days}
                </label>
              </div>
            </div>

            <label className="block">
              <span className="label-overline text-[10px] text-muted-foreground block mb-1.5">{BAN_COPY.reasonLabel}</span>
              <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={Number(data?.limits?.reason_max) || 100}
                placeholder={BAN_COPY.reasonPlaceholder} autoComplete="off" data-testid="bans-reason" className={inputCls} />
            </label>

            {!armed && (
              <div className="flex flex-wrap gap-2">
                <button onClick={preview} disabled={busy === "preview"} data-testid="bans-go" className={dangerBtn} style={dangerStyle}>
                  <Ban size={16} /> {busy === "preview" ? "Un momento…" : BAN_COPY.banButton}
                </button>
                <button onClick={clearForm} className={ghostBtn} data-testid="bans-drop">{BAN_COPY.cancel}</button>
              </div>
            )}

            {armed && (
              <div className="rounded-xl p-4" style={{ background: "rgba(226,74,74,0.08)", border: "1px solid rgba(226,74,74,0.45)" }} data-testid="bans-confirm">
                <p className="font-display font-bold text-base mb-1">{BAN_COPY.confirmTitle}</p>
                <p className="text-sm">{confirmSentence(picked, armed.preview)}</p>
                {confirmNote(armed.preview) && <p className="text-xs text-muted-foreground mt-1">{confirmNote(armed.preview)}</p>}
                <div className="flex flex-wrap gap-2 mt-3">
                  <button onClick={confirm} disabled={busy === "confirm"} data-testid="bans-confirm-yes" className={dangerBtn} style={dangerStyle}>
                    <Ban size={16} /> {busy === "confirm" ? "Un momento…" : BAN_COPY.confirmYes}
                  </button>
                  <button onClick={() => setArmed(null)} className={ghostBtn} data-testid="bans-confirm-cancel">{BAN_COPY.cancel}</button>
                </div>
              </div>
            )}

            {error && <p className="text-sm" style={{ color: "#E24A4A" }} data-testid="bans-error">{error}</p>}
          </div>
        )}
        {!picked && error && <p className="text-sm mt-3" style={{ color: "#E24A4A" }} data-testid="bans-error">{error}</p>}
        {status && <p className="text-sm text-emerald mt-4" data-testid="bans-status">{status}</p>}
      </div>

      <div className="glass rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck size={18} className="text-gold" />
          <h3 className="font-display font-bold text-xl">{BAN_COPY.activeTitle}</h3>
          {data?.counts?.active > 0 && <span className="text-xs font-bold px-2 py-0.5 rounded-full glass border border-white/10">{data.counts.active}</span>}
        </div>
        {!data && !loadError && <p className="text-sm text-muted-foreground">Cargando…</p>}
        {data && active.length === 0 && <p className="text-sm text-muted-foreground" data-testid="bans-active-empty">{BAN_COPY.activeEmpty}</p>}
        <div className="space-y-2" data-testid="bans-active-rows">
          {active.map((row) => (
            <BanRow key={row.id || row.steam_id} row={row} withActions onLifted={async (done) => { await load(); setStatus(done); }} />
          ))}
        </div>
      </div>

      {history.length > 0 && (
        <div className="glass rounded-2xl p-6" data-testid="bans-history">
          <button onClick={() => setShowHistory((s) => !s)} className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground" data-testid="bans-history-open">
            <History size={15} /> {fill(BAN_COPY.historyToggle, { count: history.length })}
          </button>
          {showHistory && (
            <div className="mt-3 space-y-2" data-testid="bans-history-rows">
              {history.map((row) => <BanRow key={row.id || row.steam_id + row.banned_at} row={row} withActions={false} />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
