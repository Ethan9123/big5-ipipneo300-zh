# -*- coding: utf-8 -*-
"""qa_voice.py -- 口吻与安全红线扫描器 (243 人格画像)

按 tools/profile_spec.md 的"硬性禁止"逐条正则全量扫描，不抽样。

用法:
    python tools/qa_voice.py [profiles.json]
默认目标 tools/out/profiles_raw.json，缺失时回退 tools/out/profiles_ordered.json。

输出:
    stdout 人类可读汇总
    tools/out/qa_voice_report.json 机器可读明细
"""
from __future__ import unicode_literals

import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

LV = ["低", "中", "高"]
KEYS = ["O", "C", "E", "A", "N"]
TEXT_FIELDS = ["lead", "summary", "life", "friends", "love", "work"]
LIST_FIELDS = ["pros", "cons", "practice"]


# ---------------------------------------------------------------- 加载

def cell_from_index(i):
    """索引编码 O*81 + C*27 + E*9 + A*3 + N，低=0 中=1 高=2。"""
    lv = [(i // 81) % 3, (i // 27) % 3, (i // 9) % 3, (i // 3) % 3, i % 3]
    return "".join(k + LV[v] for k, v in zip(KEYS, lv))


def load(path):
    data = json.load(io.open(path, encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("期望顶层是数组，实际是 %s" % type(data))
    for i, p in enumerate(data):
        if not p.get("cell"):
            p["cell"] = cell_from_index(i)          # 无 cell 字段时按索引约定补
            p["_cell_derived"] = True
    return data


def levels(cell):
    """'O中C高E高A高N低' -> {'O':1,'C':2,...}"""
    out = {}
    for k in KEYS:
        m = re.search(k + "([低中高])", cell)
        out[k] = LV.index(m.group(1)) if m else None
    return out


def all_text(p):
    """返回 [(field_label, text), ...]，列表字段逐条拆开。"""
    chunks = []
    for f in TEXT_FIELDS:
        v = p.get(f)
        if isinstance(v, str):
            chunks.append((f, v))
    for f in LIST_FIELDS:
        v = p.get(f) or []
        if isinstance(v, list):
            for j, item in enumerate(v):
                if isinstance(item, str):
                    chunks.append("%s[%d]" % (f, j), ) if False else chunks.append(("%s[%d]" % (f, j), item))
    return chunks


# ---------------------------------------------------------------- 规则

# 1 类型名 / 身份标签。先宽扫再用白名单剔除常用词。
RE_TYPE_NAME = re.compile(
    r"[一-鿿]{2,5}型(?![号式态])"          # XX型
    r"|[一-鿿]{2,4}者(?!是)"               # XX者
    r"|[一-鿿]{2,4}家(?![里庭人务具])"      # XX家
    r"|[一-鿿]{2,4}人格"                   # XX人格
    r"|[一-鿿]{2,4}星人"
)
# 这些是正常中文词，不是自造身份标签
TYPE_WHITELIST = set("""
类型 型号 典型 模型 原型 体型 题型 句型 造型 转型 定型 成型 大型 小型 新型 各型
或者 读者 作者 记者 前者 后者 二者 三者 两者 使用者 参与者 旁观者 患者 长者 老者
再者 更有者 其他者 所有者 与会者
大家 人家 专家 国家 回家 搬家 老家 娘家 婆家 商家 店家 玩家 到家 起家 全家 一家
自家 别家 出家 当家 管家
人格 品格 性格 风格 资格 合格 严格 价格 格子
""".split())

# 2 决定论
RE_DETERMINISM = re.compile(
    r"你天生|你注定|你就是|你永远|必然|一定会|生来就|与生俱来|改不了的|骨子里就是|"
    r"这辈子都|命里|天生就是|注定会|无论如何都会"
)

# 3 吹捧 / 星座腔
RE_FLATTERY = re.compile(
    r"完美|天赋异禀|独一无二|上天|命中注定|魅力四射|天选|光芒万丈|人见人爱|"
    r"万里挑一|得天独厚|无人能及|羡慕不来|幸运儿|注定不凡|闪闪发光"
)

# 4 临床词汇 —— 最高优先级
RE_CLINICAL = re.compile(
    r"抑郁症|焦虑症|强迫症|恐惧症|社交恐惧|社恐症|ADHD|多动症|多动|注意力缺陷|"
    r"自闭|孤独症|阿斯伯格|人格障碍|心理障碍|情绪障碍|精神障碍|心理疾病|精神疾病|"
    r"精神病|神经症|病态|躁郁|双相|精神分裂|创伤后应激|PTSD|OCD|"
    r"厌食|暴食|成瘾|依赖症|抑郁倾向|焦虑障碍|心理病"
)
# 暗示诊断（不含临床名词但在做诊断动作）
RE_DIAGNOSIS_HINT = re.compile(
    r"你可能有[^。，]{0,8}(症|障碍|疾病)|建议(就医|就诊|看医生|看心理医生)|需要(治疗|药物|服药)|"
    r"确诊|临床上|症状|发病|病症|病情|求医|去医院|精神科|心理咨询师会诊断"
)

# 5 评判他人 / 影响他人权益
RE_JUDGE_OTHERS = re.compile(
    r"筛选(?!信息|选项)|招聘|录用|面试(?:官|时)?别|淘汰(?:掉)?(?:这类|这种|对方)|"
    r"择偶时(?:排除|避开)|不要和这类人|远离这种人|识别(?:出)?(?:这类|这种)人|"
    r"判断对方(?:是不是|适不适合)|评估对方(?:的)?人格|挑选(?:伴侣|下属|队友)时排除|"
    r"不适合(?:当|做)(?:领导|伴侣|父母)|开除|裁掉|拉黑(?:这类|这种)|"
    r"给对方(?:打分|贴标签)|测测你(?:的)?(?:另一半|同事|老板)"
)

# 6 英文术语残留
RE_ENGLISH = re.compile(
    r"Conscientious\w*|Neurotic\w*|Openness|Extra[vy]ers\w*|Introver\w*|Agreeable\w*|"
    r"Big\s*Five|BigFive|IPIP|NEO-?PI|OCEAN|MBTI|Five\s*Factor",
    re.IGNORECASE,
)

# 7 内向者 / 外向者 当身份标签
RE_INTROVERT_LABEL = re.compile(
    r"内向者|外向者|内向型(?:的)?人?|外向型(?:的)?人?|内向人格|外向人格|"
    r"高神经质者|低神经质者|高分者|低分者|神经质者|尽责者"
)

RULES = [
    ("clinical",        "临床词汇",        RE_CLINICAL,        "high"),
    ("diagnosis_hint",  "暗示诊断",        RE_DIAGNOSIS_HINT,  "high"),
    ("determinism",     "决定论措辞",      RE_DETERMINISM,     "medium"),
    ("flattery",        "吹捧/星座腔",     RE_FLATTERY,        "medium"),
    ("judge_others",    "评判他人/影响他人权益", RE_JUDGE_OTHERS, "high"),
    ("english_term",    "英文术语残留",    RE_ENGLISH,         "medium"),
    ("introvert_label", "内向者/外向者身份标签", RE_INTROVERT_LABEL, "medium"),
]

RE_PLACEHOLDER = re.compile(r"占位|placeholder|TODO|待写|lorem|XXX")


def scan_type_names(text):
    hits = []
    for m in RE_TYPE_NAME.finditer(text):
        s = m.group(0)
        if s in TYPE_WHITELIST:
            continue
        # 尾字前缀也可能是白名单词的一部分（如"心理咨询者"含"询者"）
        if any(w in s for w in ("或者", "读者", "作者", "前者", "后者", "两者", "使用者")):
            continue
        hits.append(s)
    return hits


# ---------------------------------------------------------------- 检查 8：代价

# N低 的代价语义（对危险/他人情绪迟钝）
N_LOW_COST = re.compile(
    r"迟钝|不敏感|察觉不到|意识不到|后知后觉|低估|轻视|没当回事|不当回事|"
    r"体会不到|感受不到|共情|理解不了|冷|漠|风险|危险|警觉|预警|"
    r"不上心|无所谓|不痛不痒|置身事外|隔了一层|不着急|拖到最后|缺乏紧迫"
)
# A高 的代价语义（过度让步、不敢提要求）
A_HIGH_COST = re.compile(
    r"让步|吃亏|占便宜|不敢|说不出口|拒绝|忍|退让|讨好|委屈|界限|边界|"
    r"提要求|积怨|压抑|被动|背锅|烂摊子|好人|和稀泥|回避冲突|不好意思|"
    r"揽事|扛下来|憋|迁就|牺牲"
)
# cons 里出现这些说明在夸而不是在指代价
RE_PRAISE_IN_CONS = re.compile(
    r"优秀|出色|可靠|靠谱|强大|突出|值得|难得|优势|长处|善于|擅长|受欢迎|被喜欢|"
    r"稳重|成熟|温暖|贴心|有魅力|讨人喜欢"
)
# 空话/不痛不痒
RE_VAGUE = re.compile(
    r"^(有时|偶尔|可能|或许|稍微|略微|多少)?[^，。；]{0,6}(而已|罢了|一点点|一些)?$"
)


def cost_audit(profiles):
    """检查 N低(81) 与 A高(81) 的 cons 是否真的写了代价。"""
    res = {}
    for tag, dim, want_lv, costre in (("N低", "N", 0, N_LOW_COST),
                                      ("A高", "A", 2, A_HIGH_COST)):
        group, weak = [], []
        for p in profiles:
            lv = levels(p["cell"])
            if lv.get(dim) != want_lv:
                continue
            group.append(p)
            cons = [c for c in (p.get("cons") or []) if isinstance(c, str)]
            joined = "".join(cons)
            has_cost = bool(costre.search(joined))
            praise = RE_PRAISE_IN_CONS.findall(joined)
            # 每条 cons 是否短且空泛
            vague_n = sum(1 for c in cons if len(c) < 6 or RE_VAGUE.match(c))
            empty = (len(cons) < 3) or (not joined.strip())
            # 缺陷分：越高越差
            score = 0
            if not has_cost:
                score += 3
            if praise:
                score += 2 * len(praise)
            score += vague_n
            if empty:
                score += 4
            if score >= 3:
                weak.append({
                    "cell": p["cell"], "score": score, "cons": cons,
                    "has_cost_keyword": has_cost,
                    "praise_words": praise, "vague_items": vague_n,
                    "cons_missing_or_empty": empty,
                })
        weak.sort(key=lambda x: (-x["score"], x["cell"]))
        res[tag] = {
            "group_size": len(group),
            "weak_count": len(weak),
            "weak_ratio": round(len(weak) / len(group), 4) if group else None,
            "worst10": weak[:10],
        }
    return res


# ---------------------------------------------------------------- 主流程

def main():
    default = os.path.join(OUT, "profiles_raw.json")
    fallback = os.path.join(OUT, "profiles_ordered.json")
    if len(sys.argv) > 1:
        path = os.path.abspath(sys.argv[1])
    elif os.path.exists(default):
        path = default
    else:
        path = fallback
        print("!! 目标文件不存在: %s" % default)
        print("!! 回退到: %s" % fallback)

    if not os.path.exists(path):
        raise SystemExit("找不到任何画像文件: %s" % path)

    profiles = load(path)
    print("扫描文件: %s" % path)
    print("画像条数: %d" % len(profiles))

    # 完整性
    cells = [p["cell"] for p in profiles]
    expected = set(cell_from_index(i) for i in range(243))
    print("cell 字段自带: %d / 按索引推导: %d"
          % (sum(1 for p in profiles if not p.get("_cell_derived")),
             sum(1 for p in profiles if p.get("_cell_derived"))))
    print("覆盖 243 格: %s  重复: %d"
          % (set(cells) == expected, len(cells) - len(set(cells))))

    # 占位文本
    ph = []
    for p in profiles:
        for f, t in all_text(p):
            if RE_PLACEHOLDER.search(t):
                ph.append((p["cell"], f))
                break
    print("含占位/未完成文本的画像: %d / %d" % (len(ph), len(profiles)))

    # 规则扫描
    findings = {k: [] for k, _, _, _ in RULES}
    findings["type_name"] = []
    for p in profiles:
        for f, t in all_text(p):
            for key, label, rx, sev in RULES:
                for m in rx.finditer(t):
                    findings[key].append({"cell": p["cell"], "field": f,
                                          "match": m.group(0),
                                          "ctx": t[max(0, m.start() - 12):m.end() + 12]})
            for s in scan_type_names(t):
                findings["type_name"].append({"cell": p["cell"], "field": f, "match": s,
                                              "ctx": t[:40]})

    print("\n--- 红线扫描 (命中次数 / 涉及画像数) ---")
    order = [("type_name", "1 自造类型名"), ("determinism", "2 决定论措辞"),
             ("flattery", "3 吹捧/星座腔"), ("clinical", "4a 临床词汇"),
             ("diagnosis_hint", "4b 暗示诊断"), ("judge_others", "5 评判他人"),
             ("english_term", "6 英文术语"), ("introvert_label", "7 内向者/外向者标签")]
    summary = {}
    for key, label in order:
        hits = findings[key]
        ncell = len(set(h["cell"] for h in hits))
        summary[key] = {"hits": len(hits), "profiles": ncell,
                        "examples": hits[:8]}
        print("%-22s %5d 次 / %4d 个画像" % (label, len(hits), ncell))
        for h in hits[:3]:
            print("        · %s %s  「%s」" % (h["cell"], h["field"], h["ctx"].replace("\n", "")))

    # 检查 8
    print("\n--- 8 每一档是否写了代价 ---")
    cost = cost_audit(profiles)
    for tag in ("N低", "A高"):
        r = cost[tag]
        print("%s 组: %d 个画像，cons 未写出真实代价 %d 个 (%.1f%%)"
              % (tag, r["group_size"], r["weak_count"],
                 100.0 * (r["weak_ratio"] or 0)))
        for w in r["worst10"]:
            print("        · %s  分=%d  cons=%s" % (w["cell"], w["score"], w["cons"]))

    report = {
        "file": path,
        "n_profiles": len(profiles),
        "covers_243": set(cells) == expected,
        "placeholder_profiles": len(ph),
        "rules": summary,
        "cost_audit": cost,
    }
    rp = os.path.join(OUT, "qa_voice_report.json")
    io.open(rp, "w", encoding="utf-8").write(
        json.dumps(report, ensure_ascii=False, indent=1))
    print("\n明细写入 %s" % rp)


if __name__ == "__main__":
    main()
