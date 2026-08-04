# -*- coding: utf-8 -*-
"""Completeness-critic pass 4: payload, plus two claims the page makes that the
sample can check directly.

PAYLOAD.  Measure before proposing.  Transfer size is what matters, so every
candidate restructuring is scored gzipped AND brotli'd, not just raw.

CLAIMS.
  * "加粗一圈 = 50（人群中位数）" -- is the printed 50 the sample median?
  * "30 和 70 附近是模糊边界" vs the code's level() cutoffs of 45/55.
  * hero chips: do deviation-ranked chips repeat the domain bar above them?

Writes tools/out/gaps_payload.json.
"""
import gzip
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

try:
    import brotli
    HAVE_BROTLI = True
except ImportError:
    HAVE_BROTLI = False


def gz(b):
    return len(gzip.compress(b if isinstance(b, bytes) else b.encode("utf-8"), 9))


def br(b):
    if not HAVE_BROTLI:
        return None
    return len(brotli.compress(b if isinstance(b, bytes) else b.encode("utf-8"), quality=11))


def main():
    html = io.open(ipip.SITE, encoding="utf-8").read()
    start = html.index("const DATA = ") + len("const DATA = ")
    end = html.index("};\n", start) + 1
    data_src = html[start:end]
    data = json.loads(data_src)

    out = {"have_brotli": HAVE_BROTLI}
    pb = html.encode("utf-8")
    out["page"] = {"utf8_bytes": len(pb), "gzip": gz(pb), "brotli": br(pb),
                   "chars": len(html)}
    db = data_src.encode("utf-8")
    out["DATA_literal"] = {"utf8_bytes": len(db), "gzip": gz(db), "brotli": br(db),
                           "chars": len(data_src),
                           "share_of_page_utf8": round(len(db) / len(pb), 4)}
    # DATA's contribution to the COMPRESSED page (the number that actually matters)
    without = html[:start] + "{}" + html[end:]
    wb = without.encode("utf-8")
    out["DATA_marginal_compressed_cost"] = {
        "page_gzip_with": gz(pb), "page_gzip_without": gz(wb),
        "gzip_delta": gz(pb) - gz(wb),
        "page_brotli_with": br(pb), "page_brotli_without": br(wb),
        "brotli_delta": (br(pb) - br(wb)) if HAVE_BROTLI else None,
    }

    comp = {}
    for key in data:
        s = json.dumps(data[key], ensure_ascii=False, separators=(",", ":"))
        comp[key] = {"utf8_bytes": len(s.encode("utf-8")), "gzip": gz(s), "brotli": br(s)}
    # notes sub-fields
    notes = data["notes"]
    for fld in ["note", "lo", "hi", "mid"]:
        s = json.dumps([x.get(fld, "") for x in notes], ensure_ascii=False, separators=(",", ":"))
        comp["notes." + fld] = {"utf8_bytes": len(s.encode("utf-8")), "gzip": gz(s), "brotli": br(s)}
    for fld in ["zh", "en"]:
        s = json.dumps([x[fld] for x in data["items"]], ensure_ascii=False, separators=(",", ":"))
        comp["items." + fld] = {"utf8_bytes": len(s.encode("utf-8")), "gzip": gz(s), "brotli": br(s)}
    out["components"] = comp

    # ---- candidate lossless restructurings ----
    cand = {}
    # baseline: minified JSON of the same object
    base = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    cand["0_minify_json_only"] = base
    # A: items -> parallel arrays; notes -> arrays of 4 (mid may be "")
    d2 = dict(data)
    d2["items"] = {"id": [x["id"] for x in data["items"]],
                   "zh": [x["zh"] for x in data["items"]],
                   "en": [x["en"] for x in data["items"]]}
    d2["notes"] = [[x["note"], x["lo"], x["hi"], x.get("mid", "")] for x in notes]
    cand["A_columnar_items_and_notes"] = json.dumps(d2, ensure_ascii=False, separators=(",", ":"))
    # B: A + id dropped (it is just 1..300)
    d3 = dict(d2)
    d3["items"] = {"zh": d2["items"]["zh"], "en": d2["items"]["en"]}
    cand["B_A_plus_drop_item_ids"] = json.dumps(d3, ensure_ascii=False, separators=(",", ":"))
    # C: B + all strings moved into one delimiter-joined blob per field
    d4 = dict(d3)
    d4["items"] = {"zh": "".join(d3["items"]["zh"]), "en": "".join(d3["items"]["en"])}
    d4["notes"] = "".join("".join(r) for r in d2["notes"])
    cand["C_B_plus_delimiter_joined"] = json.dumps(d4, ensure_ascii=False, separators=(",", ":"))
    # D: C + norms as flat arrays rounded to 2dp (already floats), facets columnar
    d5 = dict(d4)
    d5["norms"] = {g: [round(float(v), 2) for v in data["norms"][g]["ns"]] for g in data["norms"]}
    cand["D_C_plus_flat_norms"] = json.dumps(d5, ensure_ascii=False, separators=(",", ":"))

    rows = []
    for k, s in cand.items():
        b = s.encode("utf-8")
        rows.append({"variant": k, "utf8_bytes": len(b), "gzip": gz(b), "brotli": br(b),
                     "raw_saving_vs_current": len(db) - len(b),
                     "gzip_saving_vs_current": gz(db) - gz(b),
                     "brotli_saving_vs_current": (br(db) - br(b)) if HAVE_BROTLI else None})
    out["restructurings"] = rows

    # how much of the compressed payload is the 300 Chinese hint objects?
    d_nonotes = dict(data)
    d_nonotes["notes"] = []
    s = json.dumps(d_nonotes, ensure_ascii=False, separators=(",", ":"))
    out["notes_marginal"] = {
        "DATA_gzip_with_notes": gz(base), "DATA_gzip_without_notes": gz(s),
        "gzip_delta": gz(base) - gz(s),
        "DATA_brotli_with_notes": br(base), "DATA_brotli_without_notes": br(s),
        "brotli_delta": (br(base) - br(s)) if HAVE_BROTLI else None,
    }
    # lazy-load split: could notes ship as a second request?
    out["notes_marginal"]["share_of_page_gzip"] = round(
        (gz(base) - gz(s)) / gz(pb), 4)

    # ================= claims =================
    z = ipip.load()
    facet_raw = z["facet_raw"].astype(np.float64)
    domain_raw = z["domain_raw"].astype(np.float64)
    sex, age = z["sex"], z["age"]
    n = len(sex)
    masks = ipip.group_masks(sex, age)
    fT = np.zeros((n, 30)); dT = np.zeros((n, 5))
    for g in ["M_lt21", "M_gte21", "F_lt21", "F_gte21"]:
        m = masks[g]
        ns = np.asarray(data["norms"][g]["ns"], dtype=np.float64)
        for d_i, dom in enumerate(ipip.DOMAIN_ORDER):
            di = ipip.DOMAIN_INDEX[dom]
            dT[m, d_i] = 50 + 10 * (domain_raw[m, d_i] - ns[di]) / ns[di + 5]
            mo, so = ipip.FACET_OFFSET[dom]
            for fno in range(1, 7):
                slot = ipip.facet_slot(dom, fno)
                fT[m, slot] = 50 + 10 * (facet_raw[m, slot] - ns[fno + mo]) / ns[fno + so]
    fP = ipip.pct_from_t(fT); dP = ipip.pct_from_t(dT)
    allP = np.concatenate([dP, fP], axis=1)
    out["claim_50_is_the_median"] = {
        "median_printed_percentile_over_all_35_scales": round(float(np.median(allP)), 2),
        "mean_printed_percentile": round(float(allP.mean()), 2),
        "per_domain_median": {ipip.DOMAIN_ORDER[i]: round(float(np.median(dP[:, i])), 2)
                              for i in range(5)},
        "facet_median_min": round(float(np.median(fP, axis=0).min()), 2),
        "facet_median_max": round(float(np.median(fP, axis=0).max()), 2),
        "share_of_printed_percentiles_below_50": round(float((allP < 50).mean()), 4),
        "share_pinned_at_1": round(float((allP <= 1).mean()), 5),
        "share_pinned_at_99": round(float((allP >= 99).mean()), 5),
    }
    # 30/70 vs 45/55
    out["claim_30_70_fuzzy_vs_code_45_55"] = {
        "share_scales_between_30_and_70": round(float(((allP >= 30) & (allP <= 70)).mean()), 4),
        "share_scales_between_45_and_55": round(float(((allP >= 45) & (allP <= 55)).mean()), 4),
    }
    # chip redundancy
    rng = np.random.default_rng(20260802)
    idx = rng.choice(n, 20000, replace=False)
    dev = np.abs(fP[idx] - 50)
    own_dom = np.array([slot % 5 for slot in range(30)])
    gap = np.abs(fP[idx] - dP[idx][:, own_dom])
    top6 = np.argsort(-dev, axis=1)[:, :6]
    gap_top6 = np.take_along_axis(gap, top6, axis=1)
    top6s = np.argsort(-gap, axis=1)[:, :6]
    gap_top6s = np.take_along_axis(gap, top6s, axis=1)
    out["chip_redundancy"] = {
        "median_gap_to_own_domain_current_chips": round(float(np.median(gap_top6)), 2),
        "median_gap_to_own_domain_if_ranked_by_gap": round(float(np.median(gap_top6s)), 2),
        "share_current_chips_within_10pts_of_their_domain_bar": round(float((gap_top6 <= 10).mean()), 4),
    }

    with open(os.path.join(ipip.OUT, "gaps_payload.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("PAGE utf8 %d  gzip %d  brotli %s" % (out["page"]["utf8_bytes"], out["page"]["gzip"],
                                                out["page"]["brotli"]))
    print("DATA utf8 %d (%.1f%% of page)  gzip %d  brotli %s"
          % (out["DATA_literal"]["utf8_bytes"], 100 * out["DATA_literal"]["share_of_page_utf8"],
             out["DATA_literal"]["gzip"], out["DATA_literal"]["brotli"]))
    m = out["DATA_marginal_compressed_cost"]
    print("DATA marginal cost in the COMPRESSED page: gzip %d bytes, brotli %s bytes"
          % (m["gzip_delta"], m["brotli_delta"]))
    print("components (utf8 / gzip / brotli):")
    for k, v in sorted(comp.items(), key=lambda kv: -kv[1]["utf8_bytes"]):
        print("   %-14s %7d %7d %7s" % (k, v["utf8_bytes"], v["gzip"], v["brotli"]))
    print("restructurings:")
    for r in rows:
        print("   %-28s utf8 %7d (save %6d)  gzip %6d (save %5d)  brotli %6s (save %5s)"
              % (r["variant"], r["utf8_bytes"], r["raw_saving_vs_current"], r["gzip"],
                 r["gzip_saving_vs_current"], r["brotli"], r["brotli_saving_vs_current"]))
    nm = out["notes_marginal"]
    print("notes marginal: gzip %d bytes (%.1f%% of the gzipped page), brotli %s"
          % (nm["gzip_delta"], 100 * nm["share_of_page_gzip"], nm["brotli_delta"]))
    c = out["claim_50_is_the_median"]
    print("CLAIM 50=median: actual median printed percentile %.2f (mean %.2f); %.1f%% below 50; "
          "facet medians span %.1f..%.1f; pinned at 1: %.3f%%, at 99: %.3f%%"
          % (c["median_printed_percentile_over_all_35_scales"], c["mean_printed_percentile"],
             100 * c["share_of_printed_percentiles_below_50"], c["facet_median_min"],
             c["facet_median_max"], 100 * c["share_pinned_at_1"], 100 * c["share_pinned_at_99"]))
    print("CLAIM 30/70 fuzzy: %.1f%% of printed scales fall in 30-70; only %.1f%% in the code's 45-55 band"
          % (100 * out["claim_30_70_fuzzy_vs_code_45_55"]["share_scales_between_30_and_70"],
             100 * out["claim_30_70_fuzzy_vs_code_45_55"]["share_scales_between_45_and_55"]))
    print("CHIPS: median |chip - its domain bar| = %.1f pts now, %.1f if ranked by that gap; "
          "%.1f%% of chips sit within 10 pts of the bar above them"
          % (out["chip_redundancy"]["median_gap_to_own_domain_current_chips"],
             out["chip_redundancy"]["median_gap_to_own_domain_if_ranked_by_gap"],
             100 * out["chip_redundancy"]["share_current_chips_within_10pts_of_their_domain_bar"]))


if __name__ == "__main__":
    main()
