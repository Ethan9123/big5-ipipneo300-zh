# -*- coding: utf-8 -*-
"""qa_distinct.py -- 243 人格画像「区分度」体检。

四项检查：
  1. 邻居相似度   (只差一个维度一档的格子对，共 810 对)
  2. 复用句子     (按标点切句，统计跨画像出现 >=3 次的句子)
  3. pros/cons/practice 条目复用率 (243*3 = 729 条 x 三个字段)
  4. 差异维度是否真的驱动内容 (抽 20 对只差神经质一档的邻居，看 love/work)

相似度定义：**字符 3-gram 的 Jaccard 系数**。
  对一段文本 t，先剔除空白，取所有长度为 3 的连续字符窗口构成集合 G(t)；
  两段文本相似度 = |G(a) ∩ G(b)| / |G(a) ∪ G(b)|。
  1.0 = 完全相同，0.0 = 没有任何共同的三字片段。
  中文没有词边界，字符 n-gram 比分词更稳，且对语序变化和同义替换都敏感——
  只换几个形容词的「伪改写」仍会得到很高的分数，正好是我们要抓的东西。
  一对邻居的总分 = summary/life/friends/love/work 五个字段 Jaccard 的算术平均。

用法：
  python qa_distinct.py [profiles.json]
不传路径时按 profiles_raw.json -> profiles_ordered.json 的顺序找。
"""
from __future__ import annotations

import io
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

KEYS = ["O", "C", "E", "A", "N"]
KEY_ZH = {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"}
LV = ["低", "中", "高"]
TEXT_FIELDS = ["summary", "life", "friends", "love", "work"]
LIST_FIELDS = ["pros", "cons", "practice"]

# 索引编码：O*81 + C*27 + E*9 + A*3 + N，低=0 中=1 高=2
def idx_to_levels(i):
    return [(i // 81) % 3, (i // 27) % 3, (i // 9) % 3, (i // 3) % 3, i % 3]


def levels_to_cell(lv):
    return "".join(k + LV[v] for k, v in zip(KEYS, lv))


# ---------------------------------------------------------------- 载入
def load(path=None):
    if path is None:
        for cand in ("profiles_raw.json", "profiles_ordered.json"):
            p = os.path.join(OUT, cand)
            if os.path.exists(p):
                path = p
                break
    if path is None or not os.path.exists(path):
        sys.exit("找不到画像文件：out/profiles_raw.json 和 out/profiles_ordered.json 都不存在")
    data = json.load(io.open(path, encoding="utf-8"))
    if not isinstance(data, list):
        sys.exit("顶层不是数组")
    return path, data


PLACEHOLDER_MARKS = ("占位", "TODO", "TBD", "placeholder", "lorem", "真实文案")


def audit_shape(data):
    """返回 (problems, cells)。cells[i] 是第 i 条的格子编码。"""
    problems = []
    cells = []
    if len(data) != 243:
        problems.append("条目数 %d，应为 243" % len(data))
    for i, p in enumerate(data):
        derived = levels_to_cell(idx_to_levels(i))
        cell = p.get("cell")
        if cell is None:
            problems.append("[%d] 缺 cell 字段（按索引推得 %s）" % (i, derived))
            cell = derived
        elif cell != derived:
            problems.append("[%d] cell=%s 与索引位置不符，应为 %s" % (i, cell, derived))
        cells.append(cell)
        for f in TEXT_FIELDS + ["lead"]:
            v = p.get(f)
            if not isinstance(v, str) or not v.strip():
                problems.append("[%s] 字段 %s 缺失或为空" % (cell, f))
        for f in LIST_FIELDS:
            v = p.get(f)
            if not isinstance(v, list) or len(v) != 3 or any(
                    not isinstance(x, str) or not x.strip() for x in v):
                problems.append("[%s] 字段 %s 不是 3 条非空字符串" % (cell, f))
    return problems, cells


def placeholder_count(data):
    n = 0
    for p in data:
        blob = json.dumps(p, ensure_ascii=False)
        if any(m in blob for m in PLACEHOLDER_MARKS):
            n += 1
    return n


# ---------------------------------------------------------------- 相似度
WS = re.compile(r"\s+")


def grams(text, n=3):
    t = WS.sub("", text or "")
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def jaccard(a, b):
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def neighbors():
    """所有「恰好一个维度差一档」的无序对 (i, j, 差异维度)。共 810 对。"""
    pairs = []
    for i in range(243):
        li = idx_to_levels(i)
        for d in range(5):
            for nl in (li[d] - 1, li[d] + 1):
                if not 0 <= nl <= 2:
                    continue
                lj = list(li)
                lj[d] = nl
                j = lj[0] * 81 + lj[1] * 27 + lj[2] * 9 + lj[3] * 3 + lj[4]
                if i < j:
                    pairs.append((i, j, KEYS[d]))
    return pairs


def pct(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


# ---------------------------------------------------------------- 切句
SENT_SPLIT = re.compile(r"[。！？!?；;\n]+")


def sentences(text):
    for s in SENT_SPLIT.split(text or ""):
        s = s.strip().strip("，,、—…　 ")
        if len(s) >= 6:            # 太短的片段（"是的""对"）不算复用风险
            yield s


# ---------------------------------------------------------------- 主流程
def main():
    path, data = load(sys.argv[1] if len(sys.argv) > 1 else None)
    rep = []
    w = rep.append
    w("画像文件：%s" % path)
    w("条目数：%d" % len(data))

    problems, cells = audit_shape(data)
    ph = placeholder_count(data)
    w("含占位标记（占位/TODO/真实文案 等）的画像：%d / %d" % (ph, len(data)))
    w("结构问题：%d 条" % len(problems))
    for p in problems[:12]:
        w("  - " + p)
    if len(problems) > 12:
        w("  … 另有 %d 条同类问题" % (len(problems) - 12))
    w("")

    # 预算 n-gram
    gcache = [{f: grams(p.get(f, "")) for f in TEXT_FIELDS} for p in data]

    # --- 1. 邻居相似度
    w("=" * 66)
    w("1. 邻居相似度（字符 3-gram Jaccard，五字段平均）")
    w("=" * 66)
    pairs = neighbors()
    w("邻居对总数：%d（每格 %d~%d 个邻居）" % (
        len(pairs),
        min(Counter([i for i, _, _ in pairs] + [j for _, j, _ in pairs]).values()),
        max(Counter([i for i, _, _ in pairs] + [j for _, j, _ in pairs]).values())))
    scored = []
    for i, j, d in pairs:
        per = {f: jaccard(gcache[i][f], gcache[j][f]) for f in TEXT_FIELDS}
        scored.append((sum(per.values()) / len(TEXT_FIELDS), i, j, d, per))
    scored.sort(key=lambda t: -t[0])
    vals = sorted(s[0] for s in scored)
    w("分布：min=%.3f  中位数=%.3f  p90=%.3f  p99=%.3f  max=%.3f  均值=%.3f" % (
        vals[0], pct(vals, .5), pct(vals, .9), pct(vals, .99), vals[-1],
        sum(vals) / len(vals)))
    for thr in (0.9, 0.7, 0.5, 0.3):
        n = sum(1 for v in vals if v >= thr)
        w("  相似度 >= %.1f 的邻居对：%d (%.1f%%)" % (thr, n, 100.0 * n / len(vals)))
    w("")
    w("按维度分组的中位相似度（该维度是两格唯一的差异）：")
    bydim = defaultdict(list)
    for s in scored:
        bydim[s[3]].append(s[0])
    for k in KEYS:
        v = sorted(bydim[k])
        w("  %s %s : 中位=%.3f  p90=%.3f  n=%d" % (k, KEY_ZH[k], pct(v, .5), pct(v, .9), len(v)))
    w("")
    w("相似度最高的 25 对邻居：")
    for rank, (sc, i, j, d, per) in enumerate(scored[:25], 1):
        w("  %2d. %.3f  %s  <->  %s   (差异维度 %s %s)" % (
            rank, sc, cells[i], cells[j], d, KEY_ZH[d]))
        w("      逐字段 " + "  ".join("%s=%.2f" % (f, per[f]) for f in TEXT_FIELDS))
    w("")

    # --- 2. 复用句子
    w("=" * 66)
    w("2. 跨画像复用的句子（按 。！？；换行 切句，长度>=6 字）")
    w("=" * 66)
    sent_cells = defaultdict(set)
    sent_hits = Counter()
    total_sent = 0
    for idx, p in enumerate(data):
        for f in TEXT_FIELDS:
            for s in sentences(p.get(f, "")):
                total_sent += 1
                sent_hits[s] += 1
                sent_cells[s].add(cells[idx])
    uniq = len(sent_hits)
    w("句子总数：%d，去重后：%d（唯一率 %.1f%%）" % (total_sent, uniq, 100.0 * uniq / max(total_sent, 1)))
    rep3 = [s for s, c in sent_hits.items() if c >= 3]
    w("出现 >=3 次的句子：%d 句，覆盖 %d 次出现（占全部句子的 %.1f%%）" % (
        len(rep3), sum(sent_hits[s] for s in rep3),
        100.0 * sum(sent_hits[s] for s in rep3) / max(total_sent, 1)))
    w("")
    w("出现次数最多的 20 句：")
    for rank, (s, c) in enumerate(sent_hits.most_common(20), 1):
        w("  %2d. x%-4d 落在 %d 个格子 | %s" % (rank, c, len(sent_cells[s]), s[:70]))
    w("")

    # --- 3. pros / cons / practice
    w("=" * 66)
    w("3. pros / cons / practice 条目复用")
    w("=" * 66)
    for f in LIST_FIELDS:
        items = []
        for p in data:
            v = p.get(f) or []
            items.extend(x.strip() for x in v if isinstance(x, str))
        c = Counter(items)
        w("%s：共 %d 条，唯一 %d 条（唯一率 %.1f%%），最高复用 %d 次" % (
            f, len(items), len(c), 100.0 * len(c) / max(len(items), 1),
            max(c.values()) if c else 0))
    allitems = []
    for p in data:
        for f in LIST_FIELDS:
            allitems.extend(x.strip() for x in (p.get(f) or []) if isinstance(x, str))
    ac = Counter(allitems)
    w("三字段合计：%d 条，唯一 %d 条（唯一率 %.1f%%）" % (
        len(allitems), len(ac), 100.0 * len(ac) / max(len(allitems), 1)))
    w("")
    w("复用最多的 15 条：")
    for rank, (s, c) in enumerate(ac.most_common(15), 1):
        w("  %2d. x%-4d | %s" % (rank, c, s[:60]))
    w("")

    # --- 4. 差异维度是否真的驱动内容（神经质）
    w("=" * 66)
    w("4. 只差神经质一档的邻居：love / work 是否写出了压力反应与恢复速度的差别")
    w("=" * 66)
    STRESS = ["压力", "抗压", "情绪", "起伏", "反刍", "恢复", "缓过来", "平复", "焦躁",
              "紧张", "担心", "放大", "敏感", "稳", "淡定", "扛", "自责", "内耗",
              "委屈", "复盘", "睡不着", "反复", "消化", "崩", "后怕", "钝", "波动",
              "翻篇", "过去", "沉住气", "急"]
    npairs = [s for s in scored if s[3] == "N"]
    w("只差神经质一档的邻居对：%d（抽 20 对细看）" % len(npairs))
    rng = random.Random(20260803)
    sample = rng.sample(npairs, min(20, len(npairs)))
    sample.sort(key=lambda t: -t[0])
    drove = 0
    for rank, (sc, i, j, d, per) in enumerate(sample, 1):
        a, b = data[i], data[j]
        lex_a = {t for f in ("love", "work") for t in STRESS if t in (a.get(f) or "")}
        lex_b = {t for f in ("love", "work") for t in STRESS if t in (b.get(f) or "")}
        only_a, only_b = lex_a - lex_b, lex_b - lex_a
        # 判定：love 与 work 都不能几乎雷同，且两边的压力词要有差集
        ok = (per["love"] < 0.6 and per["work"] < 0.6 and (only_a or only_b))
        drove += 1 if ok else 0
        w("  %2d. [%s] %s -> %s  love相似=%.2f work相似=%.2f  %s" % (
            rank, "驱动" if ok else "未驱动", cells[i], cells[j],
            per["love"], per["work"], ""))
        w("      压力词 仅低N侧: %s" % ("、".join(sorted(only_a)) or "(无)"))
        w("      压力词 仅高N侧: %s" % ("、".join(sorted(only_b)) or "(无)"))
        w("      love低N: %s" % (a.get("love") or "")[:80])
        w("      love高N: %s" % (b.get("love") or "")[:80])
    w("")
    w("20 对中判定为「差异维度真正驱动了内容」的：%d 对" % drove)

    # ---------------------------------------------------------------- 输出
    txt = "\n".join(rep)
    dest = os.path.join(OUT, "qa_distinct_report.txt")
    io.open(dest, "w", encoding="utf-8").write(txt)

    worst = [{"cell_a": cells[i], "cell_b": cells[j], "dim": d,
              "score": round(sc, 4), "per_field": {k: round(v, 4) for k, v in per.items()}}
             for sc, i, j, d, per in scored[:60]]
    json.dump({
        "source": path,
        "n": len(data),
        "placeholder_profiles": ph,
        "shape_problems": problems,
        "neighbor_pairs": len(pairs),
        "similarity": {"median": pct(vals, .5), "p90": pct(vals, .9),
                       "p99": pct(vals, .99), "max": vals[-1], "min": vals[0]},
        "top60_similar_pairs": worst,
        "repeated_sentences_top20": [{"text": s, "count": c, "cells": len(sent_cells[s])}
                                     for s, c in sent_hits.most_common(20)],
        "list_item_unique_rate": len(ac) / float(max(len(allitems), 1)),
        "list_items_top15": [{"text": s, "count": c} for s, c in ac.most_common(15)],
        "n_pairs_driven": drove,
    }, io.open(os.path.join(OUT, "qa_distinct.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=1)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(txt)
    print("\n[wrote] %s" % dest)


if __name__ == "__main__":
    main()
