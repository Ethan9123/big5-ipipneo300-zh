import sys, numpy as np, collections
sys.path.insert(0, r"C:\Users\kids1\Downloads\bigfive\tools")
import ipip
Z = ipip.load()
items = np.ascontiguousarray(Z["items"].astype(np.uint8))
v = items.view(np.dtype((np.void, 300))).ravel()
uniq, inv, cnts = np.unique(v, return_inverse=True, return_counts=True)
dup = np.where(cnts > 1)[0]
for gi in dup:
    idx = np.where(inv == gi)[0]
    print("dup group rows:", idx, "cases:", Z["case"][idx], "sex:", Z["sex"][idx],
          "age:", Z["age"][idx], "year:", Z["year"][idx])
# rail summary, honest denominator
print()
print("reversed list: n=%d min=%d max=%d" % (len(ipip.site_data()["reversed"]),
      min(ipip.site_data()["reversed"]), max(ipip.site_data()["reversed"])))
