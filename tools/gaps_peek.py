# -*- coding: utf-8 -*-
"""Scratch: inspect what concurrent agents already produced, and the site DATA shape."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402


def walk(o, p="", depth=0, maxdepth=2):
    if depth > maxdepth:
        return
    if isinstance(o, dict):
        for k, v in list(o.items())[:18]:
            n = len(v) if isinstance(v, (dict, list, str)) else v
            print("  " * depth + p + "/" + str(k), type(v).__name__, n)
            walk(v, p + "/" + str(k), depth + 1, maxdepth)


print("=== psychometrics.json ===")
walk(json.load(io.open(os.path.join(ipip.OUT, "psychometrics.json"), encoding="utf-8")))

print()
print("=== site DATA ===")
d = ipip.site_data()
for k, v in d.items():
    print(" ", k, type(v).__name__, len(v) if isinstance(v, (dict, list, str)) else v)
    if isinstance(v, dict):
        for k2, v2 in list(v.items())[:6]:
            print("     ", k2, type(v2).__name__,
                  len(v2) if isinstance(v2, (dict, list, str)) else v2)

print()
print("=== byte sizes ===")
html = io.open(ipip.SITE, encoding="utf-8").read()
raw = html[html.index("const DATA = ") + len("const DATA = "):]
raw = raw[:raw.index("};\n") + 1]
print("page chars", len(html), "utf8 bytes", len(html.encode("utf-8")))
print("DATA chars", len(raw), "utf8 bytes", len(raw.encode("utf-8")))
