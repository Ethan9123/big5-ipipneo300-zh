# -*- coding: utf-8 -*-
"""Part K: can any variant reproduce the claimed runner-up cell values?"""
import io, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip

Z = ipip.load()
facet_raw = Z["facet_raw"].astype(np.float64)
domain_raw = Z["domain_raw"].astype(np.float64)
masks = ipip.group_masks(Z["sex"], Z["age"])
D = ipip.site_data()
NORMS = {k: np.array(v["ns"], dtype=np.float64) for k, v in D["norms"].items()}

scales = [("domain", k, None) for k in ipip.DOMAIN_ORDER]
for k in ipip.DOMAIN_ORDER:
    for f in range(1, 7): scales.append(("facet", k, f))

CLAIM = {("F_lt21","N5"):12.83, ("N_lt21","N5"):9.80, ("N_lt21","A5"):7.49,
         ("F_lt21","A5"):6.84, ("M_lt21","A5"):6.79, ("F_lt21","O5"):6.57}

for variant in ["unrounded", "norms_1dp", "empirical_midrank"]:
    rows = []
    for g in ipip.GROUPS:
        mk = masks[g]; ns = NORMS[g]
        for kind, dom, fno in scales:
            if kind == "domain":
                r = domain_raw[mk, ipip.DOMAIN_ORDER.index(dom)]
                i = ipip.DOMAIN_INDEX[dom]; mu_s, sd_s = ns[i], ns[i+5]; nm = dom
            else:
                r = facet_raw[mk, ipip.facet_slot(dom, fno)]
                a, b = ipip.FACET_OFFSET[dom]; mu_s, sd_s = ns[a+fno], ns[b+fno]; nm = f"{dom}{fno}"
            pa = ipip.pct_from_t(50 + 10*(r - mu_s)/sd_s)
            if variant == "unrounded":
                pb = ipip.pct_from_t(50 + 10*(r - r.mean())/r.std(ddof=1))
            elif variant == "norms_1dp":
                pb = ipip.pct_from_t(50 + 10*(r - round(r.mean(),1))/round(r.std(ddof=1),1))
            else:
                o = np.argsort(r, kind="mergesort"); rk = np.empty(len(r))
                sr = r[o]
                # mid-rank empirical percentile
                _, first, cnts = np.unique(sr, return_index=True, return_counts=True)
                tmp = np.empty(len(r))
                for st, c in zip(first, cnts):
                    tmp[st:st+c] = 100.0*(st + 0.5*c)/len(r)
                rk[o] = tmp; pb = rk
            rows.append((g, nm, float(np.abs(pa-pb).mean())))
    rows.sort(key=lambda x: -x[2])
    print("--- variant:", variant)
    for g, nm, v in rows[:7]:
        c = CLAIM.get((g, nm))
        print("   %-9s %-4s mine=%7.4f  claimed=%s  %s" %
              (g, nm, v, c if c else "-", "MATCH" if c and abs(round(v,2)-c) < 0.005 else ""))
