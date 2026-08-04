# -*- coding: utf-8 -*-
"""Half-width punctuation inside Chinese prose reads as sloppy. Measure it, then fix it.

Only convert punctuation that sits between CJK characters -- an ASCII comma inside
"IPIP-NEO-300" or a decimal point in "47.2%" must be left alone.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

RAW = os.path.join(ipip.OUT, "profiles_raw.json")
SHIP = os.path.join(ipip.OUT, "profiles_ordered.json")
CJK = r"一-鿿　-〿＀-￯"

# half-width -> full-width, applied only when flanked by CJK
PAIRS = [(",", "，"), (";", "；"), (":", "："), ("!", "！"), ("?", "？")]
FIELDS_STR = ["lead", "summary", "life", "friends", "love", "work"]
FIELDS_LIST = ["pros", "cons", "practice"]

profiles = json.load(io.open(RAW, encoding="utf-8"))


def count_bad(text):
    n = 0
    for a, _ in PAIRS:
        n += len(re.findall(r"(?<=[%s])%s(?=[%s])" % (CJK, re.escape(a), CJK), text))
    # a full stop between CJK chars
    n += len(re.findall(r"(?<=[%s])\.(?=[%s])" % (CJK, CJK), text))
    # straight quotes around CJK
    n += len(re.findall(r'"[^"]*[%s][^"]*"' % CJK, text))
    return n


def fix(text):
    # Quotes FIRST: 「」 are themselves CJK-range characters, so converting them first
    # lets the punctuation pass below see CJK on both sides of a comma that follows a
    # closing quote. Doing it the other way round leaves "…",而 unconverted.
    text = re.sub(r'"([^"]*[%s][^"]*)"' % CJK, r"「\1」", text)
    for a, b in PAIRS:
        text = re.sub(r"(?<=[%s])%s(?=[%s])" % (CJK, re.escape(a), CJK), b, text)
    text = re.sub(r"(?<=[%s])\.(?=[%s])" % (CJK, CJK), "。", text)
    # trailing half-width comma/period at end of a field
    text = re.sub(r"(?<=[%s]),$" % CJK, "，", text)
    text = re.sub(r"(?<=[%s])\.$" % CJK, "。", text)
    return text


def walk(p, fn):
    total = 0
    for f in FIELDS_STR:
        total += fn(p, f, None)
    for f in FIELDS_LIST:
        for i in range(len(p[f])):
            total += fn(p, f, i)
    return total


def counter(p, f, i):
    return count_bad(p[f] if i is None else p[f][i])


before = sum(walk(p, counter) for p in profiles)
affected = sum(1 for p in profiles if walk(p, counter) > 0)
print("half-width punctuation inside Chinese prose")
print("  occurrences : %d" % before)
print("  profiles hit: %d / 243 (%.1f%%)" % (affected, 100.0 * affected / 243))

if "--fix" not in sys.argv:
    print("\nsamples:")
    shown = 0
    for p in profiles:
        for f in FIELDS_STR:
            if count_bad(p[f]) and shown < 6:
                print("  [%s %s] %s" % (p["cell"], f, p[f][:78]))
                shown += 1
    print("\nrun with --fix to convert")
    sys.exit(0)


def fixer(p, f, i):
    if i is None:
        old = p[f]; p[f] = fix(old); return 0 if old == p[f] else 1
    old = p[f][i]; p[f][i] = fix(old); return 0 if old == p[f][i] else 1


changed = sum(walk(p, fixer) for p in profiles)
after = sum(walk(p, counter) for p in profiles)
print("\nfields changed  : %d" % changed)
print("remaining bad   : %d" % after)

io.open(RAW, "w", encoding="utf-8").write(json.dumps(profiles, ensure_ascii=False, indent=1))
ship = [{k: v for k, v in p.items() if k != "cell"} for p in profiles]
io.open(SHIP, "w", encoding="utf-8").write(json.dumps(ship, ensure_ascii=False, separators=(",", ":")))
print("rewrote profiles_raw.json and profiles_ordered.json")
