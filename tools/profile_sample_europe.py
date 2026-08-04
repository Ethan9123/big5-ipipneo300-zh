# -*- coding: utf-8 -*-
"""One-off: how much of the norm sample is actually *European* (the site says 欧美)?"""
import io
import json
import os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "profile_sample.json")
d = json.load(io.open(P, encoding="utf-8"))
n = d["n_total"]
cc = dict(d["country"]["all_codes_sorted_by_n"])

EUROPE_EX_UKIE = [
    "Netherlands", "Finland", "Sweden", "Germany", "Norway", "France", "Denmark", "Belgium",
    "Greece", "Albania", "Romania", "Portugal", "Italy", "Spain", "Russian Fed", "Poland",
    "Croatia", "Austria", "Latvia", "Switzerland", "Serbia", "Estonia", "Iceland", "Bulgaria",
    "Slovenia", "Ukraine", "Yugoslavia", "Hungary", "Lithuania", "Czech Repub", "Slovakia",
    "Belarus", "Bosnia and", "Macedonia", "Luxembourg", "Malta", "Moldova", "Cyprus",
    "Monaco", "Andorra", "San Marino", "Liechtenstein", "Montenegro", "Faroe Islan",
    "Gibraltar", "Greenland", "Isle of Man", "Jersey", "Guernsey", "Aland Islan",
]
tot = sum(cc.get(k, 0) for k in EUROPE_EX_UKIE)
print("continental Europe (excl UK/Ireland): n=%d  %.3f%%" % (tot, 100.0 * tot / n))
print("present:", {k: cc[k] for k in EUROPE_EX_UKIE if k in cc})
print("USA alone: %d (%.3f%%)" % (cc["USA"], 100.0 * cc["USA"] / n))
print("anglosphere: %d (%.3f%%)" % (d["country"]["anglosphere"]["n"],
                                    d["country"]["anglosphere"]["share_pct"]))
rest = n - d["country"]["anglosphere"]["n"] - tot
print("everything else: %d (%.3f%%)" % (rest, 100.0 * rest / n))
