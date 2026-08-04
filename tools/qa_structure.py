# -*- coding: utf-8 -*-
"""QA: structural / spec-conformance check for the 243 personality profiles.

Checks (per the brief):
  1. coverage      -- 243 cells present, no dupes, names match "O?C?E?A?N?" with 低/中/高
  2. length        -- per-field CJK char counts vs spec bands
  3. practice      -- executability scan (bans "要多沟通"-class filler)
  4. interaction   -- summary must reference >=2 dimensions (keyword heuristic)
  5. pack          -- sort by index O*81+C*27+E*9+A*3+N, drop cell, measure raw/gzip/brotli

Input : tools/out/profiles_raw.json   (array of 243 objects)
Output: tools/out/profiles_ordered.json  (only written with --write, and only if
        coverage passes and the input is not placeholder text)

Run:  python tools/qa_structure.py [--write]
"""
import gzip
import io
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RAW = os.path.join(OUT, "profiles_raw.json")
ORDERED = os.path.join(OUT, "profiles_ordered.json")

LV = {"低": 0, "中": 1, "高": 2}
KEYS = ["O", "C", "E", "A", "N"]
CELL_RE = re.compile(r"^O([低中高])C([低中高])E([低中高])A([低中高])N([低中高])$")

STR_FIELDS = ["lead", "summary", "life", "friends", "love", "work"]
LIST_FIELDS = ["pros", "cons", "practice"]
ALL_FIELDS = STR_FIELDS + LIST_FIELDS

# spec bands, on CJK-char count (punctuation excluded)
BANDS = {
    "lead": (18, 28),
    "summary": (110, 160),
    "life": (80, 120),
    "friends": (80, 120),
    "love": (80, 120),
    "work": (80, 120),
    "pros": (8, 20),      # per item
    "cons": (8, 20),      # per item
    "practice": (20, 45),  # per item
}

CJK = re.compile(r"[一-鿿]")
# "含标点" count: everything that isn't whitespace
NONSPACE = re.compile(r"\S")


def n_cjk(s):
    return len(CJK.findall(s))


def n_with_punct(s):
    return len(NONSPACE.findall(s))


# ---------------------------------------------------------------- 1. coverage
def all_cells():
    cells = []
    for o in "低中高":
        for c in "低中高":
            for e in "低中高":
                for a in "低中高":
                    for n in "低中高":
                        cells.append("O%sC%sE%sA%sN%s" % (o, c, e, a, n))
    return cells


def cell_index(cell):
    m = CELL_RE.match(cell)
    o, c, e, a, n = [LV[g] for g in m.groups()]
    return o * 81 + c * 27 + e * 9 + a * 3 + n


def check_coverage(profiles):
    seen, dupes, malformed = {}, [], []
    for i, p in enumerate(profiles):
        cell = p.get("cell")
        if not isinstance(cell, str) or not CELL_RE.match(cell or ""):
            malformed.append((i, repr(cell)))
            continue
        if cell in seen:
            dupes.append((cell, seen[cell], i))
        else:
            seen[cell] = i
    missing = [c for c in all_cells() if c not in seen]
    return {"n_input": len(profiles), "n_valid_unique": len(seen),
            "missing": missing, "dupes": dupes, "malformed": malformed}


# ------------------------------------------------------------------ 2. length
def check_lengths(profiles):
    per_field = {f: [] for f in ALL_FIELDS}   # (cell, cjk, punct, idx_in_list)
    violations = []
    missing_fields = []
    for p in profiles:
        cell = p.get("cell", "?")
        for f in STR_FIELDS:
            v = p.get(f)
            if not isinstance(v, str) or not v.strip():
                missing_fields.append((cell, f))
                continue
            c, w = n_cjk(v), n_with_punct(v)
            per_field[f].append((cell, c, w, None))
            lo, hi = BANDS[f]
            if c < lo or c > hi:
                violations.append({"cell": cell, "field": f, "item": None,
                                   "chars": c, "band": [lo, hi],
                                   "delta": (lo - c) if c < lo else (c - hi)})
        for f in LIST_FIELDS:
            v = p.get(f)
            if not isinstance(v, list) or len(v) == 0:
                missing_fields.append((cell, f))
                continue
            if len(v) != 3:
                violations.append({"cell": cell, "field": f, "item": "count",
                                   "chars": len(v), "band": [3, 3],
                                   "delta": abs(len(v) - 3)})
            for j, item in enumerate(v):
                if not isinstance(item, str) or not item.strip():
                    missing_fields.append((cell, "%s[%d]" % (f, j)))
                    continue
                c, w = n_cjk(item), n_with_punct(item)
                per_field[f].append((cell, c, w, j))
                lo, hi = BANDS[f]
                if c < lo or c > hi:
                    violations.append({"cell": cell, "field": f, "item": j,
                                       "chars": c, "band": [lo, hi],
                                       "delta": (lo - c) if c < lo else (c - hi)})

    stats = {}
    for f in ALL_FIELDS:
        rows = per_field[f]
        if not rows:
            stats[f] = None
            continue
        cjk = sorted(r[1] for r in rows)
        pun = sorted(r[2] for r in rows)
        lo, hi = BANDS[f]
        oob = sum(1 for x in cjk if x < lo or x > hi)
        stats[f] = {
            "n": len(cjk), "band": [lo, hi],
            "cjk_min": cjk[0], "cjk_median": int(statistics.median(cjk)), "cjk_max": cjk[-1],
            "punct_min": pun[0], "punct_median": int(statistics.median(pun)), "punct_max": pun[-1],
            "out_of_band": oob, "out_of_band_pct": round(100.0 * oob / len(cjk), 1),
        }
    violations.sort(key=lambda d: -d["delta"])
    return {"stats": stats, "violations": violations,
            "missing_fields": missing_fields}


# ---------------------------------------------------------------- 3. practice
# Filler that names no observable action. Spec: must be an executable concrete act.
FILLER_PATTERNS = [
    r"多沟通", r"多交流", r"多聊聊", r"好好沟通", r"注意沟通",
    r"学会放松", r"放松心情", r"适当放松", r"注意放松",
    r"保持心态", r"调整心态", r"放平心态", r"摆正心态", r"端正心态",
    r"保持乐观", r"积极面对", r"乐观面对", r"保持积极", r"保持自信",
    r"多点耐心", r"保持耐心", r"耐心一点",
    r"注意休息", r"好好休息", r"多休息", r"劳逸结合",
    r"提高效率", r"提升自己", r"完善自己", r"充实自己",
    r"顺其自然", r"想开一点", r"看开一点", r"别想太多", r"不要想太多",
    r"相信自己", r"做好自己", r"坚持下去", r"持之以恒",
    r"培养.{0,4}习惯$", r"养成.{0,4}习惯$",
    r"加强.{0,6}$", r"增强.{0,6}$", r"提高.{0,6}能力$",
    r"学会.{0,4}$",
    r"占位",
]
FILLER_RE = [(p, re.compile(p)) for p in FILLER_PATTERNS]

# concreteness markers: a real action has a hook -- a number, a time, an artifact,
# or an imperative verb attached to a thing.
CONCRETE_RE = re.compile(
    r"[0-9０-９]|"
    r"每天|每周|每月|每次|隔天|隔\s*[0-9０-９]|当天|睡前|早上|晚上|周[一二三四五六日末]|"
    r"分钟|小时|天内|秒|"
    r"写下|记下|列出|列一|写一|发一|问一|说一句|读出来|打一通|设一个|定一个|建一个|"
    r"存到|存进|放进|加到|贴在|挂在|摆在|"
    r"清单|便签|备忘|日历|闹钟|提醒|计时|表格|文档|草稿|"
    r"删掉|退出|关掉|拉黑|静音|取消|推迟|延后|提前|"
    r"先.{1,8}再|不要.{1,10}直到|直到.{1,10}才"
)


def check_practice(profiles):
    bad = []
    total = 0
    for p in profiles:
        cell = p.get("cell", "?")
        items = p.get("practice")
        if not isinstance(items, list):
            continue
        for j, it in enumerate(items):
            if not isinstance(it, str):
                continue
            total += 1
            hits = [pat for pat, rx in FILLER_RE if rx.search(it)]
            concrete = bool(CONCRETE_RE.search(it))
            if hits or not concrete:
                bad.append({"cell": cell, "item": j, "text": it,
                            "filler_hits": hits,
                            "has_concrete_marker": concrete,
                            "reason": "filler phrase" if hits else "no concrete action marker"})
    return {"total": total, "bad": bad,
            "bad_pct": round(100.0 * len(bad) / total, 1) if total else None}


# ------------------------------------------------------------- 4. interaction
# A summary satisfies the spec if it invokes >=2 distinct dimensions, by proper
# name or by an unambiguous behavioural proxy for that dimension.
DIM_TERMS = {
    "O": ["开放性", "好奇", "新鲜感", "新想法", "抽象", "审美", "想象",
          "务实", "熟悉的", "经过验证", "新奇"],
    "C": ["尽责性", "计划性", "条理", "自律", "拖延", "收尾", "守时",
          "目标导向", "有序", "随性", "执行力"],
    "E": ["外向性", "社交", "独处", "人群", "热闹", "话多", "话少",
          "主动搭话", "社交后", "补充能量", "安静"],
    "A": ["宜人性", "让步", "配合", "体谅", "温和", "直率", "冲突",
          "对抗", "以关系为先", "不肯先退", "照顾别人", "顺从"],
    "N": ["神经质", "情绪起伏", "反刍", "焦躁", "自责", "敏感", "抗压",
          "情绪平稳", "紧张", "情绪上来", "越想越"],
}


def dims_in(text):
    found = set()
    for d, terms in DIM_TERMS.items():
        for t in terms:
            if t in text:
                found.add(d)
                break
    return found


def check_interaction(profiles):
    weak = []
    counts = []
    for p in profiles:
        cell = p.get("cell", "?")
        s = p.get("summary")
        if not isinstance(s, str):
            continue
        d = dims_in(s)
        counts.append(len(d))
        if len(d) < 2:
            weak.append({"cell": cell, "dims_found": sorted(d), "summary": s})
    n = len(counts)
    return {"n": n, "weak": weak,
            "weak_pct": round(100.0 * len(weak) / n, 1) if n else None,
            "mean_dims": round(sum(counts) / float(n), 2) if n else None}


# ------------------------------------------------------- 4b. hard prohibitions
# profile_spec.md section 硬性禁止. These are absolute -- any hit is a blocker.
BANNED = {
    "determinism": ["你天生", "你注定", "你就是一个", "你生来", "命中注定"],
    "identity_label": ["内向者", "外向者", "内向的人天生", "社恐", "社牛"],
    "clinical": ["抑郁症", "焦虑症", "多动症", "ADHD", "自闭", "阿斯伯格",
                 "强迫症", "双相", "躁郁", "人格障碍", "心理疾病", "精神疾病"],
    "horoscope": ["星座", "命理", "运势", "天赋异禀", "得天独厚"],
}
# type-naming ban: a coined "XX型" label (spec forbids inventing type names)
TYPE_NAME_RE = re.compile(r"[一-鿿]{2,6}型(?![号式])")


def check_bans(profiles):
    hits = []
    for p in profiles:
        cell = p.get("cell", "?")
        for f in ALL_FIELDS:
            v = p.get(f)
            texts = v if isinstance(v, list) else [v]
            for j, t in enumerate(texts):
                if not isinstance(t, str):
                    continue
                for cat, words in BANNED.items():
                    for w in words:
                        if w in t:
                            hits.append({"cell": cell, "field": f,
                                         "item": j if isinstance(v, list) else None,
                                         "category": cat, "phrase": w,
                                         "text": t[:60]})
                for m in TYPE_NAME_RE.findall(t):
                    hits.append({"cell": cell, "field": f,
                                 "item": j if isinstance(v, list) else None,
                                 "category": "coined_type_name", "phrase": m,
                                 "text": t[:60]})
    return {"hits": hits, "n": len(hits)}


# -------------------------------------------------------------------- 5. pack
def pack(profiles, write=False):
    ordered = sorted(profiles, key=lambda p: cell_index(p["cell"]))
    stripped = [{k: v for k, v in p.items() if k != "cell"} for p in ordered]
    blob = json.dumps(stripped, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = gzip.compress(blob, 9)
    try:
        import brotli
        br = brotli.compress(blob, quality=11)
        br_n = len(br)
    except ImportError:
        br_n = None
    if write:
        io.open(ORDERED, "wb").write(blob)
    return {"n": len(stripped), "raw_utf8": len(blob), "gzip": len(gz), "brotli": br_n,
            "written": bool(write)}


# -------------------------------------------------------------------- driver
def main():
    write = "--write" in sys.argv

    src = RAW
    placeholder = False
    if not os.path.exists(RAW):
        print("!! FATAL: input not found: %s" % RAW)
        if os.path.exists(ORDERED):
            print("!! Falling back to %s for diagnostics only." % ORDERED)
            src = ORDERED
        else:
            print("!! No fallback either. Nothing to check.")
            return 2

    profiles = json.load(io.open(src, encoding="utf-8"))
    print("loaded %d objects from %s" % (len(profiles), os.path.basename(src)))

    # placeholder sniff
    blob = json.dumps(profiles, ensure_ascii=False)
    ph_hits = blob.count("占位")
    if ph_hits:
        placeholder = True
        print("!! PLACEHOLDER CONTENT DETECTED: '占位' appears %d times." % ph_hits)

    # if we fell back to ordered (no cell field), synthesize cells by position
    if profiles and "cell" not in profiles[0]:
        print("!! no 'cell' field; synthesizing from array position (index encoding)")
        cs = all_cells()
        cs.sort(key=cell_index)
        for i, p in enumerate(profiles):
            p["cell"] = cs[i] if i < len(cs) else "?"

    rep = {}
    rep["coverage"] = check_coverage(profiles)
    rep["length"] = check_lengths(profiles)
    rep["practice"] = check_practice(profiles)
    rep["interaction"] = check_interaction(profiles)

    cov = rep["coverage"]
    print("\n== 1. COVERAGE ==")
    print("  input=%d  valid+unique=%d  missing=%d  dupes=%d  malformed=%d"
          % (cov["n_input"], cov["n_valid_unique"], len(cov["missing"]),
             len(cov["dupes"]), len(cov["malformed"])))
    if cov["missing"]:
        print("  missing sample: %s" % ", ".join(cov["missing"][:10]))
    if cov["malformed"]:
        print("  malformed sample: %s" % cov["malformed"][:5])

    print("\n== 2. LENGTH (CJK chars; punct-inclusive in parens) ==")
    print("  %-9s %-9s %-22s %-22s %s" % ("field", "band", "cjk min/med/max",
                                          "punct min/med/max", "out-of-band"))
    for f in ALL_FIELDS:
        s = rep["length"]["stats"][f]
        if not s:
            print("  %-9s  -- no data --" % f)
            continue
        print("  %-9s %-9s %-22s %-22s %d/%d (%.1f%%)"
              % (f, "%d-%d" % tuple(s["band"]),
                 "%d/%d/%d" % (s["cjk_min"], s["cjk_median"], s["cjk_max"]),
                 "%d/%d/%d" % (s["punct_min"], s["punct_median"], s["punct_max"]),
                 s["out_of_band"], s["n"], s["out_of_band_pct"]))
    v = rep["length"]["violations"]
    print("  total violations: %d" % len(v))
    print("  --- worst 20 ---")
    for x in v[:20]:
        print("   %-16s %-9s item=%-5s chars=%-4d band=%s  off_by=%d"
              % (x["cell"], x["field"], x["item"], x["chars"], x["band"], x["delta"]))

    pr = rep["practice"]
    print("\n== 3. PRACTICE EXECUTABILITY ==")
    print("  items=%s  failing=%d (%s%%)" % (pr["total"], len(pr["bad"]), pr["bad_pct"]))
    for x in pr["bad"][:25]:
        print("   %-16s [%s] %-28s %s" % (x["cell"], x["item"], x["reason"], x["text"][:40]))

    it = rep["interaction"]
    print("\n== 4. SUMMARY DIMENSION INTERACTION ==")
    print("  summaries=%d  mean dims mentioned=%s  <2 dims=%d (%s%%)"
          % (it["n"], it["mean_dims"], len(it["weak"]), it["weak_pct"]))
    for x in it["weak"][:15]:
        print("   %-16s dims=%-12s %s" % (x["cell"], ",".join(x["dims_found"]) or "-",
                                          x["summary"][:44]))

    rep["bans"] = check_bans(profiles)
    bn = rep["bans"]
    print("\n== 4b. HARD PROHIBITIONS (spec 硬性禁止) ==")
    print("  violations=%d" % bn["n"])
    for x in bn["hits"][:20]:
        print("   %-16s %-9s %-18s '%s'  %s"
              % (x["cell"], x["field"], x["category"], x["phrase"], x["text"][:34]))

    print("\n== 5. PACK ==")
    blocked = (placeholder or cov["missing"] or cov["dupes"] or cov["malformed"]
               or bn["n"])
    if blocked and write:
        print("  REFUSING --write: coverage failed or content is placeholder.")
        write = False
    pk = pack(profiles, write=write)
    rep["pack"] = pk
    kb = lambda n: "%s B (%.1f KB)" % ("{:,}".format(n), n / 1024.0)
    print("  entries=%d" % pk["n"])
    print("  raw utf-8 : %s" % kb(pk["raw_utf8"]))
    print("  gzip -9   : %s" % kb(pk["gzip"]))
    print("  brotli q11: %s" % (kb(pk["brotli"]) if pk["brotli"] else "brotli module missing"))
    if placeholder:
        print("  !! sizes are NOT representative -- placeholder text is highly repetitive,")
        print("  !! so gzip/brotli ratios here are wildly optimistic vs real prose.")
    print("  written: %s" % pk["written"])

    io.open(os.path.join(OUT, "qa_structure_report.json"), "w", encoding="utf-8").write(
        json.dumps(rep, ensure_ascii=False, indent=1))
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
