# -*- coding: utf-8 -*-
"""Pretty-print tools/out/profile_sample.json for the report."""
import io
import json
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "profile_sample.json")
d = json.load(io.open(P, encoding="utf-8"))

s = d["straightlining"]
print("finding:", s["finding"])
print("cut_comparison:", json.dumps(s["cut_comparison"], ensure_ascii=False))
print("raw_keypress flagged: %d (%.4f%%)" % (s["variants"]["raw_keypress"]["n_flagged"],
                                             s["variants"]["raw_keypress"]["flag_rate_pct"]))
print("--- tail evidence (raw keypress)")
print(json.dumps(s["tail_evidence"]["raw_keypress"], ensure_ascii=False, indent=1))
print("--- duplicates")
print(json.dumps(d["duplicates"], ensure_ascii=False, indent=1))
