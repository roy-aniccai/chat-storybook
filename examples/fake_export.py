#!/usr/bin/env python3
"""Write a made-up WhatsApp export, for trying the skill without a real chat.

usage: python3 fake_export.py out.zip [--style android-us|android-eu|android-de|ios-us|ios-eu]
                              [--lang en|he] [--people 5] [--months 30] [--gap-days 0]
                              [--title "Sunday League"] [--phone] [--seed 7]

Everything in the output is invented: the names, the words and the numbers.
"""

import argparse
import datetime
import io
import random
import zipfile

NAMES = {
    "en": [
        "Maya Cohen",
        "Jonas Berg",
        "Priya Nair",
        "Leo Marsh",
        "Sam Okafor",
        "Ines Duarte",
        "Tom Hale",
        "Uma Reyes",
        "Kit Lowe",
    ],
    "he": ["מאיה", "יונתן", "שירה", "עומר", "נטע", "איתי", "הדס", "גיל", "רוני"],
}
WORDS = {
    "en": "ok so who is bringing the snacks tonight I thought we said eight no way that was last week fine see you there running late again save me a seat the game was wild did anyone book the pitch yes done great thanks coffee tomorrow maybe after work sounds good to me".split(),
    "he": "טוב אז מי מביא חטיפים הערב חשבתי שאמרנו בשמונה אין מצב זה היה בשבוע שעבר סבבה נתראה שם אני מאחר שוב תשמרו לי מקום המשחק היה מטורף מישהו הזמין מגרש כן סגור מעולה תודה קפה מחר אולי אחרי העבודה נשמע לי טוב".split(),
}
LAUGH = {"en": ["haha", "hahaha", "lol", "hahahaha"], "he": ["חחח", "חחחח", "חחחחחח"]}
PHONE = "+1 (555) 010-0142"  # 555-01xx is reserved for fiction


def stamp(t, style):
    if style == "android-us":
        return "%d/%d/%02d, %02d:%02d - " % (
            t.month,
            t.day,
            t.year % 100,
            t.hour,
            t.minute,
        )
    if style == "android-eu":
        return "%02d/%02d/%04d, %02d:%02d - " % (
            t.day,
            t.month,
            t.year,
            t.hour,
            t.minute,
        )
    if style == "android-de":
        return "%02d.%02d.%02d, %02d:%02d - " % (
            t.day,
            t.month,
            t.year % 100,
            t.hour,
            t.minute,
        )
    if style == "ios-us":
        return "[%d/%d/%02d, %d:%02d:%02d %s] " % (
            t.month,
            t.day,
            t.year % 100,
            t.hour % 12 or 12,
            t.minute,
            t.second,
            "AM" if t.hour < 12 else "PM",
        )
    return "[%02d/%02d/%04d, %02d:%02d:%02d] " % (
        t.day,
        t.month,
        t.year,
        t.hour,
        t.minute,
        t.second,
    )


def main():
    ap = argparse.ArgumentParser(description="write an invented WhatsApp export")
    ap.add_argument("out", help="a .zip (or .txt) to write")
    ap.add_argument(
        "--style",
        default="android-us",
        choices=["android-us", "android-eu", "android-de", "ios-us", "ios-eu"],
    )
    ap.add_argument("--lang", default="en", choices=["en", "he"])
    ap.add_argument("--people", type=int, default=5)
    ap.add_argument("--months", type=int, default=30)
    ap.add_argument(
        "--gap-days", type=int, default=0, help="one long silence in the middle"
    )
    ap.add_argument("--title", default=None)
    ap.add_argument(
        "--phone", action="store_true", help="one sender is an unsaved phone number"
    )
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    rnd = random.Random(a.seed)
    ios = a.style.startswith("ios")
    title = a.title or ("Sunday League" if a.lang == "en" else "ליגת יום ראשון")
    names = NAMES[a.lang][: max(2, min(a.people, len(NAMES[a.lang])))]
    if a.phone:
        names[-1] = PHONE
    weight = [1.0 / (i + 1.4) for i in range(len(names))]
    words, laughs = WORDS[a.lang], LAUGH[a.lang]

    # a long invented chat starts earlier, so it never runs into the future
    length = datetime.timedelta(days=int(a.months * 30.4))
    start = min(
        datetime.datetime(2021, 3, 14, 9, 0, 0),
        datetime.datetime(2026, 3, 14, 9, 0, 0) - length,
    )
    end = start + length
    gap0 = start + (end - start) * 0.45
    gap1 = gap0 + datetime.timedelta(days=a.gap_days)
    lines = []
    notice = "Messages and calls are end-to-end encrypted."
    lines.append(
        stamp(start, a.style) + ("%s: ‎%s" % (title, notice) if ios else notice)
    )

    day = start
    while day < end:
        day += datetime.timedelta(days=rnd.choice([1, 1, 1, 2, 3]))
        if a.gap_days and gap0 <= day < gap1:
            continue
        # a day is one or two bursts of conversation, busier in spring
        for _ in range(rnd.choice([1, 1, 2]) + (2 if day.month in (3, 4) else 0)):
            hour = rnd.choice([8, 9, 12, 13, 13, 18, 19, 20, 20, 20, 21, 21, 22, 23])
            t = day.replace(
                hour=hour, minute=rnd.randrange(60), second=rnd.randrange(60)
            )
            for _ in range(rnd.randrange(3, 14)):
                t += datetime.timedelta(seconds=rnd.randrange(8, 240))
                who = rnd.choices(names, weight)[0]
                roll = rnd.random()
                if roll < 0.06:
                    body = "‎image omitted" if ios else "<Media omitted>"
                elif roll < 0.16:
                    body = rnd.choice(laughs)
                elif roll < 0.19:
                    # a pasted note with a date inside: it must stay part of this message
                    body = (
                        " ".join(rnd.choices(words, k=5))
                        + "\n12/05/2021, 10:00 - "
                        + " ".join(rnd.choices(words, k=4))
                    )
                else:
                    body = " ".join(rnd.choices(words, k=rnd.randrange(2, 16)))
                    if roll > 0.97 and not ios:
                        body += " <This message was edited>"
                lines.append(stamp(t, a.style) + "%s: %s" % (who, body))

    text = "\n".join(lines) + "\n"
    if a.out.lower().endswith(".zip"):
        inner = "_chat.txt" if ios else "WhatsApp Chat with %s.txt" % title
        with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(inner, text)
            z.writestr("00000001-PHOTO.jpg", io.BytesIO(b"not a real photo").getvalue())
    else:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(
        "wrote %s: %d lines, %d senders, title '%s'"
        % (a.out, len(lines), len(names), title)
    )


if __name__ == "__main__":
    main()
