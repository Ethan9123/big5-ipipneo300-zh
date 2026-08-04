# -*- coding: utf-8 -*-
"""
qa2_voice.py  --  口吻与安全红线全量扫描（243 画像，无抽样）

只读输入:
  tools/out/profiles_raw.json
  tools/profile_spec.md   （仅作依据，不解析）

输出:
  tools/out/qa2_voice_v2.json   机器可读全量命中
  tools/out/qa2_voice_v2.txt    人读报告

用法:
  python qa2_voice.py            # 先自检合成违规样本，再扫真实语料
  python qa2_voice.py --selftest # 只跑自检
"""
import json, re, io, os, sys, collections

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "tools", "out", "profiles_raw.json")
OUT_JSON = os.path.join(ROOT, "tools", "out", "qa2_voice_v2.json")
OUT_TXT = os.path.join(ROOT, "tools", "out", "qa2_voice_v2.txt")

TEXT_FIELDS = ["lead", "summary", "life", "friends", "love", "work"]
LIST_FIELDS = ["pros", "cons", "practice"]
CJK = r"[\u4e00-\u9fff]"

# ---------------------------------------------------------------------------
# 通用：否定前缀检测（"你不是懒" 这类不该算违规）
NEG_PREFIX = re.compile(r"(不是|并非|并不|不叫|没有|不算|未必|别|不会|不该|不必|谈不上|说不上|而不是|不用)$")


def negated(text, start, window=6):
    return bool(NEG_PREFIX.search(text[max(0, start - window):start]))


# ---------------------------------------------------------------------------
# 规则表
# (rule_id, 中文名, section, severity, 正则, 白名单正则(对上下文), 说明)
RULES = [
    # ---- 2. 决定论 ----------------------------------------------------
    ("det.tiansheng", "决定论·天生", "2决定论", "high", r"天生", None, "『天生』断言不可变"),
    ("det.zhuding", "决定论·注定", "2决定论", "high", r"注定", None, "『注定』断言不可变"),
    ("det.nijiushi", "决定论·你就是", "2决定论", "high", r"你就是|你本来就(是|会)|你从来就是", None, "身份断言"),
    ("det.niyongyuan", "决定论·你永远/这辈子", "2决定论", "high", r"你(这辈子|一辈子|永远|从此)", None, "对读者的永久性断言"),
    ("det.biran", "决定论·必然", "2决定论", "high", r"必然|势必|必定", None, "必然性断言"),
    ("det.yidinghui", "决定论·一定会", "2决定论", "high", r"一定会|肯定会|必定会|绝对会|注定会|铁定", None, "确定性预测"),
    ("det.gaibuliao", "决定论·改不了", "2决定论", "high", r"改不了|无法改变|不可能改变|改不掉|变不了", None, "断言不可改变"),
    ("det.benxing", "决定论·本性/骨子里(扩展)", "2决定论", "medium",
     r"骨子里|本性|生来|与生俱来|打小就|基因里|命里", None, "本质化措辞"),
    ("det.yongyuan_bare", "决定论·裸『永远』(扩展/需人判)", "2决定论", "low", r"永远", None,
     "『永远』修饰读者=违规；修饰事务状态(『手上永远有半成品』)=可接受"),

    # ---- 3. 吹捧/星座腔 ------------------------------------------------
    ("astro.wanmei", "吹捧·完美", "3吹捧", "medium", r"完美", r"完美主义", "『完美』式吹捧（完美主义为术语，白名单）"),
    ("astro.tianfu", "吹捧·天赋/天赋异禀", "3吹捧", "medium", r"天赋异禀|天资过人|才华横溢|天赋", None, "天赋叙事"),
    ("astro.duyi", "吹捧·独一无二", "3吹捧", "high", r"独一无二|绝无仅有|世上少有|万里挑一|世上唯一", None, "星座腔"),
    ("astro.shangtian", "吹捧·上天/命运", "3吹捧", "high", r"上天|老天|上帝|命运(安排|眷顾|给)|天赐|冥冥之中", None, "宿命腔"),
    ("astro.mingzhong", "吹捧·命中注定", "3吹捧", "high", r"命中注定|天生一对|注定的缘分", None, "星座腔"),
    ("astro.meili", "吹捧·魅力四射", "3吹捧", "high", r"魅力四射|光芒四射|闪闪发光|人见人爱|自带光环|万人迷", None, "吹捧"),
    ("astro.yushengjulai", "吹捧·与生俱来", "3吹捧", "high", r"与生俱来|得天独厚|生来就(有|是)", None, "本质化吹捧"),
    ("astro.chaofan", "吹捧·卓越/正能量(扩展)", "3吹捧", "low",
     r"卓越|超凡|非凡|出类拔萃|了不起|令人羡慕|人人都想|正能量|磁场|能量场|贵人运|桃花运", None, "吹捧扩展词"),

    # ---- 4. 临床词汇（最高优先级）--------------------------------------
    ("clin.yiyu", "临床·抑郁症", "4临床", "high", r"抑郁症|抑郁障碍|重度抑郁", None, "临床诊断名"),
    ("clin.jiaolvzheng", "临床·焦虑症", "4临床", "high", r"焦虑症|广泛性焦虑|惊恐发作|社交恐惧症|恐惧症", None, "临床诊断名"),
    ("clin.qiangpo", "临床·强迫症", "4临床", "high", r"强迫症|强迫障碍|强迫倾向", None, "临床诊断名"),
    ("clin.zaoyu", "临床·躁郁/双相", "4临床", "high", r"躁郁|双相|狂躁症|躁狂", None, "临床诊断名"),
    ("clin.adhd", "临床·ADHD/多动", "4临床", "high", r"ADHD|多动症|多动|注意力缺陷|注意力障碍", None, "临床诊断名"),
    ("clin.zibi", "临床·自闭/亚斯伯格", "4临床", "high", r"自闭|孤独症|亚斯伯格|阿斯伯格|谱系", None, "临床诊断名"),
    ("clin.renge", "临床·人格障碍", "4临床", "high", r"人格障碍|边缘型人格|回避型人格|反社会人格", None, "临床诊断名"),
    ("clin.jibing", "临床·心理疾病/病态", "4临床", "high",
     r"心理疾病|精神疾病|病态|心理障碍|情绪障碍|精神障碍|心理问题|心理健康问题", None, "疾病化措辞"),
    ("clin.zhengzhuang", "临床·症状/障碍/确诊", "4临床", "high", r"症状|确诊|诊断|临床|发病|病症|障碍|病症", None, "诊断化措辞"),
    ("clin.yiliao", "临床暗示·就医/服药/治疗", "4临床", "high",
     r"看医生|就医|去医院|精神科|心理科|心理医生|精神卫生|吃药|服药|药物|治疗|干预治疗|专业帮助|求助专业|"
     r"心理咨询|咨询师|治疗师|这是病|生病了|不正常|需要帮助的信号", None, "暗示诊断或医疗介入"),
    ("clin.bare_yiyu", "临床边缘·裸『抑郁』", "4临床", "medium", r"抑郁", r"抑郁症", "裸『抑郁』二字仍带疾病联想"),
    ("clin.bare_jiaolv", "临床边缘·裸『焦虑』(日常词，计数供判断)", "4临床", "low", r"焦虑", r"焦虑症",
     "中文日常情绪词，非临床名；仅统计密度"),

    # ---- 5. 评判他人 / 影响他人权益 -------------------------------------
    ("oth.shaixuan", "评判他人·筛选/筛掉人", "5评判他人", "high",
     r"筛(选|掉|除)" + CJK + r"{0,8}(人|对方|朋友|同事|伴侣)|(把|将)" + CJK + r"{0,6}人筛|挑人|挑选(对象|伴侣|朋友)", None,
     "建议读者筛人"),
    ("oth.pingjia", "评判他人·评价/评判他人", "5评判他人", "high",
     r"(评价|评判|打分|贴标签)(别人|他人|对方|同事|朋友|伴侣|下属|候选人)|去评(价|判)" + CJK + r"{0,2}人", None,
     "建议读者评判他人"),
    ("oth.shitan", "评判他人·试探/考验对方", "5评判他人", "high",
     r"试探(一下)?(对方|别人|他|她|同事|伴侣)|考验(对方|别人|感情|他|她)|测试(对方|别人)", None, "建议读者试探他人"),
    ("oth.paichu", "评判他人·排除/远离某类人", "5评判他人", "high",
     r"(排除|剔除|淘汰|远离|避开|绕开|别找|不要找|不要选|少接触)" + CJK + r"{0,6}(的人|这类人|那种人|型的人)", None,
     "建议读者排除某类人"),
    ("oth.zhaopin", "评判他人·招聘/择偶场景", "5评判他人", "high",
     r"招聘|面试(别人|候选)|录用|选人用人|择偶(标准)?|相亲时看|找对象要找", None, "涉及他人权益的选人建议"),
    ("oth.shibie", "评判他人·识别/判断对方(扩展)", "5评判他人", "low",
     r"识别(对方|别人|他人)|判断(对方|别人)是否|看清(对方|别人)", None, "扩展：诱导读者对他人下判断"),
    ("oth.raw_shai", "评判他人·裸『筛/试探/挑人』(供人判)", "5评判他人", "low",
     r"筛选|筛掉|筛除|试探|考验|挑人|排除", None, "裸词，需看上下文是不是针对他人"),

    # ---- 6. 英文术语残留 ------------------------------------------------
    ("en.terms", "英文术语·五大维度英文名", "6英文残留", "high",
     r"(?i)Conscientiousness|Neuroticism|Openness|Extraversion|Extroversion|Agreeableness", None, "英文术语"),
    ("en.bigfive", "英文术语·Big Five / MBTI", "6英文残留", "high",
     r"(?i)Big\s*Five|MBTI|IPIP|NEO-?PI|OCEAN|16型人格|九型人格", None, "英文/他系测评术语"),
    ("en.any_latin", "英文残留·任意拉丁字母串(≥2)", "6英文残留", "medium", r"[A-Za-z]{2,}", None, "任何英文单词残留"),

    # ---- 7. 内向者/外向者当身份标签 --------------------------------------
    ("lab.zhe", "身份标签·内向者/外向者", "7身份标签", "high",
     r"内向者|外向者|宜人者|尽责者|开放者|神经质者|高分者|低分者", None, "维度词+者=身份标签"),
    ("lab.deren", "身份标签·内向的人/外向的人(扩展)", "7身份标签", "medium",
     r"(内向|外向)的人", r"(外向|开放|尽责|宜人|神经质)性" + CJK + r"{0,4}的人", "规格要求写『外向性分数偏低的人』"),
    ("lab.xingge", "身份标签·把读者归类(扩展)", "7身份标签", "low",
     r"你这种人|你这类人|你们这种|典型的你", None, "把读者归类"),
]

# ---- 1. 自造类型名（单独处理，需要上下文判定）------------------------------
LABEL_SUFFIX = re.compile(CJK + r"{1,5}(型|者|家|党|派|控|系)")
LABEL_WHITELIST = set("""
两者 或者 前者 后者 三者 再者 来者 笔者 患者 读者 作者 记者 学者 长者 老者 使用者 参与者 二者
类型 典型 原型 模型 题型 户型 体型 大型 小型 新型 转型 成型 造型 型号
大家 回家 人家 一家 搬家 在家 到家 专家 行家 商家 店家 老家 全家 娘家 别家 哪家 几家 那家 这家
学派 流派 党派
""".split())
# 明确的"给读者贴标签"句式
LABEL_TAG_PAT = re.compile(
    r"你(是|就是|属于|算是|会是|常是|往往是|多半是|既是|也是|成了|变成|被叫做|被称为|叫做|称为)"
    r"(一个|一名|那种|这种|典型的)?" + CJK + r"{0,6}(型|者|家)")
# 造名式复合词：X型Y者 / X型Y人
LABEL_COINED = re.compile(CJK + r"{2,4}型" + CJK + r"{1,4}(者|人|家)")

# ---------------------------------------------------------------------------
# 8. 代价检查：N低 / A高；9. C低 道德批判
N_LOW_COST = [
    # (a) 对他人情绪/状态的分辨率低、反应慢
    ("共情/情绪信号迟钝", re.compile(
        r"迟钝|慢半拍|反应慢|反应偏淡|缺乏反应|不敏感|分辨率|无感"
        r"|(察觉|觉察|意识|感觉|发现|读|接|听|看)不(到|出|懂|见|了)"
        r"|接不住|读不出|没察觉|毫无察觉|才发现|后知后觉"
        r"|(他人|别人|对方|身边人?|队友|伴侣)" + CJK + r"{0,8}(情绪|难处|低落|难过|疲态|状态|沉默|暗示|信号|积累|暗流|紧张|失望|受伤|委屈|痛)"
        r"|(察觉|觉察|感知|反应|回应)(偏慢|慢|偏淡|弱|不足)|很少(察觉|注意到|意识到|留意)"
        r"|(情绪|低落|难处|暗流|疲态|疲劳|沉默|暗示|不满|失望|受伤)" + CJK + r"{0,6}(察觉|觉察|反应|接|读|发现)"
        r"|把(别人|对方)的沉默当|安慰(缺席|不到位)|把倾诉当|把安慰当成解决|用安排事情代替情绪支持|情绪支持缺席")),
    # (b) 自己这边缺少痛感/警报/自省信号
    ("缺少内部警报/痛感", re.compile(
        r"(没有|没|缺少|缺乏|毫无|无)" + CJK + r"{0,10}(警报|报警器|信号|痛感|余震|不适感|刹车|内疚|愧疚|负担|压力|成本|提醒|动力|代价感|心理负担|情绪)"
        r"|(信号|痛感|警报|余震)(弱|少|不足|不够)|不太自责|不够自责|自责不足"
        r"|不自知|不自责|内疚不足|愧疚不足|难以自我修正|难自纠|自我纠正|改不动|自己发现不了|发现不了"
        r"|(很少|从不|不)(复盘|示弱|求助|检查自己|反省|自省)|不检查自己"
        r"|太稳|只增不减|(问题|事)一拖(多年|很久)|落空(没|毫无)|失约却没有|反应只是算了|只是算了"
        r"|损耗|不痛不痒|没在怕|不当回事|没当回事")),
    # (c) 低估风险 / 拿自己的耐受当别人的标准
    ("低估风险/高估自己", re.compile(
        r"低估|高估|过于乐观|盲目|轻视"
        r"|把自己的(耐受|抗压|强度|标准)" + CJK + r"{0,4}当|当(成)?默认标准|按自己的强度要求别人|当成别人的默认")),
    # (d) 平静被读成冷
    ("被读成冷/无温度", re.compile(
        r"(读成|听成|误读为|当成|看成)" + CJK + r"{0,3}(冷|冷淡|冷漠|冷酷|不在意|不上心|不在乎)|冷酷|冷漠|冷淡")),
]
N_LOW_FAKE = re.compile(r"^(情绪(很|都)?稳定|抗压(能力)?强?|不容易(焦虑|受影响|被影响)|沉得住气|很稳|心态好|"
                        r"稳定可靠|情绪平稳)[，,。]?$")

A_HIGH_COST = [
    ("拒绝困难/过度答应", re.compile(
        r"拒绝|说不出(口|拒绝)|当场说不出|不好意思|来者不拒|什么都答应|一直答应|难以拒绝|难拒绝"
        r"|答应(超出|太|得太|得快|之后|量|与|和)|答应的(量|事)|承诺量|产能的两倍"
        r"|(默默)?接(下|过|单)|揽活|不属于自己的(活|事)|杂活|日程(被|里)|活往你这边|多过自己的"
        r"|不会提(延期|涨价|加钱)|不敢开口|开不了口|不敢(拒绝|提|说|要)|又不敢")),
    ("替别人扛/超载", re.compile(
        r"超载|超量|过载|硬扛|透支|扛|背锅|补漏|替(别人|对方|人)(认|扛|背|担)"
        r"|自己的(事|需求)" + CJK + r"{0,3}(排最后|排在最后)|排在最后|排最后|排最后|活往你这边流"
        r"|精力大量花在维护|加班硬|(补|做)(容易|漏)|承接方")),
    ("憋着/事后独自消化", re.compile(
        r"憋|忍(着|下)|委屈|攒(着|委屈|到)|记账|账本|自己消化|独自(消化|后悔|扛|委屈|承受|把)"
        r"|不满" + CJK + r"{0,4}(不说|自己消化|记在心里|攒)|(不说破|说不出口|不公开|不出口|不上台面)"
        r"|等对方(来猜|察觉)|突然爆发|一次爆发|最后(以)?疏远|用变安静|内化|没生气的生气"
        r"|(不|没)(说|提|讲)出来|(最后|最终|始终|一直|从来|都)不说|清算自己|夜里逐条")),
    ("不提要求/无边界/先退让", re.compile(
        r"不提(要求|需求)|(需求|要求|偏好|想法|意见)" + CJK + r"{0,4}(不提|不说|不表达|隐形|被默认|被当成|被转述)"
        r"|不表达(需求|要求|偏好)|从不提|不争取|很少争取|不为自己争取"
        r"|让步|让出|退让|先松口|撤回|一被否就|被反驳一次|不坚持"
        r"|(边界|界限|底线)|刹车|被默认(为)?(总是有空|没有需要|无所谓|随便)|以为你都行|被占"
        r"|贡献" + CJK + r"{0,6}(脱节|被低估)|习惯性道歉|讨好|迎合|附和|怕(伤和气|添麻烦|让人失望|打扰|被讨厌)"
        r"|付出很多还觉得|觉得自己不够")),
]
A_HIGH_FAKE = re.compile(r"太(为别人|替别人|善良|好心|体贴|在乎别人|考虑别人|好说话|心软|无私)"
                         r"|过于(善良|体贴|无私|为别人)|对人太好|心太软|人太好")

C_LOW_MORAL_HARD = re.compile(
    r"懒(?!得)|懒惰|懒散|好逸恶劳|不负责任|没有?责任心|自私|幼稚|无能|废物|没用|差劲|窝囊|软弱|"
    r"没出息|不上进|不求上进|堕落|烂人|人品|品行|德行|失败者|靠不住的人|不成熟")
C_LOW_MORAL_SPEC_OK = re.compile(r"不可靠|靠不住")   # 规格自己的维度表用词（"灵活但不可靠"）
C_LOW_MORAL_SOFT = re.compile(r"散漫|懒得|随性|不靠谱|拖沓|吊儿郎当")


def parse_cell(cell):
    return dict(re.findall(r"([OCEAN])([低中高])", cell))


# ---------------------------------------------------------------------------
def iter_units(p):
    for f in TEXT_FIELDS:
        yield f, p.get(f, "") or ""
    for f in LIST_FIELDS:
        for i, s in enumerate(p.get(f, []) or []):
            yield "%s[%d]" % (f, i), s


def ctx(s, a, b, pad=14):
    return s[max(0, a - pad):min(len(s), b + pad)]


def scan_rules(profiles):
    hits = []
    for p in profiles:
        for field, s in iter_units(p):
            for rid, name, sec, sev, pat, wl, note in RULES:
                for m in re.finditer(pat, s):
                    if wl and re.search(wl, ctx(s, m.start(), m.end(), 6)):
                        continue
                    hits.append(dict(rule=rid, name=name, section=sec, severity=sev,
                                     cell=p["cell"], field=field, frag=m.group(0),
                                     ctx=ctx(s, m.start(), m.end()),
                                     negated=negated(s, m.start()), note=note))
    return hits


def scan_labels(profiles):
    tagged, coined, tokens = [], [], collections.Counter()
    for p in profiles:
        for field, s in iter_units(p):
            for m in LABEL_SUFFIX.finditer(s):
                tokens[m.group(0)[-2:]] += 1
            for m in LABEL_TAG_PAT.finditer(s):
                if m.group(0)[-2:] in LABEL_WHITELIST:
                    continue
                tagged.append(dict(cell=p["cell"], field=field, frag=m.group(0),
                                   ctx=ctx(s, m.start(), m.end())))
            for m in LABEL_COINED.finditer(s):
                coined.append(dict(cell=p["cell"], field=field, frag=m.group(0),
                                   ctx=ctx(s, m.start(), m.end())))
    return tagged, coined, tokens


def cost_check(profiles, dim, lev, families, fake_pat):
    sel = [p for p in profiles if parse_cell(p["cell"]).get(dim) == lev]
    rows = []
    for p in sel:
        cons = p.get("cons", [])
        matched = []
        for i, c in enumerate(cons):
            fams = [fn for fn, rx in families if rx.search(c)]
            if fams:
                matched.append((i, c, fams))
        fake = [c for c in cons if fake_pat.search(c)]
        body = " ".join((p.get(f) or "") for f in TEXT_FIELDS)
        body_fams = [fn for fn, rx in families if rx.search(body)]
        rows.append(dict(cell=p["cell"], cons=cons, n_matched=len(matched),
                         matched=[{"i": i, "text": c, "families": f} for i, c, f in matched],
                         families=sorted({f for _, _, fs in matched for f in fs}),
                         fake=fake, body_families=body_fams,
                         passed=len(matched) > 0,
                         passed_with_body=len(matched) > 0 or len(body_fams) > 0))
    return sel, rows


def c_low_moral(profiles):
    sel = [p for p in profiles if parse_cell(p["cell"]).get("C") == "低"]
    hard, spec_ok, soft = [], [], []
    for p in sel:
        for i, c in enumerate(p.get("cons", [])):
            for m in C_LOW_MORAL_HARD.finditer(c):
                hard.append(dict(cell=p["cell"], field="cons[%d]" % i, frag=m.group(0),
                                 text=c, negated=negated(c, m.start())))
            for m in C_LOW_MORAL_SPEC_OK.finditer(c):
                spec_ok.append(dict(cell=p["cell"], field="cons[%d]" % i, frag=m.group(0), text=c))
            for m in C_LOW_MORAL_SOFT.finditer(c):
                soft.append(dict(cell=p["cell"], field="cons[%d]" % i, frag=m.group(0),
                                 text=c, negated=negated(c, m.start())))
    allhard = []
    for p in sel:
        for field, s in iter_units(p):
            for m in C_LOW_MORAL_HARD.finditer(s):
                allhard.append(dict(cell=p["cell"], field=field, frag=m.group(0),
                                    ctx=ctx(s, m.start(), m.end()), negated=negated(s, m.start())))
    return sel, hard, spec_ok, soft, allhard


# ---------------------------------------------------------------------------
# 自检：合成违规样本
def make_synthetic():
    def mk(cell, **kw):
        d = dict(cell=cell, lead="占位", summary="占位", life="占位", friends="占位",
                 love="占位", work="占位", pros=["占位"], cons=["占位"], practice=["占位"])
        d.update(kw)
        return d

    bad = [
        mk("O低C低E低A低N低", lead="你是风暴型创作者",
           summary="你天生就是这样的人，注定改不了，你永远会这样，必然如此，一定会重复。",
           life="你就是那种指挥官型的人", friends="你是推动者，也是一个协调者",
           love="你这辈子都会这样", work="骨子里的东西，与生俱来"),
        mk("O高C高E高A高N高",
           summary="你完美无缺，天赋异禀，独一无二，上天给了你魅力四射的气场，命中注定。",
           life="卓越非凡，出类拔萃，人见人爱，自带光环，老天赏饭，正能量满满。"),
        mk("O中C中E中A中N高",
           summary="你可能有抑郁症或焦虑症，甚至是强迫症、躁郁倾向。",
           life="这看起来像 ADHD 或多动症，也可能是自闭谱系、亚斯伯格。",
           friends="这是人格障碍的表现，属于心理疾病，是病态的症状，需要确诊。",
           love="你可能需要看医生，去精神科心理咨询，或者吃药治疗。",
           work="这是病，你不正常，建议寻求专业帮助。",
           cons=["有情绪障碍", "抑郁倾向明显", "焦虑症状明显"]),
        mk("O中C中E中A低N中",
           summary="建议你筛选掉不合适的人，评价别人的可靠度。",
           life="可以试探对方是否真心，考验对方。",
           friends="远离那种拖后腿的人，排除低分的人。",
           love="择偶要看对方分数；相亲时看他的尽责性。",
           work="招聘时优先录用高分候选人。"),
        mk("O中C高E中A中N中",
           summary="你的 Conscientiousness 很高，Neuroticism 偏低。",
           life="Big Five 和 MBTI 都说明这一点，Openness 中等。",
           friends="Extraversion 与 Agreeableness 的组合。"),
        mk("O中C中E低A中N中",
           summary="作为一个内向者，你和外向者不同。",
           life="内向的人普遍如此，外向的人相反。",
           friends="你这种人往往如此。"),
        mk("O中C中E中A中N低", cons=["情绪很稳定", "抗压能力强", "不容易受影响"]),
        mk("O中C中E中A高N中", cons=["太为别人着想", "过于善良", "对人太好"]),
        mk("O中C低E中A中N中", cons=["懒，什么都不想干", "不负责任", "自私又幼稚"]),
    ]

    good = [mk("O中C中E中A中N中",
               lead="五个维度都落在中间，行为更多由场合决定",
               summary="你目前的分数落在中间地带。这个组合通常意味着行为由场合决定，"
                       "而不是由某个突出倾向决定。代价是缺少默认设置，选择时容易反复权衡。",
               life="作息大体规律，两者之间你常默认前者，或者随情况调整。",
               friends="朋友对你的评价往往是挺好相处。别人的评价你会记很久。",
               love="冲突后你不太记仇，回家路上会想很久。",
               work="你在团队里常是发起者，手上永远有一两件半成品。",
               cons=["对他人情绪反应迟钝", "不提要求导致长期不对等", "半成品长期挂着不收尾"],
               practice=["兴奋的当下不要答应任何事，隔 24 小时还想做再答应。"])]
    return bad, good


def selftest():
    bad, good = make_synthetic()
    hits = scan_rules(bad)
    by_rule = collections.Counter(h["rule"] for h in hits)
    # 这些是"扩展/低优先"规则，合成样本不保证覆盖
    optional = {"det.yongyuan_bare", "clin.bare_yiyu", "clin.bare_jiaolv", "astro.chaofan",
                "oth.shibie", "lab.xingge", "oth.raw_shai", "det.benxing"}
    lines = ["=" * 78, "自检 A：合成违规样本 —— 每条规则是否被触发", "=" * 78]
    missed = []
    for rid, name, sec, sev, pat, wl, note in RULES:
        n = by_rule.get(rid, 0)
        if n:
            flag = "OK "
        elif rid in optional:
            flag = "n/a"
        else:
            flag = "MISS"
            missed.append(rid)
        lines.append("  [%s] %-22s %-30s hits=%d" % (flag, rid, name, n))

    tg, cn, _ = scan_labels(bad)
    lines.append("  [%s] %-22s %-30s hits=%d" %
                 ("OK " if tg else "MISS", "label.tagged", "自造类型名·贴标签句式", len(tg)))
    lines.append("  [%s] %-22s %-30s hits=%d" %
                 ("OK " if cn else "MISS", "label.coined", "自造类型名·X型Y者复合词", len(cn)))
    if not tg:
        missed.append("label.tagged")
    if not cn:
        missed.append("label.coined")

    _, rows_n = cost_check(bad, "N", "低", N_LOW_COST, N_LOW_FAKE)
    _, rows_a = cost_check(bad, "A", "高", A_HIGH_COST, A_HIGH_FAKE)
    _, hard, _, _, _ = c_low_moral(bad)
    nfail = [r for r in rows_n if not r["passed"]]
    nfake = [r for r in rows_n if r["fake"]]
    afail = [r for r in rows_a if not r["passed"]]
    afake = [r for r in rows_a if r["fake"]]
    lines.append("  [%s] %-22s %-30s fail=%d fake=%d" %
                 ("OK " if (nfail and nfake) else "MISS", "cost.Nlow", "N低 变相夸奖 cons 判 fail", len(nfail), len(nfake)))
    lines.append("  [%s] %-22s %-30s fail=%d fake=%d" %
                 ("OK " if (afail and afake) else "MISS", "cost.Ahigh", "A高 伪缺点判 fail", len(afail), len(afake)))
    lines.append("  [%s] %-22s %-30s hits=%d" %
                 ("OK " if hard else "MISS", "moral.Clow", "C低 道德批判词", len(hard)))
    for k, ok in (("cost.Nlow", nfail and nfake), ("cost.Ahigh", afail and afake), ("moral.Clow", hard)):
        if not ok:
            missed.append(k)

    lines += ["", "=" * 78, "自检 B：干净对照样本 —— high/medium 规则不应误报", "=" * 78]
    ghits = [h for h in scan_rules(good) if h["severity"] in ("high", "medium")]
    gtag, gcoined, _ = scan_labels(good)
    if not ghits and not gcoined:
        lines.append("  [OK ] 干净样本 0 条 high/medium 误报；0 条造名复合词")
    for h in ghits:
        lines.append("  [FP ] %s %s :: %s" % (h["rule"], h["frag"], h["ctx"]))
    for h in gcoined:
        lines.append("  [FP ] label.coined %s :: %s" % (h["frag"], h["ctx"]))
    for h in gtag:
        lines.append("  [注 ] label.tagged 命中(设计上需人工判定): %s :: %s" % (h["frag"], h["ctx"]))
    _, grn = cost_check([dict(good[0], cell="O中C中E中A中N低")], "N", "低", N_LOW_COST, N_LOW_FAKE)
    _, gra = cost_check([dict(good[0], cell="O中C中E中A高N中")], "A", "高", A_HIGH_COST, A_HIGH_FAKE)
    lines.append("  [%s] 干净样本 N低 cons 判为合格 = %s" % ("OK " if grn[0]["passed"] else "FP ", grn[0]["passed"]))
    lines.append("  [%s] 干净样本 A高 cons 判为合格 = %s" % ("OK " if gra[0]["passed"] else "FP ", gra[0]["passed"]))
    lines.append("")
    lines.append("自检结论：%s（未触发: %s）" %
                 ("全部通过" if not missed else "有 %d 条规则未触发" % len(missed),
                  ",".join(missed) if missed else "无"))
    return lines, missed


# ---------------------------------------------------------------------------
def main():
    only_self = "--selftest" in sys.argv
    st_lines, missed = selftest()
    print("\n".join(st_lines))
    if only_self:
        return

    profiles = json.load(io.open(RAW, encoding='utf-8'))
    assert len(profiles) == 243, len(profiles)
    n_units = sum(1 for p in profiles for _ in iter_units(p))
    n_chars = sum(len(s) for p in profiles for _, s in iter_units(p))

    out = ["", "=" * 78,
           "真实语料全量扫描：%d 画像 / %d 文本单元 / %d 字" % (len(profiles), n_units, n_chars),
           "=" * 78]

    hits = scan_rules(profiles)
    by_rule = collections.defaultdict(list)
    for h in hits:
        by_rule[h["rule"]].append(h)

    out += ["", "---- 规则命中总表 ----",
            "%-22s %-32s %-8s %6s %6s" % ("rule", "name", "sev", "hits", "cells")]
    for rid, name, sec, sev, pat, wl, note in RULES:
        hs = by_rule.get(rid, [])
        out.append("%-22s %-32s %-8s %6d %6d" % (rid, name, sev, len(hs), len({h["cell"] for h in hs})))

    for rid, name, sec, sev, pat, wl, note in RULES:
        hs = by_rule.get(rid, [])
        if not hs:
            continue
        out += ["", "### %s | %s | severity=%s | 命中 %d 条，涉及 %d 格"
                % (rid, name, sev, len(hs), len({h["cell"] for h in hs})), "    说明: " + note]
        for h in hs[:60]:
            out.append("    [%s] %-16s %-10s %s :: %s"
                       % ("否定" if h["negated"] else "  ", h["cell"], h["field"], h["frag"], h["ctx"]))
        if len(hs) > 60:
            out.append("    ...（共 %d 条，完整见 JSON）" % len(hs))

    tagged, coined, tokens = scan_labels(profiles)
    out += ["", "=" * 78, "1. 自造类型名 / 身份标签", "=" * 78,
            "  X型/X者/X家 等后缀词共出现 %d 次（含『两者』『回家』等正常词）" % sum(tokens.values()),
            "  造名式复合词 (X型Y者/X型Y人): %d 条" % len(coined)]
    for h in coined:
        out.append("    !! %-16s %-10s %s :: %s" % (h["cell"], h["field"], h["frag"], h["ctx"]))
    out.append("  『你(是/会是/常是/也是)…者/型/家』句式: %d 条，涉及 %d 格"
               % (len(tagged), len({h["cell"] for h in tagged})))
    for h in tagged:
        out.append("    ?  %-16s %-10s %s :: %s" % (h["cell"], h["field"], h["frag"], h["ctx"]))
    out.append("  ---- 全部 型/者/家 后缀词频（供人工核对白名单）----")
    for k, v in tokens.most_common():
        out.append("     %-6s %4d  %s" % (k, v, "白名单" if k in LABEL_WHITELIST else ""))

    res = {}
    for gname, dim, lev, fams, fake in (("N低", "N", "低", N_LOW_COST, N_LOW_FAKE),
                                        ("A高", "A", "高", A_HIGH_COST, A_HIGH_FAKE)):
        sel, rows = cost_check(profiles, dim, lev, fams, fake)
        npass = sum(1 for r in rows if r["passed"])
        npb = sum(1 for r in rows if r["passed_with_body"])
        nfake = [r for r in rows if r["fake"]]
        out += ["", "=" * 78, "8. 代价检查 · %s（%d 格）" % (gname, len(sel)), "=" * 78,
                "  cons 里含该档具体代价行为: %d/%d = %.1f%%" % (npass, len(sel), 100.0 * npass / len(sel)),
                "  含 >=2 条具体代价:          %d/%d = %.1f%%"
                % (sum(1 for r in rows if r["n_matched"] >= 2), len(sel),
                   100.0 * sum(1 for r in rows if r["n_matched"] >= 2) / len(sel)),
                "  cons 未命中但正文写了代价:  %d 格（合并口径 %d/%d = %.1f%%）"
                % (npb - npass, npb, len(sel), 100.0 * npb / len(sel)),
                "  命中『伪缺点/变相夸奖』模板: %d 格" % len(nfake)]
        famc = collections.Counter(f for r in rows for f in r["families"])
        out.append("  代价家族分布(按格计): " + ", ".join("%s=%d" % (k, v) for k, v in famc.most_common()))
        worst = sorted(rows, key=lambda r: (r["n_matched"], len(r["body_families"]), r["cell"]))[:10]
        out.append("  ---- 最弱的 10 格（cons 命中代价条数升序）----")
        for r in worst:
            out.append("    %-16s cons命中=%d  正文兜底=%s"
                       % (r["cell"], r["n_matched"], ",".join(r["body_families"]) or "无"))
            for c in r["cons"]:
                out.append("        - " + c)
        res[gname] = dict(n=len(sel), pass_cons=npass, pass_body=npb, fake=len(nfake), rows=rows)

    sel, hard, spec_ok, soft, allhard = c_low_moral(profiles)
    out += ["", "=" * 78, "9. C低（%d 格）cons 是否滑向道德批判" % len(sel), "=" * 78,
            "  硬性人格价值判断词(懒/不负责任/自私/幼稚/无能…) in cons: %d 条（其中否定用法 %d）"
            % (len(hard), sum(1 for h in hard if h["negated"]))]
    for h in hard:
        out.append("    [%s] %-16s %-10s %s :: %s"
                   % ("否定" if h["negated"] else "命中", h["cell"], h["field"], h["frag"], h["text"]))
    out.append("  同类词在全文(含 summary/life/…)出现: %d 条（否定用法 %d）"
               % (len(allhard), sum(1 for h in allhard if h["negated"])))
    for h in allhard:
        out.append("    [%s] %-16s %-10s %s :: %s"
                   % ("否定" if h["negated"] else "命中", h["cell"], h["field"], h["frag"], h["ctx"]))
    out.append("  规格自身认可的可靠性用词(不可靠/靠不住) in cons: %d 条" % len(spec_ok))
    for h in spec_ok:
        out.append("    [OK] %-16s %s :: %s" % (h["cell"], h["frag"], h["text"]))
    out.append("  边缘描述词(散漫/懒得/随性/不靠谱) in cons: %d 条" % len(soft))
    for h in soft:
        out.append("    [? ] %-16s %s :: %s" % (h["cell"], h["frag"], h["text"]))

    io.open(OUT_TXT, "w", encoding="utf-8").write("\n".join(st_lines + out))
    payload = dict(
        n_profiles=len(profiles), n_units=n_units, n_chars=n_chars, selftest_missed=missed,
        rule_summary=[dict(rule=r[0], name=r[1], section=r[2], severity=r[3],
                           hits=len(by_rule.get(r[0], [])),
                           cells=sorted({h["cell"] for h in by_rule.get(r[0], [])})) for r in RULES],
        hits=hits, label_tagged=tagged, label_coined=coined,
        label_tokens=dict(tokens),
        cost=dict((k, dict(n=v["n"], pass_cons=v["pass_cons"], pass_body=v["pass_body"],
                           fake=v["fake"], rows=v["rows"])) for k, v in res.items()),
        c_low=dict(n=len(sel), hard=hard, hard_all=allhard, spec_ok=spec_ok, soft=soft))
    io.open(OUT_JSON, "w", encoding="utf-8").write(json.dumps(payload, ensure_ascii=False, indent=1))
    print("\n".join(out))
    print("\n written: %s\n written: %s" % (OUT_TXT, OUT_JSON))


if __name__ == "__main__":
    main()
