// Original synthesized soundtrack for the paper-storybook film: a small folk band (ukulele, bass, cajon, shaker,
// glockenspiel) arranged bar by bar at 120 BPM, plus paper sounds placed on the cues the page exports.
// usage: node audio.mjs <meta.json> <out.wav> [target_rms]
import { readFileSync, writeFileSync } from 'node:fs';

const [metaPath, outPath] = process.argv.slice(2);
const { duration, cues, scenes } = JSON.parse(readFileSync(metaPath, 'utf8'));
const SR = 44100, N = Math.ceil(duration * SR);
const bus = () => ({ L: new Float32Array(N), R: new Float32Array(N) });
const UKE = bus(), BASS = bus(), DRUMS = bus(), NOTES = bus(), SFX = bus(), SEND = bus();

let seed = 20150424;
const rnd = () => { seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const noise = () => rnd() * 2 - 1;
const TAU = Math.PI * 2, mtof = m => 440 * Math.pow(2, (m - 69) / 12);
const lp = fc => { let y = 0; const a = 1 - Math.exp(-TAU * fc / SR); return x => (y += a * (x - y)); };
const hp = fc => { const f = lp(fc); return x => x - f(x); };
function voice(b, t0, dur, fn, { gain = 1, pan = 0, send = 0 } = {}) {
  const i0 = Math.round(t0 * SR), n = Math.round(dur * SR);
  const gl = gain * Math.cos((pan + 1) * Math.PI / 4) * Math.SQRT2, gr = gain * Math.sin((pan + 1) * Math.PI / 4) * Math.SQRT2;
  for (let i = 0; i < n; i++) {
    const k = i0 + i; if (k < 0) continue; if (k >= N) break;
    const edge = Math.min(1, i / 64, (n - i) / 256), s = fn(i / SR) * edge;
    b.L[k] += s * gl; b.R[k] += s * gr;
    if (send) { SEND.L[k] += s * gl * send; SEND.R[k] += s * gr * send; }
  }
}
// the band stops dead when the page tears: nothing it plays may ring across the rip
// films without a torn page have no rip cue; the yarn scene plays one note per pair
const ripCue = cues.find(c => c.k === 'rip'), RIP = ripCue ? ripCue.t : -99;
const YARNS = cues.filter(c => c.k === 'yarn').length;
const play = (b, t0, dur, fn, o) => { if (t0 >= RIP && t0 < RIP + .5) return; voice(b, t0, t0 < RIP && t0 + dur > RIP ? RIP - t0 + .006 : dur, fn, o); };

// ---------- instruments ----------
// Karplus-Strong string: a noise burst circulating in a tuned delay line, with an all-pass for the fractional sample
const pluck = (f, bright, t60) => {
  const total = SR / f - .5; let L = Math.floor(total), fr = total - L;
  if (fr < .1) { L -= 1; fr += 1; }
  const C = (1 - fr) / (1 + fr), buf = new Float32Array(L), tone = lp(700 + bright * 6000), sustain = Math.exp(-6.9 / (f * t60));
  let m = 0, pk = 0;
  for (let i = 0; i < L; i++) { buf[i] = tone(noise()); m += buf[i]; }
  for (let i = 0; i < L; i++) { buf[i] -= m / L; pk = Math.max(pk, Math.abs(buf[i])); }
  for (let i = 0; i < L; i++) buf[i] /= pk;
  let i = 0, last = 0, x1 = 0, y1 = 0;
  return () => {
    const out = buf[i], avg = (out + last) * .5 * sustain; last = out;
    const y = C * avg + x1 - C * y1; x1 = avg; y1 = y;
    buf[i] = y; i = (i + 1) % L;
    return out;
  };
};
const glock = f => t => Math.sin(TAU * f * t) * Math.exp(-t * 3.4) + .4 * Math.sin(TAU * 2.756 * f * t) * Math.exp(-t * 6.5) + .15 * Math.sin(TAU * 5.404 * f * t) * Math.exp(-t * 12) + noise() * .12 * Math.exp(-t * 500);
const bassNote = f => { const l = lp(900); return t => l(Math.sin(TAU * f * t) + .55 * Math.sin(TAU * 2 * f * t) * Math.exp(-t * 2.5) + .3 * Math.sin(TAU * 3 * f * t) * Math.exp(-t * 5) + noise() * .25 * Math.exp(-t * 120)) * Math.exp(-t * 3.4); };
const thump = () => { const l = lp(900); return t => { const p = TAU * (70 * t + 80 * (1 - Math.exp(-30 * t)) / 30); return (Math.sin(p) + .35 * Math.sin(2 * p)) * Math.exp(-t * 11) + l(noise()) * Math.exp(-t * 60) * .5; }; };
const boxSlap = () => { const a = hp(700), b = lp(5200); return t => b(a(noise())) * Math.exp(-t * 38) * .9 + Math.sin(TAU * 210 * t) * Math.exp(-t * 30) * .45; };
const clap = () => { const a = hp(900), b = lp(6500); return t => b(a(noise())) * (Math.exp(-t * 180) + (t > .011 ? Math.exp(-(t - .011) * 180) : 0) + (t > .023 ? Math.exp(-(t - .023) * 40) : 0)) * .6; };
const shake = d => { const a = hp(4500), b = lp(11000); return t => b(a(noise())) * Math.min(1, t / .012) * Math.exp(-Math.max(0, t - .012) * d); };
const jingle = () => { const a = hp(6000); return t => (a(noise()) * .7 + (Math.sin(TAU * 5300 * t) + Math.sin(TAU * 7130 * t) + Math.sin(TAU * 8750 * t)) * .12) * Math.exp(-t * 22); };
const block = f => t => (Math.sin(TAU * f * t) + .5 * Math.sin(TAU * f * 2.4 * t)) * Math.exp(-t * 48);
const chirp = (f0, f1, dur, dec) => { let ph = 0; return t => { ph += TAU * (f0 + (f1 - f0) * Math.min(1, t / dur)) / SR; return Math.sin(ph) * Math.exp(-t * dec); }; };
const paperSlap = () => { const a = lp(2600), b = hp(500); return t => b(a(noise())) * Math.exp(-t * 70) + Math.sin(TAU * 150 * t) * Math.exp(-t * 60) * .5; };
// a sheet moving through air: band-passed noise whose band rises and falls, with a little flutter
const whoosh = dur => {
  let lo = 0, hi = 0, fl = 1, n = 0;
  return t => {
    const u = t / dur, s = Math.sin(Math.PI * u), x = noise();
    if (n++ % 500 === 0) fl = .65 + .35 * rnd();
    hi += (1 - Math.exp(-TAU * (700 + 4200 * s) / SR)) * (x - hi); lo += (1 - Math.exp(-TAU * (250 + 900 * s) / SR)) * (x - lo);
    return (hi - lo) * Math.pow(s, 1.5) * fl;
  };
};
// paper tearing: bright noise chopped into irregular crackles
const tear = dur => {
  const a = hp(1300), b = lp(9000); let g = 1, n = 0;
  return t => { if (n++ % 150 === 0) g = rnd() < .22 ? .15 : .5 + .5 * rnd(); return b(a(noise())) * g * Math.min(1, t / .01) * Math.min(1, (dur - t) / .05) * (.7 + .3 * t / dur); };
};
const zip = dur => { const a = hp(1800), b = lp(5200); return t => b(a(noise())) * (Math.sin(TAU * 95 * t) > 0 ? 1 : .2) * Math.min(1, (dur - t) / .03); };

// ---------- the song: 33 bars of 2 s ----------
const BAR = 2, SWING = .018;
const CH = { C: [67, 60, 64, 72], G: [67, 62, 67, 71], Am: [69, 60, 64, 69], F: [69, 60, 65, 69] };   // ukulele shapes, string 4 → 1
const LOW = { C: [36, 43], G: [43, 38], Am: [45, 40], F: [41, 36] };                                   // bass: root, fifth
const TRIAD = { C: [84, 88, 91], G: [83, 86, 91], Am: [81, 84, 88], F: [81, 84, 89] };                 // glockenspiel accents
const FULL = { strum: 1, bass: 1, cajon: 1, shaker: 1 }, PARTY = { ...FULL, four: 1, tamb: 1, clap: 1, shaker: 1.2 };
const bar = (c, o = {}) => ({ c, ...o });
const SONG = [
  // the pile of messages becomes a book
  bar('C', { strum: .7 }), bar('F', { strum: .8, shaker: .6 }), bar('G', { strum: 1, bass: 1, shaker: 1, tamb: 1, fill: 1 }),
  // seven friends
  bar('C', FULL), bar('G', FULL), bar('Am', FULL), bar('F', FULL), bar('G', { ...FULL, fill: 1 }),
  // the clock: night, then the whole town wakes
  bar('Am', { pick: .8, bass: .6 }), bar('F', { ...FULL, cajon: .7 }), bar('C', { ...FULL, tamb: 1 }), bar('G', { ...FULL, tamb: 1, fill: 1 }),
  // the mountains: walk, tear, silence, climb, summit
  bar('C', FULL), bar('G', FULL), bar('Am', { alone: 1 }), bar('F', { strum: .8, bass: 1, shaker: 1, build: 1 }), bar('C', { ...FULL, tamb: 1, clap: 1 }), bar('G', { ...FULL, tamb: 1, clap: 1, fill: 1 }),
  // the yarn
  bar('Am', { pick: .8, bass: .7 }), bar('F', { pick: .8, bass: .7, shaker: .5 }), bar('C', { pick: .9, bass: .8, shaker: .7 }), bar('G', { pick: .9, strum: .5, bass: 1, shaker: 1, tamb: 1, fill: 1 }),
  // eleven books, and the laughs
  bar('F', FULL), bar('G', FULL), bar('F', { ...FULL, tamb: 1 }), bar('G', { ...FULL, tamb: 1, fill: 1 }),
  // the party
  bar('C', PARTY), bar('G', { ...PARTY, fill: 1 }),
  // the back cover
  bar('C', { strum: .8, bass: 1, shaker: .8 }), bar('G', { strum: .8, bass: 1, shaker: .8 }), bar('F', { beats: 1, bass: 1, shaker: .5 }), bar('C', { last: 1 }), bar('C'),
];
if (SONG.length * BAR !== duration) throw new Error(`song is ${SONG.length * BAR}s, film is ${duration}s`);
const chordAt = t => SONG[Math.min(SONG.length - 1, Math.floor(t / BAR))].c;
const hum = () => (rnd() - .5) * .008;

const ISLAND = [[0, 1, 1], [2, 1, .8], [3, -1, .55], [5, -1, .6], [6, 1, .9], [7, -1, .55]];   // eighth, direction, weight: D-DU-UDU
const ON_BEATS = [[0, 1, .9], [2, 1, .75], [4, 1, .8]];
function strum(t, chord, dir, vel, ring, spread = .013, t60 = 2.1) {
  const order = dir > 0 ? [0, 1, 2, 3] : [3, 2, 1];   // up-strokes catch the top three strings
  order.forEach((s, k) => play(UKE, t + k * (spread + rnd() * .005), ring, pluck(mtof(chord[s]), dir > 0 ? .5 : .68, t60),
    { gain: .46 * vel * (.82 + rnd() * .3), pan: -.3 + s * .12, send: .16 }));
}
SONG.forEach((b, i) => {
  const t0 = i * BAR, chord = CH[b.c], next = SONG[i + 1], at = e => t0 + e * .25 + (e % 2 ? SWING : 0);
  const hits = b.strum ? ISLAND : b.beats ? ON_BEATS : [];
  hits.forEach(([e, dir, w], k) => {
    const gap = k + 1 < hits.length ? (hits[k + 1][0] - e) * .25 : next && (next.strum || next.beats) ? (8 - e) * .25 : 1.3;
    strum(at(e) + hum(), chord, dir, w * (b.strum || .8), gap + .06);
  });
  if (b.pick) [1, 2, 3, 2, 0, 2, 3, 2].forEach((s, e) => play(UKE, at(e) + hum(), .95, pluck(mtof(chord[s]), .38, 2.4), { gain: .52 * b.pick * (e % 4 ? .8 : 1), pan: -.3 + s * .12, send: .3 }));
  if (b.alone) {   // after the tear: one bass note and three lonely strings
    voice(BASS, t0, 1.6, bassNote(mtof(LOW[b.c][0])), { gain: .22 });
    [[2, 2], [4, 3], [6, 0]].forEach(([e, s]) => voice(UKE, at(e), 1.4, pluck(mtof(chord[s]), .32, 2.6), { gain: .46, pan: -.2 + s * .12, send: .5 }));
  }
  if (b.last) {    // the last chord, rolled slowly and left to ring
    strum(t0, chord, 1, 1.15, 4, .05, 3.4);
    [[1, 88, .1], [1.5, 91, .09], [2, 96, .11]].forEach(([d, m, g]) => voice(NOTES, t0 + d, 2, glock(mtof(m)), { gain: g, pan: .3 - d * .2, send: .5 }));   // a last twinkle while the credits are read
    voice(BASS, t0, 3, bassNote(mtof(LOW.C[0])), { gain: .36 });
    [84, 88].forEach((m, k) => voice(NOTES, t0 + .2 + k * .12, 3, glock(mtof(m)), { gain: .16, pan: .25, send: .4 }));
    voice(DRUMS, t0, .5, jingle(), { gain: .1, pan: -.35, send: .3 });
  }
  if (b.bass) {
    const [root, fifth] = LOW[b.c];
    play(BASS, t0, .7, bassNote(mtof(root)), { gain: .34 * b.bass });
    play(BASS, t0 + 1, .6, bassNote(mtof(fifth)), { gain: .28 * b.bass });
    if (b.cajon || b.build) play(BASS, at(7), .22, bassNote(mtof(root)), { gain: .2 * b.bass });
  }
  if (b.cajon) {
    (b.four ? [0, 2, 4, 6] : [0, 4]).forEach(e => play(DRUMS, at(e), .3, thump(), { gain: .5 * b.cajon }));
    if (!b.four) play(DRUMS, at(7), .2, thump(), { gain: .22 * b.cajon });
    [2, 6].forEach(e => play(DRUMS, at(e) + hum(), .2, boxSlap(), { gain: .34 * b.cajon, pan: .08, send: .12 }));
  }
  if (b.build) for (let e = 0; e < 8; e += 2) play(DRUMS, at(e), .3, thump(), { gain: .22 + e * .045 });
  if (b.shaker) for (let e = 0; e < 8; e++) play(DRUMS, at(e) + hum(), .12, shake(e % 2 ? 42 : 60), { gain: .1 * b.shaker * (e % 2 ? 1 : .6), pan: .4 });
  if (b.four) for (let e = 0; e < 8; e++) play(DRUMS, t0 + e * .25 + .125, .08, shake(80), { gain: .05, pan: .4 });
  if (b.tamb) (b.four ? [1, 2, 3, 5, 6, 7] : [2, 6]).forEach(e => play(DRUMS, at(e), .25, jingle(), { gain: e % 2 ? .07 : .12, pan: -.4, send: .15 }));
  if (b.clap) [2, 6].forEach(e => [-.3, .3].forEach(p => play(DRUMS, at(e) + hum(), .2, clap(), { gain: .2, pan: p, send: .25 })));
  if (b.fill || b.build) [6, 6.5, 7, 7.5].forEach((e, k) => play(DRUMS, t0 + e * .25, .16, boxSlap(), { gain: .16 + k * .07, pan: -.1 + k * .07, send: .15 }));
});

// the tune: one five-note shape, bent to fit each chord
const SHAPE = {
  C: [[0, 76], [1, 79], [3, 84], [5, 83], [6, 79]], G: [[0, 74], [1, 79], [3, 83], [5, 81], [6, 79]],
  Am: [[0, 76], [1, 81], [3, 84], [5, 83], [6, 81]], F: [[0, 77], [1, 81], [3, 84], [4, 81], [6, 79]],
};
const TUNE = { 7: 1, 10: 1, 11: 1, 12: 1, 13: 1, 16: 2, 17: 2, 24: 1, 25: 1, 26: 2, 27: 2 };   // bar → 1 plain, 2 doubled an octave up
const ring = (t, m, g = .2, pan = .25, dur = 1.3) => voice(NOTES, t, dur, glock(mtof(m)), { gain: g, pan, send: .32 });
for (const [i, kind] of Object.entries(TUNE)) SHAPE[SONG[i].c].forEach(([e, m]) => {
  const t = i * BAR + e * .25 + (e % 2 ? SWING : 0);
  if (t >= RIP && t < RIP + .5) return;
  ring(t, m, e ? .17 : .21); if (kind === 2) ring(t, m + 12, .09, .4);
});

// ---------- cues: paper sounds and the notes the pictures play ----------
const POPS = [72, 74, 76, 79, 81, 83, 86], DINGS = [69, 72, 76, 79, 81, 84, 89], RUN = [72, 74, 76, 77, 79, 81, 84];
const PENTA = [57, 60, 62, 64, 67, 69, 72, 74, 76, 79, 81, 84, 86, 88], BEADS = [81, 79, 76, 79, 84, 83, 86, 83, 79];
const BOOKS = [72, 74, 77, 79, 81, 84, 79, 81, 83, 86, 91], CARDS = [76, 79, 83];
const bubble = (t, f, g, pan) => voice(SFX, t, .12, chirp(f, f * 1.9, .05, 26), { gain: g, pan, send: .2 });
const accent = (t, g = 1) => {
  TRIAD[chordAt(t)].forEach((m, k) => ring(t + k * .035, m, .15 * g, .1 + k * .15, 1.6));
  voice(DRUMS, t, .35, jingle(), { gain: .16 * g, pan: -.3, send: .25 });
};
const crowd = (t, g = 1) => {
  for (let k = 0; k < 12; k++) voice(DRUMS, t + rnd() * .55, .2, clap(), { gain: .14 * g * (.6 + rnd() * .5), pan: rnd() * 1.6 - .8, send: .3 });
  for (let k = 0; k < 8; k++) voice(DRUMS, t + k * .07, .1, jingle(), { gain: .07 * g, pan: -.35, send: .2 });
  TRIAD[chordAt(t)].concat(TRIAD[chordAt(t)][0] + 12).forEach((m, k) => ring(t + k * .06, m, .12 * g, -.2 + k * .2));
};
const FX = {
  slap: t => voice(SFX, t, .12, paperSlap(), { gain: .2, pan: rnd() * .4 - .2, send: .1 }),
  page: t => { voice(SFX, t, .5, whoosh(.5), { gain: .55, send: .2 }); voice(SFX, t + .47, .14, paperSlap(), { gain: .3, send: .15 }); },
  bub: (t, v) => bubble(t, 420 + (v * 53) % 360, .17, ((v * 37) % 11) / 5.5 - 1),
  tada: t => { TRIAD[chordAt(t)].concat(TRIAD[chordAt(t)][0] + 12).forEach((m, k) => ring(t + k * .06, m, .16, -.2 + k * .2)); voice(DRUMS, t, .4, jingle(), { gain: .16, pan: -.3, send: .25 }); voice(SFX, t, .14, paperSlap(), { gain: .32, send: .15 }); },
  roll: t => RUN.forEach((m, k) => ring(t + .1 + k * .07, m, .1, -.4 + k * .13, .6)),
  pop: (t, v) => { voice(SFX, t, .1, chirp(950, 320, .035, 55), { gain: .3, pan: -.5 + v / 6, send: .15 }); ring(t, POPS[v], .2, -.4 + v * .13); },
  chatter: (t, v) => { for (let k = 0; k < 14; k++) bubble(t + .15 + rnd() * (v - .3), 380 + rnd() * 500, .07, rnd() * 1.6 - .8); },
  crown: t => { [84, 89, 93, 96].forEach((m, k) => ring(t + k * .045, m, .13, .1 + k * .12)); voice(DRUMS, t, .3, jingle(), { gain: .12, pan: -.3, send: .2 }); },
  stack: (t, v) => { const n = Math.round(v / .125); for (let k = 0; k < n; k++) voice(SFX, t + k * .125, .08, block(520 + 700 * k / n), { gain: .05 + .05 * k / n, pan: -.5 + k / n, send: .1 }); },
  ding: (t, v) => ring(t, DINGS[6 - v], .17, .5 - v * .16),
  clock: (t, v) => { for (let x = Math.ceil(t * 4) / 4; x < t + v; x += .25) voice(SFX, x, .1, block(Math.round(x * 2) === x * 2 ? 1250 : 930), { gain: .13, pan: Math.round(x * 2) === x * 2 ? -.25 : .25, send: .2 }); },
  flag: t => accent(t, Math.abs(t - 32) < .01 ? 1.35 : 1),
  spin: t => { for (let k = 0; k < 12; k++) voice(SFX, t + k * .045, .06, block(1700 - k * 75), { gain: .1, pan: .3 - k * .05, send: .1 }); },
  rip: t => { voice(SFX, t, .42, tear(.42), { gain: .5, pan: -.1, send: .28 }); voice(SFX, t, .2, thump(), { gain: .3 }); },
  tape: t => { voice(SFX, t, .2, zip(.2), { gain: .3, pan: .1, send: .12 }); voice(SFX, t + .22, .14, paperSlap(), { gain: .34, send: .15 }); ring(t + .22, 72, .12, 0, 1.6); },
  cheer: t => crowd(t, t > 50 ? 1.15 : 1),
  yarn: (t, v) => { voice(NOTES, t, .7, pluck(mtof(PENTA[Math.floor(v * 13 / Math.max(1, YARNS - 1))]), .6, 1.2), { gain: v === YARNS - 1 ? .34 : .2 + v * .004, pan: v % 2 ? .6 : -.6, send: .3 }); if (v === YARNS - 1) ring(t, 88, .16, 0, 1.6); },
  bead: (t, v) => { const k = Math.round((t - beads0) / .5); bubble(t, 520, .12, v ? .6 : -.6); ring(t, BEADS[k % BEADS.length], .17, v ? .6 : -.6); },
  book: (t, v) => { voice(SFX, t, .16, paperSlap(), { gain: .3 + v * .012, pan: -.1, send: .1 }); voice(SFX, t, .12, block(260 + v * 22), { gain: .14, send: .1 }); ring(t, BOOKS[v % BOOKS.length], .15, -.3 + v * .06); },
  laugh: (t, v) => { for (let b = 0; b < v * 2 - 1; b++) [0, 1, 2].forEach(k => voice(SFX, t + b * .5 + k * .125, .1, chirp(760 - k * 70 + (b % 3) * 45, 520 - k * 50 + (b % 3) * 30, .07, 24), { gain: .1 * (1 - b / (v * 2.6)), pan: b % 2 ? .5 : -.5, send: .2 })); },
  typing: (t, v) => { for (let b = 0; b * .5 < v - .2; b++) [0, 1, 2].forEach(k => voice(SFX, t + b * .5 + k * .125, .07, block(1500 + k * 180), { gain: .07, pan: .2, send: .2 })); },
  card: (t, v) => { voice(SFX, t, .14, paperSlap(), { gain: .34, send: .12 }); ring(t, CARDS[v], .2, -.2 + v * .2, 1.6); },
  end: t => { ring(t + .15, 81, .14, .1); ring(t + .4, 83, .15, .2); },
};
const beads0 = cues.find(c => c.k === 'bead').t;
for (const c of cues) { if (!FX[c.k]) throw new Error('no sound for cue ' + c.k); FX[c.k](c.t, c.v); }

// ---------- ukulele body, reverb (Schroeder), mix, soft limiter ----------
for (const ch of [UKE.L, UKE.R]) { const lo = hp(190), a = hp(330), b = lp(1150); for (let n = 0; n < N; n++) { const x = ch[n]; ch[n] = lo(x) * .85 + b(a(x)) * .6; } }
function reverb(x, off) {
  const out = new Float32Array(N), combs = [1557, 1617, 1491, 1422, 1277].map(d => ({ buf: new Float32Array(d + off), i: 0, lp: 0 }));
  for (let n = 0; n < N; n++) {
    let s = 0;
    for (const c of combs) { const y = c.buf[c.i]; c.lp += .5 * (y - c.lp); c.buf[c.i] = x[n] + c.lp * .8; c.i = (c.i + 1) % c.buf.length; s += y; }
    out[n] = s / combs.length;
  }
  for (const d of [225 + off, 556 + off]) {
    const buf = new Float32Array(d); let i = 0;
    for (let n = 0; n < N; n++) { const b = buf[i], v = out[n] + b * .5; buf[i] = v; i = (i + 1) % d; out[n] = b - v * .5; }
  }
  return out;
}
const WET = { L: reverb(SEND.L, 0), R: reverb(SEND.R, 23) };
const from = Math.round(scenes[1].t0 * SR), to = Math.round(scenes[scenes.length - 1].t0 * SR);
const db = b => { let q = 0; for (let n = from; n < to; n++) q += b.L[n] ** 2 + b.R[n] ** 2; return (10 * Math.log10(q / (to - from) / 2)).toFixed(1); };
console.log(`stems dBFS: ukulele ${db(UKE)}, bass ${db(BASS)}, percussion ${db(DRUMS)}, glockenspiel+plucks ${db(NOTES)}, paper fx ${db(SFX)}, reverb ${db(WET)}`);
const pcm = Buffer.alloc(44 + N * 4), TARGET_RMS = +(process.argv[4] || .175);
const master = ['L', 'R'].map(k => {
  const out = new Float32Array(N), rumble = hp(35), air = hp(3500);
  for (let n = 0; n < N; n++) { const s = rumble(UKE[k][n] + BASS[k][n] + DRUMS[k][n] + NOTES[k][n] + SFX[k][n] * 1.35 + WET[k][n] * .5); out[n] = s + .2 * air(s); }
  return out;
});
let sq = 0;
for (let n = from; n < to; n++) sq += master[0][n] ** 2 + master[1][n] ** 2;
const drive = TARGET_RMS / Math.sqrt(sq / (to - from) / 2);
let sum = 0, clipped = 0;
for (let n = 0; n < N; n++) {
  const t = n / SR, fade = Math.min(1, t / .01, (duration - t) / .6);
  for (const k of [0, 1]) {
    const x = master[k][n] * drive, y = Math.tanh(x) * .89 * fade; sum += y * y; if (Math.abs(x) > 1) clipped++;
    pcm.writeInt16LE(Math.round(y * 32767), 44 + n * 4 + k * 2);
  }
}
pcm.write('RIFF', 0); pcm.writeUInt32LE(36 + N * 4, 4); pcm.write('WAVEfmt ', 8); pcm.writeUInt32LE(16, 16); pcm.writeUInt16LE(1, 20); pcm.writeUInt16LE(2, 22);
pcm.writeUInt32LE(SR, 24); pcm.writeUInt32LE(SR * 4, 28); pcm.writeUInt16LE(4, 32); pcm.writeUInt16LE(16, 34); pcm.write('data', 36); pcm.writeUInt32LE(N * 4, 40);
writeFileSync(outPath, pcm);
console.log(`audio ${duration}s, ${SONG.length} bars, ${cues.length} cues, drive ${drive.toFixed(2)}, rms ${(10 * Math.log10(sum / N / 2)).toFixed(1)} dBFS, ${(100 * clipped / N / 2).toFixed(2)}% of samples in the soft-clip knee`);
