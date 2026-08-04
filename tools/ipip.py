# -*- coding: utf-8 -*-
"""Shared helpers for analysing the IPIP-NEO-300 norm sample against the deployed site.

IMPORTANT — keying
------------------
Johnson's published dataset (IPIP300-SCORES.csv) ships the 148 reverse-keyed items
ALREADY recoded (1=5, 2=4, 4=2, 5=1).  Verified: scoring the columns as-is reproduces
the CSV's own percentile columns with max abs error 0.000000 over 145,388 x 5 values;
applying the site's `6 - x` a second time destroys it (mean abs error 32.8).

So: dataset items are used AS-IS.  A live respondent's raw answers still need
`6 - x` applied, which is what the site does.
"""
import io
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SITE = os.path.join(os.path.dirname(HERE), "site", "index.html")
CSV = os.path.join(
    os.path.expanduser("~"), ".cache", "kagglehub", "datasets", "edersoncorbari",
    "ipip-neo-big-five-personality-300-item-version", "versions", "1", "IPIP300-SCORES.csv",
)

DOMAIN_ORDER = ["N", "E", "O", "A", "C"]          # facet slot j -> DOMAIN_ORDER[j % 5]
OCEAN = ["O", "C", "E", "A", "N"]
CUB = [210.335958661391, 16.7379362643389, 0.405936512733332, 0.00270624341822222]
T_MIN, T_MAX = 32, 73
GROUPS = ["M_lt21", "M_gte21", "F_lt21", "F_gte21", "N_lt21", "N_gte21"]

# ns vector layout (length 71), matching five-factor-e:
#   [0]      pad
#   [1..5]   domain means  N,E,O,A,C
#   [6..10]  domain SDs    N,E,O,A,C
#   [11..16] N facet means      [17..22] N facet SDs
#   [23..28] E facet means      [29..34] E facet SDs
#   [35..40] O facet means      [41..46] O facet SDs
#   [47..52] A facet means      [53..58] A facet SDs
#   [59..64] C facet means      [65..70] C facet SDs
FACET_OFFSET = {"N": (10, 16), "E": (22, 28), "O": (34, 40), "A": (46, 52), "C": (58, 64)}
DOMAIN_INDEX = {"N": 1, "E": 2, "O": 3, "A": 4, "C": 5}

FACET_RAW_MIN, FACET_RAW_MAX = 10, 50           # 10 items x 1..5
DOMAIN_RAW_MIN, DOMAIN_RAW_MAX = 60, 300        # 60 items x 1..5


def site_data():
    """The DATA constant, parsed straight out of the deployed page."""
    html = io.open(SITE, encoding="utf-8").read()
    start = html.index("const DATA = ") + len("const DATA = ")
    end = html.index("};\n", start) + 1
    return json.loads(html[start:end])


def facet_slot(domain, facet_no):
    """facet_no is 1..6; returns the 0..29 slot index used by the item interleave."""
    return (facet_no - 1) * 5 + DOMAIN_ORDER.index(domain)


def facet_items(slot):
    """0-based item column indices feeding facet `slot` (0..29)."""
    return [i * 30 + slot for i in range(10)]


def cubic(t):
    t = np.asarray(t, dtype=np.float64)
    return CUB[0] - CUB[1] * t + CUB[2] * t ** 2 - CUB[3] * t ** 3


def pct_from_t(t):
    """The site's T -> percentile map: cubic polynomial with hard rails at T<32 / T>73."""
    t = np.asarray(t, dtype=np.float64)
    p = cubic(t)
    p = np.where(t < T_MIN, 1.0, p)
    p = np.where(t > T_MAX, 99.0, p)
    return p


def load():
    """Load the cached scored arrays produced by prep.py."""
    z = np.load(os.path.join(OUT, "scored.npz"), allow_pickle=False)
    return {k: z[k] for k in z.files}


def group_masks(sex, age):
    """The six norm cohorts.  N_* pools the M and F samples (the site averages M/F norms)."""
    m, f = sex == 1, sex == 2
    young, adult = age < 21, age >= 21
    return {
        "M_lt21": m & young, "M_gte21": m & adult,
        "F_lt21": f & young, "F_gte21": f & adult,
        "N_lt21": (m | f) & young, "N_gte21": (m | f) & adult,
    }


def facet_and_domain_raw(items):
    """items: (N,300) int array of 1..5, ALREADY reverse-keyed."""
    n = len(items)
    facet = np.zeros((n, 30), dtype=np.int32)
    for j in range(30):
        facet[:, j] = items[:, facet_items(j)].sum(axis=1)
    domain = np.zeros((n, 5), dtype=np.int32)          # ordered N,E,O,A,C
    for d in range(5):
        domain[:, d] = facet[:, [j for j in range(30) if j % 5 == d]].sum(axis=1)
    return facet, domain


def scale_index():
    """Canonical ordering of the 35 scales: 5 domains then 30 facets, grouped by domain."""
    out = [("domain", k, None) for k in DOMAIN_ORDER]
    for k in DOMAIN_ORDER:
        for f in range(1, 7):
            out.append(("facet", k, f))
    return out
