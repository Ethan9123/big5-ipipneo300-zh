# -*- coding: utf-8 -*-
"""Lexical cross-check of the site's 148-item reversed list against the item text
the site itself ships.  Independent of the covariance analysis."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

NEG = re.compile(
    r"\b(don't|dont|do not|does not|dislike|dislikes|am not|is not|are not|never|"
    r"rarely|seldom|avoid|hate|can't|cannot|lack|refuse|reject|resent|neglect|"
    r"waste|worry|dread|fear|shirk|dodge)\b", re.I)


def main():
    d = ipip.site_data()
    rev = set(int(x) for x in d["reversed"])
    marked, unmarked = [], []
    for i in range(1, 301):
        en = d["items"][i - 1]["en"]
        if NEG.search(en):
            (marked if i in rev else unmarked).append(i)
    print("site reversed-list size: %d of 300" % len(rev))
    print("items whose English text contains an explicit negation/aversion marker: %d"
          % (len(marked) + len(unmarked)))
    print("  marked reversed on site : %d" % len(marked))
    print("  NOT marked reversed     : %d" % len(unmarked))
    for i in unmarked:
        j = (i - 1) % 30
        print("     %3d %s%d | %s" % (i, ipip.DOMAIN_ORDER[j % 5], j // 5 + 1,
                                      d["items"][i - 1]["en"]))
    no_marker = [i for i in sorted(rev) if not NEG.search(d["items"][i - 1]["en"])]
    print("reversed items with no lexical negation marker: %d of %d" % (len(no_marker), len(rev)))
    print("  first 10:", [d["items"][i - 1]["en"] for i in no_marker[:10]])


if __name__ == "__main__":
    main()
