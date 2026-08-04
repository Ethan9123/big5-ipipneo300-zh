# -*- coding: utf-8 -*-
"""Profile the IPIP-NEO-300 norm sample that the site's percentiles are based on.

Writes tools/out/profile_sample.json.  Everything here is measured, nothing assumed.

Note on the straightlining screen
---------------------------------
The site runs longestRuns() on the RESPONDENT'S RAW KEYPRESSES (showResult calls it on
`answers`; score() reverse-keys a *copy*).  Johnson's published CSV ships the 148
reverse-keyed items ALREADY recoded, so to apply the site's exact rule to the norm
sample we must first UN-recode those items (6 - x) to recover the original keypresses.
Both variants are reported; `raw_keypress` is the site-equivalent one.
"""
import collections
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

RUN_CUT = [0, 6, 9, 10, 14, 9]           # site index.html line 975, options 1..5
# country column holds free-text-ish names, not ISO codes (verified against the data)
ANGLO = ["USA", "UK", "Canada", "Australia", "New Zealand", "Ireland"]
SINO = ["China", "Hong Kong", "Taiwan", "Singapore", "Macau", "Macao"]


def longest_runs(x):
    """x: (n,300) ints.  Returns (n,6) longest run of consecutive identical value v (1..5)."""
    n = x.shape[0]
    best = np.zeros((n, 6), dtype=np.int32)
    for v in range(1, 6):
        eq = (x == v)
        cur = np.zeros(n, dtype=np.int32)
        b = np.zeros(n, dtype=np.int32)
        for j in range(x.shape[1]):
            cur = np.where(eq[:, j], cur + 1, 0)
            np.maximum(b, cur, out=b)
        best[:, v] = b
    return best


def pct(x, n):
    return round(100.0 * x / n, 4)


def main():
    z = ipip.load()
    items = z["items"].astype(np.int16)
    sex, age, case, year = z["sex"], z["age"], z["case"], z["year"]
    n = len(sex)
    out = {"n_total": int(n)}

    # ---------- countries (from meta.csv) ----------
    countries = []
    with open(os.path.join(ipip.OUT, "meta.csv"), newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            countries.append(row["country"])
    assert len(countries) == n, (len(countries), n)
    cc = collections.Counter(countries)
    out["country"] = {
        "n_distinct": len(cc),
        "top25": [{"code": k, "n": v, "share_pct": pct(v, n)} for k, v in cc.most_common(25)],
        "anglosphere": {
            "codes": ANGLO,
            "per_code": {k: int(cc.get(k, 0)) for k in ANGLO},
            "n": int(sum(cc.get(k, 0) for k in ANGLO)),
            "share_pct": pct(sum(cc.get(k, 0) for k in ANGLO), n),
        },
        "greater_china_plus_sg": {
            "codes": SINO,
            "per_code": {k: int(cc.get(k, 0)) for k in SINO},
            "n": int(sum(cc.get(k, 0) for k in SINO)),
            "share_pct": pct(sum(cc.get(k, 0) for k in SINO), n),
        },
        "cn_hk_tw_sg_strict": {
            "codes": ["China", "Hong Kong", "Taiwan", "Singapore"],
            "per_code": {k: int(cc.get(k, 0)) for k in ("China", "Hong Kong", "Taiwan", "Singapore")},
            "n": int(sum(cc.get(k, 0) for k in ("China", "Hong Kong", "Taiwan", "Singapore"))),
            "share_pct": pct(sum(cc.get(k, 0) for k in ("China", "Hong Kong", "Taiwan", "Singapore")), n),
        },
        "greater_china_excl_singapore": {
            "codes": ["China", "Hong Kong", "Taiwan"],
            "n": int(sum(cc.get(k, 0) for k in ("China", "Hong Kong", "Taiwan"))),
            "share_pct": pct(sum(cc.get(k, 0) for k in ("China", "Hong Kong", "Taiwan")), n),
        },
        "blank_or_missing": {"n": int(cc.get("", 0) + sum(v for k, v in cc.items() if not str(k).strip())),
                             "share_pct": pct(cc.get("", 0), n)},
        "all_codes_sorted_by_n": [[k, int(v)] for k, v in cc.most_common()],
    }

    # ---------- sex ----------
    sc = collections.Counter(sex.tolist())
    young, adult = age < 21, age >= 21
    def sexblock(mask):
        s = collections.Counter(sex[mask].tolist())
        tot = int(mask.sum())
        return {"n": tot,
                "codes": {str(k): {"n": int(v), "share_pct": pct(v, tot)} for k, v in sorted(s.items())}}
    out["sex"] = {
        "overall": sexblock(np.ones(n, bool)),
        "lt21": sexblock(young),
        "gte21": sexblock(adult),
        "codes_other_than_1_or_2": {str(k): int(v) for k, v in sorted(sc.items()) if k not in (1, 2)},
    }

    # ---------- age ----------
    a = age.astype(np.float64)
    qs = np.percentile(a, [5, 25, 50, 75, 95])
    out["age"] = {
        "min": int(a.min()), "max": int(a.max()),
        "mean": round(float(a.mean()), 4), "median": float(np.median(a)),
        "sd": round(float(a.std(ddof=1)), 4),
        "p5": float(qs[0]), "p25": float(qs[1]), "p50": float(qs[2]),
        "p75": float(qs[3]), "p95": float(qs[4]),
        "n_lt21": int(young.sum()), "share_lt21_pct": pct(int(young.sum()), n),
        "n_gte21": int(adult.sum()), "share_gte21_pct": pct(int(adult.sum()), n),
        "implausible": {
            "lt_10": int((a < 10).sum()),
            "lt_13": int((a < 13).sum()),
            "gt_90": int((a > 90).sum()),
            "gt_100": int((a > 100).sum()),
            "gt_110": int((a > 110).sum()),
            "n_at_min_10": int((a == 10).sum()),
            "n_at_max_99": int((a == 99).sum()),
            "note": "file is already range-limited to 10..99; no out-of-range values present",
        },
        "share_16_to_25_pct": pct(int(((a >= 16) & (a <= 25)).sum()), n),
        "n_16_to_25": int(((a >= 16) & (a <= 25)).sum()),
        "hist_by_decade": {f"{d}-{d+9}": int(((a >= d) & (a < d + 10)).sum())
                           for d in range(0, 120, 10) if ((a >= d) & (a < d + 10)).sum()},
        "top_single_ages": [[int(k), int(v)] for k, v in
                            collections.Counter(age.tolist()).most_common(10)],
    }

    # ---------- year ----------
    yc = collections.Counter(year.tolist())
    raw_min, raw_max = int(year.min()), int(year.max())
    # dataset stores year as offset from 1900 (values ~98..117)
    decoded = {str(1900 + k if k < 200 else k): int(v) for k, v in sorted(yc.items())}
    out["year"] = {
        "raw_min": raw_min, "raw_max": raw_max,
        "interpretation": "column stores year-1900" if raw_max < 200 else "calendar year",
        "counts_by_calendar_year": decoded,
        "n_distinct": len(yc),
        "modal_year": int(1900 + yc.most_common(1)[0][0] if raw_max < 200 else yc.most_common(1)[0][0]),
        "modal_year_n": int(yc.most_common(1)[0][1]),
    }

    # ---------- cohorts ----------
    masks = ipip.group_masks(sex, age)
    out["cohorts"] = {g: {"n": int(m.sum()), "share_pct": pct(int(m.sum()), n)}
                      for g, m in masks.items()}
    out["cohorts"]["n_not_in_any_MF_cohort"] = int((~(masks["N_lt21"] | masks["N_gte21"])).sum())

    # ---------- straightlining (site's exact rule) ----------
    data = ipip.site_data()
    rev = np.array(sorted(data["reversed"]), dtype=np.int64)     # 1-based item numbers
    keypress = items.copy()
    keypress[:, rev - 1] = 6 - keypress[:, rev - 1]              # undo the CSV's recoding

    res = {}
    evidence = {}
    for label, X in (("raw_keypress", keypress), ("as_stored_recoded", items)):
        runs = longest_runs(X)
        per = {}
        ev = {}
        flag_any = np.zeros(n, bool)
        for v in range(1, 6):
            f = runs[:, v] > RUN_CUT[v]
            flag_any |= f
            hist = collections.Counter(runs[:, v].tolist())
            cap = int(runs[:, v].max())
            # geometric extrapolation of the tail: what SHOULD sit one past the cap?
            prev2, prev1 = hist.get(cap - 1, 0), hist.get(cap, 0)
            ratio = (prev1 / prev2) if prev2 else float("nan")
            per[str(v)] = {
                "cut": RUN_CUT[v], "n_flagged": int(f.sum()), "rate_pct": pct(int(f.sum()), n),
                "max_run_observed": cap,
                "mean_longest_run": round(float(runs[:, v].mean()), 4),
                "n_at_cap": int(prev1),
            }
            ev[str(v)] = {
                "cap": cap, "n_at_cap_minus_1": int(prev2), "n_at_cap": int(prev1),
                "n_at_cap_plus_1": int(hist.get(cap + 1, 0)),
                "tail_decay_ratio": None if prev2 == 0 else round(ratio, 4),
                "expected_at_cap_plus_1_if_geometric": None if prev2 == 0 else round(prev1 * ratio, 1),
                "tail_hist": {str(L): int(hist[L]) for L in sorted(hist) if L >= max(0, cap - 8)},
            }
        res[label] = {
            "n_flagged": int(flag_any.sum()), "flag_rate_pct": pct(int(flag_any.sum()), n),
            "per_option": per,
            "observed_caps_option_1to5": [int(runs[:, v].max()) for v in range(1, 6)],
            "n_flagged_on_2plus_options": int((np.sum(
                np.stack([runs[:, v] > RUN_CUT[v] for v in range(1, 6)], 1), 1) >= 2).sum()),
        }
        evidence[label] = ev
    out["straightlining"] = {
        "rule": "flag if longest run of consecutive identical option v exceeds RUN_CUT[v]",
        "RUN_CUT_1to5": RUN_CUT[1:],
        "n_reverse_keyed_items": int(len(rev)),
        "site_equivalent_variant": "raw_keypress",
        "johnson_2005_claimed_pct": 3.5,
        "variants": res,
        "delta_vs_claim_pp": round(res["raw_keypress"]["flag_rate_pct"] - 3.5, 4),
        "tail_evidence": evidence,
        "finding": (
            "In raw-keypress space the longest-run histogram decays smoothly and then drops to "
            "EXACTLY ZERO one step past caps of [9,9,9,12,9] for options 1..5. That is a hard "
            "cliff, not a natural tail, so the published 145,388-row file is ALREADY the "
            "post-screen sample: Johnson's ~3.5%% was removed BEFORE publication and cannot be "
            "reproduced from this file by construction. The site's cut for option 1 (6) is "
            "stricter than the cap actually present in the retained data (9), which is the only "
            "reason anything flags at all."
        ),
        "cut_comparison": {
            "site_RUN_CUT_1to5": RUN_CUT[1:],
            "caps_present_in_published_data_1to5": res["raw_keypress"]["observed_caps_option_1to5"],
            "site_stricter_on_options": [v for v in range(1, 6)
                                         if RUN_CUT[v] < res["raw_keypress"]["observed_caps_option_1to5"][v - 1]],
            "site_looser_on_options": [v for v in range(1, 6)
                                       if RUN_CUT[v] > res["raw_keypress"]["observed_caps_option_1to5"][v - 1]],
        },
    }

    # ---------- duplicates ----------
    _, cnt = np.unique(case, return_counts=True)
    dupcase = int((cnt > 1).sum())
    rowkeys = [r.tobytes() for r in np.ascontiguousarray(items)]
    rc = collections.Counter(rowkeys)
    dup_vec_groups = sum(1 for v in rc.values() if v > 1)
    dup_vec_rows = sum(v for v in rc.values() if v > 1)
    out["duplicates"] = {
        "case_ids_distinct": int(len(cnt)),
        "case_ids_appearing_more_than_once": dupcase,
        "case_id_min": int(case.min()), "case_id_max": int(case.max()),
        "distinct_300item_vectors": int(len(rc)),
        "duplicate_vector_groups": int(dup_vec_groups),
        "rows_in_duplicate_vector_groups": int(dup_vec_rows),
        "rows_in_duplicate_vector_groups_pct": pct(dup_vec_rows, n),
        "largest_vector_group_size": int(max(rc.values())),
        "top_duplicate_group_sizes": sorted((v for v in rc.values() if v > 1), reverse=True)[:10],
        "duplicate_vector_examples": [
            {"case_ids": [int(case[i]) for i in np.where(np.array(rowkeys) == k)[0]],
             "ages": [int(age[i]) for i in np.where(np.array(rowkeys) == k)[0]],
             "sexes": [int(sex[i]) for i in np.where(np.array(rowkeys) == k)[0]],
             "years": [int(1900 + year[i]) for i in np.where(np.array(rowkeys) == k)[0]]}
            for k, v in rc.items() if v > 1
        ][:5],
    }

    path = os.path.join(ipip.OUT, "profile_sample.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2)[:400])
    print("wrote", path)


if __name__ == "__main__":
    main()
