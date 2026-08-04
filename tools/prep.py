# -*- coding: utf-8 -*-
"""Load IPIP300-SCORES.csv and cache scored arrays as out/scored.npz.

The dataset ships reverse-keyed items already recoded, so items are summed as-is.
See ipip.py for the verification that establishes this.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

ITEM_COLS = ["i%d" % i for i in range(1, 301)]
META_COLS = ["case", "sex", "age", "country", "sec", "min", "hour", "date", "month", "year"]
DOMAIN_SCORE_COLS = {"O": "openness", "C": "conscientiousness", "E": "extraversion",
                     "A": "agreeableness", "N": "neuroticism"}
FACET_COLS = [
    "facet_imagination", "facet_artistic_interests", "facet_emotionality",
    "facet_adventurousness", "facet_intellect", "facet_liberalism",
    "facet_self_efficacy", "facet_orderliness", "facet_dutifulness",
    "facet_achievement_striving", "facet_self_discipline", "facet_cautiousness",
    "facet_friendliness", "facet_gregariousness", "facet_assertiveness",
    "facet_activity_level", "facet_excitement_seeking", "facet_cheerfulness",
    "facet_trust", "facet_morality", "facet_altruism", "facet_cooperation",
    "facet_modesty", "facet_sympathy",
    "facet_anxiety", "facet_anger", "facet_depression", "facet_self_consciousness",
    "facet_immoderation", "facet_vulnerability",
]


def main():
    os.makedirs(ipip.OUT, exist_ok=True)
    usecols = META_COLS + ITEM_COLS + list(DOMAIN_SCORE_COLS.values()) + FACET_COLS
    df = pd.read_csv(ipip.CSV, usecols=usecols, low_memory=False)
    print("rows: %d" % len(df))

    items = df[ITEM_COLS].to_numpy(dtype=np.int16)
    print("item values present: %s" % sorted(set(np.unique(items).tolist())))

    facet_raw, domain_raw = ipip.facet_and_domain_raw(items.astype(np.int32))

    np.savez_compressed(
        os.path.join(ipip.OUT, "scored.npz"),
        items=items, facet_raw=facet_raw, domain_raw=domain_raw,
        sex=df["sex"].to_numpy(np.int8), age=df["age"].to_numpy(np.int16),
        case=df["case"].to_numpy(np.int64),
        sec=df["sec"].to_numpy(np.int16), minute=df["min"].to_numpy(np.int16),
        hour=df["hour"].to_numpy(np.int16), year=df["year"].to_numpy(np.int16),
        ref_domain_pct=df[[DOMAIN_SCORE_COLS[k] for k in ipip.DOMAIN_ORDER]].to_numpy(np.float64),
        ref_facet_pct=df[FACET_COLS].to_numpy(np.float64),
    )
    df[["case", "country", "sex", "age", "year"]].to_csv(
        os.path.join(ipip.OUT, "meta.csv"), index=False)

    # sanity: reproduce the CSV's own domain percentiles
    data = ipip.site_data()
    masks = ipip.group_masks(df["sex"].to_numpy(), df["age"].to_numpy())
    pred = np.full((len(df), 5), np.nan)
    for g in ("M_lt21", "M_gte21", "F_lt21", "F_gte21"):
        ns, mask = data["norms"][g]["ns"], masks[g]
        for d, key in enumerate(ipip.DOMAIN_ORDER):
            t = 10.0 * (domain_raw[mask, d] - ns[ipip.DOMAIN_INDEX[key]]) / ns[ipip.DOMAIN_INDEX[key] + 5] + 50.0
            pred[mask, d] = ipip.pct_from_t(t)
    ref = df[[DOMAIN_SCORE_COLS[k] for k in ipip.DOMAIN_ORDER]].to_numpy(np.float64)
    ok = ~np.isnan(pred[:, 0])
    print("reproduction of CSV domain percentiles: max abs err = %.10f over %d rows"
          % (np.abs(pred[ok] - ref[ok]).max(), ok.sum()))
    print("wrote out/scored.npz and out/meta.csv")


if __name__ == "__main__":
    main()
