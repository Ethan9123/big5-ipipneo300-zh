# -*- coding: utf-8 -*-
"""How stable is the site's low / average / high label?

The site cuts the percentile at 45 and 55.  Pushed back through the cubic that
band is only ~2.8 T points wide -- narrower than one standard error of
measurement for EVERY facet.  Quantify the retest label-flip rate.
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402


def phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def main():
    ts = np.linspace(25, 80, 110001)
    ps = ipip.pct_from_t(ts)
    t45 = float(ts[np.argmin(abs(ps - 45))])
    t55 = float(ts[np.argmin(abs(ps - 55))])
    half = (t55 - t45) / 2.0
    print("site label cuts: percentile 45 -> T=%.3f, percentile 55 -> T=%.3f" % (t45, t55))
    print("the whole 'average' band is %.3f T points wide (half-width %.3f)\n"
          % (t55 - t45, half))

    d = json.load(open(os.path.join(ipip.OUT, "psychometrics.json"), encoding="utf-8"))
    rows = []
    for f in d["reliability"]["facets"]:
        sem = 10.0 * math.sqrt(1.0 - f["alpha"])
        p_same = 2.0 * phi(half / sem) - 1.0          # true score dead centre at T=50
        # true score sitting exactly on the 55 cut: chance the label flips to 'average' or 'low'
        p_flip_at_cut = phi(0.0) + (1.0 - phi((t55 - t45) / sem))
        rows.append((f["alpha"], f["code"], f["en"], sem, half / sem, p_same, p_flip_at_cut))
    rows.sort()
    print("%-4s %-22s %6s %7s %8s %9s" % ("code", "facet", "alpha", "SEM_T", "band/SEM", "P(same)"))
    for a, code, en, sem, ratio, p_same, _ in rows:
        print("%-4s %-22s %6.4f %7.2f %8.2f %8.1f%%" % (code, en, a, sem, ratio, 100 * p_same))
    print()
    for dm in d["reliability"]["domains"]:
        sem = 10.0 * math.sqrt(1.0 - dm["alpha"])
        p_same = 2.0 * phi(half / sem) - 1.0
        print("DOMAIN %s alpha=%.4f SEM_T=%.2f band/SEM=%.2f P(labelled 'average' again)=%.1f%%"
              % (dm["domain"], dm["alpha"], sem, half / sem, 100 * p_same))

    best = max(r[5] for r in rows)
    worst = min(r[5] for r in rows)
    print("\nfacet P(same label) for a dead-centre-average respondent: %.1f%% .. %.1f%%"
          % (100 * worst, 100 * best))


if __name__ == "__main__":
    main()
