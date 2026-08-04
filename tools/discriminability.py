# -*- coding: utf-8 -*-
"""Can the band be recovered from the text alone?

Keyword lists are a bad detector for "did this dimension drive the writing" -- mine
missed profiles that open with 「桌上常年摊着三四样学到一半的东西」, which is about as
high-openness as behaviour gets. This measures the thing directly instead: hold one
profile out, build per-band centroids from the other 242, and see which band the held-out
text is closest to. If the text encodes the band, accuracy is high; if the writing is
generic, it collapses to the 33.3% baseline.

Also reports per-field accuracy, which localises WHERE a dimension is (or isn't) written.
"""
import io
import json
import os
import re
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipip  # noqa: E402

LV = ["低", "中", "高"]
KEYS = ["O", "C", "E", "A", "N"]
DIM = {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"}
FIELDS = ["lead", "summary", "life", "friends", "love", "work"]

args = [a for a in sys.argv[1:] if not a.startswith("--")]
path = args[0] if args else os.path.join(ipip.OUT, "profiles_raw.json")
profiles = json.load(io.open(path, encoding="utf-8"))
profiles.sort(key=lambda p: p["cell"])
n = len(profiles)


def bands(cell):
    return [LV.index(cell[i * 2 + 1]) for i in range(5)]


Y = np.array([bands(p["cell"]) for p in profiles])          # (n, 5)

# Strip the dimension names themselves -- otherwise the classifier just reads
# 「神经质偏低」 off the page and reports a discriminability that is not there.
STRIP = re.compile("|".join(list(DIM.values()) + ["偏低", "偏高", "中等", "低分", "高分"]))


def featurise(texts):
    """character 2+3-gram counts -> L2-normalised tf-idf rows"""
    docs = []
    for t in texts:
        t = STRIP.sub("", re.sub(r"[^一-鿿]", "", t))
        g = Counter()
        for k in (2, 3):
            for i in range(len(t) - k + 1):
                g[t[i:i + k]] += 1
        docs.append(g)
    vocab = {}
    for d in docs:
        for w in d:
            if w not in vocab:
                vocab[w] = len(vocab)
    X = np.zeros((len(docs), len(vocab)), dtype=np.float32)
    for r, d in enumerate(docs):
        for w, c in d.items():
            X[r, vocab[w]] = c
    df = (X > 0).sum(axis=0)
    idf = np.log((len(docs) + 1) / (df + 1)) + 1.0
    X *= idf
    norm = np.linalg.norm(X, axis=1, keepdims=True)
    norm[norm == 0] = 1
    return X / norm


def loo_accuracy(X, y):
    """leave-one-out nearest-centroid; centroids recomputed without the held-out row"""
    sums = np.zeros((3, X.shape[1]), dtype=np.float32)
    cnts = np.zeros(3, dtype=np.float32)
    for b in range(3):
        m = y == b
        sums[b] = X[m].sum(axis=0)
        cnts[b] = m.sum()
    correct = 0
    per_row = np.zeros(len(y), dtype=bool)
    for i in range(len(y)):
        best, bestsim = -1, -2.0
        for b in range(3):
            s = sums[b] - (X[i] if y[i] == b else 0)
            c = cnts[b] - (1 if y[i] == b else 0)
            if c <= 0:
                continue
            cen = s / c
            nrm = np.linalg.norm(cen)
            sim = float(X[i] @ cen / nrm) if nrm else -1.0
            if sim > bestsim:
                bestsim, best = sim, b
        per_row[i] = (best == y[i])
        correct += per_row[i]
    return correct / len(y), per_row


AS_JSON = "--json" in sys.argv
if not AS_JSON:
    print("留一法判别性测试  (n=%d, 随机基线 33.3%%)" % n)
    print("移除了维度名本身，否则分类器只是在读「神经质偏低」这几个字\n")

Xall = featurise([" ".join(p[f] for f in FIELDS) for p in profiles])
allcorrect = np.ones(n, dtype=bool)
if not AS_JSON:
    print("  维度   全文        lead    summary  life   friends  love   work")
per_field_X = {f: featurise([p[f] for p in profiles]) for f in FIELDS}
report = {"n": n, "overall": {}, "per_field": {}}
for j, k in enumerate(KEYS):
    acc, rows = loo_accuracy(Xall, Y[:, j])
    allcorrect &= rows
    report["overall"][k] = round(100 * acc, 1)
    report["per_field"][k] = {}
    line = "  %s %-4s %5.1f%%   " % (k, DIM[k], 100 * acc)
    for f in FIELDS:
        a, _ = loo_accuracy(per_field_X[f], Y[:, j])
        report["per_field"][k][f] = round(100 * a, 1)
        line += " %5.1f%% " % (100 * a)
    if not AS_JSON:
        print(line)
report["all_five"] = round(100.0 * allcorrect.mean(), 1)
if AS_JSON:
    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0)

print("\n  五个维度全部还原正确的画像: %d/%d = %.1f%%  (随机基线 0.4%%)"
      % (allcorrect.sum(), n, 100.0 * allcorrect.mean()))

# where does a dimension fail? report the cells the classifier gets wrong
print("\n每个维度最难还原的档位:")
for j, k in enumerate(KEYS):
    _, rows = loo_accuracy(Xall, Y[:, j])
    for b in range(3):
        m = Y[:, j] == b
        print("   %s%s  %5.1f%%" % (k, LV[b], 100.0 * rows[m].mean()), end="")
    print()
