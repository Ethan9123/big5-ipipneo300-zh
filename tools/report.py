# -*- coding: utf-8 -*-
"""Pull the headline numbers out of the analysis artifacts."""
import io
import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
J = lambda n: json.load(io.open(os.path.join(OUT, n), encoding="utf-8"))
def head(t): print("\n" + "=" * 76 + "\n" + t + "\n" + "=" * 76)
def kv(d, keys, indent="  "):
    for k in keys:
        if k in d:
            v = d[k]
            print("%s%-46s %s" % (indent, k, json.dumps(v, ensure_ascii=False)[:210]))

p = J("profile_sample.json")
head("SAMPLE")
print("  n_total: %d" % p["n_total"])
kv(p["country"], ["n_distinct", "anglosphere", "greater_china_plus_sg", "cn_hk_tw_sg_strict", "blank_or_missing"])
print("  top 12 countries:")
for row in p["country"]["top25"][:12]:
    print("     ", json.dumps(row, ensure_ascii=False))
kv(p["sex"], ["overall", "codes_other_than_1_or_2"])
kv(p["age"], ["min", "max", "mean", "median", "p5", "p95", "n_lt21", "share_lt21_pct", "n_gte21"])
kv(p["year"], ["raw_min", "raw_max", "interpretation", "modal_year", "modal_year_n"])
kv(p["cohorts"], list(p["cohorts"].keys()))
head("STRAIGHTLINING (site claims 3.5%)")
kv(p["straightlining"], ["RUN_CUT_1to5", "site_equivalent_variant", "johnson_2005_claimed_pct",
                         "delta_vs_claim_pp", "finding"])
print("  variants:", json.dumps(p["straightlining"]["variants"], ensure_ascii=False)[:900])
head("DUPLICATES")
kv(p["duplicates"], ["case_ids_appearing_more_than_once", "distinct_300item_vectors",
                     "duplicate_vector_groups", "rows_in_duplicate_vector_groups",
                     "rows_in_duplicate_vector_groups_pct", "largest_vector_group_size"])

n = J("norm_fidelity.json")
head("NORM FIDELITY")
kv(n, ["sanity_max_abs_pct_vs_csv_reference"])
kv(n["impact_summary"], ["overall_mean_abs_pct_shift", "overall_max_abs_pct_shift",
                         "overall_mean_share_disp_ge1", "overall_mean_share_disp_ge5",
                         "overall_mean_share_disp_ge10", "overall_mean_share_level_flip",
                         "worst_by_mean_shift", "worst_by_max_shift", "worst_by_level_flip"])
print("  top10_by_mean_shift:")
for r in n["impact_summary"]["top10_by_mean_shift"][:10]:
    print("     ", json.dumps(r, ensure_ascii=False)[:190])
kv(n["per_respondent_report_impact"], list(n["per_respondent_report_impact"].keys()))
print("  neutral_check:", json.dumps(n["neutral_check"], ensure_ascii=False)[:700])

y = J("psychometrics.json")
head("PSYCHOMETRICS")
r = y["reliability"]
kv(r, ["facet_alpha_min", "facet_alpha_median", "facet_alpha_max", "facets_below_070"])
print("  domain alphas:", json.dumps(r["domains"], ensure_ascii=False)[:400])
k = y["keying_validation"]
kv(k, ["any_miskeyed", "distribution", "negative_items", "items_below_0.15"])
print("  weakest_15:", json.dumps(k["weakest_15"], ensure_ascii=False)[:1000])
d = y["discriminant"]
kv(d, ["n_items_failing_facet_level", "n_items_failing_domain_level"])
print("  worst_10:", json.dumps(d["worst_10"], ensure_ascii=False)[:900])
ic = y["intercorrelations"]
kv(ic, ["facet_pairs_above_075", "facets_loading_on_wrong_domain"])
print("  domain_matrix_OCEAN:", json.dumps(ic["domain_matrix_OCEAN"], ensure_ascii=False)[:500])

e = J("pctmap_error.json")
head("PERCENTILE MAP ERROR")
kv(e["definition"], list(e["definition"].keys()))
kv(e["overall"], ["total_values", "all_scales", "domains_only", "facets_only",
                  "T_observed_min", "T_observed_max"])
head("RAILS")
kv(e["rails"], ["pinned_at_1", "pinned_at_99", "pinned_either", "pinned_at_1_domains",
                "pinned_at_1_facets", "pinned_at_99_domains", "pinned_at_99_facets",
                "within_type_shares_pct", "worst_scales_pooled"])
head("CUBIC SHAPE / MONOTONICITY")
kv(e["cubic_shape"], list(e["cubic_shape"].keys()))
kv(e["monotonicity"], list(e["monotonicity"].keys()))
head("RAILS vs POLYNOMIAL / ALTERNATIVES / DISPLAY IMPACT")
kv(e["rails_vs_polynomial"], list(e["rails_vs_polynomial"].keys()))
kv(e["alternatives"], list(e["alternatives"].keys()))
kv(e["level_band_disagreement"], list(e["level_band_disagreement"].keys()))
print("  worst_cells (n>=100):", json.dumps(e["worst_cells_top10_n_ge_100"][:5], ensure_ascii=False)[:900])

v = J("validity_thresholds.json")
head("VALIDITY THRESHOLDS")
kv(v, ["site_run_cut", "site_claim_pct"])
print("  raw     :", json.dumps(v["raw"], ensure_ascii=False)[:500])
print("  recoded :", json.dumps(v["recoded"], ensure_ascii=False)[:500])
print("  perm    :", json.dumps(v["perm"], ensure_ascii=False)[:500])
kv(v["keying_validation"], list(v["keying_validation"].keys()))
kv(v["pre_screening_evidence"], ["n_exceeding_site_cut_opt2345", "estimated_removed_lower_bound_total",
                                 "implied_pre_screen_removal_rate_lower_bound", "note"])
kv(v["option1_flag_anatomy"], list(v["option1_flag_anatomy"].keys()))
kv(v["time_fields"], ["verdict"])
