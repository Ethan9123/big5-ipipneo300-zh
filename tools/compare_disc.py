# -*- coding: utf-8 -*-
"""Side-by-side discriminability of two corpora, so a targeted fix can be checked for
robbing Peter to pay Paul.

  python tools/compare_disc.py out/profiles_raw.before_E.json out/profiles_raw.json
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ipip  # noqa: E402

KEYS = ["O", "C", "E", "A", "N"]
DIM = {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"}
FIELDS = ["lead", "summary", "life", "friends", "love", "work"]

a_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ipip.OUT, "profiles_raw.before_E.json")
b_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ipip.OUT, "profiles_raw.json")


def run(p):
    r = subprocess.run([sys.executable, os.path.join(HERE, "discriminability.py"), p, "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit("discriminability failed on %s\n%s" % (p, r.stderr[-1500:]))
    return json.loads(r.stdout.strip().splitlines()[-1])


A, B = run(a_path), run(b_path)
print("A = %s" % os.path.basename(a_path))
print("B = %s" % os.path.basename(b_path))
print("随机基线 33.3%\n")


def d(x, y):
    delta = y - x
    mark = "  " if abs(delta) < 1.0 else ("↑ " if delta > 0 else "↓ ")
    return "%5.1f → %5.1f %s%+5.1f" % (x, y, mark, delta)


print("全文判别率")
for k in KEYS:
    print("  %s %-4s  %s" % (k, DIM[k], d(A["overall"][k], B["overall"][k])))
print("  五维全对  %s" % d(A["all_five"], B["all_five"]))

print("\n逐字段（本次只应改动 love 和 work）")
hdr = "  维度      " + "".join("%-16s" % f for f in FIELDS)
print(hdr)
regressions = []
for k in KEYS:
    line = "  %s %-4s " % (k, DIM[k])
    for f in FIELDS:
        x, y = A["per_field"][k][f], B["per_field"][k][f]
        delta = y - x
        line += "%5.1f%+6.1f   " % (y, delta)
        if f in ("love", "work") and delta < -3.0:
            regressions.append((k, f, x, y))
        if f not in ("love", "work") and abs(delta) > 3.0:
            regressions.append((k, f, x, y))
    print(line)

print()
if regressions:
    print("需要注意的变化：")
    for k, f, x, y in regressions:
        print("   %s %s: %.1f → %.1f  (%+.1f)" % (DIM[k], f, x, y, y - x))
else:
    print("没有维度在 love/work 上倒退超过 3 点，其余字段也没有意外变动。")

eA, eB = A["per_field"]["E"], B["per_field"]["E"]
gain = ((eB["love"] - eA["love"]) + (eB["work"] - eA["work"])) / 2
print("\n本轮目标：外向性在 love/work 的平均判别率  %.1f → %.1f  (%+.1f)"
      % ((eA["love"] + eA["work"]) / 2, (eB["love"] + eB["work"]) / 2, gain))
others = [(B["per_field"][k][f] - A["per_field"][k][f]) for k in KEYS if k != "E" for f in ("love", "work")]
print("其余四维在同两段的平均变化：%+.1f  （明显为负说明是拆东墙补西墙）" % (sum(others) / len(others)))
