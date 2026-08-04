# -*- coding: utf-8 -*-
"""Chase down the 4 items that did not match, and the two facets that over-parsed."""
import difflib
import html
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

KEY_HTML = (r"C:\Users\kids1\AppData\Local\Temp\claude"
            r"\C--Users-kids1-Downloads-bigfive\3f3dea16-3b73-4559-8359-8360df8000b2"
            r"\scratchpad\newNEOFacetsKey.htm")
raw = io.open(KEY_HTML, encoding="utf-8", errors="replace").read()
text = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
text = text.replace("\u00a0", "\n").replace("\u0096", "-").replace("\u2013", "-")

HEADER = re.compile(r"\b([NEOAC])([1-6]):\s*([A-Z][A-Z \-]*?)\s*\((?:Alpha\s*=\s*)?\.?\d+\)")
marks = [(m.start(), m.group(1) + m.group(2)) for m in HEADER.finditer(text)]

sections = {}
for i, (pos, fac) in enumerate(marks):
    end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
    sections[fac] = text[pos:end]

print("=" * 74)
print("O6 与 C6 的原始段落（解析出 11 / 12 条，应为 10）")
print("=" * 74)
for fac in ("O6", "C6"):
    body = re.sub(r"\s*\n\s*", " | ", sections[fac]).strip()
    print("\n[%s] %s" % (fac, body[:900]))

# fuzzy-match the four unmatched items against every line in the key
def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", s.lower())).strip()


lines = sorted({re.sub(r"\s+", " ", l).strip() for l in text.split("\n")
                if 8 < len(l.strip()) < 90 and not HEADER.search(l)})
data = ipip.site_data()
rev = set(data["reversed"])
UNMATCHED = [58, 78, 88, 202]

print("\n" + "=" * 74)
print("4 条未匹配题目在 IPIP 键里的最近似行")
print("=" * 74)
for qid in UNMATCHED:
    en = next(it["en"] for it in data["items"] if it["id"] == qid)
    best = difflib.get_close_matches(en, lines, n=3, cutoff=0.5)
    slot = (qid - 1) % 30
    site_facet = "%s%d" % (["N", "E", "O", "A", "C"][slot % 5], slot // 5 + 1)
    print("\n#%d  site=%s  %s  [site: %s]"
          % (qid, site_facet, en, "reversed" if qid in rev else "positive"))
    if not best:
        print("     近似行：无")
    for b in best:
        # which facet section and which keying block does that line sit in?
        where, sign = "?", "?"
        for fac, body in sections.items():
            if b in re.sub(r"\s+", " ", body):
                where = fac
                idx = re.sub(r"\s+", " ", body).index(b)
                head = re.sub(r"\s+", " ", body)[:idx]
                sign = "-" if head.rfind("- keyed") > head.rfind("+ keyed") else "+"
                break
        print("     %.2f  [%s %s keyed]  %s"
              % (difflib.SequenceMatcher(None, en, b).ratio(), where, sign, b))
