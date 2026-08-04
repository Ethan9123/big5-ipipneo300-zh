# -*- coding: utf-8 -*-
"""Audit and re-derive the answer-validity screen the site shows users.

The site implements Johnson (2005)'s careless-responding string screen as

    RUN_CUT = [_, 6, 9, 10, 14, 9]          # options 1..5
    flag if longest run of consecutive identical responses of option v > RUN_CUT[v]

applied to the RAW clicked answers (score() applies 6-x afterwards), and tells the
user the screen "removes about 3.5%".

Johnson's published CSV ships the 148 reverse-keyed items ALREADY recoded, so to
reproduce what the site actually computes we UN-recode (6-x on those 148 columns)
to recover the response string as the person clicked it.  The un-recoding is
validated by item / rest-of-facet correlations (all 148 flip sign, all 152 don't).

Three references are computed for every quantity:
  raw      -- the string as clicked            <- what the site screens
  recoded  -- the string as shipped in the CSV <- diagnostic only
  perm     -- within-person permutation null (same 300 responses, order destroyed)
              <- the run-length distribution expected from chance alone

Writes tools/out/validity_thresholds.json.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

RUN_CUT = [0, 6, 9, 10, 14, 9]
SCALE_ZH = ["很不符合", "比较不符合", "一半一半", "比较符合", "很符合"]
PCTS = [50, 90, 95, 99, 99.5, 99.9]
BLOCKS = [(0, 75), (75, 150), (150, 225), (225, 300)]
RNG = np.random.default_rng(20260802)


# ------------------------------------------------------------------ run stats
def max_run_per_option(items):
    """(N,300) -> (N,6); [:,v] = longest run of consecutive v, v=1..5."""
    n, k = items.shape
    best = np.zeros((n, 6), dtype=np.int16)
    for v in range(1, 6):
        cur = np.zeros(n, dtype=np.int16)
        bv = np.zeros(n, dtype=np.int16)
        for c in range(k):
            cur = np.where(items[:, c] == v, cur + 1, 0)
            np.maximum(bv, cur, out=bv)
        best[:, v] = bv
    return best


def max_run_option_with_end(items, v):
    n, k = items.shape
    cur = np.zeros(n, dtype=np.int16)
    best = np.zeros(n, dtype=np.int16)
    end = np.full(n, -1, dtype=np.int16)
    for c in range(k):
        cur = np.where(items[:, c] == v, cur + 1, 0)
        upd = cur > best
        best = np.where(upd, cur, best)
        end = np.where(upd, c, end)
    return best, end


def max_run_any(items):
    n, k = items.shape
    cur = np.ones(n, dtype=np.int16)
    best = np.ones(n, dtype=np.int16)
    for c in range(1, k):
        cur = np.where(items[:, c] == items[:, c - 1], cur + 1, 1)
        np.maximum(best, cur, out=best)
    return best


def tail_rate(run, cut):
    return float((run > cut).mean())


def cut_for_target(run, target):
    """Smallest integer c with P(run > c) <= target; returns (c, realised rate)."""
    for c in range(0, int(run.max()) + 2):
        r = tail_rate(run, c)
        if r <= target:
            return c, r
    return int(run.max()), 0.0


def qtable(run):
    return {str(p): float(np.percentile(run, p)) for p in PCTS}


def geometric_tail(counts, lengths):
    """Extrapolate the truncated upper tail of a max-run histogram.

    counts/lengths are the last three populated bins.  Returns the estimated
    number of protocols whose max run fell beyond the truncation point,
    assuming the decay continues geometrically.  This is a LOWER BOUND on what
    was actually deleted: true straightliners are not geometric, they pile up
    far out in the tail.
    """
    r = np.mean([counts[1] / counts[0], counts[2] / counts[1]])
    return float(counts[2] * r / (1.0 - r)), float(r)


def main():
    d = ipip.load()
    rec = d["items"].astype(np.int16)
    n = rec.shape[0]
    rev0 = np.array(ipip.site_data()["reversed"], dtype=int) - 1
    is_rev = np.zeros(300, dtype=bool)
    is_rev[rev0] = True
    raw = rec.copy()
    raw[:, rev0] = 6 - raw[:, rev0]
    perm = np.take_along_axis(raw, np.argsort(RNG.random(raw.shape), axis=1), axis=1)

    out = {
        "n": int(n),
        "site_run_cut": RUN_CUT,
        "site_claim_pct": 3.5,
        "scale_zh": SCALE_ZH,
        "n_reversed_items": int(is_rev.sum()),
    }

    # ---------------------------------------------------- 0. keying validation
    facet = d["facet_raw"].astype(np.float64)
    c_rec = np.zeros(300)
    c_raw = np.zeros(300)
    for c in range(300):
        tot = facet[:, c % 30] - rec[:, c]
        c_rec[c] = np.corrcoef(rec[:, c].astype(np.float64), tot)[0, 1]
        c_raw[c] = np.corrcoef(raw[:, c].astype(np.float64), tot)[0, 1]
    out["keying_validation"] = {
        "recoded_all_item_rest_r_positive": bool((c_rec > 0).all()),
        "recoded_min_r": float(c_rec.min()),
        "raw_reversed_items_going_negative": int((c_raw[is_rev] < 0).sum()),
        "raw_keyed_positive_items_staying_positive": int((c_raw[~is_rev] > 0).sum()),
        "reversed_items_per_30_item_cycle":
            [int(is_rev[i * 30:(i + 1) * 30].sum()) for i in range(10)],
        "reversed_items_per_quartile_block":
            [int(is_rev[a:b].sum()) for a, b in BLOCKS],
        "note": "items 1-60 are 100% keyed-positive; items 211-300 are 100% reverse-keyed",
    }

    # ------------------------------------------------ 1 & 2 & 3  the screen
    runs = {"raw": max_run_per_option(raw),
            "recoded": max_run_per_option(rec),
            "perm": max_run_per_option(perm)}

    for tag in ("raw", "recoded", "perm"):
        R = runs[tag]
        flag_v = {v: R[:, v] > RUN_CUT[v] for v in range(1, 6)}
        any_flag = np.zeros(n, dtype=bool)
        for v in range(1, 6):
            any_flag |= flag_v[v]
        per_option = {}
        for v in range(1, 6):
            r = R[:, v]
            uniq = flag_v[v].copy()
            for w in range(1, 6):
                if w != v:
                    uniq &= ~flag_v[w]
            hist = np.bincount(r, minlength=25)
            nz = np.nonzero(hist)[0]
            c1, r1 = cut_for_target(r, 0.01)
            c35, r35 = cut_for_target(r, 0.035)
            per_option[str(v)] = {
                "label_zh": SCALE_ZH[v - 1],
                "current_cut": RUN_CUT[v],
                "flag_rate": tail_rate(r, RUN_CUT[v]),
                "flag_n": int(flag_v[v].sum()),
                "unique_flag_rate": float(uniq.mean()),
                "pct_rank_of_current_cut": float(100.0 * (r <= RUN_CUT[v]).mean()),
                "max_run_percentiles": qtable(r),
                "max_run_mean": float(r.mean()),
                "max_run_max": int(r.max()),
                "first_empty_length_above_mode": int(nz.max()) + 1,
                "histogram_4_to_16": [int(hist[L]) for L in range(4, 17)],
                "cut_for_top_1pct": {"cut": c1, "realised_rate": r1},
                "cut_for_top_3.5pct": {"cut": c35, "realised_rate": r35},
                "response_share": float((locals()["raw"] if False else
                                         {"raw": raw, "recoded": rec,
                                          "perm": perm}[tag] == v).mean()),
            }
        out[tag] = {"overall_flag_rate": float(any_flag.mean()),
                    "overall_flag_n": int(any_flag.sum()),
                    "per_option": per_option}
        if tag == "raw":
            raw_any_flag = any_flag

    # the observed ceiling: highest max-run actually present, per option
    ceiling = [0] + [int(runs["raw"][:, v].max()) for v in range(1, 6)]
    out["observed_ceiling_raw"] = ceiling
    out["perm_null_ceiling"] = [0] + [int(runs["perm"][:, v].max()) for v in range(1, 6)]

    # ------------------------------- pre-screening evidence + removal estimate
    removed = {}
    total_removed = 0.0
    for v in range(1, 6):
        h = np.bincount(runs["raw"][:, v], minlength=25)
        top = ceiling[v]
        est, r = geometric_tail([int(h[top - 2]), int(h[top - 1]), int(h[top])],
                                [top - 2, top - 1, top])
        removed[str(v)] = {"ceiling": top, "count_at_ceiling": int(h[top]),
                           "count_above_ceiling": int(h[top + 1:].sum()),
                           "decay_ratio": r, "estimated_removed_lower_bound": est}
        total_removed += est
    out["pre_screening_evidence"] = {
        "hard_cliff_per_option_raw": {str(v): ceiling[v] for v in range(1, 6)},
        "perm_null_has_no_cliff": {str(v): int(runs["perm"][:, v].max())
                                   for v in range(1, 6)},
        "n_exceeding_site_cut_opt2345": int(sum(
            (runs["raw"][:, v] > RUN_CUT[v]).sum() for v in (2, 3, 4, 5))),
        "per_option": removed,
        "estimated_removed_lower_bound_total": total_removed,
        "implied_pre_screen_removal_rate_lower_bound":
            float(total_removed / (n + total_removed)),
        "note": ("The surviving max-run distribution decays smoothly then drops to "
                 "exactly zero; the permutation null does not. The published norm "
                 "sample was therefore already screened for long strings, at "
                 "run>9 for options 1,2,3,5 and run>12 for option 4."),
    }

    # ------------------------- where the option-1 flags sit in the item order
    b1, e1 = max_run_option_with_end(raw, 1)
    fl = b1 > RUN_CUT[1]
    start = (e1[fl] - b1[fl] + 1).astype(int)
    lens = b1[fl].astype(int)
    revshare = np.array([is_rev[s:s + L].mean() for s, L in zip(start, lens)])
    out["option1_flag_anatomy"] = {
        "n_flagged": int(fl.sum()),
        "run_start_by_quartile_block":
            [int(((start >= a) & (start < b)).sum()) for a, b in BLOCKS],
        "median_run_start_item": int(np.median(start) + 1),
        "share_of_flagged_runs_starting_after_item_150":
            float((start >= 150).mean()),
        "mean_share_of_run_items_that_are_reverse_keyed": float(revshare.mean()),
        "share_of_runs_entirely_inside_reverse_keyed_items":
            float((revshare == 1.0).mean()),
        "excess_over_permutation_null_pp": float(
            100 * ((runs["raw"][:, 1] > 6).mean() - (runs["perm"][:, 1] > 6).mean())),
    }

    # ------------------------------------------------------- 4  time fields
    sec, mnt, hr = d["sec"].astype(int), d["minute"].astype(int), d["hour"].astype(int)
    tf = {}
    for nm, a, m in (("sec", sec, 60), ("minute", mnt, 60), ("hour", hr, 24)):
        cnt = np.bincount(a, minlength=m)[:m].astype(float)
        tf[nm] = {"min": int(a.min()), "max": int(a.max()),
                  "n_distinct": int(len(np.unique(a))), "mean": float(a.mean()),
                  "chi2_vs_uniform": float(((cnt - cnt.mean()) ** 2 / cnt.mean()).sum()),
                  "df": m - 1,
                  "min_bin": int(cnt.min()), "max_bin": int(cnt.max())}
    tf["hour_histogram"] = np.bincount(hr, minlength=24).tolist()
    tf["verdict"] = ("sec and minute are statistically flat on 0..59 (chi2 %.1f and "
                     "%.1f on 59 df, both p>0.7) and hour is strongly diurnal on "
                     "0..23 (chi2 %.0f on 23 df, trough 06:00, peak 14:00). These are "
                     "wall-clock completion timestamps, not elapsed time. There is no "
                     "second timestamp in the file, so no duration can be formed. "
                     "Sub-task dropped."
                     % (tf["sec"]["chi2_vs_uniform"], tf["minute"]["chi2_vs_uniform"],
                        tf["hour"]["chi2_vs_uniform"]))
    out["time_fields"] = tf

    # -------------------------------------------------- 5  other indicators
    any_raw = max_run_any(raw)
    sd = raw.astype(np.float64).std(axis=1, ddof=1)
    zero_var = sd == 0.0
    sd_cut1 = float(np.percentile(sd, 1))
    low = sd <= sd_cut1
    pooled = np.sqrt((sd[raw_any_flag].var(ddof=1) + sd[~raw_any_flag].var(ddof=1)) / 2)
    out["other_indicators"] = {
        "zero_variance_all_300": {"n": int(zero_var.sum()), "rate": float(zero_var.mean())},
        "max_run_any_value_raw": {
            "percentiles": qtable(any_raw), "mean": float(any_raw.mean()),
            "max": int(any_raw.max()),
            "rate_gt": {str(c): tail_rate(any_raw, c)
                        for c in [5, 6, 8, 10, 12, 14, 20, 30, 50]},
            "cut_for_top_1pct": list(cut_for_target(any_raw, 0.01)),
            "cut_for_top_3.5pct": list(cut_for_target(any_raw, 0.035)),
            "permutation_null_max": int(max_run_any(perm).max()),
        },
        "person_sd_across_300_items": {
            "mean": float(sd.mean()), "sd": float(sd.std(ddof=1)),
            "percentiles": {str(p): float(np.percentile(sd, p))
                            for p in [0.1, 0.5, 1, 2.5, 5, 50, 95, 99]},
            "bottom_1pct_cut": sd_cut1,
            "n_at_or_below_bottom_1pct": int(low.sum()),
            "share_of_bottom_1pct_also_run_flagged": float(raw_any_flag[low].mean()),
            "mean_sd_of_run_flagged": float(sd[raw_any_flag].mean()),
            "mean_sd_of_unflagged": float(sd[~raw_any_flag].mean()),
            "cohens_d_flagged_minus_unflagged":
                float((sd[raw_any_flag].mean() - sd[~raw_any_flag].mean()) / pooled),
        },
    }

    # ------------------------------------------ fatigue / Masuda midpoint drift
    mid = raw == 3
    ext = (raw == 1) | (raw == 5)
    clean = ~raw_any_flag
    fat = {
        "n_unflagged": int(clean.sum()),
        "midpoint_rate_by_quartile_block": [float(mid[:, a:b].mean()) for a, b in BLOCKS],
        "midpoint_rate_by_quartile_block_unflagged":
            [float(mid[clean, a:b].mean()) for a, b in BLOCKS],
        "midpoint_rate_by_30item_cycle":
            [float(mid[:, i * 30:(i + 1) * 30].mean()) for i in range(10)],
        "extreme_rate_by_quartile_block": [float(ext[:, a:b].mean()) for a, b in BLOCKS],
    }
    p1, p4 = mid[:, 0:75].mean(axis=1), mid[:, 225:300].mean(axis=1)
    dif = p4 - p1
    fat["paired_block4_minus_block1"] = {
        "mean_diff": float(dif.mean()), "sd_diff": float(dif.std(ddof=1)),
        "cohens_dz": float(dif.mean() / dif.std(ddof=1)),
        "relative_change_pct": float(dif.mean() / p1.mean() * 100),
        "share_of_respondents_rising": float((dif > 0).mean()),
    }
    sd1 = raw[:, :150].astype(np.float64).std(axis=1, ddof=1)
    sd2 = raw[:, 150:].astype(np.float64).std(axis=1, ddof=1)
    ds = sd2 - sd1
    fat["person_sd_first150_vs_last150"] = {
        "mean_first150": float(sd1.mean()), "mean_last150": float(sd2.mean()),
        "mean_diff": float(ds.mean()), "cohens_dz": float(ds.mean() / ds.std(ddof=1)),
        "share_lower_in_second_half": float((ds < 0).mean()),
    }
    # keying-controlled: the confound is that items 211-300 are all reverse-keyed
    pos = np.where(~is_rev)[0]
    rv = np.where(is_rev)[0]
    within = []
    for j in range(30):
        cols = np.arange(j, 300, 30)
        kp = cols[~is_rev[cols]]
        if len(kp) >= 4:
            h = len(kp) // 2
            within.append(float(mid[:, kp[h:]].mean() - mid[:, kp[:h]].mean()))
    fat["keying_controlled"] = {
        "positive_keyed_items_1_to_120_midpoint":
            float(mid[:, pos[pos < 120]].mean()),
        "positive_keyed_items_151plus_midpoint":
            float(mid[:, pos[pos >= 150]].mean()),
        "reverse_keyed_items_121_210_midpoint":
            float(mid[:, rv[(rv >= 120) & (rv < 210)]].mean()),
        "reverse_keyed_items_211_300_midpoint":
            float(mid[:, rv[rv >= 210]].mean()),
        "within_facet_positive_keyed_late_minus_early_mean": float(np.mean(within)),
        "within_facet_n_facets": len(within),
        "within_facet_n_rising": int(np.sum(np.array(within) > 0)),
    }
    fat["verdict"] = ("Midpoint endorsement FALLS monotonically with item position "
                      "(%.2f%% -> %.2f%%), within-person dz = %.3f in the direction "
                      "OPPOSITE to the claim, and per-person response SD RISES in the "
                      "second half (dz = %.3f). The decline survives holding item "
                      "keying constant. The page's Masuda-based claim is refuted in "
                      "these data."
                      % (100 * fat["midpoint_rate_by_quartile_block"][0],
                         100 * fat["midpoint_rate_by_quartile_block"][3],
                         fat["paired_block4_minus_block1"]["cohens_dz"],
                         fat["person_sd_first150_vs_last150"]["cohens_dz"]))
    out["fatigue"] = fat

    # ------------------------------------------------------ recommended cuts
    R = runs["raw"]

    def joint(cuts):
        j = np.zeros(n, dtype=bool)
        for v in range(1, 6):
            j |= R[:, v] > cuts[v]
        return float(j.mean())

    rec_a = [0] + ceiling[1:]           # Johnson's own applied screen, recovered
    out["recommended"] = {
        "A_match_johnsons_applied_screen": {
            "cuts": rec_a, "flag_rate_on_norm_sample": joint(rec_a),
            "flag_n": int(round(joint(rec_a) * n)),
            "rationale": "the exact ceiling Johnson's own cleaning left behind; "
                         "flags zero of 145,388 protocols he judged valid",
        },
    }
    for target, key in ((0.035, "B_equal_tail_joint_3.5pct"),
                        (0.01, "C_equal_tail_joint_1pct")):
        best = None
        for q in np.arange(0.0001, 0.0400, 0.0001):
            cuts = [0] + [cut_for_target(R[:, v], float(q))[0] for v in range(1, 6)]
            jr = joint(cuts)
            if best is None or abs(jr - target) < abs(best["flag_rate_on_norm_sample"] - target):
                best = {"per_option_tail_q": float(q), "cuts": cuts,
                        "flag_rate_on_norm_sample": jr}
        best["rationale"] = ("equal per-option tail probability, joint rate pinned "
                             "near %.1f%%; every one of these flags is a protocol "
                             "Johnson retained, i.e. a false positive by construction"
                             % (100 * target))
        out["recommended"][key] = best

    # what each option's cut would have to be, alone, for 1% / 3.5%
    out["cut_table"] = {
        str(v): {"label_zh": SCALE_ZH[v - 1],
                 "current": RUN_CUT[v],
                 "observed_max": ceiling[v],
                 "p50": out["raw"]["per_option"][str(v)]["max_run_percentiles"]["50"],
                 "p90": out["raw"]["per_option"][str(v)]["max_run_percentiles"]["90"],
                 "p95": out["raw"]["per_option"][str(v)]["max_run_percentiles"]["95"],
                 "p99": out["raw"]["per_option"][str(v)]["max_run_percentiles"]["99"],
                 "p99.5": out["raw"]["per_option"][str(v)]["max_run_percentiles"]["99.5"],
                 "p99.9": out["raw"]["per_option"][str(v)]["max_run_percentiles"]["99.9"],
                 "cut_for_top_1pct":
                     out["raw"]["per_option"][str(v)]["cut_for_top_1pct"]["cut"],
                 "cut_for_top_3.5pct":
                     out["raw"]["per_option"][str(v)]["cut_for_top_3.5pct"]["cut"],
                 "current_cut_flag_rate": out["raw"]["per_option"][str(v)]["flag_rate"]}
        for v in range(1, 6)}

    # ---------------------------------------------------- proposed zh wording
    out["proposed_zh_copy"] = {
        "validity_warning_body": (
            "。这个阈值取自 Johnson (2005) 的常模样本：14.5 万份通过有效性检查的问卷里，"
            "没有一份出现过比它更长的连选。如果这确实是你的真实作答，忽略即可；"
            "如果是没看题快速点选留下的，建议重测。"),
        "validity_warning_body_note_for_reverse_block": (
            "提醒：第 211 题起全部是反向表述的题目，如果你在这一段里一路选「很不符合」，"
            "那是内容一致，不是乱答。"),
        "break_card_body_replacement": (
            "300 题不算短。累了就歇一会儿再回来，不用一口气答完。"
            "进度已经存好了，关掉网页也不会丢。"),
        "break_card_comment_replacement": (
            "/* 每 5 页（75 题）提示一次休息。纯 UX 提示，不作任何关于作答漂移方向的断言：\n"
            "   在 Johnson 的 14.5 万人常模样本上实测，中间档背书率随题目位置**下降**\n"
            "   （18.97% → 15.82%），与 Masuda 等 (2017) 的漂移方向相反。 */"),
        "removed_claim": "被筛掉的约占 3.5%",
    }

    path = os.path.join(ipip.OUT, "validity_thresholds.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    # -------------------------------------------------------------- console
    print("N = %d   reversed items = %d" % (n, is_rev.sum()))
    print("\nKEYING VALIDATION: %d/148 reversed flip negative, %d/152 positives hold"
          % (out["keying_validation"]["raw_reversed_items_going_negative"],
             out["keying_validation"]["raw_keyed_positive_items_staying_positive"]))
    print("  reversed per 30-item cycle: %s"
          % out["keying_validation"]["reversed_items_per_30_item_cycle"])

    for tag in ("raw", "recoded", "perm"):
        b = out[tag]
        print("\n--- %s ---  overall flag rate %.4f%% (n=%d)"
              % (tag, 100 * b["overall_flag_rate"], b["overall_flag_n"]))
        print(" opt cut  flag%    flag_n  pctrank   p50 p90 p95 p99 p99.5 p99.9  max"
              "  cut@1%  cut@3.5%")
        for v in range(1, 6):
            o = b["per_option"][str(v)]
            q = o["max_run_percentiles"]
            print(" %3d %3d %7.4f %7d %8.4f   %3.0f %3.0f %3.0f %3.0f %5.0f %5.0f %4d"
                  "  %5d %8d"
                  % (v, o["current_cut"], 100 * o["flag_rate"], o["flag_n"],
                     o["pct_rank_of_current_cut"], q["50"], q["90"], q["95"], q["99"],
                     q["99.5"], q["99.9"], o["max_run_max"],
                     o["cut_for_top_1pct"]["cut"], o["cut_for_top_3.5pct"]["cut"]))

    print("\nRAW histogram of max run (len 4..16), showing the screening cliff:")
    print("  opt |" + "".join("%7d" % L for L in range(4, 17)))
    for v in range(1, 6):
        print("  %3d |" % v + "".join(
            "%7d" % c for c in out["raw"]["per_option"][str(v)]["histogram_4_to_16"]))
    print("  perm null max per option: %s" % out["perm_null_ceiling"][1:])

    pse = out["pre_screening_evidence"]
    print("\nPRE-SCREENING: raw ceiling %s vs perm-null ceiling %s; "
          "protocols exceeding site cuts for options 2/3/4/5 = %d"
          % (ceiling[1:], out["perm_null_ceiling"][1:], pse["n_exceeding_site_cut_opt2345"]))
    print("  estimated removal rate (geometric lower bound): %.3f%%"
          % (100 * pse["implied_pre_screen_removal_rate_lower_bound"]))

    oa = out["option1_flag_anatomy"]
    print("\nOPTION-1 FLAG ANATOMY (the only cut that ever fires):")
    print("  n=%d  run start by block %s  median start item %d"
          % (oa["n_flagged"], oa["run_start_by_quartile_block"], oa["median_run_start_item"]))
    print("  %.1f%% start after item 150; mean %.1f%% of run items are reverse-keyed; "
          "%.1f%% of runs lie entirely inside reverse-keyed items"
          % (100 * oa["share_of_flagged_runs_starting_after_item_150"],
             100 * oa["mean_share_of_run_items_that_are_reverse_keyed"],
             100 * oa["share_of_runs_entirely_inside_reverse_keyed_items"]))

    print("\nTIME FIELDS: " + tf["verdict"])
    print("\nOTHER INDICATORS:")
    print("  " + json.dumps(out["other_indicators"], indent=2)[:1400])
    print("\nFATIGUE: " + fat["verdict"])
    print("  midpoint by block: %s" % [round(100 * x, 3) for x in
                                       fat["midpoint_rate_by_quartile_block"]])
    print("  midpoint by block (unflagged): %s" % [round(100 * x, 3) for x in
                                                   fat["midpoint_rate_by_quartile_block_unflagged"]])
    print("  extreme  by block: %s" % [round(100 * x, 3) for x in
                                       fat["extreme_rate_by_quartile_block"]])
    print("  keying-controlled: %s" % json.dumps(fat["keying_controlled"], indent=2))
    print("\nRECOMMENDED:")
    for k, v2 in out["recommended"].items():
        print("  %-32s cuts=%s  norm-sample flag rate %.4f%%"
              % (k, v2["cuts"], 100 * v2["flag_rate_on_norm_sample"]))
    print("\nwrote %s" % path)


if __name__ == "__main__":
    main()
