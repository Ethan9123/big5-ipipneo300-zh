# -*- coding: utf-8 -*-
"""
qa2_distinct.py —— 243 画像的「区分度」体检（只读，不改任何成稿）

输出：
  out/qa2_distinct.json          机器可读全量结果
  out/qa2_distinct_report.txt    人读摘要
  out/qa2_pairs_N.txt / _A.txt / _E.txt   抽样对照文本（供人工核读）

作者说明：所有阈值判定按 tools/profile_spec.md 的「区分度要求」。
"""
import json, os, re, sys, random, itertools
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SCRATCH = r"~\AppData\Local\Temp\claude\C--Users-kids1-Downloads-bigfive\3f3dea16-3b73-4559-8359-8360df8000b2\scratchpad"
os.makedirs(SCRATCH, exist_ok=True)

SEED = 20260803
PROSE = ["summary", "life", "friends", "love", "work"]      # 相似度用的 5 个字段
ALL_PROSE = ["lead", "summary", "life", "friends", "love", "work"]
LIST_FIELDS = ["pros", "cons", "practice"]

PUNCT = "，。！？；：、…—－·「」“”‘’（）()《》〈〉,.!?;:\"'~/\\[]【】%　 \n\t\r"
PUNCT_SET = set(PUNCT)
SPLIT_RE = re.compile(r"[，。！？；：、…—\n]+")

# ---------- 停用词 / 维度名（变体 B 剔除） ----------
DIM_TERMS = [
    "开放性", "尽责性", "外向性", "宜人性", "神经质",
    "高开放", "低开放", "中开放", "高尽责", "低尽责", "中尽责",
    "高外向", "低外向", "中外向", "高宜人", "低宜人", "中宜人",
    "高神经质", "低神经质", "中神经质",
    "分数", "百分位", "偏低", "偏高", "中等", "较高", "较低", "这个组合", "你目前",
    "的人", "这一档", "中间档",
]
STOP_CHARS = set("的了是在也和就会很都这那有你我他她它不上下里个人之与或而但把被给对从到让要能可更还又再以为所其一些着过得地")

def strip_punct(s):
    return "".join(ch for ch in s if ch not in PUNCT_SET)

def variant_a(text):
    """变体 A：仅去标点/空白，保留全部内容字。"""
    return strip_punct(text)

def variant_b(text):
    """变体 B：在 A 基础上先删掉维度名/程度词（多字优先），再删单字停用词。"""
    t = text
    for term in sorted(DIM_TERMS, key=len, reverse=True):
        t = t.replace(term, "")
    t = strip_punct(t)
    return "".join(ch for ch in t if ch not in STOP_CHARS)

def ngrams(s, n=3):
    if len(s) < n:
        return set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}

def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)

def overlap_coef(a, b):
    """包含系数：交集 / 较小集合。对「A 的内容被 B 吞掉」更敏感。"""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))

def lev(a, b, cutoff=None):
    la, lb = len(a), len(b)
    if la == 0: return lb
    if lb == 0: return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ca = a[i - 1]
        best = cur[0]
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            cur[j] = v
            if v < best: best = v
        if cutoff is not None and best > cutoff:
            return cutoff + 1
        prev = cur
    return prev[lb]

def edit_sim(a, b):
    m = max(len(a), len(b))
    return 1 - lev(a, b) / m if m else 0.0

def pct(sorted_vals, q):
    """线性插值分位数。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx); hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

def dist_stats(vals):
    v = sorted(vals)
    return {
        "n": len(v),
        "min": round(v[0], 4),
        "p25": round(pct(v, .25), 4),
        "median": round(pct(v, .5), 4),
        "mean": round(sum(v) / len(v), 4),
        "p90": round(pct(v, .90), 4),
        "p99": round(pct(v, .99), 4),
        "max": round(v[-1], 4),
    }

# ---------- 载入 ----------
profiles = json.load(open(os.path.join(OUT, "profiles_raw.json"), encoding="utf-8"))
assert len(profiles) == 243
by_cell = {p["cell"]: p for p in profiles}
assert len(by_cell) == 243

LV = {"低": 0, "中": 1, "高": 2}
LVN = {0: "低", 1: "中", 2: "高"}
DIMS = ["O", "C", "E", "A", "N"]

def parse_cell(cell):
    m = re.findall(r"([OCEAN])([低中高])", cell)
    assert len(m) == 5, cell
    assert [x[0] for x in m] == DIMS, cell
    return [LV[x[1]] for x in m]

def make_cell(levels):
    return "".join(f"{d}{LVN[l]}" for d, l in zip(DIMS, levels))

def cell_index(levels):
    return levels[0] * 81 + levels[1] * 27 + levels[2] * 9 + levels[3] * 3 + levels[4]

levels_of = {c: parse_cell(c) for c in by_cell}
# 校验 cell 编码与 index 的一致性（顺序 O C E A N，低=0 中=1 高=2）
idx_ok = all(cell_index(levels_of[p["cell"]]) == i for i, p in enumerate(profiles))

# ---------- 预算文本 ----------
textA, textB = {}, {}   # cell -> {field: cleaned}
gramsA, gramsB = {}, {}  # cell -> {field: set, "_all": set}
for c, p in by_cell.items():
    ta = {f: variant_a(p[f]) for f in PROSE}
    tb = {f: variant_b(p[f]) for f in PROSE}
    ta["_all"] = "".join(ta[f] for f in PROSE)
    tb["_all"] = "".join(tb[f] for f in PROSE)
    textA[c], textB[c] = ta, tb
    gramsA[c] = {k: ngrams(v, 3) for k, v in ta.items()}
    gramsB[c] = {k: ngrams(v, 3) for k, v in tb.items()}

# =========================================================
# 1. 邻居相似度
# =========================================================
pairs = []
seen = set()
for c in by_cell:
    lv = levels_of[c]
    for di in range(5):
        for delta in (-1, 1):
            nl = list(lv); nl[di] += delta
            if not (0 <= nl[di] <= 2):
                continue
            nc = make_cell(nl)
            key = tuple(sorted([c, nc]))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"a": key[0], "b": key[1], "dim": DIMS[di],
                          "step": tuple(sorted([lv[di], nl[di]]))})
neighbor_count = Counter()
for pr in pairs:
    neighbor_count[pr["a"]] += 1
    neighbor_count[pr["b"]] += 1

for pr in pairs:
    a, b = pr["a"], pr["b"]
    pr["simA"] = jaccard(gramsA[a]["_all"], gramsA[b]["_all"])
    pr["simB"] = jaccard(gramsB[a]["_all"], gramsB[b]["_all"])
    pr["fieldsA"] = {f: round(jaccard(gramsA[a][f], gramsA[b][f]), 4) for f in PROSE}
    pr["maxFieldA"] = max(pr["fieldsA"].values())
    pr["maxFieldName"] = max(pr["fieldsA"], key=lambda f: pr["fieldsA"][f])

simA_all = [pr["simA"] for pr in pairs]
simB_all = [pr["simB"] for pr in pairs]
statsA = dist_stats(simA_all)
statsB = dist_stats(simB_all)
per_field_stats = {f: dist_stats([pr["fieldsA"][f] for pr in pairs]) for f in PROSE}
per_dim_stats = {d: dist_stats([pr["simA"] for pr in pairs if pr["dim"] == d]) for d in DIMS}
per_step_stats = {}
for d in DIMS:
    for st in [(0, 1), (1, 2)]:
        k = f"{d}:{LVN[st[0]]}->{LVN[st[1]]}"
        vals = [pr["simA"] for pr in pairs if pr["dim"] == d and pr["step"] == st]
        per_step_stats[k] = dist_stats(vals)

top25 = sorted(pairs, key=lambda p: -p["simA"])[:25]
over_p5 = [pr for pr in pairs if pr["simA"] > 0.5]
over_p45 = [pr for pr in pairs if pr["simA"] > 0.45]
over_p35 = [pr for pr in pairs if pr["simA"] > 0.35]
# 单字段超标（某个字段和邻居极像，即使整体不像）
field_over = [(pr, f) for pr in pairs for f in PROSE if pr["fieldsA"][f] > 0.5]

# 每格与邻居的平均/最大相似度
cell_neighbor_sim = defaultdict(list)
for pr in pairs:
    cell_neighbor_sim[pr["a"]].append(pr["simA"])
    cell_neighbor_sim[pr["b"]].append(pr["simA"])
cell_sim_summary = {c: {"mean": round(sum(v) / len(v), 4), "max": round(max(v), 4), "n": len(v)}
                    for c, v in cell_neighbor_sim.items()}

# =========================================================
# 2. 差异维度是否真的驱动内容（自动信号 + 抽样导出供人读）
# =========================================================
LEXICON = {
    "N": ["反刍", "反复", "重放", "回想", "复盘", "睡不着", "睡眠", "失眠", "焦虑", "担心", "不安",
          "情绪", "起伏", "压力", "崩", "恢复", "平静", "稳", "内耗", "自责", "后怕", "警觉",
          "敏感", "过一夜", "想很久", "放大", "推演", "钻牛角尖", "翻来覆去", "消耗", "紧张",
          "心里", "念头", "过不去", "揪", "咀嚼", "第二天", "隔天", "半小时", "冷静"],
    "A": ["冲突", "争执", "吵", "让步", "退", "妥协", "顺从", "道歉", "拒绝", "底线", "直说",
          "直率", "迁就", "忍", "委屈", "得罪", "针锋", "硬碰", "低头", "对峙", "反驳", "批评",
          "不客气", "先说", "摊牌", "为难", "占便宜", "答应", "配合", "体谅", "照顾", "顶回去",
          "翻脸", "谈判", "争", "软", "硬"],
    "E": ["主动", "发起", "张罗", "牵头", "社交", "人群", "热闹", "独处", "能量", "约", "聚",
          "话多", "话少", "沉默", "安静", "开口", "寒暄", "局", "带头", "推动", "联系", "群",
          "饭局", "party", "聚会", "恢复", "充电", "退回", "人多", "陌生人", "闲聊", "一个人",
          "社交后", "自己待", "邀请"],
}
FIELDS_FOR = {"N": ["love", "work"], "A": ["friends", "love", "work"], "E": ["friends", "life", "work"]}

def sentences(text):
    return [s for s in SPLIT_RE.split(text) if len(s.strip()) >= 2]

group_results = {}
rng = random.Random(SEED)
for d in ["N", "A", "E"]:
    grp = [pr for pr in pairs if pr["dim"] == d]
    flds = FIELDS_FOR[d]
    for pr in grp:
        a, b = pr["a"], pr["b"]
        ta = "".join(by_cell[a][f] for f in flds)
        tb = "".join(by_cell[b][f] for f in flds)
        pr["focus_sim"] = round(jaccard(ngrams(strip_punct(ta), 3), ngrams(strip_punct(tb), 3)), 4)
        lex = LEXICON[d]
        sa = {t for t in lex if t in ta}
        sb = {t for t in lex if t in tb}
        pr["lex_only_a"] = sorted(sa - sb)
        pr["lex_only_b"] = sorted(sb - sa)
        pr["lex_shared"] = len(sa & sb)
        pr["lex_diff"] = len(sa ^ sb)
        # 共享整句（强烈提示只换了形容词）
        sa_set = set(sentences(ta)); sentb = set(sentences(tb))
        pr["shared_sentences"] = sorted(sa_set & sentb)
        pr["shared_sentences_long"] = sorted(s for s in (sa_set & sentb) if len(s) >= 6)
        pr["n_sent_a"] = len(sa_set); pr["n_sent_b"] = len(sentb)
        # 「换两个字的同一句」：分句层面的近似重复（编辑相似度 > 0.6，且不完全相同）
        nd_clause = []
        for s1 in sa_set:
            if len(s1) < 5: continue
            for s2 in sentb:
                if len(s2) < 5 or s1 == s2: continue
                if abs(len(s1) - len(s2)) > 0.4 * max(len(s1), len(s2)): continue
                sm = edit_sim(s1, s2)
                if sm > 0.6:
                    nd_clause.append({"a": s1, "b": s2, "sim": round(sm, 3)})
        nd_clause.sort(key=lambda x: -x["sim"])
        pr["near_dup_clauses"] = nd_clause[:6]
        pr["n_near_dup_clauses"] = len(nd_clause)
    sample = rng.sample(grp, 25)
    sample = sorted(sample, key=lambda p: -p["focus_sim"])
    group_results[d] = {
        "n_pairs": len(grp),
        "focus_fields": flds,
        "focus_sim_stats": dist_stats([p["focus_sim"] for p in grp]),
        "lex_diff_stats": dist_stats([float(p["lex_diff"]) for p in grp]),
        "pairs_with_shared_sentence": sum(1 for p in grp if p["shared_sentences"]),
        "pairs_with_shared_sentence_len6+": sum(1 for p in grp if p["shared_sentences_long"]),
        "pairs_with_near_dup_clause": sum(1 for p in grp if p["n_near_dup_clauses"]),
        "near_dup_clause_stats": dist_stats([float(p["n_near_dup_clauses"]) for p in grp]),
        "worst_by_near_dup_clause": [
            {"a": p["a"], "b": p["b"], "n": p["n_near_dup_clauses"],
             "examples": p["near_dup_clauses"][:3]}
            for p in sorted(grp, key=lambda x: -x["n_near_dup_clauses"])[:10]],
        "sample_keys": [[p["a"], p["b"]] for p in sample],
    }
    # 导出抽样文本供人工核读
    lines = []
    lines.append(f"=== 只差 {d} 一档的 162 对，随机抽样 25 对（seed={SEED}，按 focus_sim 降序展示）===")
    lines.append(f"聚焦字段: {flds}\n")
    for i, p in enumerate(sample, 1):
        lines.append(f"--- #{i}  {p['a']}  VS  {p['b']}   ({d}: {LVN[p['step'][0]]}→{LVN[p['step'][1]]})")
        lines.append(f"    整体simA={p['simA']:.3f}  聚焦字段sim={p['focus_sim']:.3f}  "
                     f"词表独有A={p['lex_only_a']}  独有B={p['lex_only_b']}  "
                     f"共享分句={len(p['shared_sentences'])}(>=6字:{len(p['shared_sentences_long'])})  "
                     f"近重分句={p['n_near_dup_clauses']}")
        if p["near_dup_clauses"]:
            for nd in p["near_dup_clauses"][:3]:
                lines.append(f"      ~{nd['sim']}  「{nd['a']}」 / 「{nd['b']}」")
        for f in flds:
            lines.append(f"  [{f}] A({p['a']}): {by_cell[p['a']][f]}")
            lines.append(f"  [{f}] B({p['b']}): {by_cell[p['b']][f]}")
        lines.append("")
    open(os.path.join(SCRATCH, f"qa2_pairs_{d}.txt"), "w", encoding="utf-8").write("\n".join(lines))

# =========================================================
# 3. 套话检测
# =========================================================
sent_index = defaultdict(list)   # 句子 -> [(cell, field)]
for c, p in by_cell.items():
    for f in ALL_PROSE:
        for s in sentences(p[f]):
            sent_index[s.strip()].append((c, f))
repeat_sents = []
for s, occ in sent_index.items():
    cells = {c for c, _ in occ}
    if len(occ) >= 5 and len(s) >= 6:
        repeat_sents.append({"sentence": s, "len": len(s), "count": len(occ),
                             "cells": len(cells), "fields": sorted({f for _, f in occ})})
repeat_sents.sort(key=lambda x: (-x["count"], -x["len"]))
repeat_sents_short = []
for s, occ in sent_index.items():
    if len(occ) >= 5 and len(s) < 6:
        repeat_sents_short.append({"sentence": s, "len": len(s), "count": len(occ),
                                   "cells": len({c for c, _ in occ})})
repeat_sents_short.sort(key=lambda x: -x["count"])

# 列表字段里的重复整条
list_sent = defaultdict(list)
for c, p in by_cell.items():
    for f in LIST_FIELDS:
        for it in p[f]:
            list_sent[it.strip()].append((c, f))
repeat_list_items = [{"item": s, "count": len(o), "field": sorted({f for _, f in o})}
                     for s, o in list_sent.items() if len(o) >= 5]
repeat_list_items.sort(key=lambda x: -x["count"])

# 高频 n-gram（4-8 字），按「有多少个画像出现过」= df
seg_by_cell = {}
for c, p in by_cell.items():
    segs = []
    for f in ALL_PROSE:
        segs += [strip_punct(s) for s in sentences(p[f])]
    seg_by_cell[c] = [s for s in segs if s]

df = defaultdict(set)
for c, segs in seg_by_cell.items():
    seen_g = set()
    for s in segs:
        for n in range(4, 9):
            for i in range(len(s) - n + 1):
                seen_g.add(s[i:i + n])
    for g in seen_g:
        df[g].add(c)
df = {g: len(cs) for g, cs in df.items() if len(cs) >= 8}
# 保留「极大」n-gram：若存在更长且 df 相同的父串则丢弃
grams_sorted = sorted(df.items(), key=lambda kv: (-kv[1], -len(kv[0])))
by_len = defaultdict(list)
for g, d in df.items():
    by_len[len(g)].append(g)
maximal = []
for g, d in grams_sorted:
    redundant = False
    for L in range(len(g) + 1, 9):
        for h in by_len.get(L, []):
            if g in h and df[h] == d:
                redundant = True
                break
        if redundant:
            break
    if not redundant:
        maximal.append({"ngram": g, "df": d, "len": len(g)})
# 去掉互相包含的（保留 df 最大的最长者）
maximal.sort(key=lambda x: (-x["df"], -x["len"]))
top_ngrams = []
for m in maximal:
    if any(m["ngram"] in t["ngram"] for t in top_ngrams):
        continue
    top_ngrams.append(m)
    if len(top_ngrams) >= 60:
        break

# =========================================================
# 4. pros/cons/practice 近似重复
# =========================================================
def near_dups(items, thr=0.8):
    """items: list of (text, cell, field_pos). 返回 sim>thr 且不完全相同的对。"""
    n = len(items)
    counters = [Counter(t[0]) for t in items]
    res = []
    for i in range(n):
        ai, ca = items[i][0], counters[i]
        for j in range(i + 1, n):
            bj = items[j][0]
            if ai == bj:
                continue
            m = max(len(ai), len(bj))
            if abs(len(ai) - len(bj)) > (1 - thr) * m:
                continue
            cb = counters[j]
            lb_ = sum(abs(ca[k] - cb.get(k, 0)) for k in ca)
            lb_ += sum(v for k, v in cb.items() if k not in ca)
            if lb_ / 2 > (1 - thr) * m:
                continue
            cut = int((1 - thr) * m)
            d = lev(ai, bj, cutoff=cut)
            if d <= cut and d > 0:
                res.append({"a": ai, "b": bj, "cellA": items[i][1], "cellB": items[j][1],
                            "sim": round(1 - d / m, 4), "dist": d})
    res.sort(key=lambda x: -x["sim"])
    return res

listdup = {}
for f in LIST_FIELDS:
    items = []
    for c, p in by_cell.items():
        for k, it in enumerate(p[f]):
            items.append((it.strip(), c, k))
    texts = [t[0] for t in items]
    uniq = len(set(texts))
    nd = near_dups(items, 0.8)
    nd_strict = [x for x in nd if x["sim"] > 0.9]
    involved = set()
    for x in nd:
        involved.add(x["a"]); involved.add(x["b"])
    listdup[f] = {
        "n_items": len(items), "n_unique": uniq,
        "unique_rate": round(uniq / len(items), 4),
        "exact_dup_items": sum(1 for t, cnt in Counter(texts).items() if cnt > 1),
        "exact_dup_occurrences": sum(cnt for t, cnt in Counter(texts).items() if cnt > 1),
        "near_dup_pairs_gt80": len(nd),
        "near_dup_pairs_gt90": len(nd_strict),
        "distinct_items_involved": len(involved),
        "top20": nd[:20],
    }
    # 近似重复簇（>0.8 连通分量）
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry: parent[rx] = ry
    for x in nd:
        union(x["a"], x["b"])
    clus = defaultdict(set)
    for t in parent:
        clus[find(t)].add(t)
    big = sorted([sorted(v) for v in clus.values() if len(v) >= 3], key=lambda v: -len(v))
    listdup[f]["clusters_ge3"] = len(big)
    listdup[f]["top_clusters"] = big[:8]

# =========================================================
# 5. 「中」为主的格子 vs 高对比度格子
# =========================================================
HEDGE = ["可能", "往往", "容易", "一般", "有时", "大体", "多半", "取决于", "不太", "比较",
         "大概", "通常", "常常", "偏", "还行", "适度", "某种", "有点", "不至于", "既", "也不"]
CONCRETE_NOUN = ["消息", "清单", "日历", "闹钟", "微信", "聊天记录", "例会", "截止", "群", "纸",
                 "笔记", "邮件", "电话", "文档", "会议", "闹铃", "手机", "房间", "冰箱", "饭局",
                 "地铁", "床", "闹", "表格", "打卡", "工位", "红包", "朋友圈", "日程", "便签"]
NUM_RE = re.compile(r"[0-9]+|[一二三四五六七八九十半两]\s*(?:天|次|小时|分钟|周|月|年|句|条|个|件|遍|页|分)")

all_grams_df = defaultdict(int)
for c in by_cell:
    for g in gramsA[c]["_all"]:
        all_grams_df[g] += 1

def profile_metrics(c):
    p = by_cell[c]
    prose = "".join(p[f] for f in ALL_PROSE)
    clean = strip_punct(prose)
    gs = gramsA[c]["_all"]
    uniq_g = sum(1 for g in gs if all_grams_df[g] == 1)
    rare_g = sum(1 for g in gs if all_grams_df[g] <= 3)
    sims = [jaccard(gs, gramsA[o]["_all"]) for o in by_cell if o != c]
    practice_spec = sum(1 for it in p["practice"]
                        if NUM_RE.search(it) or any(w in it for w in CONCRETE_NOUN))
    return {
        "cell": c,
        "n_mid": p["cell"].count("中"),
        "chars_prose": len(clean),
        "chars_total": len(clean) + sum(len(strip_punct(x)) for f in LIST_FIELDS for x in p[f]),
        "type_token": round(len(set(clean)) / len(clean), 4),
        "uniq3_ratio": round(uniq_g / len(gs), 4),
        "rare3_ratio": round(rare_g / len(gs), 4),
        "mean_sim_all": round(sum(sims) / len(sims), 4),
        "mean_sim_neighbor": cell_sim_summary[c]["mean"],
        "max_sim_neighbor": cell_sim_summary[c]["max"],
        "hedge_per100": round(100 * sum(prose.count(w) for w in HEDGE) / len(clean), 3),
        "concrete_per100": round(100 * (len(NUM_RE.findall(prose)) +
                                        sum(prose.count(w) for w in CONCRETE_NOUN)) / len(clean), 3),
        "practice_specific": practice_spec,
    }

metrics = {c: profile_metrics(c) for c in by_cell}
METRIC_KEYS = ["chars_prose", "type_token", "uniq3_ratio", "rare3_ratio", "mean_sim_all",
               "mean_sim_neighbor", "max_sim_neighbor", "hedge_per100", "concrete_per100",
               "practice_specific"]

def group_stats(cells):
    out = {}
    for k in METRIC_KEYS:
        v = sorted(metrics[c][k] for c in cells)
        out[k] = {"mean": round(sum(v) / len(v), 4), "median": round(pct(v, .5), 4),
                  "min": round(v[0], 4), "max": round(v[-1], 4)}
    return out

mid_groups = defaultdict(list)
for c in by_cell:
    mid_groups[metrics[c]["n_mid"]].append(c)
G_mid = [c for c in by_cell if metrics[c]["n_mid"] >= 4]
G_con = [c for c in by_cell if metrics[c]["n_mid"] == 0]
G_rest = [c for c in by_cell if 1 <= metrics[c]["n_mid"] <= 3]

def perm_test(cells1, cells2, key, iters=20000):
    v1 = [metrics[c][key] for c in cells1]
    v2 = [metrics[c][key] for c in cells2]
    obs = sum(v1) / len(v1) - sum(v2) / len(v2)
    pool = v1 + v2
    r = random.Random(SEED)
    n1 = len(v1)
    cnt = 0
    for _ in range(iters):
        r.shuffle(pool)
        d = sum(pool[:n1]) / n1 - sum(pool[n1:]) / (len(pool) - n1)
        if abs(d) >= abs(obs) - 1e-12:
            cnt += 1
    # Cohen's d
    m1, m2 = sum(v1) / len(v1), sum(v2) / len(v2)
    def var(v, m): return sum((x - m) ** 2 for x in v) / max(len(v) - 1, 1)
    sp = ((var(v1, m1) * (len(v1) - 1) + var(v2, m2) * (len(v2) - 1)) /
          max(len(v1) + len(v2) - 2, 1)) ** .5
    return {"mean_mid4": round(m1, 4), "mean_contrast": round(m2, 4),
            "diff": round(obs, 4), "cohen_d": round((m1 - m2) / sp, 3) if sp else None,
            "p_perm": round(cnt / iters, 4)}

compare = {k: perm_test(G_mid, G_con, k) for k in METRIC_KEYS}
allmid = "O中C中E中A中N中"
ranks = {}
for k in METRIC_KEYS:
    order = sorted(by_cell, key=lambda c: metrics[c][k])
    ranks[k] = {"rank_asc_of_allmid": order.index(allmid) + 1, "n": 243}

# =========================================================
# 6. 基线校准：邻居 vs 非邻居（阈值 0.35/0.5 是否有区分力）
# =========================================================
cells_sorted = sorted(by_cell)
neighbor_key = {tuple(sorted([pr["a"], pr["b"]])) for pr in pairs}
gram2 = {c: ngrams(textA[c]["_all"], 2) for c in by_cell}
gram4 = {c: ngrams(textA[c]["_all"], 4) for c in by_cell}

nb_sim, far_sim = [], []
nb_ov, far_ov = [], []
nb_g2, far_g2 = [], []
nb_g4, far_g4 = [], []
hamming_sim = defaultdict(list)   # 格距离 -> sim 列表
for i in range(243):
    for j in range(i + 1, 243):
        a, b = cells_sorted[i], cells_sorted[j]
        s = jaccard(gramsA[a]["_all"], gramsA[b]["_all"])
        o = overlap_coef(gramsA[a]["_all"], gramsA[b]["_all"])
        g2 = jaccard(gram2[a], gram2[b])
        g4 = jaccard(gram4[a], gram4[b])
        # 曼哈顿档距
        dist = sum(abs(x - y) for x, y in zip(levels_of[a], levels_of[b]))
        hamming_sim[dist].append(s)
        if (a, b) in neighbor_key:
            nb_sim.append(s); nb_ov.append(o); nb_g2.append(g2); nb_g4.append(g4)
        else:
            far_sim.append(s); far_ov.append(o); far_g2.append(g2); far_g4.append(g4)

baseline = {
    "n_all_pairs": 243 * 242 // 2,
    "neighbor_3gram": dist_stats(nb_sim),
    "non_neighbor_3gram": dist_stats(far_sim),
    "neighbor_2gram": dist_stats(nb_g2),
    "non_neighbor_2gram": dist_stats(far_g2),
    "neighbor_4gram": dist_stats(nb_g4),
    "non_neighbor_4gram": dist_stats(far_g4),
    "neighbor_overlap_coef": dist_stats(nb_ov),
    "non_neighbor_overlap_coef": dist_stats(far_ov),
    "by_manhattan_distance_3gram": {str(k): dist_stats(v) for k, v in sorted(hamming_sim.items())},
    "ratio_neighbor_over_nonneighbor_median": round(
        dist_stats(nb_sim)["median"] / dist_stats(far_sim)["median"], 3),
    "note": ("字符 3-gram Jaccard 在中文长文本上天然偏小；0.35/0.5 的阈值必须和"
             "非邻居基线一起看，否则会把一切都判成 PASS。"),
}
# 用 2-gram（更宽松、更接近人的「读起来像」）复核阈值
statsA2 = dist_stats(nb_g2)
statsAov = dist_stats(nb_ov)

# =========================================================
# 7. 人工核读后补测：模板句式 & 更严的重写判据
# =========================================================
# 7a. 「维度名 + 让你」的句式密度（人读时发现的最明显结构性口癖）
RANGXING = re.compile(r"(开放性|尽责性|外向性|宜人性|神经质|开放|尽责|外向|宜人)让(你|我)?")
rang_counts = {c: len(RANGXING.findall("".join(by_cell[c][f] for f in ALL_PROSE))) for c in by_cell}
rang_hist = Counter(rang_counts.values())

# 7b. 「被批评 → 难受 N 天」模板：N 档差异的主要载体，检查它是否被过度复用
CRIT = re.compile(r"(被批评|批评|被否定|被质疑|被点名|被反驳|模糊的?反馈|含糊的?反馈|一句.{0,6}反馈)")
DUR = re.compile(r"(半天|一天|一整天|当天|一两天|两天|几天|好几天|一周|一整周|一晚上|整晚|一阵|很久|三天)")
crit_template = {}
for c in by_cell:
    hits = 0
    for f in ALL_PROSE:
        for s in SPLIT_RE.split(by_cell[c][f]):
            if CRIT.search(s) and DUR.search(s):
                hits += 1
    crit_template[c] = hits
crit_cells = sum(1 for v in crit_template.values() if v > 0)
dur_phrases = Counter()
for c in by_cell:
    for f in ALL_PROSE:
        for s in SPLIT_RE.split(by_cell[c][f]):
            if CRIT.search(s):
                for d in DUR.findall(s):
                    dur_phrases[d] += 1

# 7c. 严格重写判据（任一命中即入 rewriteList）
CRIT_SIM = 0.15          # 整体 3-gram Jaccard（非邻居基线中位数的 ~11 倍）
CRIT_FIELD = 0.40        # 任一字段
CRIT_NDCLAUSE = 4        # 近似重复分句条数
flagged = []
for pr in pairs:
    reasons = []
    if pr["simA"] >= CRIT_SIM:
        reasons.append(f"整体相似度 {pr['simA']:.3f} >= {CRIT_SIM}")
    if pr["maxFieldA"] >= CRIT_FIELD:
        reasons.append(f"{pr['maxFieldName']} 字段相似度 {pr['maxFieldA']:.3f} >= {CRIT_FIELD}")
    nd = pr.get("n_near_dup_clauses", 0)
    if nd >= CRIT_NDCLAUSE:
        reasons.append(f"近似重复分句 {nd} 条 >= {CRIT_NDCLAUSE}")
    if reasons:
        flagged.append({"a": pr["a"], "b": pr["b"], "dim": pr["dim"],
                        "simA": round(pr["simA"], 4), "maxField": pr["maxFieldName"],
                        "maxFieldSim": pr["maxFieldA"],
                        "nearDupClauses": nd, "reasons": reasons})
flagged.sort(key=lambda x: -x["simA"])
# 注意：近似分句只在 N/A/E 三组算过；O/C 两组未计算，标注清楚避免误读
flag_cells = Counter()
for x in flagged:
    flag_cells[x["a"]] += 1
    flag_cells[x["b"]] += 1
strict_rewrite = sorted(flag_cells, key=lambda c: (-flag_cells[c], c))

extra = {
    "dimension_name_formula": {
        "regex": "(维度名)让你",
        "profiles_with_at_least_one": sum(1 for v in rang_counts.values() if v),
        "share": round(sum(1 for v in rang_counts.values() if v) / 243, 4),
        "histogram_count_per_profile": {str(k): v for k, v in sorted(rang_hist.items())},
        "total_occurrences": sum(rang_counts.values()),
        "max_in_one_profile": max(rang_counts.values()),
    },
    "criticism_recovery_template": {
        "profiles_using_it": crit_cells,
        "share": round(crit_cells / 243, 4),
        "total_occurrences": sum(crit_template.values()),
        "duration_phrase_freq": dict(dur_phrases.most_common(20)),
        "note": ("这是 N 档差异的主要载体，本身合规（规格要求写恢复速度），"
                 "但同一句式覆盖面过大，读多格时会显得模板化。"),
    },
    "strict_flag_criteria": {"simA>=": CRIT_SIM, "any_field>=": CRIT_FIELD,
                             "near_dup_clauses>=": CRIT_NDCLAUSE,
                             "caveat": "近似分句只对 N/A/E 三组 486 对计算过，O/C 组未计算"},
    "flagged_pairs": flagged,
    "strict_rewrite_cells": strict_rewrite,
    "flag_count_per_cell": {c: flag_cells[c] for c in strict_rewrite},
}

# =========================================================
# 汇总 & 输出
# =========================================================
rewrite = set()
for pr in over_p5:
    rewrite.add(pr["a"]); rewrite.add(pr["b"])
for pr, f in field_over:
    rewrite.add(pr["a"]); rewrite.add(pr["b"])

report = {
    "meta": {"n_profiles": len(profiles), "n_neighbor_pairs": len(pairs),
             "cell_index_encoding_ok": idx_ok,
             "neighbors_per_cell": dict(Counter(neighbor_count.values())),
             "seed": SEED},
    "part1_neighbor_similarity": {
        "variantA_raw_stats": statsA,
        "variantB_stopword_removed_stats": statsB,
        "per_field_variantA": per_field_stats,
        "per_dim_variantA": per_dim_stats,
        "per_step_variantA": per_step_stats,
        "pairs_gt_0.5": len(over_p5),
        "pairs_gt_0.45": len(over_p45),
        "pairs_gt_0.35": len(over_p35),
        "p90_pass": statsA["p90"] < 0.35,
        "no_pair_over_0.5_pass": len(over_p5) == 0,
        "top25": [{"a": p["a"], "b": p["b"], "dim": p["dim"],
                   "step": f"{LVN[p['step'][0]]}->{LVN[p['step'][1]]}",
                   "simA": round(p["simA"], 4), "simB": round(p["simB"], 4),
                   "worst_field": p["maxFieldName"], "worst_field_sim": p["maxFieldA"],
                   "fields": p["fieldsA"]} for p in top25],
        "single_field_over_0.5": [{"a": p["a"], "b": p["b"], "field": f,
                                   "sim": p["fieldsA"][f]} for p, f in
                                  sorted(field_over, key=lambda x: -x[0]["fieldsA"][x[1]])[:20]],
        "worst_cells_by_mean_neighbor_sim": sorted(
            [{"cell": c, **v} for c, v in cell_sim_summary.items()],
            key=lambda x: -x["mean"])[:15],
    },
    "part2_dimension_drives_content": group_results,
    "part3_boilerplate": {
        "distinct_sentences": len(sent_index),
        "sentences_ge5_len_ge6": repeat_sents,
        "sentences_ge5_len_lt6": repeat_sents_short[:40],
        "repeat_list_items_ge5": repeat_list_items[:40],
        "top_ngrams_4to8": top_ngrams[:30],
        "top_ngrams_extra": top_ngrams[30:60],
    },
    "part4_list_near_dups": listdup,
    "part5_middle_cells": {
        "group_sizes": {str(k): len(v) for k, v in sorted(mid_groups.items())},
        "stats_by_n_mid": {str(k): group_stats(v) for k, v in sorted(mid_groups.items())},
        "mid4plus_cells": sorted(G_mid),
        "mid4plus": group_stats(G_mid),
        "contrast0": group_stats(G_con),
        "middle_1to3": group_stats(G_rest),
        "permutation_tests_mid4_vs_contrast0": compare,
        "allmid_cell_ranks": ranks,
        "allmid_metrics": metrics[allmid],
        "per_cell_metrics": [metrics[c] for c in sorted(by_cell, key=lambda c: -metrics[c]["n_mid"])],
    },
    "part6_baseline_calibration": baseline,
    "part7_templates_and_strict_flags": extra,
    "rewriteList_candidates_loose_0.5field": sorted(rewrite),
    "rewriteList_strict": strict_rewrite,
}

json.dump(report, open(os.path.join(OUT, "qa2_distinct.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ---------- 人读摘要 ----------
L = []
def w(s=""): L.append(str(s))
w("=" * 78)
w("qa2_distinct —— 区分度体检")
w("=" * 78)
w(f"画像 {len(profiles)}，邻居对 {len(pairs)}（每格邻居数分布 {dict(Counter(neighbor_count.values()))}）")
w(f"cell 编码与 index=O*81+C*27+E*9+A*3+N 一致: {idx_ok}")
w("")
w("--- 1. 邻居相似度（字符 3-gram Jaccard，5 字段拼接）---")
w(f"变体A（仅去标点）      : {statsA}")
w(f"变体B（再剔停用词+维度名）: {statsB}")
w(f"p90 < 0.35 ? {statsA['p90']:.4f} -> {'PASS' if statsA['p90']<0.35 else 'FAIL'}")
w(f">0.5 的对: {len(over_p5)}   >0.45: {len(over_p45)}   >0.35: {len(over_p35)}")
w("按字段:")
for f in PROSE:
    s = per_field_stats[f]
    w(f"  {f:8s} median={s['median']:.3f} p90={s['p90']:.3f} p99={s['p99']:.3f} max={s['max']:.3f}")
w("按差异维度:")
for d in DIMS:
    s = per_dim_stats[d]
    w(f"  {d} median={s['median']:.3f} p90={s['p90']:.3f} max={s['max']:.3f}")
w("按档位跨度:")
for k, s in per_step_stats.items():
    w(f"  {k:10s} median={s['median']:.3f} p90={s['p90']:.3f} max={s['max']:.3f}")
w("Top 25 最相似邻居对:")
for i, p in enumerate(top25, 1):
    w(f"  {i:2d}. {p['a']} | {p['b']}  ({p['dim']} {LVN[p['step'][0]]}→{LVN[p['step'][1]]})"
      f"  simA={p['simA']:.3f} simB={p['simB']:.3f}  最像字段={p['maxFieldName']}({p['maxFieldA']:.3f})")
w("单字段 >0.5 的对（前 20）:")
for x in report["part1_neighbor_similarity"]["single_field_over_0.5"]:
    w(f"  {x['a']} | {x['b']}  [{x['field']}] {x['sim']:.3f}")
w("")
w("--- 2. 差异维度是否驱动内容（自动信号）---")
for d in ["N", "A", "E"]:
    g = group_results[d]
    w(f"  只差 {d}: {g['n_pairs']} 对，聚焦字段 {g['focus_fields']}")
    w(f"    聚焦字段相似度 {g['focus_sim_stats']}")
    w(f"    词表命中差异个数 {g['lex_diff_stats']}")
    w(f"    存在完全相同分句的对: {g['pairs_with_shared_sentence']}"
      f"（其中分句>=6字: {g['pairs_with_shared_sentence_len6+']}）")
    w(f"    存在「近似重复分句」(编辑相似>0.6) 的对: {g['pairs_with_near_dup_clause']}"
      f"  每对条数 {g['near_dup_clause_stats']}")
    for x in g["worst_by_near_dup_clause"][:5]:
        w(f"      {x['a']} | {x['b']}  近重分句 {x['n']} 条")
        for e in x["examples"][:2]:
            w(f"        ~{e['sim']} 「{e['a']}」 / 「{e['b']}」")
w("")
w("--- 6. 基线校准（邻居 vs 非邻居）---")
w(f"邻居对 3-gram Jaccard   : {baseline['neighbor_3gram']}")
w(f"非邻居对 3-gram Jaccard : {baseline['non_neighbor_3gram']}")
w(f"中位数比值 邻居/非邻居 = {baseline['ratio_neighbor_over_nonneighbor_median']}")
w(f"邻居 2-gram: {baseline['neighbor_2gram']}   非邻居 2-gram: {baseline['non_neighbor_2gram']}")
w(f"邻居 4-gram: {baseline['neighbor_4gram']}   非邻居 4-gram: {baseline['non_neighbor_4gram']}")
w(f"邻居 包含系数: {baseline['neighbor_overlap_coef']}  非邻居 包含系数: {baseline['non_neighbor_overlap_coef']}")
w("按档距（曼哈顿）:")
for k, v in baseline["by_manhattan_distance_3gram"].items():
    w(f"  距离{k}: n={v['n']:5d} median={v['median']:.4f} p90={v['p90']:.4f} max={v['max']:.4f}")
w("")
w("--- 3. 套话 ---")
w(f"不同句子总数 {len(sent_index)}；出现 >=5 次且长度 >=6 的句子: {len(repeat_sents)}")
for s in repeat_sents[:40]:
    w(f"  x{s['count']:3d} 覆盖{s['cells']:3d}格 [{','.join(s['fields'])}] {s['sentence']}")
w(f"短句(<6字)出现 >=5 次: {len(repeat_sents_short)}（前 20）")
for s in repeat_sents_short[:20]:
    w(f"  x{s['count']:3d} 覆盖{s['cells']:3d}格 {s['sentence']}")
w(f"列表字段中重复 >=5 次的整条: {len(repeat_list_items)}")
for s in repeat_list_items[:20]:
    w(f"  x{s['count']:3d} {s['field']} {s['item']}")
w("最像套话的 4-8 字 n-gram（df = 出现该串的画像数，共 243）:")
for i, g in enumerate(top_ngrams[:30], 1):
    w(f"  {i:2d}. df={g['df']:3d} ({g['df']/243*100:4.1f}%) {g['ngram']}")
w("")
w("--- 4. pros/cons/practice 近似重复 ---")
for f in LIST_FIELDS:
    d = listdup[f]
    w(f"  {f}: {d['n_items']} 条，唯一 {d['n_unique']}（{d['unique_rate']*100:.1f}%），"
      f"完全重复条目 {d['exact_dup_items']} 个；近似对(>0.8) {d['near_dup_pairs_gt80']}，"
      f"(>0.9) {d['near_dup_pairs_gt90']}，涉及不同条目 {d['distinct_items_involved']}，"
      f"簇(>=3条) {d['clusters_ge3']}")
    for x in d["top20"]:
        w(f"     {x['sim']:.3f} | {x['a']}  <->  {x['b']}   ({x['cellA']} / {x['cellB']})")
w("")
w("--- 5. 中间档格子 ---")
w(f"分组大小 {report['part5_middle_cells']['group_sizes']}")
w(f"以中为主(>=4 中, n={len(G_mid)}) vs 无中(0 中, n={len(G_con)}):")
for k in METRIC_KEYS:
    c = compare[k]
    w(f"  {k:20s} mid4={c['mean_mid4']:>9} contrast0={c['mean_contrast']:>9} "
      f"d={c['cohen_d']} p={c['p_perm']}")
w("全中格 O中C中E中A中N中 的指标: " + json.dumps(metrics[allmid], ensure_ascii=False))
w("全中格在 243 格中的升序排名: " + json.dumps(ranks, ensure_ascii=False))
w("")
w("--- 7. 模板句式 & 严格重写判据 ---")
d7 = extra["dimension_name_formula"]
w(f"「维度名+让你」句式：{d7['profiles_with_at_least_one']}/243 篇用过（{d7['share']*100:.1f}%），"
  f"共 {d7['total_occurrences']} 次，单篇最多 {d7['max_in_one_profile']} 次")
w(f"  每篇次数分布 {d7['histogram_count_per_profile']}")
d7b = extra["criticism_recovery_template"]
w(f"「批评/反馈 + 恢复时长」模板：{d7b['profiles_using_it']}/243 篇（{d7b['share']*100:.1f}%），"
  f"共 {d7b['total_occurrences']} 处")
w(f"  时长词频 {d7b['duration_phrase_freq']}")
w(f"严格判据命中的邻居对: {len(flagged)} / 810")
for x in flagged[:30]:
    w(f"  {x['a']} | {x['b']} ({x['dim']}) simA={x['simA']:.3f} "
      f"{x['maxField']}={x['maxFieldSim']:.3f} 近重分句={x['nearDupClauses']}  <- {'; '.join(x['reasons'])}")
w(f"严格 rewriteList（{len(strict_rewrite)} 格，按被点次数排序）:")
for c in strict_rewrite:
    w(f"  {c}  被点 {flag_cells[c]} 次")
w("")
w(f"宽松 rewriteList（仅单字段 >0.5）: {sorted(rewrite)}")
open(os.path.join(OUT, "qa2_distinct_report.txt"), "w", encoding="utf-8").write("\n".join(L))
print("\n".join(L))

