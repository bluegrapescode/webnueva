import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Room, RoomEvent, DisconnectReason } from "livekit-client";
import { VoiceFalloff, volumeForDistance, resolveCut, DEFAULT_AUDIBLE_RADIUS_M, DEFAULT_HOLD_RADIUS_M } from "@/lib/voiceFalloff";
import {
  loadSettings, saveSettings, composeGain, curveConfig, normalizeSettings,
  clampMaster, clampExponent, clampHearingM, withSpeaker, DEFAULT_SETTINGS,
  clampMicMode, clampPttKey, clampDeviceId, audioCaptureOptions,
} from "@/lib/voiceSettings";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useSound } from "@/context/SoundContext";

const RETRY_BASE_MS = 1000;
const RETRY_CAP_MS = 30000;
const RETRY_RATELIMIT_FLOOR_MS = 10000;
// A session that dies this young counts as a rapid drop; two in a row switch the
// media onto the TURN-TLS relay transport (see the keepalive lane notes below).
const SHORT_SESSION_MS = 45000;
const SHORT_SESSIONS_FOR_RELAY = 2;
// Gain changes smaller than this are inaudible; skipping them keeps the poll loop
// and slider drags from re-writing the same volume onto every subscribed track.
const GAIN_EPSILON = 0.005;

const VoiceContext = createContext(null);
export const useVoice = () => useContext(VoiceContext);

/**
 * App-level proximity-voice session (livekit-client), lifted OUT of the
 * /proximity-voice route on 2026-07-16: the session used to live inside the page
 * component, so navigating to ANY other section of the site unmounted it and hung
 * the call up — "it disconnects me from the website if I change tabs". The provider
 * mounts once for the app's lifetime; the voice page is just its display. Voice now
 * survives navigating the whole site; only signing out, closing the tab, or a full
 * page reload ends it.
 *
 * PLAYBACK LANE: a subscribed RemoteAudioTrack is SILENT until attached to an
 * <audio> element — livekit-client never auto-plays. Remote audio attaches into a
 * hidden host div (rendered by the provider, so it survives navigation) on
 * TrackSubscribed and detaches on TrackUnsubscribed / disconnect. RANGE is 100%
 * server-managed (the voice bridge subscribes only in-range pairs); VOLUME is
 * ours — see the falloff lane. If the browser blocks autoplay, a visible
 * "Activar audio" button calls room.startAudio().
 *
 * FALLOFF LANE: LiveKit's server API cannot set a per-listener volume, so every
 * subscribed voice used to arrive at 100% — somebody at the edge of the audible
 * radius was as loud as somebody on top of you ("I can hear them from far
 * away"). While at least one remote voice is attached, VoiceFalloff polls the
 * bridge's GET /positions (~1/s, the cadence that endpoint suggests) and fades
 * each speaker by real 3-D distance. It is fail-safe in one direction only:
 * every unknown — poll failed, token rejected, player missing from the feed —
 * resolves to FULL volume, never to silence. Nobody polls while hearing nobody.
 *
 * KEEPALIVE LANE: no session timer, no scheduled disconnect — LiveKit validates the
 * join token only when a connection is (re)established, and every (re)join mints a
 * fresh token. While the user wants to be connected (intentRef), any non-manual
 * disconnect enters a single-flight retry loop (backoff 1s→30s cap, unlimited,
 * fresh token each try); window online / pageshow / visibility-visible trigger an
 * immediate attempt. Terminal stops only: manual disconnect, sign-out (401/403),
 * voice unconfigured (503), or the same account connecting from another tab/device
 * (DUPLICATE_IDENTITY — auto-rejoining would kick that newer session in an endless
 * war, so this tab stands down and says so). Mute survives rejoins; a lost mic
 * downgrades to listen-only instead of dying. Every room event handler no-ops
 * unless its room is still current, so late events from a replaced connection can
 * never corrupt the live session.
 *
 * RELAY ESCALATION: after two rapid session deaths (or two connect-phase transport
 * failures), rejoin relay-only (TURN); two relay failures fall back to direct.
 * Self-correcting under any server state.
 */
export function VoiceProvider({ children }) {
  const { user } = useAuth();
  const { play } = useSound();
  const [connState, setConnState] = useState("idle");
  const [muted, setMuted] = useState(false);
  const [participants, setParticipants] = useState([]); // [{identity, name, audible}]
  const [speakers, setSpeakers] = useState(() => new Set());
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [notice, setNotice] = useState(null); // terminal-stop explanation
  const roomRef = useRef(null);
  const audioHostRef = useRef(null);
  const intentRef = useRef(false);
  const connectingRef = useRef(false);
  const retryTimerRef = useRef(null);
  const retryCountRef = useRef(0);
  const mutedRef = useRef(false);
  const wasConnectedRef = useRef(false);
  const lastConnectedAtRef = useRef(0);
  const shortLivedCountRef = useRef(0);
  const relayModeRef = useRef(false);
  const relayFailCountRef = useRef(0);
  const remoteTracksRef = useRef(new Map()); // identity -> RemoteAudioTrack (falloff targets)
  const voiceTokenRef = useRef(null);
  const falloffRef = useRef(null);

  // --- adjustable settings + composition state ------------------------------
  // settings live in a ref (read by the audio hot path) mirrored into state (for
  // the UI). The falloff loop hands us a distance CURVE FACTOR per speaker; we
  // compose master * per-speaker * mute on top before it reaches the track.
  const [settings, setSettings] = useState(() => loadSettings());
  const settingsRef = useRef(settings);
  // Two radii, and the difference matters. `serverRadiusM` is the AUDIBLE range
  // the owner set — the number the player sees and the top of their own range
  // slider. The hold radius is a few metres beyond it and stays internal: it is
  // the hard cut for a pair the bridge is still holding across the boundary, and
  // showing it would tell the player a range the owner never set.
  const [serverRadiusM, setServerRadiusM] = useState(DEFAULT_AUDIBLE_RADIUS_M);
  const holdRadiusRef = useRef(DEFAULT_HOLD_RADIUS_M);       // hard cut (internal)
  const audibleRadiusRef = useRef(DEFAULT_AUDIBLE_RADIUS_M); // owner's range: near zone + UI max
  const curveGainRef = useRef(new Map());   // identity -> last distance curve factor
  const appliedGainRef = useRef(new Map()); // identity -> gain last written to the track
  const lastDistanceRef = useRef(new Map()); // identity -> last distance in metres (or null)
  // The same distances, rounded to whole metres, published for the UI. Kept as a
  // separate piece of state (not read off the ref) because the ref is written by
  // the audio hot path and must never force a render on its own; this copy is
  // set ONLY when a number a player can actually see changed, so the poll's
  // sub-metre jitter costs nothing.
  const [distances, setDistances] = useState({}); // identity -> metres (or null)
  const distancesRef = useRef({});
  const persistTimerRef = useRef(null);
  // Human names resolved from the bridge's persona cache (the game log), so the
  // roster shows who is who instead of a bare Steam id. Static per session.
  const [personaNames, setPersonaNames] = useState({}); // identity -> display name
  const personaNamesRef = useRef({});
  const personaInflightRef = useRef(new Set());
  // --- microphone & devices --------------------------------------------------
  const [devices, setDevices] = useState({ inputs: [], outputs: [] });
  const [transmitting, setTransmitting] = useState(false); // PTT key held right now
  const transmittingRef = useRef(false);

  const clearRetryTimer = () => {
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    retryTimerRef.current = null;
  };

  // Push a fully-composed gain onto one track (setVolume, or the elements as a
  // fallback for any build whose RemoteAudioTrack lacks setVolume).
  const applyGainToTrack = useCallback((identity, gain) => {
    const key = String(identity);
    const track = remoteTracksRef.current.get(key);
    if (!track) { appliedGainRef.current.delete(key); return; }
    const v = Math.min(1, Math.max(0, Number(gain)));
    if (!Number.isFinite(v)) return;
    if (typeof track.setVolume === "function") {
      // Skip writes that would not change what anyone hears. Both callers are
      // hot — the poll loop touches every speaker ~1/s and recompose touches
      // every speaker on each drag frame of any slider — and the number of
      // speakers scales with the AREA of the range, so at 100 m most of those
      // writes are the identical number.
      // Memoised against the TRACK OBJECT, not just the identity: a re-subscribe
      // hands us a brand-new track sitting at full volume, and skipping its first
      // write because the previous track had the same gain would leave it unfaded.
      const last = appliedGainRef.current.get(key);
      if (last && last.track === track && Math.abs(last.v - v) < GAIN_EPSILON) return;
      appliedGainRef.current.set(key, { track, v });
      track.setVolume(v);
      return;
    }
    // Element fallback is NOT memoised: this writes per <audio> element, and a
    // track can pick up a new element (which starts at full volume) without the
    // track object ever changing, so a skip here could strand one at 100%.
    (track.attachedElements || []).forEach((el) => {
      try { el.volume = v; } catch (e) { /* element gone */ }
    });
  }, []);

  // The falloff loop calls this with the raw distance CURVE factor; we remember
  // it and apply master/per-speaker/mute on top.
  const applyVolume = useCallback((identity, curveFactor) => {
    const key = String(identity);
    curveGainRef.current.set(key, Number.isFinite(Number(curveFactor)) ? Number(curveFactor) : 1);
    applyGainToTrack(key, composeGain(curveFactor, settingsRef.current, key));
  }, [applyGainToTrack]);

  // Re-apply gains for every held speaker WITHOUT waiting for the next poll.
  // "compose" reuses the cached curve factor (master/per-speaker/mute change);
  // "curve" first recomputes the curve from the cached distance (steepness /
  // max-hearing change) then composes.
  const recompose = useCallback((mode) => {
    const s = settingsRef.current;
    // Only the "curve" mode needs the curve config and the cut; both are loop
    // invariant, so neither is paid for by a master/per-speaker volume drag.
    const cfg = mode === "curve" ? curveConfig(s, audibleRadiusRef.current) : null;
    const cut = cfg ? resolveCut(holdRadiusRef.current, cfg.maxHearingM) : 0;
    for (const id of remoteTracksRef.current.keys()) {
      let curve = curveGainRef.current.get(id);
      if (cfg) {
        const d = lastDistanceRef.current.get(id);
        curve = (d == null) ? 1 : volumeForDistance(Number(d), cut,
          { nearRadiusM: audibleRadiusRef.current, exponent: cfg.exponent, fullFrac: cfg.fullFrac });
        curveGainRef.current.set(id, curve);
      }
      applyGainToTrack(id, composeGain(curve == null ? 1 : curve, s, id));
    }
  }, [applyGainToTrack]);

  // Update settings (state + ref + debounced persist) then re-apply audio at once.
  const commitSettings = useCallback((next, mode) => {
    const norm = normalizeSettings(next);
    settingsRef.current = norm;
    setSettings(norm);
    recompose(mode || "compose");
    if (persistTimerRef.current) clearTimeout(persistTimerRef.current);
    persistTimerRef.current = setTimeout(() => { persistTimerRef.current = null; saveSettings(norm); }, 300);
  }, [recompose]);

  /**
   * Publish the poll's distances for the roster, in whole metres.
   *
   * Called ~once a second from the falloff loop with every held speaker, so it
   * is deliberately cheap and deliberately quiet: it diffs against what the UI
   * is already showing and only sets state when a rendered number changed. A
   * player walking changes his metre reading and re-renders the roster; a player
   * standing still does not. A distance the position lane has not resolved stays
   * null — the panel renders that as unknown, never as "0 m".
   */
  const publishDistances = useCallback((distMap) => {
    const next = {};
    try {
      distMap.forEach((d, id) => {
        const n = Number(d);
        next[String(id)] = Number.isFinite(n) ? Math.round(n) : null;
      });
    } catch (e) { /* not a Map: publish nothing rather than break the poll */ }
    const prev = distancesRef.current;
    const keys = Object.keys(next);
    let changed = keys.length !== Object.keys(prev).length;
    if (!changed) {
      for (const k of keys) {
        if (!Object.prototype.hasOwnProperty.call(prev, k) || prev[k] !== next[k]) { changed = true; break; }
      }
    }
    if (!changed) return;
    distancesRef.current = next;
    setDistances(next);
  }, []);

  const ensureFalloff = useCallback(() => {
    if (falloffRef.current) return falloffRef.current;
    falloffRef.current = new VoiceFalloff({
      getToken: () => voiceTokenRef.current,
      remintToken: async () => {
        const r = await api.voiceToken();
        const token = (r.data || {}).token || null;
        if (token) voiceTokenRef.current = token;
        return token;
      },
      getIdentities: () => Array.from(remoteTracksRef.current.keys()),
      applyVolume,
      getCurveConfig: () => curveConfig(settingsRef.current, audibleRadiusRef.current),
      reportDistances: (distMap, holdRadiusM, audibleRadiusM) => {
        lastDistanceRef.current = distMap instanceof Map ? distMap : new Map();
        publishDistances(lastDistanceRef.current);
        if (Number(holdRadiusM) > 0) holdRadiusRef.current = Number(holdRadiusM);
        // Re-render only when the owner's range actually moved, so the slider
        // and its "max N m" label follow a retune without a reload.
        if (Number(audibleRadiusM) > 0 && Number(audibleRadiusM) !== audibleRadiusRef.current) {
          audibleRadiusRef.current = Number(audibleRadiusM);
          setServerRadiusM(Number(audibleRadiusM));
        }
      },
      fetchImpl: (url, init) => fetch(url, init),
      setTimer: (fn, ms) => setTimeout(fn, ms),
      clearTimer: (h) => clearTimeout(h),
      now: () => Date.now(),
      onLog: (msg, extra) => console.info(`[voice] ${msg}`, extra === undefined ? "" : extra),
    });
    return falloffRef.current;
  }, [applyVolume, publishDistances]);

  // Compute the mic's desired enabled state and apply it with the current capture
  // options. In PTT mode the mic is live only while the key is held; in open mode
  // it follows the manual mute. Fail-safe: any error keeps the session up
  // (listen-only) instead of dropping the call. `republish` forces an off->on so a
  // device / noise-suppression change is re-acquired.
  const applyMicState = useCallback(async (opts = {}) => {
    const room = roomRef.current;
    if (!room || !room.localParticipant) return;
    const s = settingsRef.current;
    const desired = s.micMode === "ptt" ? transmittingRef.current : !mutedRef.current;
    try {
      if (opts.republish && desired) await room.localParticipant.setMicrophoneEnabled(false);
      await room.localParticipant.setMicrophoneEnabled(desired, audioCaptureOptions(s));
    } catch (e) { console.warn("[voice] mic state apply failed", e); }
  }, []);
  const applyMicStateRef = useRef(() => {});
  applyMicStateRef.current = applyMicState;

  // Enumerate mic + speaker devices (labels populate once a session/permission
  // exists). Never throws; keeps the last list on failure.
  const refreshDevices = useCallback(async () => {
    try {
      const [inputs, outputs] = await Promise.all([
        Room.getLocalDevices("audioinput").catch(() => []),
        Room.getLocalDevices("audiooutput").catch(() => []),
      ]);
      const map = (list) => (list || []).filter((d) => d && d.deviceId).map((d) => ({ deviceId: d.deviceId, label: d.label || "" }));
      setDevices({ inputs: map(inputs), outputs: map(outputs) });
    } catch (e) { /* enumeration blocked; keep the last list */ }
  }, []);

  // Current mic input level (0..1) for the meter — read live, no re-render.
  const getMicLevel = useCallback(() => {
    const room = roomRef.current;
    if (!room || !room.localParticipant) return 0;
    const lvl = Number(room.localParticipant.audioLevel);
    return Number.isFinite(lvl) ? Math.min(1, Math.max(0, lvl)) : 0;
  }, []);

  const attachAudio = useCallback((track, identity) => {
    try {
      const el = track.attach();
      el.dataset.voiceAudio = "1";
      (audioHostRef.current || document.body).appendChild(el);
      if (identity) {
        remoteTracksRef.current.set(String(identity), track);
        ensureFalloff().poke();
      }
    } catch (e) {
      console.warn("[voice] audio attach failed", e);
    }
  }, [ensureFalloff]);

  const stopFalloffIfIdle = useCallback(() => {
    if (remoteTracksRef.current.size === 0 && falloffRef.current) falloffRef.current.stop();
  }, []);

  const detachAudio = useCallback((track, identity) => {
    if (identity) {
      // Only drop the entry if it is still THIS track: on a republish the new
      // track can land before the old one's unsubscribe, and deleting blindly
      // would leave that speaker stuck at whatever volume he had.
      const stored = remoteTracksRef.current.get(String(identity));
      if (!stored || stored === track) remoteTracksRef.current.delete(String(identity));
    } else {
      remoteTracksRef.current.forEach((t, id) => { if (t === track) remoteTracksRef.current.delete(id); });
    }
    try { track.detach().forEach((el) => el.remove()); } catch (e) { /* already detached */ }
    stopFalloffIfIdle();
  }, [stopFalloffIfIdle]);

  const sweepAudio = useCallback(() => {
    // The session's remote audio is gone: no falloff targets, and the token that
    // authenticated /positions dies with it (every attempt mints a fresh one).
    // Session-scoped caches clear; the player's SETTINGS persist across rejoins.
    remoteTracksRef.current.clear();
    curveGainRef.current.clear();
    lastDistanceRef.current.clear();
    // The roster's copy dies with the session too: a stale "18 m" beside a
    // player who is no longer routed to you is a lie the next poll would not
    // necessarily correct (it only publishes on CHANGE).
    distancesRef.current = {};
    setDistances({});
    personaNamesRef.current = {};
    personaInflightRef.current.clear();
    setPersonaNames({});
    voiceTokenRef.current = null;
    if (falloffRef.current) falloffRef.current.stop();
    const host = audioHostRef.current;
    if (!host) return;
    try { while (host.firstChild) host.firstChild.remove(); } catch (e) { /* detached DOM */ }
  }, []);

  const refreshParticipants = useCallback(() => {
    const room = roomRef.current;
    if (!room) { setParticipants([]); return; }
    const list = [];
    room.remoteParticipants.forEach((p) => {
      let audible = false;
      try { p.audioTrackPublications.forEach((pub) => { if (pub.isSubscribed) audible = true; }); } catch (e) { /* roster-only fallback */ }
      list.push({ identity: p.identity, name: p.name || p.identity, audible });
    });
    setParticipants(list);
  }, []);

  // Resolve one Steam id -> human name via the bridge persona cache. One request
  // per player, cached for the session (names are static); any failure just
  // leaves the Steam id showing. Never throws, never blocks the roster.
  const resolvePersona = useCallback(async (identity) => {
    const id = String(identity || "");
    if (!id || personaNamesRef.current[id] || personaInflightRef.current.has(id)) return;
    const token = voiceTokenRef.current;
    if (!token) return;
    personaInflightRef.current.add(id);
    try {
      const res = await fetch(`/persona?sid=${encodeURIComponent(id)}`, {
        headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
        cache: "no-store", credentials: "same-origin",
      });
      if (res.status === 200) {
        const data = await res.json();
        const name = data && typeof data.name === "string" ? data.name.trim() : "";
        if (name) {
          personaNamesRef.current = { ...personaNamesRef.current, [id]: name };
          setPersonaNames(personaNamesRef.current);
        }
      }
    } catch (e) { /* leave the Steam id; retried when the roster next changes */ }
    finally { personaInflightRef.current.delete(id); }
  }, []);

  const scheduleRetry = useCallback((minDelayMs = 0) => {
    if (!intentRef.current || retryTimerRef.current) return;
    const n = Math.min(retryCountRef.current, 5);
    const delay = Math.max(minDelayMs, Math.min(RETRY_CAP_MS, RETRY_BASE_MS * Math.pow(2, n))) + Math.random() * 500;
    retryCountRef.current += 1;
    setConnState("reconnecting");
    retryTimerRef.current = setTimeout(() => {
      retryTimerRef.current = null;
      attemptRef.current();
    }, delay);
  }, []);

  const attempt = useCallback(async () => {
    if (!intentRef.current || connectingRef.current || roomRef.current) return;
    connectingRef.current = true;
    clearRetryTimer();
    setNotice(null);
    setConnState(retryCountRef.current > 0 ? "reconnecting" : "connecting");
    let room = null;
    try {
      const r = await api.voiceToken(); // fresh token every attempt — never reused
      const data = r.data || {};
      const token = data.token;
      const url = data.livekit_url || data.url;
      if (!token || !url) throw new Error("Respuesta de token de voz incompleta");
      if (!intentRef.current) return; // user cancelled while the token was minting
      voiceTokenRef.current = token; // the falloff lane authenticates /positions with it

      room = new Room();
      room.on(RoomEvent.ParticipantConnected, () => { if (roomRef.current === room) refreshParticipants(); });
      room.on(RoomEvent.ParticipantDisconnected, () => { if (roomRef.current === room) refreshParticipants(); });
      room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
        if (roomRef.current !== room) return;
        if (track && track.kind === "audio") attachAudio(track, participant && participant.identity);
        refreshParticipants();
      });
      room.on(RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
        if (roomRef.current !== room) return;
        if (track && track.kind === "audio") detachAudio(track, participant && participant.identity);
        refreshParticipants();
      });
      room.on(RoomEvent.ActiveSpeakersChanged, (list) => {
        if (roomRef.current === room) setSpeakers(new Set((list || []).map((p) => p.identity)));
      });
      room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        if (roomRef.current === room) setAudioBlocked(!room.canPlaybackAudio);
      });
      room.on(RoomEvent.Reconnecting, () => { if (roomRef.current === room) setConnState("reconnecting"); });
      if (RoomEvent.SignalReconnecting) {
        room.on(RoomEvent.SignalReconnecting, () => { if (roomRef.current === room) setConnState("reconnecting"); });
      }
      room.on(RoomEvent.Reconnected, () => {
        if (roomRef.current !== room) return;
        setConnState("connected");
        setAudioBlocked(!room.canPlaybackAudio);
        refreshParticipants();
      });
      room.on(RoomEvent.Disconnected, (reason) => {
        if (roomRef.current !== room) return; // late event from a replaced connection
        roomRef.current = null;
        sweepAudio();
        setAudioBlocked(false);
        setParticipants([]);
        if (!intentRef.current) { setConnState("idle"); return; }
        if (reason === DisconnectReason.DUPLICATE_IDENTITY) {
          // Auto-rejoining would kick the newer session and start an endless kick
          // war between the user's own tabs — this tab stands down instead.
          intentRef.current = false;
          wasConnectedRef.current = false;
          setConnState("error");
          setNotice("Tu cuenta se conectó a la voz desde otra pestaña o dispositivo — esta pestaña se desconectó. Pulsa Conectar para usar la voz aquí.");
          toast.message("Voz activa en otra pestaña — esta pestaña se desconectó.");
          return;
        }
        if (lastConnectedAtRef.current) {
          const lived = Date.now() - lastConnectedAtRef.current;
          lastConnectedAtRef.current = 0;
          shortLivedCountRef.current = lived < SHORT_SESSION_MS ? shortLivedCountRef.current + 1 : 0;
          if (!relayModeRef.current && shortLivedCountRef.current >= SHORT_SESSIONS_FOR_RELAY) {
            relayModeRef.current = true;
            relayFailCountRef.current = 0;
            console.info("[voice] repeated rapid drops - switching media to the relay transport");
          }
        }
        if (wasConnectedRef.current) {
          wasConnectedRef.current = false;
          toast.message("Voz desconectada — reconectando…");
        }
        scheduleRetry();
      });

      roomRef.current = room; // set BEFORE awaiting connect so events above are "current"
      // autoSubscribe:false is LOAD-BEARING — the browser subscribes to NOBODY on
      // its own; the voice bridge is the SOLE subscriber and only ever wires in
      // players inside the audible radius. Without this the client auto-subscribes
      // to everyone the instant they publish and a cross-map voice leaks through
      // before the bridge can trim it (the "hear them from the other side of the
      // map" bug). The bridge's server-side UpdateSubscriptions still lands and
      // still fires TrackSubscribed, so nothing else changes.
      const connectOpts = relayModeRef.current
        ? { autoSubscribe: false, rtcConfig: { iceTransportPolicy: "relay" } }
        : { autoSubscribe: false };
      await room.connect(url, token, connectOpts);
      // Apply the chosen speaker (playback only — a failure just uses the default).
      try {
        const outId = clampDeviceId(settingsRef.current.outputDeviceId);
        if (outId) await room.switchActiveDevice("audiooutput", outId);
      } catch (e) { /* unsupported browser / device gone */ }
      try {
        // PTT mode starts muted (waits for the key); open mode follows the manual
        // mute. The chosen mic device + noise suppression ride the capture options.
        const s = settingsRef.current;
        const desired = s.micMode === "ptt" ? false : !mutedRef.current;
        await room.localParticipant.setMicrophoneEnabled(desired, audioCaptureOptions(s));
      } catch (micErr) {
        // Mic lost (permission revoked / device gone): keep the session alive
        // listen-only instead of failing the whole connection.
        console.warn("[voice] mic enable failed — continuing listen-only", micErr);
        mutedRef.current = true;
        setMuted(true);
        toast.error("Micrófono no disponible — sigues conectado en modo escucha. Usa el botón del micrófono para reintentar.");
      }
      refreshDevices(); // labels are available now that a session exists
      const recovered = retryCountRef.current > 0;
      retryCountRef.current = 0;
      relayFailCountRef.current = 0;
      lastConnectedAtRef.current = Date.now();
      wasConnectedRef.current = true;
      setConnState("connected");
      setAudioBlocked(!room.canPlaybackAudio);
      refreshParticipants();
      play("success");
      toast.success(recovered ? "Voz reconectada" : "Conectado al chat de proximidad");
    } catch (e) {
      if (roomRef.current === room) roomRef.current = null;
      if (room) { try { room.disconnect(); } catch (e2) { /* never connected */ } }
      const status = e?.response?.status;
      if (!intentRef.current) { setConnState("idle"); return; }
      if (status === 401 || status === 403) {
        intentRef.current = false;
        setConnState("error");
        setNotice("Tu sesión del sitio expiró — vuelve a iniciar sesión para usar la voz.");
        return;
      }
      if (status === 503) {
        intentRef.current = false;
        setConnState("error");
        setNotice(e?.response?.data?.detail || "El chat de voz no está disponible en este momento.");
        return;
      }
      if (relayModeRef.current) {
        // Relay connect failed (e.g. relay transport rolled back server-side):
        // after two consecutive failures fall back to the direct transport.
        relayFailCountRef.current += 1;
        if (relayFailCountRef.current >= 2) {
          relayModeRef.current = false;
          relayFailCountRef.current = 0;
          shortLivedCountRef.current = 0;
          console.warn("[voice] relay transport unavailable - falling back to direct media");
        }
      } else if (room && !status) {
        // Token + Room existed but the connection itself failed (no HTTP error):
        // transport failure. Networks that block the direct media ports entirely
        // never produce a connected-then-died session, so count these too.
        shortLivedCountRef.current += 1;
        if (shortLivedCountRef.current >= SHORT_SESSIONS_FOR_RELAY) {
          relayModeRef.current = true;
          relayFailCountRef.current = 0;
          console.info("[voice] repeated rapid drops - switching media to the relay transport");
        }
      }
      if (retryCountRef.current === 0) {
        // First-ever attempt failed: show the error but keep trying in the background.
        play("error");
        toast.error(e?.response?.data?.detail || e?.message || "No se pudo conectar al chat de proximidad — reintentando…");
      }
      scheduleRetry(status === 429 ? RETRY_RATELIMIT_FLOOR_MS : 0);
    } finally {
      connectingRef.current = false;
    }
  }, [attachAudio, detachAudio, sweepAudio, refreshParticipants, scheduleRetry, play]);

  const attemptRef = useRef(() => {});
  attemptRef.current = attempt;

  const connect = useCallback(() => {
    intentRef.current = true;
    retryCountRef.current = 0;
    attemptRef.current();
  }, []);

  const disconnect = useCallback((opts = {}) => {
    const { silent = false } = opts;
    intentRef.current = false;
    clearRetryTimer();
    retryCountRef.current = 0;
    wasConnectedRef.current = false;
    const room = roomRef.current;
    roomRef.current = null; // null first: the room's Disconnected handler must see it stale
    if (room) { try { room.disconnect(); } catch (e) { /* already gone */ } }
    sweepAudio();
    setAudioBlocked(false);
    setParticipants([]);
    setNotice(null);
    if (!silent) { setConnState("idle"); play("close"); }
  }, [play, sweepAudio]);

  // Wake-from-sleep / network-restored / tab-foregrounded: retry NOW, not at the
  // next backoff slot (background tabs throttle timers — these events do not).
  useEffect(() => {
    const wake = () => {
      if (!intentRef.current || roomRef.current || connectingRef.current) return;
      clearRetryTimer();
      retryCountRef.current = 0;
      attemptRef.current();
    };
    const onVisible = () => { if (document.visibilityState === "visible") wake(); };
    window.addEventListener("online", wake);
    window.addEventListener("pageshow", wake);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("online", wake);
      window.removeEventListener("pageshow", wake);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  // Signed out (manually or by an expired session): tear the voice session down.
  useEffect(() => {
    if (!user && (roomRef.current || intentRef.current)) disconnect({ silent: true });
  }, [user, disconnect]);

  // Resolve a human name for every player in the roster (once each, cached).
  useEffect(() => {
    if (connState !== "connected") return;
    participants.forEach((p) => resolvePersona(p.identity));
  }, [participants, connState, resolvePersona]);

  // Push-to-talk: hold the bound key to transmit. Ignored while typing in a field,
  // and force-released on tab blur / hide / disconnect so the mic can never stick
  // open. Reads settings from the ref so the listeners never need re-binding.
  useEffect(() => {
    const typing = (el) => {
      if (!el) return false;
      const t = el.tagName;
      return t === "INPUT" || t === "TEXTAREA" || t === "SELECT" || el.isContentEditable;
    };
    const release = () => {
      if (!transmittingRef.current) return;
      transmittingRef.current = false;
      setTransmitting(false);
      applyMicStateRef.current();
    };
    const down = (e) => {
      const s = settingsRef.current;
      if (s.micMode !== "ptt" || e.code !== s.pttKey || e.repeat) return;
      if (!roomRef.current || typing(e.target)) return;
      if (e.code === "Space") e.preventDefault(); // stop the page scrolling
      if (transmittingRef.current) return;
      transmittingRef.current = true;
      setTransmitting(true);
      applyMicStateRef.current();
    };
    const up = (e) => {
      if (e.code !== settingsRef.current.pttKey) return;
      release();
    };
    const onVis = () => { if (document.visibilityState !== "visible") release(); };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", release);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", release);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  // Re-enumerate devices when the system's device list changes (plug/unplug).
  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices || !navigator.mediaDevices.addEventListener) return;
    const onChange = () => refreshDevices();
    navigator.mediaDevices.addEventListener("devicechange", onChange);
    return () => navigator.mediaDevices.removeEventListener("devicechange", onChange);
  }, [refreshDevices]);

  // Provider unmount (full page teardown): never leave the falloff poll running,
  // and flush any pending settings write.
  useEffect(() => () => {
    if (falloffRef.current) falloffRef.current.stop();
    if (persistTimerRef.current) { clearTimeout(persistTimerRef.current); persistTimerRef.current = null; saveSettings(settingsRef.current); }
  }, []);

  // --- settings setters (each: clamp -> commit -> re-apply audio at once) -----
  const setMaster = useCallback((v) => commitSettings({ ...settingsRef.current, master: clampMaster(v) }, "compose"), [commitSettings]);
  const setExponent = useCallback((v) => commitSettings({ ...settingsRef.current, exponent: clampExponent(v) }, "curve"), [commitSettings]);
  // Personal hearing range in metres; 0 = follow whatever range the server is on.
  const setHearingM = useCallback((v) => commitSettings({ ...settingsRef.current, hearingM: clampHearingM(v) }, "curve"), [commitSettings]);
  const setSpeakerVolume = useCallback((id, v) => commitSettings(withSpeaker(settingsRef.current, id, { volume: v }), "compose"), [commitSettings]);
  const toggleSpeakerMute = useCallback((id) => {
    const cur = settingsRef.current.speakers[String(id)];
    commitSettings(withSpeaker(settingsRef.current, id, { muted: !(cur && cur.muted) }), "compose");
  }, [commitSettings]);
  const resetSettings = useCallback(() => {
    transmittingRef.current = false; setTransmitting(false);
    commitSettings(DEFAULT_SETTINGS, "curve");
    applyMicStateRef.current({ republish: true });
  }, [commitSettings]);

  // --- microphone setters (persist + apply to the live session) --------------
  const setMicMode = useCallback((mode) => {
    transmittingRef.current = false; setTransmitting(false);
    commitSettings({ ...settingsRef.current, micMode: clampMicMode(mode) }, "compose");
    applyMicStateRef.current(); // PTT -> mute now; open -> follow the mute button
  }, [commitSettings]);
  const setPttKey = useCallback((key) => commitSettings({ ...settingsRef.current, pttKey: clampPttKey(key) }, "compose"), [commitSettings]);
  const setNoiseSuppression = useCallback((on) => {
    commitSettings({ ...settingsRef.current, noiseSuppression: !!on }, "compose");
    applyMicStateRef.current({ republish: true });
  }, [commitSettings]);
  const setInputDevice = useCallback((deviceId) => {
    commitSettings({ ...settingsRef.current, inputDeviceId: clampDeviceId(deviceId) }, "compose");
    applyMicStateRef.current({ republish: true }); // re-acquire on the new mic
  }, [commitSettings]);
  const setOutputDevice = useCallback(async (deviceId) => {
    const id = clampDeviceId(deviceId);
    commitSettings({ ...settingsRef.current, outputDeviceId: id }, "compose");
    const room = roomRef.current;
    try { if (room && id) await room.switchActiveDevice("audiooutput", id); }
    catch (e) { toast.error("No se pudo cambiar el altavoz en este navegador."); }
  }, [commitSettings]);

  const enableAudio = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    try {
      await room.startAudio();
      setAudioBlocked(!room.canPlaybackAudio);
      play("click");
    } catch (e) {
      play("error");
      toast.error("El navegador sigue bloqueando el audio — revisa el permiso de sonido del sitio.");
    }
  }, [play]);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    if (settingsRef.current.micMode === "ptt") return; // in PTT the key controls the mic
    const next = !mutedRef.current;
    try {
      await room.localParticipant.setMicrophoneEnabled(!next, audioCaptureOptions(settingsRef.current));
      mutedRef.current = next;
      setMuted(next);
      play("click");
    } catch (e) { play("error"); toast.error("No se pudo cambiar el estado del micrófono"); }
  }, [play]);

  const value = {
    connState, muted, participants, speakers, audioBlocked, notice, personaNames,
    // identity -> whole metres (or null when the position lane has not placed
    // that player yet). Display only: routing and gain never read this copy.
    distances,
    connect, disconnect, toggleMute, enableAudio,
    // the player's own adjustable voice settings:
    settings, serverRadiusM,
    setMaster, setExponent, setHearingM, setSpeakerVolume, toggleSpeakerMute, resetSettings,
    // microphone & devices:
    devices, transmitting, getMicLevel, refreshDevices,
    setMicMode, setPttKey, setNoiseSuppression, setInputDevice, setOutputDevice,
  };
  return (
    <VoiceContext.Provider value={value}>
      {/* Hidden host for remote <audio> elements — lives at app level so playback
          survives navigating between site sections. Playback only, never visual. */}
      <div ref={audioHostRef} style={{ display: "none" }} aria-hidden="true" data-testid="voice-audio-host" />
      {children}
    </VoiceContext.Provider>
  );
}
