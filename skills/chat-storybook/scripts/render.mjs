// Capture the film page frame by frame with headless Chromium.
// usage: node render.mjs <film.html> <out_dir> [--frames 12,300,4.5s,...] [--workers 4] [--fps 24]
//        node render.mjs --check      (exit 0 when Playwright and a browser are ready)
// Needs Playwright: found via PLAYWRIGHT_CORE (path to its index.mjs), or `playwright` / `playwright-core`
// resolvable from the current directory, this script's directory, ~/.chat-storybook, or NODE_PATH.
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const HELP = `Playwright was not found. Install it once, anywhere you like, for example:
  mkdir -p ~/.chat-storybook && cd ~/.chat-storybook && npm init -y && npm i playwright && npx playwright install chromium
It is looked for there, in the current directory, and on NODE_PATH.
Already installed somewhere else? Set PLAYWRIGHT_CORE=/path/to/playwright-core/index.mjs instead.`;

const loadChromium = async () => {
  if (process.env.PLAYWRIGHT_CORE) {
    const mod = await import(pathToFileURL(path.resolve(process.env.PLAYWRIGHT_CORE)).href);
    return mod.chromium ?? mod.default.chromium;
  }
  const here = path.dirname(fileURLToPath(import.meta.url));
  for (const base of [process.cwd(), here, path.join(os.homedir(), '.chat-storybook')].map(d => path.join(d, 'x.js'))) {
    for (const name of ['playwright', 'playwright-core']) {
      try { return createRequire(base)(name).chromium; } catch { /* try the next place */ }
    }
  }
  return null;
};

const chromium = await loadChromium();
if (!chromium) { console.error(HELP); process.exit(2); }

const [html, outDir, ...rest] = process.argv.slice(2);
const CHECK = html === '--check';
if (!CHECK && (!html || !outDir)) { console.error('usage: node render.mjs <film.html> <out_dir> [--frames 12,4.5s] [--workers 4] [--fps 24]'); process.exit(2); }
const arg = (k, d) => { const i = rest.indexOf('--' + k); return i < 0 ? d : rest[i + 1]; };
const fps = +arg('fps', 24), workers = Math.max(1, +arg('workers', 4)), only = arg('frames', null);

// the browser Playwright downloads is preferred; an installed Google Chrome is the fallback
const ARGS = ['--font-render-hinting=none', '--force-color-profile=srgb'];
let browser;
try { browser = await chromium.launch({ args: ARGS }); } catch (e1) {
  try { browser = await chromium.launch({ args: ARGS, channel: 'chrome' }); } catch {
    console.error(String(e1.message).split('\n')[0]);
    console.error('No browser to render with. Run `npx playwright install chromium`, or install Google Chrome.');
    process.exit(2);
  }
}
if (CHECK) { await browser.close(); console.log('render: ok'); process.exit(0); }
mkdirSync(outDir, { recursive: true });

const open = async () => {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  page.on('pageerror', e => { console.error('PAGE ERROR', e.message); process.exitCode = 1; });
  await page.goto(pathToFileURL(path.resolve(html)).href + '?capture=1');
  await page.evaluate(() => window.READY);
  return page;
};

const first = await open();
const meta = await first.evaluate(() => ({ duration: window.DURATION, cues: window.CUES, scenes: window.SCENES }));
const total = Math.round(meta.duration * fps);
writeFileSync(path.join(outDir, 'meta.json'), JSON.stringify({ ...meta, fps, frames: total }));
console.log(`duration ${meta.duration}s, ${total} frames, ${meta.cues.length} cues`);

// a computer that falls asleep mid-render wakes up to an expired screenshot timer, so a frame gets a few tries
const shoot = async (page, f, name) => {
  for (let tries = 1; ; tries++) {
    try {
      await page.evaluate(t => window.seek(t), f / fps);
      await page.screenshot({ path: path.join(outDir, name), type: 'jpeg', quality: 94 });
      return;
    } catch (e) {
      if (tries >= 5) throw e;
      console.log(`frame ${f}: trying again (${String(e.message).split('\n')[0]})`);
    }
  }
};

if (only) {
  for (const s of only.split(',')) {
    const f = s.endsWith('s') ? Math.round(parseFloat(s) * fps) : +s;
    await shoot(first, f, `k${String(f).padStart(5, '0')}.jpg`);
  }
} else {
  const t0 = Date.now();
  let next = 0, done = 0;
  const run = async page => {
    for (;;) {
      const f = next++;
      if (f >= total) return;
      await shoot(page, f, `${String(f).padStart(5, '0')}.jpg`);
      if (++done % 300 === 0) console.log(`${done}/${total} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    }
  };
  const pages = [first, ...(await Promise.all(Array.from({ length: workers - 1 }, open)))];
  await Promise.all(pages.map(run));
  console.log(`captured ${done} frames in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}
await browser.close();
