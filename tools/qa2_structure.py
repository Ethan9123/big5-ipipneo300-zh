# -*- coding: utf-8 -*-
"""
qa2_structure.py —— 结构与规格符合度 + 打包体积
只读：不修改 profiles_raw.json / profile_spec.md / site/ 下任何文件。
所有临时文件写到 scratchpad。
"""
import json, os, re, gzip, io, shutil, sys, unicodedata, statistics, tempfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "tools", "out", "profiles_raw.json")
ORDERED = os.path.join(ROOT, "tools", "out", "profiles_ordered.json")
SITE = os.path.join(ROOT, "site")
SCRATCH = r"~\AppData\Local\Temp\claude\<project>\3f3dea16-3b73-4559-8359-8360df8000b2\scratchpad"
os.makedirs(SCRATCH, exist_ok=True)
OUTJSON = os.path.join(SCRATCH, "qa2_structure_report.json")

LEVELS = ["低", "中", "高"]
DIMS = ["O", "C", "E", "A", "N"]
DIMNAME = {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"}

SPEC = {  # field -> (lo, hi, per_item?)
    "lead": (18, 28, False),
    "summary": (110, 160, False),
    "life": (80, 120, False),
    "friends": (80, 120, False),
    "love": (80, 120, False),
    "work": (80, 120, False),
    "pros": (8, 20, True),
    "cons": (8, 20, True),
    "practice": (20, 45, True),
}
FIELDS = list(SPEC.keys())

report = {}


# ---------------------------------------------------------------- 计数工具
def is_punct(ch):
    if ch.isspace():
        return True
    cat = unicodedata.category(ch)
    return cat.startswith("P") or cat.startswith("S") or cat in ("Zs", "Cf")


def n_all(s):
    """含标点：去掉空白后的全部可见字符数"""
    return sum(1 for ch in s if not ch.isspace())


def n_np(s):
    """不含标点：剔除标点/符号后的字符数"""
    return sum(1 for ch in s if not is_punct(ch))


# ---------------------------------------------------------------- 载入
raw = json.load(open(RAW, encoding="utf-8"))
ordered = json.load(open(ORDERED, encoding="utf-8"))

# ================================================================ 1 完整性
comp = {"n_raw": len(raw), "n_ordered": len(ordered), "errors": []}
CELL_RE = re.compile(r"^O([低中高])C([低中高])E([低中高])A([低中高])N([低中高])$")

cells = []
for i, p in enumerate(raw):
    c = p.get("cell")
    if not isinstance(c, str):
        comp["errors"].append({"idx": i, "kind": "cell缺失/非字符串", "got": repr(c)})
        cells.append(None)
        continue
    cells.append(c)
    m = CELL_RE.match(c)
    if not m:
        comp["errors"].append({"idx": i, "kind": "命名不合规", "cell": c})
        continue
    b = [LEVELS.index(g) for g in m.groups()]
    want = b[0] * 81 + b[1] * 27 + b[2] * 9 + b[3] * 3 + b[4]
    if want != i:
        comp["errors"].append({"idx": i, "kind": "索引不一致", "cell": c, "expect_idx": want})

from collections import Counter
dup = {c: n for c, n in Counter([c for c in cells if c]).items() if n > 1}
comp["duplicates"] = dup
# 全集覆盖
allcells = set()
for o in LEVELS:
    for c in LEVELS:
        for e in LEVELS:
            for a in LEVELS:
                for n in LEVELS:
                    allcells.add(f"O{o}C{c}E{e}A{a}N{n}")
comp["missing"] = sorted(allcells - set(x for x in cells if x))
comp["extra"] = sorted(set(x for x in cells if x) - allcells)
comp["ok"] = (len(raw) == 243 and not comp["errors"] and not dup
              and not comp["missing"] and not comp["extra"])

# ordered 与 raw 的字段一致性（去掉 cell 后应逐条相等）
ord_mismatch = []
for i in range(min(len(raw), len(ordered))):
    a = {k: v for k, v in raw[i].items() if k != "cell"}
    b = dict(ordered[i])
    if a != b:
        diff = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
        ord_mismatch.append({"idx": i, "cell": cells[i], "fields": diff})
comp["ordered_has_cell_field"] = any("cell" in o for o in ordered)
comp["ordered_vs_raw_mismatch"] = ord_mismatch[:20]
comp["ordered_vs_raw_mismatch_n"] = len(ord_mismatch)

# 字段缺失/空
fieldprob = []
for i, p in enumerate(raw):
    for f in FIELDS:
        v = p.get(f)
        if v is None:
            fieldprob.append({"cell": cells[i], "field": f, "kind": "缺失"})
        elif SPEC[f][2]:
            if not isinstance(v, list) or len(v) != 3:
                fieldprob.append({"cell": cells[i], "field": f, "kind": f"非3元素列表(len={len(v) if isinstance(v,list) else 'NA'})"})
            elif any((not isinstance(x, str)) or not x.strip() for x in v):
                fieldprob.append({"cell": cells[i], "field": f, "kind": "有空条目"})
        else:
            if not isinstance(v, str) or not v.strip():
                fieldprob.append({"cell": cells[i], "field": f, "kind": "空字符串"})
comp["field_problems"] = fieldprob
report["completeness"] = comp

# ================================================================ 2 字数
def collect(metric):
    """metric: 'all' 含标点 / 'np' 不含标点 -> {field: [(cell, idx_in_list, count)]}"""
    fn = n_all if metric == "all" else n_np
    d = {}
    for f in FIELDS:
        rows = []
        for i, p in enumerate(raw):
            v = p.get(f)
            if SPEC[f][2]:
                if isinstance(v, list):
                    for j, x in enumerate(v):
                        if isinstance(x, str):
                            rows.append((cells[i], j, fn(x)))
            else:
                if isinstance(v, str):
                    rows.append((cells[i], None, fn(v)))
        d[f] = rows
    return d


def sev(cnt, lo, hi):
    """返回 (是否越界, 相对偏离比例, 等级)"""
    if lo <= cnt <= hi:
        return False, 0.0, "ok"
    if cnt < lo:
        rel = (lo - cnt) / lo
    else:
        rel = (cnt - hi) / hi
    if rel > 0.25:
        lvl = "严重"
    elif rel <= 0.10:
        lvl = "轻微"
    else:
        lvl = "中度"
    return True, rel, lvl


length = {}
for metric in ("all", "np"):
    data = collect(metric)
    per = {}
    viols = []
    for f, rows in data.items():
        lo, hi = SPEC[f][0], SPEC[f][1]
        counts = [r[2] for r in rows]
        cnt_v = {"轻微": 0, "中度": 0, "严重": 0}
        under = over = 0
        for cell, j, c in rows:
            bad, rel, lvl = sev(c, lo, hi)
            if bad:
                cnt_v[lvl] += 1
                if c < lo:
                    under += 1
                else:
                    over += 1
                viols.append({"cell": cell, "field": f, "item": j, "count": c,
                              "spec": [lo, hi], "rel": round(rel, 4), "level": lvl,
                              "dir": "偏短" if c < lo else "偏长"})
        per[f] = {
            "spec": [lo, hi], "n": len(rows),
            "min": min(counts), "p25": int(statistics.quantiles(counts, n=4)[0]),
            "median": statistics.median(counts),
            "p75": int(statistics.quantiles(counts, n=4)[2]), "max": max(counts),
            "mean": round(statistics.mean(counts), 1),
            "n_viol": sum(cnt_v.values()),
            "pct_viol": round(100 * sum(cnt_v.values()) / len(rows), 1),
            "under": under, "over": over,
            "轻微": cnt_v["轻微"], "中度": cnt_v["中度"], "严重": cnt_v["严重"],
        }
    viols.sort(key=lambda x: -x["rel"])
    length[metric] = {"per_field": per, "n_viol_total": len(viols),
                      "n_units_total": sum(len(v) for v in data.values()),
                      "top25": viols[:25], "all_viol": viols}

# 有多少个 profile 至少有一处越界
for metric in ("all", "np"):
    bad_cells = set(v["cell"] for v in length[metric]["all_viol"])
    length[metric]["profiles_with_any_violation"] = len(bad_cells)
report["length"] = length

# ================================================================ 3 practice 可执行性
VAGUE = [
    "要多沟通", "多沟通", "学会放松", "保持心态", "保持好心态", "多注意", "试着改变",
    "调整心态", "放平心态", "摆正心态", "积极面对", "保持积极", "多多益善",
    "学会拒绝", "学会表达", "学会倾听", "多关心", "多理解", "多包容", "多体谅",
    "增强自信", "提升自信", "培养兴趣", "多运动", "注意休息", "早睡早起",
    "多读书", "多思考", "放松心情", "保持乐观", "凡事想开", "顺其自然",
    "提高效率", "加强管理", "注重细节", "适当放松", "适度", "尽量",
    "试着去", "努力去", "学着", "尝试着", "多一点", "少一点",
]
# 具体性证据：时间 / 数量 / 场合 / 可数动作
TIME_PAT = re.compile(
    r"(每天|每周|每月|每晚|每次|每回|当天|次日|隔天|隔\d|周[一二三四五六日末]|"
    r"\d+\s*(分钟|小时|天|周|个月|次|条|件|句|页|轮|遍|人|个|年)|"
    r"[一二两三四五六七八九十]\s*(分钟|小时|天|周|个月|次|条|件|句|页|遍|轮|人|个)|"
    r"24\s*小时|半小时|睡前|起床后|饭后|下班|上班前|周末|月底|季度|截止|deadline|"
    r"第二天|当场|立刻|马上|先|再)")
NUM_PAT = re.compile(r"[0-9０-９]|[一二两三四五六七八九十]个|[一二两三四五六七八九十]条|[一二两三四五六七八九十]次|[一二两三四五六七八九十]句")
SCENE_PAT = re.compile(
    r"(会议|例会|开会|聊天|对话|吵架|争执|冲突|消息|微信|邮件|清单|待办|日历|闹钟|"
    r"备忘|笔记|本子|纸上|写下|记下|列出|说出|问出|发出|发一|回复|拒绝|约|见面|"
    r"饭局|聚会|独处|房间|工位|电脑|手机|文档|复盘|打卡|设置|定个|定一|删掉|关掉|"
    r"退出|离开|起身|喝水|散步|走一)")
ACTION_PAT = re.compile(
    r"(写下|记下|列出|说出|问出|发出|发一|发条|回复|拒绝|删掉|关掉|设成|设一|设个|定个|定一|"
    r"挑一|选一|留出|空出|安排|预约|打印|贴在|放在|拿出|读出|念出|重复|复述|计时|倒数|"
    r"起身|走开|离开|停下|按下|打开|关上|标记|打勾|划掉|存进|加进|换成|改成|告诉|问对方|"
    r"告知|申明|提出|报出|摊开|摆出|做完|交出|提交|上交)")

prac = {"vague_hits": [], "no_concreteness": [], "n_items": 0}
for i, p in enumerate(raw):
    for j, x in enumerate(p.get("practice") or []):
        if not isinstance(x, str):
            continue
        prac["n_items"] += 1
        hits = [w for w in VAGUE if w in x]
        # 「适度」「尽量」「先」「再」这类过宽的词单独降权：只有在没有任何具体性证据时才算
        strong_hits = [h for h in hits if h not in ("适度", "尽量", "多一点", "少一点", "学着", "试着去", "努力去")]
        has_time = bool(TIME_PAT.search(x))
        has_num = bool(NUM_PAT.search(x))
        has_scene = bool(SCENE_PAT.search(x))
        has_act = bool(ACTION_PAT.search(x))
        conc = sum([has_time, has_num, has_scene, has_act])
        if strong_hits:
            prac["vague_hits"].append({"cell": cells[i], "item": j, "text": x,
                                       "hit": strong_hits, "concrete_signals": conc})
        if conc == 0:
            prac["no_concreteness"].append({"cell": cells[i], "item": j, "text": x,
                                            "soft_hit": hits})
prac["n_vague"] = len(prac["vague_hits"])
prac["n_no_conc"] = len(prac["no_concreteness"])
prac["pct_vague"] = round(100 * prac["n_vague"] / prac["n_items"], 2)
prac["pct_no_conc"] = round(100 * prac["n_no_conc"] / prac["n_items"], 2)
report["practice"] = prac

# ================================================================ 4 summary 维度交互
DIM_KW = {
    "O": ["开放性", "开放", "好奇", "新鲜", "新想法", "新点子", "抽象", "审美", "想象", "新奇",
          "点子", "创意", "新东西", "熟悉的", "务实", "求新", "试新", "新的可能"],
    "C": ["尽责性", "尽责", "计划", "条理", "自律", "拖延", "收尾", "目标导向", "有序", "守时",
          "执行力", "清单", "规矩", "计划性", "完成度", "半途", "烂尾", "标准", "秩序"],
    "E": ["外向性", "外向", "社交", "独处", "人群", "话多", "话少", "热闹", "主动搭", "社交后",
          "一个人待", "人际能量", "内敛", "沉默", "外放", "交际"],
    "A": ["宜人性", "宜人", "让步", "冲突", "直率", "迁就", "讨好", "体谅", "以关系为先",
          "不肯先退", "拒绝", "对抗", "顺从", "好说话", "不留情面", "为对方", "退让"],
    "N": ["神经质", "情绪", "反刍", "敏感", "焦虑", "起伏", "抗压", "平稳", "内耗",
          "自责", "钻牛角尖", "紧绷", "不安", "波动", "情绪化", "淡定"],
}
CONN = ["让", "使", "导致", "于是", "所以", "因此", "但", "却", "而", "加上", "叠加",
        "叠在", "叠", "放大", "拉扯", "推着", "推动", "结果", "同时", "又", "既",
        "反过来", "互相", "彼此", "一边", "另一边", "配上", "碰上", "遇上", "本来",
        "原本", "偏偏", "反而", "抵消", "抵住", "拽", "夹", "撞", "压住", "压着",
        "放在一起", "合在一起", "一起", "组合", "两股", "双重", "则", "才", "越",
        "换来", "带来", "变成", "转成", "加剧", "加深", "削弱", "补上", "补足", "——", "："]


def dims_in(text):
    found = {}
    for d, kws in DIM_KW.items():
        for k in kws:
            if k in text:
                found.setdefault(d, []).append(k)
    return found


def all_pos(s, fd):
    pos = []
    for d, kws in fd.items():
        for k in kws:
            st = 0
            while True:
                j = s.find(k, st)
                if j < 0:
                    break
                pos.append((j, d, k))
                st = j + 1
    pos.sort()
    return pos


inter = {"pass": 0, "fail": [], "detail": []}
for i, p in enumerate(raw):
    s = p.get("summary") or ""
    fd = dims_in(s)
    conn = [c for c in CONN if c in s]
    ok = len(fd) >= 2 and len(conn) > 0
    # 严格版：两个不同维度的关键词相距 <= 40 字，且区间内出现因果/转折连接词
    tight = False
    evid = None
    pos = all_pos(s, fd)
    for a in range(len(pos)):
        for b in range(a + 1, len(pos)):
            if pos[b][1] == pos[a][1] or pos[b][0] - pos[a][0] > 40:
                continue
            seg = s[pos[a][0]:pos[b][0] + 12]
            hit = [c for c in CONN if c in seg]
            if hit:
                tight = True
                evid = {"seg": seg, "dims": [pos[a][1], pos[b][1]],
                        "kw": [pos[a][2], pos[b][2]], "conn": hit[:3]}
                break
        if tight:
            break
    score = (2 if tight else 0) + (1 if ok else 0)
    inter["detail"].append({"cell": cells[i], "n_dims": len(fd), "dims": sorted(fd),
                            "n_conn": len(conn), "loose_ok": ok, "tight_ok": tight,
                            "score": score, "evid": evid})
    if tight:
        inter["pass"] += 1
    else:
        inter["fail"].append({"cell": cells[i], "n_dims": len(fd), "dims": sorted(fd),
                              "summary": s})
inter["n"] = len(raw)
inter["pass_rate_tight"] = round(100 * inter["pass"] / len(raw), 1)
inter["pass_rate_loose"] = round(100 * sum(1 for d in inter["detail"] if d["loose_ok"]) / len(raw), 1)
report["interaction"] = inter

# lead 不得以句号结尾（规格明写）
lead_bad = [{"cell": cells[i], "lead": raw[i]["lead"]}
            for i in range(len(raw)) if (raw[i].get("lead") or "").rstrip().endswith(("。", ".", "！", "？"))]
report["lead_ends_with_period"] = lead_bad

# 越界在 243 格里的分布（看是不是集中在某一族）
from collections import defaultdict
bycell = defaultdict(list)
for v in length["all"]["all_viol"]:
    bycell[v["cell"]].append(v["field"])
prefix_cnt = Counter()
for c, fs in bycell.items():
    prefix_cnt[c[:4]] += len(fs)
report["violation_cluster_by_OC"] = prefix_cnt.most_common()
# 只看正文四段（life/friends/love/work）偏短的画像
short4 = sorted(set(v["cell"] for v in length["all"]["all_viol"]
                    if v["field"] in ("life", "friends", "love", "work") and v["dir"] == "偏短"))
report["profiles_with_short_body"] = short4
report["profiles_with_short_body_n"] = len(short4)

# ================================================================ 5 打包与体积
def sizes(b: bytes):
    import brotli
    return {
        "raw": len(b),
        "gzip": len(gzip.compress(b, 9)),
        "brotli": len(brotli.compress(b, quality=11)),
    }


compact = json.dumps(ordered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
pack = {"profiles_ordered_compact": sizes(compact)}
pack["profiles_ordered_pretty_file_bytes"] = os.path.getsize(ORDERED)
raw_compact = json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
pack["profiles_raw_compact"] = sizes(raw_compact)
pack["cell_field_overhead_bytes"] = len(raw_compact) - len(compact)

# 页面体积：全部在 scratchpad 里算，不碰 site/
tmp = os.path.join(SCRATCH, "sizecalc")
os.makedirs(tmp, exist_ok=True)
src_plain = os.path.join(SITE, "index.html")
src_opt = os.path.join(SITE, "index.optimized.html")
cp_plain = os.path.join(tmp, "index.copy.html")
cp_opt = os.path.join(tmp, "index.optimized.copy.html")
shutil.copyfile(src_plain, cp_plain)
shutil.copyfile(src_opt, cp_opt)

plain = open(cp_plain, encoding="utf-8").read()
opt = open(cp_opt, encoding="utf-8").read()
pack["site_index_html"] = sizes(plain.encode("utf-8"))
pack["site_index_optimized_html_current"] = sizes(opt.encode("utf-8"))

# a) 把 payload 塞进 index.html 的副本（在首个 </body> 前插一个 script）
payload_js = "\n<script>const PROFILES=" + compact.decode("utf-8") + ";</script>\n"
k = plain.rfind("</body>")
injected = plain[:k] + payload_js + plain[k:] if k > 0 else plain + payload_js
open(os.path.join(tmp, "index.injected.html"), "w", encoding="utf-8").write(injected)
pack["index_html_plus_payload"] = sizes(injected.encode("utf-8"))

# b) 把 optimized 里的占位 PROFILES 数组换成真数据（更贴近上线形态）
i0 = opt.find("const PROFILES = [")
i1 = opt.find("];", i0)
if i0 > 0 and i1 > i0:
    swapped = opt[:i0] + "const PROFILES=" + compact.decode("utf-8") + opt[i1 + 2:]
    open(os.path.join(tmp, "index.optimized.swapped.html"), "w", encoding="utf-8").write(swapped)
    pack["index_optimized_with_real_payload"] = sizes(swapped.encode("utf-8"))
    pack["embedded_payload_bytes_now"] = len(opt[i0:i1 + 2].encode("utf-8"))
    # 去掉 PROFILES 数组 = 页面骨架（HTML/CSS/JS/常模表），用于拆解占比
    chrome = opt[:i0] + "const PROFILES=[];" + opt[i1 + 2:]
    pack["page_chrome_no_payload"] = sizes(chrome.encode("utf-8"))
else:
    pack["index_optimized_with_real_payload"] = None
pack["_snapshot"] = {
    "index.optimized.html_bytes": os.path.getsize(src_opt),
    "index.optimized.html_mtime": os.path.getmtime(src_opt),
    "placeholder_count_remaining": opt.count("占位"),
}

# c) 已嵌入页面的 PROFILES 是否就是 profiles_ordered.json（逐条深比较）
embed_check = {"parsed": False}
if i0 > 0 and i1 > i0:
    txt = opt[opt.find("[", i0):i1 + 1]
    try:
        emb = json.loads(txt)
        embed_check["parsed"] = True
        embed_check["n"] = len(emb)
        embed_check["deep_equal_to_ordered"] = (emb == ordered)
        if emb != ordered:
            embed_check["first_diff_idx"] = next(
                (k for k in range(min(len(emb), len(ordered))) if emb[k] != ordered[k]), None)
    except Exception as e:
        embed_check["error"] = repr(e)[:200]
pack["embedded_payload_check"] = embed_check

# d) 「占位」出现在哪
ph = []
st = 0
while True:
    j = opt.find("占位", st)
    if j < 0:
        break
    ph.append(opt[max(0, j - 70):j + 40].replace("\n", "⏎"))
    st = j + 2
pack["placeholder_contexts"] = ph
report["packaging"] = pack

# ================================================================ 6 供人工核读的低分样本
# 25 个 = 全部严格未达标(19) + 达标里置信度最低的若干（维度关键词最少 / 连接词最少）
passes = [d for d in inter["detail"] if d["tight_ok"]]
passes.sort(key=lambda d: (d["n_dims"], d["n_conn"]))
lowconf = passes[:max(0, 25 - len(inter["fail"]))]
bycellmap = {cells[i]: raw[i] for i in range(len(raw))}
manual = []
for d in inter["fail"]:
    manual.append({"cell": d["cell"], "verdict_auto": "FAIL", "n_dims": d["n_dims"],
                   "dims": d["dims"], "summary": bycellmap[d["cell"]]["summary"]})
for d in lowconf:
    manual.append({"cell": d["cell"], "verdict_auto": "PASS(低置信)", "n_dims": d["n_dims"],
                   "dims": d["dims"], "n_conn": d["n_conn"],
                   "evid": d["evid"], "summary": bycellmap[d["cell"]]["summary"]})
report["interaction_manual_sample"] = manual

# 越界按 O?C? 前缀归一化（每族 27 格 × 15 个正文/短语单元不等，这里只看正文四段）
body_units = defaultdict(int)
body_viol = defaultdict(int)
for i, p in enumerate(raw):
    for f in ("life", "friends", "love", "work"):
        body_units[cells[i][:4]] += 1
for v in length["all"]["all_viol"]:
    if v["field"] in ("life", "friends", "love", "work"):
        body_viol[v["cell"][:4]] += 1
report["body_violation_rate_by_OC"] = sorted(
    [(k, body_viol.get(k, 0), body_units[k], round(100 * body_viol.get(k, 0) / body_units[k], 1))
     for k in body_units], key=lambda x: -x[3])

# practice：只靠单一弱信号过关的条目（供人工复核假阴性）
weak = []
for i, p in enumerate(raw):
    for j, x in enumerate(p.get("practice") or []):
        if not isinstance(x, str):
            continue
        sig = {"time": bool(TIME_PAT.search(x)), "num": bool(NUM_PAT.search(x)),
               "scene": bool(SCENE_PAT.search(x)), "act": bool(ACTION_PAT.search(x))}
        if sum(sig.values()) == 1:
            weak.append({"cell": cells[i], "item": j, "text": x,
                         "only": [k for k, v in sig.items() if v][0]})
report["practice_weak_signal"] = weak

# ================================================================ 输出
json.dump(report, open(OUTJSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def P(*a):
    print(*a)


P("=" * 70)
P("1. 完整性")
P("  raw=%d ordered=%d  ok=%s" % (comp["n_raw"], comp["n_ordered"], comp["ok"]))
P("  命名/索引错误 %d  重复 %d  缺格 %d  多余 %d" %
  (len(comp["errors"]), len(dup), len(comp["missing"]), len(comp["extra"])))
P("  ordered 含 cell 字段: %s ; ordered vs raw 不一致 %d 条" %
  (comp["ordered_has_cell_field"], comp["ordered_vs_raw_mismatch_n"]))
P("  字段缺失/空/结构问题 %d 条" % len(fieldprob))
for e in comp["errors"][:10]:
    P("   ", e)
for e in fieldprob[:10]:
    P("   ", e)

for metric, label in (("all", "含标点"), ("np", "不含标点")):
    L = length[metric]
    P("=" * 70)
    P("2. 字数 [%s]  越界单元 %d / %d (%.1f%%)  受影响画像 %d/243" %
      (label, L["n_viol_total"], L["n_units_total"],
       100 * L["n_viol_total"] / L["n_units_total"], L["profiles_with_any_violation"]))
    P("  %-9s %-9s %5s %5s %6s %5s %5s | %6s %6s | %4s %4s %4s" %
      ("field", "spec", "min", "p25", "median", "p75", "max", "越界", "%", "轻", "中", "严"))
    for f in FIELDS:
        s = L["per_field"][f]
        P("  %-9s %-9s %5d %5d %6.1f %5d %5d | %6d %5.1f%% | %4d %4d %4d" %
          (f, "%d-%d" % tuple(s["spec"]), s["min"], s["p25"], s["median"], s["p75"],
           s["max"], s["n_viol"], s["pct_viol"], s["轻微"], s["中度"], s["严重"]))
    P("  -- 越界最严重 25 --")
    for v in L["top25"]:
        P("   %-14s %-9s%s %4d字 (规格%d-%d) %s%s 偏离%.0f%%" %
          (v["cell"], v["field"], "" if v["item"] is None else "[%d]" % v["item"],
           v["count"], v["spec"][0], v["spec"][1], v["dir"], v["level"], 100 * v["rel"]))

P("=" * 70)
P("3. practice 可执行性  条目 %d" % prac["n_items"])
P("  命中空话词表: %d (%.2f%%)   零具体性信号: %d (%.2f%%)" %
  (prac["n_vague"], prac["pct_vague"], prac["n_no_conc"], prac["pct_no_conc"]))
for v in prac["vague_hits"][:40]:
    P("   [空话] %-14s #%d %s | 命中%s 具体信号%d" % (v["cell"], v["item"], v["text"], v["hit"], v["concrete_signals"]))
for v in prac["no_concreteness"][:40]:
    P("   [无具体] %-14s #%d %s" % (v["cell"], v["item"], v["text"]))

P("=" * 70)
P("4. summary 维度交互  严格达标 %d/243 = %.1f%%   宽松 %.1f%%" %
  (inter["pass"], inter["pass_rate_tight"], inter["pass_rate_loose"]))
from collections import Counter as C2
P("  维度关键词命中个数分布: %s" % sorted(C2(d["n_dims"] for d in inter["detail"]).items()))
P("  -- 未达标（严格）清单 %d 个 --" % len(inter["fail"]))
for v in inter["fail"]:
    P("   %-14s dims=%s" % (v["cell"], v["dims"]))
    P("     %s" % v["summary"])

P("=" * 70)
P("附加检查")
P("  lead 以句号/叹号/问号结尾: %d 个 %s" % (len(lead_bad), [x["cell"] for x in lead_bad][:10]))
P("  越界按 O?C? 前缀聚集: %s" % report["violation_cluster_by_OC"][:12])
P("  正文四段偏短的画像数: %d" % report["profiles_with_short_body_n"])

P("  正文四段越界率 按 O?C? 归一化 (越界/单元):")
for k, nv, nu, r in report["body_violation_rate_by_OC"]:
    P("    %-8s %3d/%3d = %5.1f%%" % (k, nv, nu, r))

P("=" * 70)
P("6. 人工核读样本 (%d 个)" % len(manual))
for m in manual:
    if m["verdict_auto"] != "FAIL":
        P("   [%s] %-14s dims=%s conn=%d evid=%s" %
          (m["verdict_auto"], m["cell"], m["dims"], m.get("n_conn", -1),
           (m.get("evid") or {}).get("seg", "")[:60]))
P("  practice 仅靠单一弱信号过关: %d 条" % len(weak))
for w in weak[:60]:
    P("    (%s) %-14s #%d %s" % (w["only"], w["cell"], w["item"], w["text"]))

P("=" * 70)
P("5. 打包与体积")
for k, v in pack.items():
    P("  %-40s %s" % (k, v))
P("\n报告 JSON: %s" % OUTJSON)

