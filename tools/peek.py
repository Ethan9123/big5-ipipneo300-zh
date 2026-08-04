# -*- coding: utf-8 -*-
"""Inspect the schema and basic quality of IPIP300-SCORES.csv."""
import io
import os

import pandas as pd

CSV = os.path.join(
    os.path.expanduser("~"), ".cache", "kagglehub", "datasets", "edersoncorbari",
    "ipip-neo-big-five-personality-300-item-version", "versions", "1", "IPIP300-SCORES.csv",
)

with io.open(CSV, encoding="utf-8", errors="replace") as fh:
    head = [next(fh) for _ in range(3)]
print("--- raw first lines ---")
for line in head:
    print(repr(line[:400]))

sep = "\t" if head[0].count("\t") > head[0].count(",") else ","
print("\ndetected separator:", repr(sep))

df = pd.read_csv(CSV, sep=sep, nrows=50000, low_memory=False)
print("\ncolumns (%d):" % len(df.columns))
print(list(df.columns))
print("\ndtypes sample:")
print(df.dtypes.head(20))
print("\nhead:")
print(df.head(3).to_string(max_cols=20))

# full row count without loading everything
with io.open(CSV, encoding="utf-8", errors="replace") as fh:
    n = sum(1 for _ in fh) - 1
print("\ntotal rows: %d" % n)
