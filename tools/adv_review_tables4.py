# -*- coding: utf-8 -*-
"""Part 4: 688-vs-868 brotli cost, and full 868-level array Python vs JS parity."""
import io, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip
import brotli, gzip

J = json.load(io.open(os.path.join(ipip.OUT,"pct_tables.json"), encoding="utf-8"))
cohorts, scales = J["cohorts"], J["scales"]
EX = {(g,nm): np.array(J["tables"][g][nm]["pct_exact"]) for g in cohorts for nm in scales}
AL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

def levels_of(spec):
    v=[]
    for i,(st,sp) in enumerate(spec):
        en = spec[i+1][0] if i+1<len(spec) else 100.0
        for k in range(int(round((en-st)/sp))): v.append(st+(k+0.5)*sp)
    return np.round(np.array(v),6)
def quant(p,L):
    p=np.clip(p,L[0],L[-1]); i=np.clip(np.searchsorted(L,p),1,len(L)-1)
    lo,hi=L[i-1],L[i]; return np.where(p-lo<hi-p-1e-9,i-1,i).astype(np.int64)
def ladder_text(spec):
    f=lambda x:(("%.10f"%x).rstrip("0").rstrip(".") or "0")
    return "|".join("%s:%s"%(f(a),f(b)) for a,b in spec)
def enc_val(v,o):
    if v<48: o.append(AL[v])
    else:
        w=v-48; o.append(AL[48+(w>>6)]); o.append(AL[w&63])
def enc_u18(v,o):
    o.append(AL[(v>>12)&63]); o.append(AL[(v>>6)&63]); o.append(AL[v&63])

norms = J["norms"]
def build_payload(spec):
    L=levels_of(spec); q={k:quant(EX[k],L) for k in EX}
    parts=["B5PCT1", ",".join(cohorts), ",".join(scales), ladder_text(spec)]
    nb=[]
    for g in cohorts:
        for nm in scales:
            enc_u18(int(round(norms[g][nm]["mean"]*100)),nb); enc_u18(int(round(norms[g][nm]["sd"]*100)),nb)
    parts.append("".join(nb))
    tb=[]
    for nm in scales:
        for g in cohorts:
            a=q[(g,nm)]; enc_val(int(a[0]),tb)
            for d in np.diff(a): enc_val(int(d),tb)
    parts.append("".join(tb))
    return "~".join(parts), L

S868 = [(0,.001),(0.1,.01),(0.75,.05),(5.25,.25),(94.75,.05),(99.25,.01),(99.9,.001)]
S688 = [(0,.01),(0.75,.05),(5.25,.25),(94.75,.05),(99.25,.01)]
p868,L868 = build_payload(S868)
p688,L688 = build_payload(S688)
real = io.open(os.path.join(ipip.OUT,"pct_tables_encoded.txt"),encoding="ascii").read()
print("my rebuilt 868 payload identical to shipped file:", p868 == real, "(len %d vs %d)"%(len(p868),len(real)))
for nm,p in (("868 shipped",p868),("688 rejected",p688)):
    print("%-13s raw %6d  brotli11 %6d  gzip9 %6d" % (nm,len(p),len(brotli.compress(p.encode(),quality=11)),len(gzip.compress(p.encode(),9))))
d=len(brotli.compress(p868.encode(),quality=11))-len(brotli.compress(p688.encode(),quality=11))
print("brotli cost of the extra 180 levels: %d bytes   <-- claim says 675" % d)
np.save(os.path.join(ipip.OUT,"_adv_levels868.npy"), L868)
io.open(os.path.join(ipip.OUT,"_adv_levels868.json"),"w").write(json.dumps([float(x) for x in L868]))
print("wrote 868 python levels for JS parity check")
