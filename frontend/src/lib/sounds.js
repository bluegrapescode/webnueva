// Lightweight Web Audio UI sound engine — no asset files required.
let ctx = null;
let master = null;

function getCtx() {
  if (typeof window === "undefined") return null;
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) {
      ctx = new AC();
      // gentle master chain: soft compressor + lowpass to remove harshness
      master = ctx.createGain();
      master.gain.value = 0.9;
      const comp = ctx.createDynamicsCompressor();
      comp.threshold.value = -18;
      comp.knee.value = 24;
      comp.ratio.value = 4;
      comp.attack.value = 0.003;
      comp.release.value = 0.18;
      const lp = ctx.createBiquadFilter();
      lp.type = "lowpass";
      lp.frequency.value = 8200;
      master.connect(comp);
      comp.connect(lp);
      lp.connect(ctx.destination);
    }
  }
  if (ctx && ctx.state === "suspended") ctx.resume();
  return ctx;
}

const MASTER = 1.7;

// A single voice with ADSR envelope, optional pitch glide, detune layering and filter.
function voice({
  freq = 440, type = "sine", dur = 0.12, gain = 0.05,
  slideTo = null, delay = 0, attack = 0.008, release = null,
  detune = 0, filterType = null, filterFreq = 6000, filterQ = 0.7, pan = 0,
}) {
  const ac = getCtx();
  if (!ac) return;
  const t0 = ac.currentTime + delay;
  const rel = release == null ? Math.max(0.04, dur * 0.6) : release;

  const osc = ac.createOscillator();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(Math.max(1, slideTo), t0 + dur);
  if (detune) osc.detune.setValueAtTime(detune, t0);

  const g = ac.createGain();
  const peak = Math.min(gain * MASTER, 0.16);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(peak, t0 + attack);          // attack
  g.gain.exponentialRampToValueAtTime(peak * 0.7, t0 + dur * 0.6); // decay/sustain
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur + rel);     // release

  let node = osc;
  if (filterType) {
    const f = ac.createBiquadFilter();
    f.type = filterType;
    f.frequency.setValueAtTime(filterFreq, t0);
    f.Q.value = filterQ;
    osc.connect(f);
    node = f;
  }
  node.connect(g);

  if (pan && ac.createStereoPanner) {
    const p = ac.createStereoPanner();
    p.pan.value = pan;
    g.connect(p);
    p.connect(master || ac.destination);
  } else {
    g.connect(master || ac.destination);
  }

  osc.start(t0);
  osc.stop(t0 + dur + rel + 0.03);
}

// Bell-like FM voice (carrier + modulator) for premium notification chimes.
function bell({ freq = 880, dur = 0.5, gain = 0.06, delay = 0, ratio = 2.0, index = 220 }) {
  const ac = getCtx();
  if (!ac) return;
  const t0 = ac.currentTime + delay;
  const carrier = ac.createOscillator();
  const mod = ac.createOscillator();
  const modGain = ac.createGain();
  const g = ac.createGain();
  carrier.type = "sine";
  mod.type = "sine";
  carrier.frequency.setValueAtTime(freq, t0);
  mod.frequency.setValueAtTime(freq * ratio, t0);
  modGain.gain.setValueAtTime(index, t0);
  modGain.gain.exponentialRampToValueAtTime(1, t0 + dur); // FM index decays → metallic → pure
  const peak = Math.min(gain * MASTER, 0.16);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(peak, t0 + 0.006);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  mod.connect(modGain);
  modGain.connect(carrier.frequency);
  carrier.connect(g);
  g.connect(master || ac.destination);
  carrier.start(t0); mod.start(t0);
  carrier.stop(t0 + dur + 0.05); mod.stop(t0 + dur + 0.05);
}

// Short noise burst (for tactile clicks / transients).
function noise({ dur = 0.03, gain = 0.05, delay = 0, filterType = "highpass", filterFreq = 2000, filterQ = 0.7 }) {
  const ac = getCtx();
  if (!ac) return;
  const t0 = ac.currentTime + delay;
  const len = Math.max(1, Math.floor(ac.sampleRate * dur));
  const buf = ac.createBuffer(1, len, ac.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len); // decaying noise
  const src = ac.createBufferSource();
  src.buffer = buf;
  const f = ac.createBiquadFilter();
  f.type = filterType;
  f.frequency.value = filterFreq;
  f.Q.value = filterQ;
  const g = ac.createGain();
  const peak = Math.min(gain * MASTER, 0.18);
  g.gain.setValueAtTime(peak, t0);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  src.connect(f); f.connect(g); g.connect(master || ac.destination);
  src.start(t0); src.stop(t0 + dur + 0.02);
}

// backward-compatible simple tone
function tone(opts) { voice(opts); }

// ── Crash: sustained rising tone (professional, non-arcade) ──
let _crashOsc = null, _crashSub = null, _crashGain = null;
function crashRiseStart() {
  const ac = getCtx(); if (!ac) return;
  crashRiseStop(true);
  const t = ac.currentTime;
  _crashOsc = ac.createOscillator();
  _crashSub = ac.createOscillator();
  _crashGain = ac.createGain();
  const lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 1300; lp.Q.value = 0.5;
  _crashOsc.type = "sine"; _crashOsc.frequency.setValueAtTime(160, t);
  _crashSub.type = "sine"; _crashSub.frequency.setValueAtTime(80, t);
  _crashGain.gain.setValueAtTime(0.0001, t);
  _crashGain.gain.exponentialRampToValueAtTime(0.028, t + 0.4);
  _crashOsc.connect(lp); _crashSub.connect(lp); lp.connect(_crashGain); _crashGain.connect(master || ac.destination);
  _crashOsc.start(t); _crashSub.start(t);
}
function crashRiseUpdate(mult = 1) {
  const ac = getCtx(); if (!ac || !_crashOsc) return;
  const f = 160 + Math.min(mult, 40) * 22;
  try {
    _crashOsc.frequency.linearRampToValueAtTime(f, ac.currentTime + 0.12);
    _crashSub.frequency.linearRampToValueAtTime(f / 2, ac.currentTime + 0.12);
  } catch (e) { /* noop */ }
}
function crashRiseStop(immediate = false) {
  const ac = getCtx(); if (!ac || !_crashOsc) return;
  const t = ac.currentTime;
  try {
    _crashGain.gain.cancelScheduledValues(t);
    _crashGain.gain.setValueAtTime(Math.max(0.0001, _crashGain.gain.value), t);
    _crashGain.gain.exponentialRampToValueAtTime(0.0001, t + (immediate ? 0.03 : 0.18));
    _crashOsc.stop(t + 0.24); _crashSub.stop(t + 0.24);
  } catch (e) { /* noop */ }
  _crashOsc = null; _crashSub = null; _crashGain = null;
}

// ─── Nublar Spin (daily wheel): real MP3 pool ──────────────────────────────
// The wheel's sounds are recorded assets (public/sounds/wheel), not synthesis:
// a carousel ticking at 60 Hz needs overlapping plays, so each file keeps a
// small pool of HTMLAudioElements. Lazily built on first play — a page that
// never opens the wheel never touches the network for them.
class SoundPool {
  constructor(map, poolSize = 3) {
    this.map = map; this.poolSize = poolSize;
    this.pools = null; this.idx = {};
  }
  _build() {
    this.pools = {};
    if (typeof window === "undefined" || typeof Audio === "undefined") return;
    for (const key of Object.keys(this.map)) {
      this.pools[key] = []; this.idx[key] = 0;
      for (let i = 0; i < this.poolSize; i++) {
        try { const a = new Audio(this.map[key]); a.preload = "auto"; this.pools[key].push(a); } catch (_) { /* noop */ }
      }
    }
  }
  play(key, { volume = 1, rate = 1, maxDuration = 0 } = {}) {
    if (!this.pools) this._build();
    const p = this.pools[key];
    if (!p || !p.length) return null;
    const a = p[this.idx[key]];
    this.idx[key] = (this.idx[key] + 1) % p.length;
    try {
      a.currentTime = 0;
      a.volume = Math.min(1, Math.max(0, volume));
      a.playbackRate = Math.max(0.25, Math.min(4, rate));
      const pr = a.play();
      if (pr && pr.catch) pr.catch(() => {});
      if (maxDuration > 0) {
        setTimeout(() => {
          const start = a.volume;
          for (let i = 1; i <= 8; i++) setTimeout(() => { try { a.volume = start * (1 - i / 8); } catch (_) { /* noop */ } }, i * 25);
          setTimeout(() => { try { a.pause(); a.currentTime = 0; a.volume = start; } catch (_) { /* noop */ } }, 220);
        }, maxDuration);
      }
    } catch (_) { /* noop */ }
    return a;
  }
}

const _wheelPool = new SoundPool({
  whoosh:           "/sounds/wheel/whoosh.mp3",
  tick:             "/sounds/wheel/tick.mp3",
  impact:           "/sounds/wheel/impact.mp3",
  coin:             "/sounds/wheel/coin.mp3",
  sparkle:          "/sounds/wheel/sparkle.mp3",
  reveal_rare:      "/sounds/wheel/reveal_rare.mp3",
  reveal_legendary: "/sounds/wheel/reveal_legendary.mp3",
  jackpot:          "/sounds/wheel/jackpot.mp3",
});

export const SOUNDS = {
  hover: () => voice({ freq: 640, type: "sine", dur: 0.05, gain: 0.014, attack: 0.004, filterType: "lowpass", filterFreq: 3200 }),
  // Satisfying tactile "mechanical" click: snappy noise tick + soft body pop.
  click: () => {
    noise({ dur: 0.018, gain: 0.05, filterType: "highpass", filterFreq: 2600, filterQ: 0.6 });
    voice({ freq: 190, type: "triangle", dur: 0.05, gain: 0.055, slideTo: 130, attack: 0.001, release: 0.03, filterType: "lowpass", filterFreq: 2600 });
    voice({ freq: 1300, type: "sine", dur: 0.03, gain: 0.02, delay: 0.004, attack: 0.001 });
  },
  open: () => { voice({ freq: 320, type: "sine", dur: 0.14, gain: 0.045, slideTo: 620, filterType: "lowpass", filterFreq: 5000 }); },
  close: () => { voice({ freq: 560, type: "sine", dur: 0.13, gain: 0.04, slideTo: 240, filterType: "lowpass", filterFreq: 4000 }); },

  // ── Navigation dropdowns — a soft, "lindo" descending arpeggio that reads as
  // options gently dropping down. Warm bells + a light glide underneath. ──
  menu: () => {
    voice({ freq: 300, type: "sine", dur: 0.16, gain: 0.03, slideTo: 520, attack: 0.006, filterType: "lowpass", filterFreq: 5200 });
    [784, 988, 1318].forEach((f, i) => bell({ freq: f, dur: 0.34, gain: 0.03, delay: i * 0.045, ratio: 2, index: 90 }));
  },
  menuClose: () => {
    voice({ freq: 520, type: "sine", dur: 0.13, gain: 0.028, slideTo: 300, attack: 0.005, filterType: "lowpass", filterFreq: 4200 });
    [988, 660].forEach((f, i) => bell({ freq: f, dur: 0.22, gain: 0.026, delay: i * 0.04, ratio: 2, index: 80 }));
  },

  // ── Notifications (premium bell-based) ──
  success: () => { bell({ freq: 660, dur: 0.4, gain: 0.06, ratio: 3, index: 120 }); bell({ freq: 990, dur: 0.55, gain: 0.055, delay: 0.1, ratio: 2, index: 90 }); },
  error: () => { voice({ freq: 300, type: "sine", dur: 0.16, gain: 0.06, slideTo: 180, filterType: "lowpass", filterFreq: 1600 }); voice({ freq: 150, type: "triangle", dur: 0.22, gain: 0.05, slideTo: 110, delay: 0.02 }); },
  notification: () => { bell({ freq: 1046, dur: 0.5, gain: 0.06, ratio: 2.0, index: 160 }); bell({ freq: 1568, dur: 0.6, gain: 0.045, delay: 0.11, ratio: 1.5, index: 120 }); },
  message: () => { bell({ freq: 784, dur: 0.35, gain: 0.055, ratio: 2.5, index: 140 }); bell({ freq: 1175, dur: 0.45, gain: 0.045, delay: 0.09, ratio: 2, index: 100 }); },

  // ── Rewards / economy ──
  purchase: () => { [523, 659, 784, 1046].forEach((f, i) => bell({ freq: f, dur: 0.4, gain: 0.05, delay: i * 0.06, ratio: 2, index: 100 })); },
  coins: () => { for (let i = 0; i < 4; i++) voice({ freq: 1400 + i * 220, type: "triangle", dur: 0.07, gain: 0.03, delay: i * 0.045, filterType: "bandpass", filterFreq: 2600, filterQ: 3 }); },
  // Single crisp "coin pickup" (Mario-style two ascending blips) — short so it
  // can fire on every item click without stacking.
  coinClick: () => {
    voice({ freq: 987.77, type: "square", dur: 0.055, gain: 0.03, attack: 0.001, release: 0.03, filterType: "bandpass", filterFreq: 2000, filterQ: 2 });
    voice({ freq: 1318.51, type: "square", dur: 0.13, gain: 0.032, delay: 0.055, attack: 0.001, release: 0.09, filterType: "bandpass", filterFreq: 2600, filterQ: 2 });
    bell({ freq: 2637, dur: 0.12, gain: 0.014, delay: 0.055, ratio: 3, index: 60 });
  },
  // Soft, rounded "select" bloop — a warm upward pop, no metallic ring. Used
  // when picking items into a trade offer (fires rapidly, stays gentle).
  tileClick: () => {
    voice({ freq: 430, type: "triangle", dur: 0.06, gain: 0.05, slideTo: 640, attack: 0.001, release: 0.04, filterType: "lowpass", filterFreq: 3000 });
    voice({ freq: 860, type: "sine", dur: 0.035, gain: 0.018, delay: 0.006, attack: 0.001, release: 0.03, filterType: "lowpass", filterFreq: 4000 });
  },
  reward: () => { [523, 659, 784, 988, 1318].forEach((f, i) => bell({ freq: f, dur: 0.5, gain: 0.05, delay: i * 0.07, ratio: 2, index: 130 })); },

  // Single roulette "tick" (ball clicking a divider) — driven repeatedly & decelerating by the Roll component.
  tick: () => {
    noise({ dur: 0.012, gain: 0.05, filterType: "highpass", filterFreq: 3400, filterQ: 0.8 });
    voice({ freq: 1050, type: "square", dur: 0.02, gain: 0.022, attack: 0.001, release: 0.015, filterType: "bandpass", filterFreq: 2200, filterQ: 6 });
  },
  // Satisfying "ding" when the roulette lands on the winning number.
  rollLand: () => {
    bell({ freq: 880, dur: 0.42, gain: 0.075, ratio: 3, index: 120 });
    bell({ freq: 1320, dur: 0.5, gain: 0.05, delay: 0.06, ratio: 2, index: 90 });
    noise({ dur: 0.02, gain: 0.04, filterType: "highpass", filterFreq: 3000 });
  },
  // Rising tone during Crash — smooth sustained tone (professional, controlled by the Crash component).
  crashRiseStart: () => crashRiseStart(),
  crashRiseUpdate: (m) => crashRiseUpdate(m),
  crashRiseStop: () => crashRiseStop(),
  // Deep, clean impact when Crash busts (no arcade harshness).
  crashBoom: () => {
    crashRiseStop();
    voice({ freq: 130, type: "sine", dur: 0.6, gain: 0.09, slideTo: 42, filterType: "lowpass", filterFreq: 800 });
    noise({ dur: 0.45, gain: 0.05, filterType: "lowpass", filterFreq: 480, filterQ: 0.5 });
  },
  // Soft, elegant chime when you cash out.
  crashCashout: () => {
    bell({ freq: 784, dur: 0.5, gain: 0.05, ratio: 2, index: 90 });
    bell({ freq: 1175, dur: 0.62, gain: 0.04, delay: 0.08, ratio: 1.5, index: 70 });
  },
  // Gentle harp-like note that rises in pitch as the multiplier climbs (elegant, sparse).
  crashNote: (mult = 1) => {
    const scale = [523.25, 587.33, 659.25, 783.99, 880.0, 1046.5, 1174.66, 1318.5];
    const idx = Math.min(scale.length - 1, Math.max(0, Math.floor(Math.log2(Math.max(1, mult)) * 2)));
    bell({ freq: scale[idx], dur: 0.7, gain: 0.03, ratio: 2, index: 55 });
  },

  // ── Creator Program ──
  // Short, friendly two-note ding — fires often (every new referral), so it
  // stays quick and unobtrusive rather than a full fanfare.
  newReferral: () => {
    bell({ freq: 880, dur: 0.28, gain: 0.045, ratio: 2.4, index: 90 });
    bell({ freq: 1318.5, dur: 0.36, gain: 0.035, delay: 0.07, ratio: 2, index: 70 });
  },
  // PrimeMeat landing in the wallet: a small `coins`-style trickle that
  // resolves into a soft bell, since this is a one-shot reward notice rather
  // than a running tally.
  rewardReceived: () => {
    for (let i = 0; i < 3; i++) {
      voice({ freq: 1100 + i * 180, type: "triangle", dur: 0.06, gain: 0.028, delay: i * 0.05, filterType: "bandpass", filterFreq: 2400, filterQ: 3 });
    }
    bell({ freq: 784, dur: 0.4, gain: 0.05, delay: 0.16, ratio: 2, index: 100 });
  },
  // Climbing the leaderboard — a rising slide under an ascending bell pair,
  // `success` made more triumphant.
  rankUp: () => {
    voice({ freq: 260, type: "sawtooth", dur: 0.22, gain: 0.03, slideTo: 640, filterType: "lowpass", filterFreq: 3200 });
    bell({ freq: 740, dur: 0.4, gain: 0.06, delay: 0.08, ratio: 2.5, index: 110 });
    bell({ freq: 1108.7, dur: 0.55, gain: 0.05, delay: 0.18, ratio: 2, index: 90 });
  },
  // Exclusive-skin / APEX unlock — the most elaborate cue in the set (drives
  // CelebrationOverlay's full-screen moment): a shimmering ascending run
  // instead of a single chime.
  skinUnlocked: () => {
    const scale = [523.25, 659.25, 784.0, 987.77, 1174.66];
    scale.forEach((f, i) => bell({ freq: f, dur: 0.6, gain: 0.05, delay: i * 0.075, ratio: 2, index: 130 }));
    noise({ dur: 0.5, gain: 0.02, delay: 0.35, filterType: "highpass", filterFreq: 5000, filterQ: 0.4 });
  },
  // A milestone banner lighting up — sits between `notification` and `reward`
  // in weight.
  milestone: () => {
    bell({ freq: 987.77, dur: 0.45, gain: 0.055, ratio: 2, index: 130 });
    bell({ freq: 1318.5, dur: 0.55, gain: 0.04, delay: 0.1, ratio: 1.6, index: 100 });
  },
  // Copy-to-clipboard tap — quieter than `click`, no pitch drop, just a soft
  // confirmation tick.
  copyCode: () => {
    noise({ dur: 0.014, gain: 0.035, filterType: "highpass", filterFreq: 3800, filterQ: 0.7 });
    voice({ freq: 1500, type: "sine", dur: 0.045, gain: 0.03, attack: 0.002, release: 0.03 });
  },

  // EPIC & CHILLING zombie roar — cinematic undead horror.
  //   [impact boom] → [multi-voice growl w/ detune choir] → [wet gurgle + ring-mod horror]
  //   → [high inharmonic shriek] → [sub drop] → [cave delay tail + last gasp]
  // Fully synthesised, no assets. ~3.6s total.
  zombieRoar: () => {
    const ac = getCtx(); if (!ac) return;
    const t = ac.currentTime;
    const DUR = 3.6;

    // ─── Shared cave-tunnel reverb bus ────────────────────────────────────
    // Feedback delay simulates a long reverb tail (dungeon / crypt).
    const revIn = ac.createGain();
    const revLp = ac.createBiquadFilter();
    revLp.type = "lowpass"; revLp.frequency.value = 2400; revLp.Q.value = 0.6;
    const delay = ac.createDelay(1.2);
    delay.delayTime.value = 0.32;
    const feedback = ac.createGain(); feedback.gain.value = 0.55;
    const revOut = ac.createGain(); revOut.gain.value = 0.42;
    revIn.connect(revLp); revLp.connect(delay);
    delay.connect(feedback); feedback.connect(delay);
    delay.connect(revOut); revOut.connect(master || ac.destination);

    // Helper — send a node into the reverb bus
    const sendReverb = (node, amount = 0.35) => {
      const g = ac.createGain(); g.gain.value = amount;
      node.connect(g); g.connect(revIn);
    };

    // ─── 1) IMPACT BOOM (dramatic entrance) ───────────────────────────────
    // Deep thud + short whoosh sets the stage before the roar hits.
    voice({ freq: 55, type: "sine",     dur: 0.35, gain: 0.13, slideTo: 28, attack: 0.001, release: 0.28, filterType: "lowpass", filterFreq: 200 });
    voice({ freq: 110, type: "triangle", dur: 0.22, gain: 0.08, slideTo: 44, attack: 0.001, release: 0.18, filterType: "lowpass", filterFreq: 320 });
    noise({ dur: 0.28, gain: 0.055, filterType: "bandpass", filterFreq: 380, filterQ: 1.4 });
    // Reverse-like swell for tension (very short up-sweep)
    voice({ freq: 60, type: "sawtooth", dur: 0.28, gain: 0.02, slideTo: 200, attack: 0.24, release: 0.03, filterType: "lowpass", filterFreq: 800, delay: 0.02 });

    // ─── 2) MULTI-VOICE GROWL CHOIR ───────────────────────────────────────
    // Three detuned sawtooth oscillators to sound MASSIVE + not human.
    // Each has its own irregular LFO so they beat against each other unnaturally.
    const CHOIR = [
      { base: 96, slide: 55, detune:  0,   lfoRate: 17, lfoDepth: 24, delay: 0.18 },
      { base: 108, slide: 62, detune: -14, lfoRate: 21, lfoDepth: 18, delay: 0.22 },
      { base: 82,  slide: 46, detune: +12, lfoRate: 13, lfoDepth: 30, delay: 0.20 },
    ];
    const choirEnd = t + DUR - 0.55;
    CHOIR.forEach(({ base, slide, detune, lfoRate, lfoDepth, delay: d }) => {
      const start = t + d;
      const osc = ac.createOscillator();
      const g = ac.createGain();
      const bp = ac.createBiquadFilter();
      const lfo = ac.createOscillator();
      const lfoG = ac.createGain();
      osc.type = "sawtooth";
      osc.detune.value = detune;
      osc.frequency.setValueAtTime(base, start);
      osc.frequency.exponentialRampToValueAtTime(slide + 5, start + 0.6);
      osc.frequency.linearRampToValueAtTime(slide, choirEnd);
      bp.type = "bandpass";
      bp.frequency.setValueAtTime(560, start);
      bp.frequency.linearRampToValueAtTime(420, choirEnd);
      bp.Q.value = 2.8;
      lfo.type = "square"; // uneven / irregular
      lfo.frequency.setValueAtTime(lfoRate, start);
      lfo.frequency.linearRampToValueAtTime(Math.max(3, lfoRate * 0.4), choirEnd);
      lfoG.gain.value = lfoDepth;
      lfo.connect(lfoG); lfoG.connect(osc.frequency);
      const peak = Math.min(0.045 * MASTER, 0.12);
      g.gain.setValueAtTime(0.0001, start);
      g.gain.exponentialRampToValueAtTime(peak, start + 0.14);
      g.gain.setValueAtTime(peak, choirEnd - 0.4);
      g.gain.exponentialRampToValueAtTime(0.0001, choirEnd);
      osc.connect(bp); bp.connect(g); g.connect(master || ac.destination);
      sendReverb(g, 0.5);
      osc.start(start); lfo.start(start);
      osc.stop(choirEnd + 0.05); lfo.stop(choirEnd + 0.05);
    });

    // ─── 3) RING-MODULATED HORROR TEXTURE ─────────────────────────────────
    // A carrier oscillator × slow modulator = metallic, inhuman timbre.
    // Sits under the choir to add that "possessed" quality.
    const carrier = ac.createOscillator();
    const modulator = ac.createOscillator();
    const modGain = ac.createGain();
    const ringGain = ac.createGain();
    const ringLp = ac.createBiquadFilter();
    carrier.type = "sine"; carrier.frequency.value = 78;
    modulator.type = "sine"; modulator.frequency.value = 37;
    modGain.gain.value = 90; // depth of ring modulation
    modulator.connect(modGain); modGain.connect(carrier.frequency);
    ringLp.type = "lowpass"; ringLp.frequency.value = 900;
    ringGain.gain.setValueAtTime(0.0001, t + 0.3);
    ringGain.gain.exponentialRampToValueAtTime(0.035, t + 0.7);
    ringGain.gain.setValueAtTime(0.035, t + DUR - 0.9);
    ringGain.gain.exponentialRampToValueAtTime(0.0001, t + DUR - 0.4);
    carrier.connect(ringLp); ringLp.connect(ringGain); ringGain.connect(master || ac.destination);
    sendReverb(ringGain, 0.55);
    carrier.start(t + 0.3); modulator.start(t + 0.3);
    carrier.stop(t + DUR - 0.35); modulator.stop(t + DUR - 0.35);

    // ─── 4) HIGH INHARMONIC SHRIEK (unsettling upper layer) ────────────────
    // Enters on top of the growl for a moment — inhuman screech overtones.
    const shriekStart = t + 0.75;
    const shriekEnd   = t + 1.9;
    const shriekOsc = ac.createOscillator();
    const shriekBp = ac.createBiquadFilter();
    const shriekG = ac.createGain();
    shriekOsc.type = "square";
    shriekOsc.frequency.setValueAtTime(680, shriekStart);
    shriekOsc.frequency.exponentialRampToValueAtTime(940, shriekStart + 0.35);
    shriekOsc.frequency.exponentialRampToValueAtTime(520, shriekEnd);
    shriekBp.type = "bandpass";
    shriekBp.frequency.setValueAtTime(1700, shriekStart);
    shriekBp.frequency.linearRampToValueAtTime(2300, shriekEnd);
    shriekBp.Q.value = 8;
    shriekG.gain.setValueAtTime(0.0001, shriekStart);
    shriekG.gain.exponentialRampToValueAtTime(0.022, shriekStart + 0.12);
    shriekG.gain.setValueAtTime(0.022, shriekEnd - 0.25);
    shriekG.gain.exponentialRampToValueAtTime(0.0001, shriekEnd);
    shriekOsc.connect(shriekBp); shriekBp.connect(shriekG); shriekG.connect(master || ac.destination);
    sendReverb(shriekG, 0.7);
    shriekOsc.start(shriekStart); shriekOsc.stop(shriekEnd + 0.05);

    // ─── 5) WET GURGLE (throat bubbles, chaotic AM noise) ──────────────────
    const gBuf = ac.createBuffer(1, ac.sampleRate * 2, ac.sampleRate);
    const gData = gBuf.getChannelData(0);
    for (let i = 0; i < gData.length; i++) gData[i] = Math.random() * 2 - 1;
    const gNoise = ac.createBufferSource(); gNoise.buffer = gBuf;
    const gBp = ac.createBiquadFilter(); gBp.type = "bandpass"; gBp.frequency.value = 720; gBp.Q.value = 5;
    const gGain = ac.createGain();
    const gAmp = ac.createOscillator(); const gAmpG = ac.createGain();
    gAmp.type = "sine"; gAmp.frequency.setValueAtTime(13, t + 0.4);
    gAmp.frequency.linearRampToValueAtTime(6, t + DUR - 0.5);
    gAmpG.gain.value = 0.055;
    gAmp.connect(gAmpG); gAmpG.connect(gGain.gain);
    gGain.gain.setValueAtTime(0.0001, t + 0.4);
    gGain.gain.exponentialRampToValueAtTime(0.05, t + 0.6);
    gGain.gain.setValueAtTime(0.05, t + DUR - 0.9);
    gGain.gain.exponentialRampToValueAtTime(0.0001, t + DUR - 0.5);
    gNoise.connect(gBp); gBp.connect(gGain); gGain.connect(master || ac.destination);
    sendReverb(gGain, 0.4);
    gNoise.start(t + 0.4); gAmp.start(t + 0.4);
    gNoise.stop(t + DUR - 0.4); gAmp.stop(t + DUR - 0.4);

    // ─── 6) SUB DROP (climax at ~1.4s, feels like the roar "lands") ────────
    voice({ freq: 70, type: "sine",     dur: 0.9, gain: 0.11, slideTo: 30, attack: 0.02, release: 0.6, filterType: "lowpass", filterFreq: 220, delay: 1.15 });
    voice({ freq: 45, type: "triangle", dur: 1.3, gain: 0.09, slideTo: 25, attack: 0.05, release: 0.9, filterType: "lowpass", filterFreq: 160, delay: 1.25 });

    // ─── 7) CAVE TAIL — noise fading with heavy reverb send ────────────────
    const tailNoise = () => {
      const tb = ac.createBuffer(1, ac.sampleRate * 1.3, ac.sampleRate);
      const td = tb.getChannelData(0);
      for (let i = 0; i < td.length; i++) td[i] = (Math.random() * 2 - 1) * (1 - i / td.length);
      const src = ac.createBufferSource(); src.buffer = tb;
      const bp = ac.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 1400; bp.Q.value = 0.9;
      const gt = ac.createGain();
      gt.gain.setValueAtTime(0.0001, t + DUR - 1.1);
      gt.gain.exponentialRampToValueAtTime(0.04, t + DUR - 0.9);
      gt.gain.exponentialRampToValueAtTime(0.0001, t + DUR);
      src.connect(bp); bp.connect(gt); gt.connect(master || ac.destination);
      sendReverb(gt, 0.9);
      src.start(t + DUR - 1.1); src.stop(t + DUR + 0.05);
    };
    tailNoise();

    // ─── 8) LAST GASP — dying breath at the very end ───────────────────────
    noise({ dur: 0.55, gain: 0.028, filterType: "highpass", filterFreq: 2400, filterQ: 0.7, delay: DUR - 0.55 });
    noise({ dur: 0.35, gain: 0.02,  filterType: "lowpass",  filterFreq: 320,  filterQ: 0.7, delay: DUR - 0.35 });
  },

  // ─── Nublar Spin (daily wheel) — ONE sound per event, nothing lingers ───
  wheelStart: () => { _wheelPool.play("whoosh", { volume: 0.12, rate: 1.2, maxDuration: 500 }); },
  // The tick pitch follows the carousel speed: fast steps pitch up, the
  // slowdown pitches back down. Throttled so a 60 Hz animation never stacks.
  wheelTick: (() => {
    let idx = 0, lastCallAt = 0;
    const rates = [1.20, 1.30, 1.42, 1.54, 1.65, 1.78, 1.90, 1.75, 1.55, 1.35];
    return () => {
      const now = performance.now();
      const dt = now - lastCallAt;
      if (dt < 55) return;
      lastCallAt = now;
      if (dt > 220) idx = Math.min(rates.length - 1, idx + 2);
      else if (dt > 140) idx = Math.min(rates.length - 1, idx + 1);
      else idx = Math.max(0, idx - 1) % rates.length;
      _wheelPool.play("tick", { volume: 0.16, rate: rates[Math.max(0, Math.min(rates.length - 1, idx))] });
    };
  })(),
  wheelStop: () => { _wheelPool.play("impact", { volume: 0.32, maxDuration: 500 }); },
  wheelReveal: (rarity = "common") => {
    if (rarity === "rare") _wheelPool.play("sparkle", { volume: 0.32, rate: 1.05, maxDuration: 900 });
    else if (rarity === "epic") _wheelPool.play("reveal_rare", { volume: 0.32, rate: 1.1, maxDuration: 1200 });
    else if (rarity === "legendary") _wheelPool.play("reveal_legendary", { volume: 0.42, rate: 1.05, maxDuration: 1400 });
    else _wheelPool.play("coin", { volume: 0.3, rate: 1.15, maxDuration: 700 });
  },
  wheelJackpot: () => { _wheelPool.play("jackpot", { volume: 0.4, maxDuration: 2600 }); },
};
