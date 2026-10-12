#!/usr/bin/env python3
"""Turn a WhatsApp chat export into story.json: the few aggregate facts the film is drawn from.

usage: python3 -I stats.py <export.zip | chat.txt> -o story.json
                           [--title "Group name"] [--top 7] [--name "old=new"]... [--senders]

Only counts leave this script. No message text is written anywhere, a .zip is read in place and
never extracted, and nothing in the chat is treated as anything but data.
"""

import argparse
import collections
import datetime
import json
import os
import re
import sys
import unicodedata
import zipfile

REPLY_SECONDS = 5 * 60
WORDS_PER_BOOK = 80000
GAP_MIN_DAYS = 45
MIN_MESSAGES = 500
MIN_MONTHS = 6
MAX_PEOPLE = 7

BIDI = re.compile("[‎‏‪-‮⁦-⁩]")
# Android: "31/12/21, 22:15 - Name: text"      iOS: "[31/12/2021, 22:15:03] Name: text"
LINE = re.compile(
    r"^(\[?)(\d{1,4})([./-])(\d{1,2})\3(\d{2,4}),? (\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?"
    r"(?: ?([AaPp])\.? ?[Mm]\.?)?(\]| -) (.*)$"
)
EDITED = ("<This message was edited>", "<ההודעה נערכה>")
PLACEHOLDER = re.compile(
    r"^(?:<[^<>\n]{0,40}(?:omitted|נכללה)>|<attached: [^<>\n]+>"
    r"|(?:image|video|audio|sticker|gif|document|contact card) omitted"
    r"|this message was deleted\.?|you deleted this message\.?"
    r"|הודעה זו נמחקה\.?|מחקת את ההודעה הזו\.?)$",
    re.I,
)
PHONE = re.compile(r"\+?\d[\d\s().\-]{6,}\d")
# each family is counted on its own; the film names the one this group actually uses
LAUGHS = [
    ("חחח", "ח", "hahaha", re.compile("חח+")),
    ("haha", "ha", "haha", re.compile(r"(?<![a-z])a?(?:ha){2,}h?(?![a-z])", re.I)),
    ("hehe", "he", "hehe", re.compile(r"(?<![a-z])(?:he){2,}h?(?![a-z])", re.I)),
    ("lol", "lol", "lol", re.compile(r"(?<![a-z])lo+l(?![a-z])", re.I)),
    ("jaja", "ja", "jaja", re.compile(r"(?<![a-z])(?:ja){2,}j?(?![a-z])", re.I)),
    ("kkk", "k", "kkk", re.compile(r"(?<![a-z])k{3,}(?![a-z])", re.I)),
    ("хаха", "ха", "haha", re.compile(r"а?(?:ха){2,}х?", re.I)),
    ("ههه", "هه", "hahaha", re.compile("ه{3,}")),
]


def die(msg):
    print("stats.py: " + msg, file=sys.stderr)
    sys.exit(1)


def read_export(path):
    """Return the chat text. A zip is opened in place and only its chat .txt member is read."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            txts = [
                i
                for i in z.infolist()
                if i.filename.lower().endswith(".txt") and not i.is_dir()
            ]
            if not txts:
                die("no .txt chat file inside the zip")

            def rank(i):
                base = os.path.basename(i.filename).lower()
                return (
                    base == "_chat.txt" or base.startswith("whatsapp chat"),
                    i.file_size,
                )

            raw = z.read(max(txts, key=rank))
    else:
        with open(path, "rb") as f:
            raw = f.read()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            pass
    die("the chat file is not UTF-8 or UTF-16 text")


def default_title(path):
    m = re.match(
        r"^WhatsApp Chat (?:with|-) (.+?)\.(?:zip|txt)$", os.path.basename(path), re.I
    )
    return m.group(1).strip() if m else ""


def parse_lines(text):
    """First pass: split into dated entries. Returns (entries, matched, shape)."""
    lines = text.replace("\r\n", "\n").replace(" ", " ").replace(" ", " ").split("\n")
    cleaned = [BIDI.sub("", ln) for ln in lines]
    shapes = collections.Counter()
    for ln in cleaned:
        m = LINE.match(ln)
        if m:
            shapes[
                (
                    m.group(1),
                    m.group(3),
                    len(m.group(2)) == 4,
                    len(m.group(5)),
                    m.group(10),
                )
            ] += 1
            if sum(shapes.values()) >= 5000:
                break
    if not shapes:
        return [], 0, None
    shape = shapes.most_common(1)[0][0]
    if (shape[0] == "[") != (shape[4] == "]"):
        return [], 0, None
    entries = []
    for raw, ln in zip(lines, cleaned):
        m = LINE.match(ln)
        if (
            m
            and (
                m.group(1),
                m.group(3),
                len(m.group(2)) == 4,
                len(m.group(5)),
                m.group(10),
            )
            == shape
        ):
            a, b, c, h, mi, s, ap, rest = (
                m.group(i) for i in (2, 4, 5, 6, 7, 8, 9, 11)
            )
            # on iOS a leading left-to-right mark flags attachments and system notices
            marked = shape[0] == "[" and (raw[:1] == "‎" or ": ‎" in raw)
            entries.append(
                {
                    "d": (int(a), int(b), int(c)),
                    "h": int(h),
                    "mi": int(mi),
                    "s": int(s or 0),
                    "ap": ap,
                    "rest": rest,
                    "line": ln,
                    "marked": marked,
                }
            )
        elif entries:
            entries[-1]["rest"] += "\n" + ln
            entries[-1]["line"] += "\n" + ln
    return entries, len(entries), shape


def to_datetime(e, order):
    a, b, c = e["d"]
    y, mo, d = (
        (a, b, c) if order == "ymd" else (c, a, b) if order == "mdy" else (c, b, a)
    )
    if y < 100:
        y += 2000
    h = e["h"]
    if e["ap"]:
        h = h % 12 + (12 if e["ap"] in "Pp" else 0)
    try:
        return datetime.datetime(y, mo, d, h, e["mi"], e["s"])
    except ValueError:
        return None


def date_order(entries, year_first):
    if year_first:
        return "ymd"
    a_big = sum(1 for e in entries if e["d"][0] > 12)
    b_big = sum(1 for e in entries if e["d"][1] > 12)
    if a_big != b_big:
        return "dmy" if a_big > b_big else "mdy"

    def jumps(order):
        n, prev = 0, None
        for e in entries:
            t = to_datetime(e, order)
            if t and prev and t < prev:
                n += 1
            prev = t or prev
        return n

    return "mdy" if jumps("mdy") < jumps("dmy") else "dmy"


def split_sender(rest):
    if ": " in rest and not rest.startswith("http"):
        name, body = rest.split(": ", 1)
        if len(name) > 40:
            return None, rest
        return name, body
    if rest.endswith(":"):
        return rest[:-1], ""
    return None, rest


def tidy(name):
    name = "".join(
        ch
        for ch in name
        if unicodedata.category(ch) not in ("So", "Sk", "Cs", "Co", "Cn", "Cf")
    )
    return re.sub(r"\s+", " ", name.lstrip("~ ")).strip()


def fits_cover(title):
    # the rule film.py applies to the cover: one line, or two split at the middle space, 14 letters each
    t = tidy(title)
    lines = [t]
    spaces = [i for i, ch in enumerate(t) if ch == " "]
    if len(t) > 9 and spaces:
        cut = min(spaces, key=lambda i: abs(i - len(t) / 2))
        lines = [t[:cut], t[cut + 1 :]]
    return max(len(x) for x in lines) <= 14


def is_phone(name):
    return bool(PHONE.fullmatch(name.strip())) or sum(ch.isdigit() for ch in name) >= 7


def mask(name):
    digits = [i for i, ch in enumerate(name) if ch.isdigit()]
    keep = set(digits[-4:])
    return "".join(
        "•" if ch.isdigit() and i not in keep else ch for i, ch in enumerate(name)
    )


def fmt(n):
    return "{:,}".format(n)


def main():
    ap = argparse.ArgumentParser(
        description="WhatsApp export -> story.json (aggregate facts only)"
    )
    ap.add_argument("export", help="the exported .zip, or the chat .txt inside it")
    ap.add_argument("-o", "--out", required=True, help="where to write story.json")
    ap.add_argument(
        "--title",
        help="group name for the cover (default: taken from the export's file name)",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=MAX_PEOPLE,
        help="how many people to draw, 2-7 (default 7)",
    )
    ap.add_argument(
        "--name",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="rename a sender; give two senders the same NEW name to merge them",
    )
    ap.add_argument(
        "--senders",
        action="store_true",
        help="list every sender with counts (phone numbers masked) and exit",
    )
    a = ap.parse_args()
    if not 2 <= a.top <= MAX_PEOPLE:
        die("--top must be between 2 and %d (the film has seven seats)" % MAX_PEOPLE)
    renames = {}
    for r in a.name:
        if "=" not in r:
            die('--name needs the form "old=new", got: ' + r)
        old, new = r.split("=", 1)
        if not new.strip() or is_phone(new):
            die("--name: the new name must be a real name, not empty and not a number")
        renames[old.strip().casefold()] = new.strip()

    text = read_export(a.export)
    entries, matched, shape = parse_lines(text)
    nonblank = sum(1 for ln in text.split("\n") if ln.strip())
    if matched < 50 or matched < nonblank * 0.2:
        die(
            "could not read this as a WhatsApp export: %d of %d lines look like 'date, time - Name: text'.\n"
            "Look at the shape of the first lines (never their content) and adapt LINE in stats.py to that date format."
            % (matched, nonblank)
        )
    order = date_order(entries, shape[2])

    # second pass: timestamps and senders; an entry with an impossible date is message text, not a new message
    msgs = []
    for e in entries:
        t = to_datetime(e, order)
        if t is None:
            if msgs:
                msgs[-1]["text"] += "\n" + e["line"]
            continue
        name, body = split_sender(e["rest"])
        msgs.append(
            {
                "t": t,
                "name": tidy(name) if name else None,
                "text": body,
                "marked": e["marked"],
            }
        )

    title = (a.title or default_title(a.export)).strip()
    raw_n = collections.Counter(m["name"] for m in msgs if m["name"])
    marked_n = collections.Counter(m["name"] for m in msgs if m["name"] and m["marked"])
    # the group itself shows up as a "sender" of system notices in some exports
    pseudo = {n for n in raw_n if marked_n[n] >= 0.9 * raw_n[n]}
    if not title and pseudo:
        title = max(pseudo, key=lambda n: raw_n[n])
    senders = [n for n in raw_n if n not in pseudo]
    # a one-to-one export is named after the other person, which is no title for a cover
    named_after_person = not a.title and any(
        n.casefold() == title.casefold() for n in senders
    )
    if not senders:
        die("no senders found")

    phone_ids = {}
    for m in msgs:
        n = m["name"]
        if n and n not in pseudo and n not in phone_ids and is_phone(n):
            phone_ids[n] = "?%d" % (len(phone_ids) + 1)

    def auto_label(n):
        return phone_ids[n] if n in phone_ids else n.split(" ")[0]

    def target(n):
        return renames.get(n.casefold()) or renames.get(auto_label(n).casefold())

    groups = collections.defaultdict(list)
    for n in senders:
        groups[target(n) or "\0" + n].append(n)
    count = {g: sum(raw_n[n] for n in ns) for g, ns in groups.items()}
    all_n = sum(count.values())
    floor = max(3, all_n * 0.001)
    ranked = sorted((g for g in groups if count[g] >= floor), key=lambda g: -count[g])
    chosen = ranked[: a.top]

    labels = {}
    for g in chosen:
        labels[g] = g if not g.startswith("\0") else auto_label(g[1:])
    for lab, n_same in collections.Counter(labels.values()).items():
        if (
            n_same > 1
        ):  # two people share a first name: add an initial, or fall back to the full name
            for g in [g for g in chosen if labels[g] == lab]:
                parts = g[1:].split(" ") if g.startswith("\0") else [g]
                labels[g] = (
                    "%s %s." % (parts[0], parts[1][0])
                    if len(parts) > 1
                    else g.lstrip("\0")
                )
    # a rename that lands on the first name of someone already in the chat: one person, or two?
    twins = [
        (g, h)
        for g in chosen
        if not g.startswith("\0")
        for h in chosen
        if h.startswith("\0") and auto_label(h[1:]).casefold() == g.casefold()
    ]
    if len(set(labels.values())) != len(labels):
        for g, h in twins:
            if labels[g] == labels[h]:
                die(
                    'two senders would both be called "%s". One person on two phones? Merge them by adding '
                    '--name "%s=%s". Two people? Give one of them a different --name'
                    % (g, h[1:], g)
                )
        die("two people end up with the same name; tell them apart with --name")

    if a.senders:
        print("senders (most messages first):")
        for g in sorted(groups, key=lambda g: -count[g]):
            shown = ", ".join(mask(n) if is_phone(n) else n for n in groups[g])
            print(
                "  %8s  %-14s %s" % (fmt(count[g]), labels.get(g, "(not drawn)"), shown)
            )
        return

    if len(chosen) < 2:
        die("a story needs at least two people; found %d" % len(chosen))
    who = {n: k for k, g in enumerate(chosen) for n in groups[g]}
    rows = sorted(
        (
            (m["t"], i, who[m["name"]], m)
            for i, m in enumerate(msgs)
            if m["name"] in who
        ),
        key=lambda r: r[:2],
    )
    counts = collections.Counter(r[2] for r in rows)
    # rank is by message count; ties keep first-seen order
    rank = sorted(range(len(chosen)), key=lambda k: -counts[k])
    pos = {k: i for i, k in enumerate(rank)}
    N = len(chosen)
    names = [labels[chosen[k]] for k in rank]
    if named_after_person and N == 2:
        hebrew = any("\u0590" <= ch <= "\u05ff" for ch in names[0] + names[1])
        title = ("%s ו%s" if hebrew else "%s & %s") % (names[0], names[1])

    hours = [0] * 24
    months = collections.defaultdict(lambda: [0] * N)
    pair = collections.Counter()
    laugh_n = [0] * len(LAUGHS)
    words = edited = 0
    prev = None
    gap_best = (0, None, None)
    for t, _, k0, m in rows:
        k = pos[k0]
        hours[t.hour] += 1
        months[t.strftime("%Y-%m")][k] += 1
        if prev:
            if prev[1] != k and 0 <= (t - prev[0]).total_seconds() <= REPLY_SECONDS:
                pair[(min(k, prev[1]), max(k, prev[1]))] += 1
            silent = (t.date() - prev[0].date()).days - 1
            if silent > gap_best[0]:
                gap_best = (silent, prev[0].date(), t.date())
        prev = (t, k)
        body = m["text"] or ""
        for tag in EDITED:
            if tag in body:
                body, edited = body.replace(tag, ""), edited + 1
        body = body.strip()
        if (
            not body
            or PLACEHOLDER.match(body)
            or (m["marked"] and body.endswith("omitted"))
        ):
            continue
        words += len(body.split())
        for j, fam in enumerate(LAUGHS):
            if fam[3].search(body):
                laugh_n[j] += 1

    total = len(rows)
    first, last = rows[0][0].date(), rows[-1][0].date()
    ym = []
    y, mo = first.year, first.month
    while (y, mo) <= (last.year, last.month):
        ym.append("%04d-%02d" % (y, mo))
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    month_rows = [months[s] for s in ym]
    month_tot = [sum(r) for r in month_rows]
    peak_m = max(range(len(ym)), key=lambda i: month_tot[i])
    peak_h = max(range(24), key=lambda h: hours[h])
    quiet_h = min(range(24), key=lambda h: hours[h])
    pairs = sorted(([p, q, n] for (p, q), n in pair.items()), key=lambda r: r[2])
    span_months = (last.year - first.year) * 12 + last.month - first.month

    if total < MIN_MESSAGES or len(ym) < MIN_MONTHS:
        die(
            "this chat is too small for the film: %s messages over %d months (needs %d messages and %d months)"
            % (fmt(total), len(ym), MIN_MESSAGES, MIN_MONTHS)
        )
    if not pairs:
        die(
            "nobody ever answered anybody within five minutes; there is no thread to draw"
        )

    gap = None
    if gap_best[0] >= GAP_MIN_DAYS:
        gap = {
            "from": ym.index(gap_best[1].strftime("%Y-%m")),
            "to": ym.index(gap_best[2].strftime("%Y-%m")),
            "days": gap_best[0],
        }
    lj = max(range(len(LAUGHS)), key=lambda j: laugh_n[j])
    laugh = {
        "n": laugh_n[lj],
        "word": LAUGHS[lj][0],
        "bit": LAUGHS[lj][1],
        "en": LAUGHS[lj][2],
    }

    story = {
        "v": 1,
        "title": tidy(title),
        "people": [{"name": names[i], "n": counts[rank[i]]} for i in range(N)],
        "total": total,
        "first": first.isoformat(),
        "last": last.isoformat(),
        "years": (last - first).days // 365,
        "spanMonths": span_months,
        "hours": hours,
        "peakH": peak_h,
        "quietH": quiet_h,
        "ym": ym,
        "months": month_rows,
        "peakM": peak_m,
        "peakMn": month_tot[peak_m],
        "gap": gap,
        "maxGapDays": gap_best[0],
        "pairs": pairs,
        "words": words,
        "books": words // WORDS_PER_BOOK,
        "laugh": laugh,
    }
    blob = json.dumps(story, ensure_ascii=False, separators=(",", ":"))
    # nothing that looks like a phone number, and nothing that could close a <script> tag, may leave here
    leak = [s for s in names + [story["title"]] if PHONE.search(s)]
    if leak or "</" in blob:
        die(
            "a name or the title still looks like a phone number or markup; fix it with --name / --title"
        )
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(blob)

    top = pairs[-1]
    others = len(groups) - N
    print("FACTS (every number in the film comes from this table)")
    print("  title        %s" % (story["title"] or "(none: pass --title)"))
    print(
        "  format       %s, dates read as %s"
        % (
            "iOS [brackets]" if shape[0] else "Android",
            {"dmy": "day/month/year", "mdy": "month/day/year", "ymd": "year/month/day"}[
                order
            ],
        )
    )
    whole = story["years"]
    print(
        "  span         %s to %s  (%s, %d months on the timeline)"
        % (
            first,
            last,
            "under a year" if whole < 1 else "%d year%s" % (whole, "" if whole == 1 else "s"),
            len(ym),
        )
    )
    print("  messages     %s by %d people" % (fmt(total), N))
    for p in story["people"]:
        print("      %-14s %s" % (p["name"], fmt(p["n"])))
    if others > 0:
        print(
            "  not drawn    %d other sender(s), %s messages (see --senders)"
            % (others, fmt(all_n - total))
        )
    print(
        "  busiest hour %02d:00 (%s)   quietest %02d:00 (%s)"
        % (peak_h, fmt(hours[peak_h]), quiet_h, fmt(hours[quiet_h]))
    )
    print("  peak month   %s (%s)" % (ym[peak_m], fmt(month_tot[peak_m])))
    if gap:
        print(
            "  torn page    %d silent days between %s and %s"
            % (gap["days"], gap_best[1], gap_best[2])
        )
    else:
        print(
            "  torn page    none (longest silence %d days; the film skips that beat)"
            % gap_best[0]
        )
    print(
        "  top thread   %s + %s, %s replies within 5 minutes (%d pairs in all)"
        % (names[top[0]], names[top[1]], fmt(top[2]), len(pairs))
    )
    print(
        "  words        %s  = %s%s"
        % (
            fmt(words),
            "%d books of %s words" % (story["books"], fmt(WORDS_PER_BOOK))
            if story["books"] >= 2
            else "one book of about %s pages" % fmt(max(1, words // 300)),
            "  (%d edit tags ignored)" % edited if edited else "",
        )
    )
    print("  laughs       %s messages with %s" % (fmt(laugh["n"]), laugh["word"]))
    if not story["title"]:
        print('NEEDS A TITLE  ask for one, then rerun with --title "Two Words"')
    elif not fits_cover(story["title"]):
        print(
            'TITLE TOO LONG  "%s" does not fit the cover (two lines of 14 letters at most): '
            'ask for a short one, then rerun with --title "Two Words"' % story["title"]
        )
    for g, h in twins:
        print(
            'SAME PERSON?  "%s" is now two people, shown as %s and %s. Ask. If it is one person on two phones, '
            'rerun with --name "%s=%s" added to merge them'
            % (g, labels[h], labels[g], h[1:], g)
        )
    unnamed = [n for n in names if n.startswith("?")]
    for n in phone_ids:
        if phone_ids[n] in unnamed:
            print(
                'NEEDS A NAME  %s is %s: ask who that is, then rerun with --name "%s=Their name"'
                % (phone_ids[n], mask(n), phone_ids[n])
            )
    print("wrote " + a.out)


if __name__ == "__main__":
    main()
