# -*- coding: utf-8 -*-
"""Download the IPIP-NEO-300 response dataset from Kaggle and report what is in it."""
import os
import sys
import traceback

try:
    import kagglehub
except ImportError:
    sys.exit("kagglehub is not installed:  pip install kagglehub")

SLUG = "edersoncorbari/ipip-neo-big-five-personality-300-item-version"

try:
    path = kagglehub.dataset_download(SLUG)
except Exception as exc:                                    # noqa: BLE001
    print("DOWNLOAD FAILED:", type(exc).__name__)
    print(str(exc)[:2000])
    traceback.print_exc(limit=3)
    sys.exit(2)

print("Path to dataset files:", path)
print()
total = 0
for root, _dirs, files in os.walk(path):
    for name in sorted(files):
        full = os.path.join(root, name)
        size = os.path.getsize(full)
        total += size
        print("  %10.1f MB  %s" % (size / 1e6, os.path.relpath(full, path)))
print("\n  total: %.1f MB" % (total / 1e6))
