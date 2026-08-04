# -*- coding: utf-8 -*-
"""Print the top-level shape of each analysis artifact so we can pull the headline numbers."""
import io
import json
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")


def shape(v, depth=0, key=""):
    pad = "  " * depth
    if isinstance(v, dict):
        print("%s%s: dict(%d) keys=%s" % (pad, key, len(v), list(v.keys())[:14]))
        if depth < 1:
            for k, sub in list(v.items())[:14]:
                shape(sub, depth + 1, k)
    elif isinstance(v, list):
        kinds = {type(x).__name__ for x in v[:5]}
        print("%s%s: list(%d) of %s" % (pad, key, len(v), kinds))
        if v and isinstance(v[0], dict) and depth < 1:
            print("%s   item keys: %s" % (pad, list(v[0].keys())[:14]))
    else:
        s = str(v)
        print("%s%s: %s" % (pad, key, s[:160]))


for name in sys.argv[1:]:
    path = os.path.join(OUT, name)
    if not os.path.exists(path):
        print("MISSING %s" % name)
        continue
    print("\n" + "=" * 78)
    print(name, " (%.1f KB)" % (os.path.getsize(path) / 1024))
    print("=" * 78)
    shape(json.load(io.open(path, encoding="utf-8")))
