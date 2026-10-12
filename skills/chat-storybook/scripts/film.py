#!/usr/bin/env python3
"""Draw the paper-cut storybook film from story.json (made by stats.py).

usage: python3 -I film.py story.json --out film.mp4 [--lang he|en] [--title "Group name"]
                          [--preview] [--crop45] [--copy pack.json] [--font file.ttf]
                          [--kbps 3400] [--workers N] [--keep] [--check]

--preview renders twelve key frames into <out>-preview.jpg instead of the film (seconds, not minutes).
--check   only reports whether node, ffmpeg and a Playwright browser are ready.
"""

import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
PREVIEW_AT = "4s,9s,14s,20s,27s,30s,33.5s,42s,47s,50.5s,54s,64s"
OUTRO_AT = 55.5  # the page starts turning to the "your group has a story too" card here
VF = "scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
CAPTIONS = {"c0": 3, "c1": 4, "c2": 2, "c3": 6, "c4": 3, "c5": 4, "c6": 2}
SUBTITLES = {"e0": 2, "e1": 4, "e2": 2, "e3": 6, "e4": 3, "e5": 4, "e6": 2, "e7": 7}
TOKEN_LINES = ("ctaHead", "ask", "credit")
PLAIN = ("coverSub", "byline", "hourTag", "wordsTag", "laughBig", "laughSmall")
PLAIN_LISTS = {"steps": 3, "code": 2}
VAR = re.compile(r"(\[[A-Za-z0-9]+\]|\{[A-Za-z0-9]+\})")
HEB = re.compile("[\u05d0-\u05ea]")
INSTALL = """Rendering needs Node.js, ffmpeg and a Playwright browser. To set up (ask the user first):
  node + ffmpeg   macOS: brew install node ffmpeg      Debian/Ubuntu: sudo apt install nodejs npm ffmpeg
  playwright      mkdir -p ~/.chat-storybook && cd ~/.chat-storybook && npm init -y && npm i playwright && npx playwright install chromium
                  already installed somewhere else? put PLAYWRIGHT_CORE=/path/to/playwright-core/index.mjs in front of each film.py command instead"""


def die(msg):
    print("film.py: " + msg, file=sys.stderr)
    sys.exit(1)


def fmt(n):
    return "{:,}".format(n)


def run(cmd, quiet=False, live=False):
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    lines = []
    for line in p.stdout:
        line = line.rstrip()
        if not line:
            continue
        lines.append(line)
        if live:
            print("  " + line, flush=True)
    code = p.wait()
    if code:
        hint = (
            "\nDid the computer go to sleep? Keep it awake and plugged in, then run this again."
            if any("Timeout" in x for x in lines)
            else ""
        )
        die(
            "%s failed (exit %d):\n%s%s"
            % (os.path.basename(cmd[0]), code, "\n".join(lines[-15:]), hint)
        )
    if not quiet and not live and lines:
        print(lines[-1])
    return "\n".join(lines)


def check_tools():
    node, ffmpeg = shutil.which("node"), shutil.which("ffmpeg")
    ok = True
    for name, path in (("node", node), ("ffmpeg", ffmpeg)):
        print("  %-10s %s" % (name, path or "MISSING"))
        ok = ok and bool(path)
    if (
        ffmpeg
        and "libx264"
        not in subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True
        ).stdout
    ):
        print("  libx264    MISSING (this ffmpeg build cannot write H.264)")
        ok = False
    if node:
        r = subprocess.run(
            [node, os.path.join(HERE, "render.mjs"), "--check"],
            capture_output=True,
            text=True,
        )
        print("  playwright " + ("ready" if r.returncode == 0 else "MISSING"))
        ok = ok and r.returncode == 0
    if not ok:
        print(INSTALL)
    return ok


def load_pack(path):
    with open(path, encoding="utf-8") as f:
        pack = json.load(f)
    for k, n in list(CAPTIONS.items()) + list(PLAIN_LISTS.items()):
        if not isinstance(pack.get(k), list) or len(pack[k]) != n:
            die("copy pack: %s must be a list of %d lines" % (k, n))
    for k, n in SUBTITLES.items():
        if pack.get(k) is not None and (
            not isinstance(pack[k], list) or len(pack[k]) != n
        ):
            die("copy pack: %s must be null or a list of %d lines" % (k, n))
    for k in TOKEN_LINES + PLAIN + ("months", "nWord", "dayparts", "span"):
        if k not in pack:
            die("copy pack: missing " + k)
    return pack


def span_form(forms, years):
    key = (
        "months"
        if years < 1
        else "one"
        if years == 1
        else "two"
        if years == 2 and "two" in forms
        else "many"
    )
    return forms[key]


class Copy:
    """Fills a pack's lines. {x} becomes a number chip, [x] plain text; [Span]/[span] are pack-owned phrases."""

    def __init__(self, pack, story):
        p, n = story["people"], len(story["people"])
        names = [x["name"] for x in p]
        ph, qh = story["peakH"], story["quietH"]
        y, m = story["ym"][story["peakM"]].split("-")
        a, b, pair_n = story["pairs"][-1]
        words = story["words"]
        en_months = pack.get("monthsEn", pack["months"])
        self.pack = pack
        self.macros = {
            "span": span_form(pack["span"], story["years"]),
            "spanEn": span_form(pack.get("spanEn", pack["span"]), story["years"]),
        }
        self.v = {
            "years": str(story["years"]),
            "spanMonths": str(story["spanMonths"]),
            "nWord": pack["nWord"][str(n)],
            "nWordEn": pack.get("nWordEn", pack["nWord"])[str(n)],
            "total": fmt(story["total"]),
            "top": names[0],
            "quietH12": str(qh % 12 or 12),
            "quietPart": pack["dayparts"][qh],
            "quietAmpm": "%d %s" % (qh % 12 or 12, "a.m." if qh < 12 else "p.m."),
            "peakClock": "%d:00" % ph,
            "peakAmpm": "%d %s" % (ph % 12 or 12, "a.m." if ph < 12 else "p.m."),
            "peakHn": fmt(story["hours"][ph]),
            "gapDays": fmt(story["gap"]["days"]) if story["gap"] else "",
            "peakMonth": "%s %s" % (pack["months"][int(m) - 1], y),
            "peakMonthEn": "%s %s" % (en_months[int(m) - 1], y),
            "peakMn": fmt(story["peakMn"]),
            "pairA": names[a],
            "pairB": names[b],
            "pairN": fmt(pair_n),
            "words": fmt(words),
            "wordsK": fmt(min(999, (words + 500) // 1000) if words < 1000000 else words // 1000),
            "wordsM": ("%.1f" % (words / 1e6)).rstrip("0").rstrip("."),
            "books": str(story["books"]),
            "pages": fmt(max(1, words // 300)),
            "laughs": fmt(story["laugh"]["n"]),
            "laughWord": story["laugh"]["word"],
            "laughBit": story["laugh"]["bit"],
            "laughWordEn": story["laugh"]["en"],
            "title": story["title"],
        }

    def _macros(self, s):
        def sub(m):
            key = m.group(1)
            low = key[0].lower() + key[1:]
            if low not in self.macros:
                return m.group(0)
            val = self.macros[low]
            return val[0].upper() + val[1:] if key[0].isupper() else val

        return re.sub(r"\[([A-Za-z0-9]+)\]", sub, s)

    def _parts(self, s):
        """Yield ('text'|'chip', string). Values are inserted as they are and never scanned again."""
        text = ""
        for piece in VAR.split(self._macros(s)):
            if not VAR.fullmatch(piece):
                text += piece
                continue
            key = piece[1:-1]
            low = key[0].lower() + key[1:]
            if low not in self.v:
                die(
                    "copy pack uses an unknown variable: %s. Known: %s"
                    % (piece, ", ".join(sorted(self.v)))
                )
            val = self.v[low]
            if key[0].isupper():
                val = val[:1].upper() + val[1:]
            if piece[0] == "{":
                yield "text", text
                yield "chip", val
                text = ""
            else:
                if (
                    self.pack.get("hyphenPrefix")
                    and text
                    and HEB.match(text[-1])
                    and val
                    and not HEB.match(val[0])
                ):
                    val = (
                        "-" + val
                    )  # Hebrew prefixes take a hyphen before a foreign word: ל-Dana
                text += val
        yield "text", text

    def plain(self, s):
        return "".join(val for _, val in self._parts(s)).strip()

    def tokens(self, s):
        out, spaced = [], True
        for kind, val in self._parts(s):
            if kind == "chip":
                out.append({"n": val} if spaced or not out else {"n": val, "j": 1})
                spaced = False
                continue
            core = val.strip()
            if core:
                glued = out and not spaced and not val[:1].isspace()
                out.append({"t": core, "j": 1} if glued else core)
                spaced = val[-1:].isspace()
            elif val:
                spaced = True
        return out


def build_copy(pack, story):
    n, words = len(story["people"]), story["words"]
    flags = {
        "duo": n == 2,
        "fewbooks": story["books"] < 2,
        "fewwords": words < 10000,
        "bigwords": words >= 1000000,
        "nolaughs": story["laugh"]["n"] < 5,
    }
    pack = json.loads(json.dumps(pack))
    for flag, on in flags.items():
        for key, line in (pack.get("variants", {}).get(flag, {}) if on else {}).items():
            name, _, idx = key.partition(".")
            if idx:
                if pack.get(name) is not None:
                    pack[name][int(idx)] = line
            else:
                pack[name] = line
    c = Copy(pack, story)
    out = {}
    for k in CAPTIONS:
        out[k] = [c.tokens(s) for s in pack[k]]
    for k in SUBTITLES:
        out[k] = (
            None
            if pack.get(k) is None
            else [None if s is None else c.plain(s) for s in pack[k]]
        )
    if out["e3"] and not story["gap"]:
        out["e3"][2] = out["e3"][3] = None
    for k in TOKEN_LINES:
        out[k] = c.tokens(pack[k])
    for k in PLAIN:
        out[k] = c.plain(pack[k])
    for k in PLAIN_LISTS:
        out[k] = [c.plain(s) for s in pack[k]]
    return out


def title_lines(title):
    t = "".join(
        ch
        for ch in title
        if unicodedata.category(ch) not in ("So", "Sk", "Cs", "Co", "Cn", "Cf")
    )
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        die('the film needs a title for its cover: pass --title "Group name"')
    lines = [t]
    spaces = [i for i, ch in enumerate(t) if ch == " "]
    if len(t) > 9 and spaces:
        cut = min(spaces, key=lambda i: abs(i - len(t) / 2))
        lines = [t[:cut], t[cut + 1 :]]
    longest = max(len(x) for x in lines)
    if longest > 14:
        die(
            'the title "%s" is too long for the cover (%d letters on one line, 14 at most): '
            'pass a short one with --title, two short words work best' % (t, longest)
        )
    if longest > 12:
        print(
            'note: the title is long for the cover tiles ("%s"); a shorter --title will look better'
            % t
        )
    return lines


def font_face(family, path):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    kind = {".otf": "opentype", ".woff2": "woff2", ".woff": "woff"}.get(
        os.path.splitext(path)[1].lower(), "truetype"
    )
    return (
        "@font-face{font-family:%s;src:url(data:font/%s;base64,%s) format('%s');font-weight:300 900;font-display:block}"
        % (
            family,
            kind if kind != "truetype" else "ttf",
            b64,
            kind,
        )
    )


def build_html(story, pack, args):
    faces = [font_face("Rubik", os.path.join(HERE, "fonts", "Rubik.ttf"))]
    stack = "Rubik, 'Arial Hebrew', 'Noto Sans', Arial, sans-serif"
    if args.font:
        faces.insert(0, font_face("StoryFont", args.font))
        stack = "StoryFont, " + stack
    data = {
        "people": story["people"],
        "rtl": pack.get("dir") == "rtl",
        "font": stack,
        "titleLines": title_lines(story["title"]),
        "gap": story["gap"],
        "hours": story["hours"],
        "peakH": story["peakH"],
        "ym": story["ym"],
        "months": story["months"],
        "peakM": story["peakM"],
        "peakMn": story["peakMn"],
        "pairs": story["pairs"],
        "books": story["books"],
        "copy": build_copy(pack, story),
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    blob = (
        blob.replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    with open(os.path.join(HERE, "film.tpl.html"), encoding="utf-8") as f:
        page = f.read()
    for key, val in (
        ("__LANG__", html.escape(str(pack.get("lang", "en")), quote=True)),
        ("__DIR__", "rtl" if data["rtl"] else "ltr"),
        ("__TITLE__", html.escape(story["title"])),
        ("__FONTFACE__", "\n".join(faces)),
        ("__BLOB__", blob),
    ):
        if page.count(key) != 1:
            die("template is damaged: expected exactly one " + key)
        page = page.replace(key, val)
    return page


def validate(story):
    need = (
        "people",
        "total",
        "years",
        "spanMonths",
        "hours",
        "peakH",
        "quietH",
        "ym",
        "months",
        "peakM",
        "peakMn",
        "gap",
        "pairs",
        "words",
        "books",
        "laugh",
        "title",
    )
    missing = [k for k in need if k not in story]
    if story.get("v") != 1 or missing:
        die(
            "this is not a story.json from stats.py (missing: %s)"
            % (", ".join(missing) or "v")
        )
    if not 2 <= len(story["people"]) <= 7:
        die("the film draws 2 to 7 people; story.json has %d" % len(story["people"]))
    unnamed = [p["name"] for p in story["people"] if p["name"].startswith("?")]
    if unnamed:
        die(
            'someone still has no name (%s). Ask who they are, then rerun stats.py with --name "%s=Their name"'
            % (", ".join(unnamed), unnamed[0])
        )
    if not story["pairs"]:
        die("story.json has no reply threads to draw")


def encode(ffmpeg, frames, wav, out, kbps, work, crop, outro=True):
    vf = ("crop=1080:1350:0:285," if crop else "") + VF
    cut = [] if outro else ["-t", str(OUTRO_AT)]
    log = os.path.join(work, "x264-45" if crop else "x264")
    src = ["-framerate", "24", "-i", os.path.join(frames, "%05d.jpg")]
    video = [
        "-c:v",
        "libx264",
        "-profile:v",
        "high",
        "-preset",
        "slow",
        "-b:v",
        "%dk" % kbps,
        "-passlogfile",
        log,
        "-vf",
        vf,
    ]
    run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        + src
        + video
        + cut
        + ["-pass", "1", "-an", "-f", "null", os.devnull],
        quiet=True,
    )
    has_at = (
        "aac_at"
        in subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True
        ).stdout
    )
    audio = [
        "-af",
        "volume=-0.3dB"
        + ("" if outro else ",afade=t=out:st=%s:d=1.5" % (OUTRO_AT - 1.5)),
        "-c:a",
        "aac_at" if has_at else "aac",
        "-b:a",
        "192k",
    ]
    run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        + src
        + ["-i", wav]
        + video
        + ["-pass", "2"]
        + audio
        + cut
        + ["-movflags", "+faststart", "-shortest", out],
        quiet=True,
    )
    print("wrote %s (%.1f MB)" % (out, os.path.getsize(out) / 1e6))


def main():
    ap = argparse.ArgumentParser(
        description="story.json -> paper-cut storybook film (1080x1920, 66 s, with music)"
    )
    ap.add_argument("story", nargs="?", help="story.json written by stats.py")
    ap.add_argument("--out", help="the .mp4 to write")
    ap.add_argument(
        "--lang",
        help="copy pack: he or en (default: he when the names are Hebrew, else en)",
    )
    ap.add_argument(
        "--copy", help="your own copy pack (start from a copy of copy/en.json)"
    )
    ap.add_argument("--title", help="cover title; overrides the one in story.json")
    ap.add_argument(
        "--font", help="a .ttf/.otf for scripts the bundled Rubik does not cover"
    )
    ap.add_argument(
        "--preview",
        action="store_true",
        help="render twelve key frames into <out>-preview.jpg and stop",
    )
    ap.add_argument(
        "--crop45", action="store_true", help="also write a 4:5 crop, <out>-4x5.mp4"
    )
    ap.add_argument(
        "--no-outro",
        action="store_true",
        help='end at 0:55, before the page turns to the "your group has a story too" card',
    )
    ap.add_argument(
        "--kbps", type=int, default=3400, help="video bitrate (default 3400)"
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=min(8, os.cpu_count() or 4),
        help="parallel browser pages",
    )
    ap.add_argument(
        "--keep",
        action="store_true",
        help="keep the work folder (frames, film.html, audio); it is removed otherwise, also after a failure",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="report whether node, ffmpeg and Playwright are ready",
    )
    a = ap.parse_args()

    if a.check:
        sys.exit(0 if check_tools() else 1)
    if not a.story or not a.out:
        ap.error("story.json and --out are required")
    with open(a.story, encoding="utf-8") as f:
        story = json.load(f)
    validate(story)
    if a.title:
        story["title"] = a.title.strip()

    if a.copy:
        pack_path = a.copy
    else:
        sample = story["title"] + "".join(p["name"] for p in story["people"])
        lang = a.lang or (
            "he"
            if len(HEB.findall(sample)) > len(re.findall("[A-Za-z]", sample))
            else "en"
        )
        pack_path = os.path.join(HERE, "copy", lang + ".json")
        if not os.path.isfile(pack_path):
            die(
                "no copy pack for '%s'. Copy copy/en.json, translate the lines, and pass it with --copy"
                % lang
            )
    pack = load_pack(pack_path)

    out = os.path.abspath(a.out)
    stem = os.path.splitext(out)[0]
    work = stem + ".work"
    os.makedirs(work, exist_ok=True)
    page_path = os.path.join(work, "film.html")
    with open(page_path, "w", encoding="utf-8") as f:
        f.write(build_html(story, pack, a))

    node, ffmpeg = shutil.which("node"), shutil.which("ffmpeg")
    if not node or not ffmpeg:
        die("node and ffmpeg are needed to render.\n" + INSTALL)
    render = [node, os.path.join(HERE, "render.mjs"), page_path]

    try:
        if a.preview:
            keys = os.path.join(work, "keys")
            shutil.rmtree(keys, ignore_errors=True)
            at = PREVIEW_AT
            if a.no_outro:  # show the last second of the film instead of the card
                at = at.rsplit(",", 1)[0] + ",%ss" % (OUTRO_AT - 0.5)
            run(render + [keys, "--frames", at], quiet=True)
            shots = sorted(x for x in os.listdir(keys) if x.endswith(".jpg"))
            for i, name in enumerate(shots):
                os.replace(os.path.join(keys, name), os.path.join(keys, "p%02d.jpg" % i))
            sheet = stem + "-preview.jpg"
            tile = [
                "-vf",
                "scale=360:640,tile=6x2:padding=6:color=white",
                "-frames:v",
                "1",
                "-q:v",
                "3",
            ]
            run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-framerate",
                    "1",
                    "-i",
                    os.path.join(keys, "p%02d.jpg"),
                ]
                + tile
                + [sheet],
                quiet=True,
            )
            print("wrote %s  (look at it before rendering the film)" % sheet)
        else:
            frames = os.path.join(work, "frames")
            shutil.rmtree(frames, ignore_errors=True)
            print("drawing the frames ...", flush=True)
            run(render + [frames, "--workers", str(max(1, a.workers))], live=True)
            wav = os.path.join(work, "music.wav")
            run(
                [
                    node,
                    os.path.join(HERE, "audio.mjs"),
                    os.path.join(frames, "meta.json"),
                    wav,
                ],
                quiet=True,
            )
            encode(ffmpeg, frames, wav, out, a.kbps, work, False, not a.no_outro)
            if a.crop45:
                encode(
                    ffmpeg, frames, wav, stem + "-4x5.mp4", a.kbps, work, True, not a.no_outro
                )
    finally:
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
