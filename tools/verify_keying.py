# -*- coding: utf-8 -*-
"""Independently verify the site's 148-item reverse-keyed list against IPIP's own key.

This is the one check nothing else in the project could make. Johnson's published dataset
ships items already recoded, so scoring it as-is validates his facet sums no matter which
items you call reversed -- undoing the recoding with the site's own list to check the list
is circular. The site's list is byte-identical to five-factor-e's, but that is the same
lineage (Johnson -> Kholia -> NeuroQuest), not an independent source.

IPIP's own published NEO Facets Key is independent: it lists, per facet, the item text
under "+ keyed" and "- keyed" headings. Matching by item text closes the loop.

Source: https://ipip.ori.org/newNEOFacetsKey.htm
"""
import difflib
import html
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

KEY_URL = "https://ipip.ori.org/newNEOFacetsKey.htm"
KEY_HTML = os.path.join(ipip.OUT, "newNEOFacetsKey.htm")

if not os.path.exists(KEY_HTML):
    import urllib.request
    print("fetching %s" % KEY_URL)
    os.makedirs(ipip.OUT, exist_ok=True)
    with urllib.request.urlopen(KEY_URL, timeout=30) as r:
        io.open(KEY_HTML, "w", encoding="utf-8").write(r.read().decode("utf-8", "replace"))

raw = io.open(KEY_HTML, encoding="utf-8", errors="replace").read()
text = re.sub(r"<[^>]+>", "\n", raw)
text = html.unescape(text)
text = text.replace("\u00a0", "\n").replace("\u0096", "-").replace("\u2013", "-").replace("\u2212", "-")

# facet headers look like "N1: ANXIETY (Alpha = .83)" or "E3: ASSERTIVENESS (.84)"
HEADER = re.compile(r"\b([NEOAC])([1-6]):\s*([A-Z][A-Z \-]*?)\s*\((?:Alpha\s*=\s*)?\.?\d+\)")
marks = [(m.start(), m.group(1), int(m.group(2)), m.group(3).strip()) for m in HEADER.finditer(text)]
print("facet sections found in the IPIP key: %d" % len(marks))
if len(marks) != 30:
    sys.exit("expected 30 facet sections; the page layout may have changed")

KEYED = re.compile(r"^\s*([+\-])\s*keyed\s*$", re.I)


def clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    return s


def norm(s):
    """text key for matching across sources"""
    s = s.lower().strip()
    s = re.sub(r"[^a-z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


ipip_items = {}          # norm(text) -> (facet, sign)
per_facet = {}
for i, (pos, dom, fno, name) in enumerate(marks):
    end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
    body = text[pos:end]
    body = body[body.index(")") + 1:]          # drop the header itself
    sign, plus, minus = None, [], []
    # page-footer navigation leaks into the last facet's block
    NAV = {"return to", "multiple constructs", "the ipip home page", "home page"}
    for line in body.split("\n"):
        line = clean(line)
        if not line or len(line) < 4:
            continue
        m = KEYED.match(line)
        if m:
            sign = "+" if m.group(1) == "+" else "-"
            continue
        if sign is None or line.lower().strip(".") in NAV:
            continue
        bucket = plus if sign == "+" else minus
        # long items wrap across lines in the source; a fragment that does not end in
        # sentence-final punctuation is a continuation, not a new item. A closing quote
        # counts as terminal -- 'Want everything to be "just right."' is a whole item.
        TERM = (".", '."', ".'", '.”', "?", "!", '?"', '!"')
        if bucket and not bucket[-1].rstrip().endswith(TERM):
            bucket[-1] = bucket[-1] + " " + line
        else:
            bucket.append(line)
    per_facet["%s%d" % (dom, fno)] = (name, plus, minus)
    for t in plus:
        ipip_items[norm(t)] = ("%s%d" % (dom, fno), "+")
    for t in minus:
        ipip_items[norm(t)] = ("%s%d" % (dom, fno), "-")

counts = {k: (len(v[1]), len(v[2])) for k, v in per_facet.items()}
bad = {k: v for k, v in counts.items() if sum(v) != 10}
print("facets whose + and - items do not sum to 10: %d %s" % (len(bad), bad if bad else ""))
print("total items parsed from the IPIP key: %d" % len(ipip_items))
print("of which '- keyed': %d" % sum(1 for v in ipip_items.values() if v[1] == "-"))

# ------------------------------------------------------------------ compare
data = ipip.site_data()
site_rev = set(data["reversed"])
LV = ["N", "E", "O", "A", "C"]

matched, unmatched, mismatches, facet_mismatch, fuzzy = 0, [], [], [], []
for item in data["items"]:
    qid, en = item["id"], item["en"]
    rec = ipip_items.get(norm(en))
    if rec is None:
        # the two sources differ on a few leading "Am " and on or/and; accept a very
        # close text match rather than leaving those four items unverified
        near = difflib.get_close_matches(norm(en), list(ipip_items), n=1, cutoff=0.90)
        if near:
            rec = ipip_items[near[0]]
            fuzzy.append((qid, en, near[0]))
        else:
            unmatched.append((qid, en))
            continue
    matched += 1
    ipip_facet, sign = rec
    site_says_reversed = qid in site_rev
    ipip_says_reversed = (sign == "-")
    if site_says_reversed != ipip_says_reversed:
        mismatches.append((qid, en, "site=%s ipip=%s" %
                           ("reversed" if site_says_reversed else "positive",
                            "reversed" if ipip_says_reversed else "positive")))
    # facet placement, using the site's interleave: slot (qid-1) % 30
    slot = (qid - 1) % 30
    site_facet = "%s%d" % (LV[slot % 5], slot // 5 + 1)
    if site_facet != ipip_facet:
        facet_mismatch.append((qid, en, site_facet, ipip_facet))

print("\n" + "=" * 72)
print("site items matched to an IPIP key item by text : %d / 300" % matched)
print("unmatched (text differs between sources)       : %d" % len(unmatched))
for qid, en in unmatched[:15]:
    print("     %3d  %s" % (qid, en))
print("\nKEYING mismatches (site vs IPIP)               : %d" % len(mismatches))
for qid, en, why in mismatches[:20]:
    print("     %3d  %-52s %s" % (qid, en[:52], why))
print("FACET-placement mismatches                     : %d" % len(facet_mismatch))
for qid, en, a, b in facet_mismatch[:15]:
    print("     %3d  %-46s site=%s ipip=%s" % (qid, en[:46], a, b))

print("\n" + "=" * 72)
if matched == 300 and not mismatches and not facet_mismatch:
    print("CONFIRMED: all 300 items matched IPIP's published key, the 148-item reversed")
    print("list agrees item-for-item, and every item sits in the facet IPIP assigns it.")
elif mismatches or facet_mismatch:
    print("DISAGREEMENT with the published key -- investigate before trusting any score.")
else:
    print("Partial: %d items could not be matched by text; the %d that matched all agree."
          % (len(unmatched), matched))

