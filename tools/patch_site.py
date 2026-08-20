# -*- coding: utf-8 -*-
"""Build site/index.optimized.html from site/index.html.

Changes, all backed by measurements in tools/out/:

 1. Percentile map: the cubic polynomial + hard rails at T=32/73 is replaced by
    empirical lookup tables built from Johnson's own 145,388-respondent sample.
    Measured error over 5,088,580 respondent x scale values: 2.94 -> 0.06 points.
 2. Norms: the shipped 6x71 vectors are dropped in favour of the sample-recomputed
    means/SDs carried inside the tables, so the T score and the percentile finally
    come from the same sample.
 3. level(): 45/55 on a percentile (a T-score band applied to the wrong units, and
    contradicting the page's own copy) -> 30/70, which the page already states.
 4. Copy: the norm-sample description, the percentile explanation, the footer and the
    careless-responding warning are replaced with the measured figures.
 5. Dead code: `const REV` was declared and never used.
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(os.path.dirname(HERE), "site")
SRC = os.path.join(SITE, "index.html")
DST = os.path.join(SITE, "index.optimized.html")
OUT = os.path.join(HERE, "out")

html = io.open(SRC, encoding="utf-8").read()
payload = io.open(os.path.join(OUT, "pct_tables_encoded.txt"), encoding="utf-8").read().strip()
decoder = io.open(os.path.join(OUT, "decoder.js"), encoding="utf-8").read()
# drop the doc comment header and the node export tail
decoder_js = decoder.split("*/", 1)[1].split("if (typeof module")[0].strip()

edits = []


def sub(old, new, what):
    """Exactly-once replacement, loudly."""
    global html
    n = html.count(old)
    if n != 1:
        sys.exit("PATCH FAILED (%s): expected 1 occurrence, found %d\n---\n%s" % (what, n, old[:300]))
    html = html.replace(old, new, 1)
    edits.append((what, len(new) - len(old)))


# ------------------------------------------------------------------ 1. drop DATA.norms
start = html.index('"norms":')
depth, i = 0, html.index("{", start)
while True:
    if html[i] == "{":
        depth += 1
    elif html[i] == "}":
        depth -= 1
        if depth == 0:
            break
    i += 1
norms_block = html[start:i + 1]
# swallow the comma that separated it from its neighbour
if html[start - 1] == ",":
    norms_block = "," + norms_block
    start -= 1
html = html[:start] + html[start + len(norms_block):]
edits.append(("drop DATA.norms (superseded by the sample-recomputed norms in the tables)",
              -len(norms_block.encode("utf-8"))))

# ------------------------------------------------------------------ 2. scoring block
old_scoring = html[html.index("/* ================= SCORING"):html.index("/* ================= TEST UI")]

new_scoring = '''/* ================= 经验百分位查找表 =================
   由 Johnson 的 IPIP-NEO-300 常模样本（145,388 份作答）直接计算，
   每个 (常模组, 量表, 原始分) 一格，共 14,610 格，单调、无空洞。
   构建与校验脚本见 tools/build_tables.py。                                */
''' + decoder_js + '''

const PCT_PAYLOAD = "''' + payload + '''";

/* ================= SCORING =================
   面向与维度的聚合沿用 five-factor-e (MIT) 的布局，已与参考实现逐值核对：
   145,388 份作答 x 35 个量表 = 5,088,580 个百分位全部精确复现。

   唯一不同的是「原始分 -> 百分位」这一步。原版用一条三次多项式近似正态分布，
   并在 T<32 / T>73 处硬截断为 1 和 99。在常模样本上实测，那条映射平均偏
   2.94 个百分位（最大 17.2），且 4.47% 的分数被截断压平；这里改为直接查
   经验百分位表，平均偏 0.06 个百分位，没有截断。                        */
const OCEAN = ["O","C","E","A","N"];
const PCT = decodePctTables(PCT_PAYLOAD);

/* 低 / 中等 / 高 切在 30 与 70 —— 和页面正文里说的模糊边界一致。
   原版用 45/55，那是 T 分的惯用分界，套在百分位上只会把 88% 的量表
   推进「低」或「高」两端。百分位在常模样本上是均匀分布的，
   30/70 恰好切出 30% / 40% / 30%。                                    */
const level = p => p <= 30 ? "低" : (p < 70 ? "中等" : "高");

/* 各量表的 Cronbach α（145,388 份常模样本实测），用于置信区间。
   SEM = SD·√(1−α)；95% 区间 = 原始分 ±1.96·SEM，再过同一张经验百分位表——
   区间在原始分空间是对称的，映到百分位后两端自动变窄，与查表逻辑自洽。 */
const ALPHA = {"O":0.907,"O1":0.855,"O2":0.811,"O3":0.788,"O4":0.817,"O5":0.852,"O6":0.784,"C":0.947,"C1":0.829,"C2":0.858,"C3":0.801,"C4":0.84,"C5":0.894,"C6":0.846,"E":0.943,"E1":0.89,"E2":0.891,"E3":0.862,"E4":0.725,"E5":0.849,"E6":0.844,"A":0.92,"A1":0.885,"A2":0.789,"A3":0.839,"A4":0.774,"A5":0.778,"A6":0.785,"N":0.956,"N1":0.865,"N2":0.914,"N3":0.916,"N4":0.832,"N5":0.784,"N6":0.86};

function ci95(g, scale, raw){
  const half = 1.96 * PCT.norms[g][scale].sd * Math.sqrt(1 - ALPHA[scale]);
  return [PCT.lookup(g, scale, Math.round(raw - half)),
          PCT.lookup(g, scale, Math.round(raw + half))];
}

/* 轨道上的浅色区段 */
function ciBand(ci, color){
  if (!ci) return "";
  const l = Math.max(0, Math.min(100, ci[0]));
  const w = Math.max(0.8, Math.min(100, ci[1]) - l);
  return '<s style="left:' + l.toFixed(1) + '%;width:' + w.toFixed(1) + '%;background:' + color + '"></s>';
}

function cohortKey(sex, age){
  const s = (sex === "M" || sex === "F") ? sex : "N";
  return s + "_" + (age < 21 ? "lt21" : "gte21");
}

function score(ans, sex, age){
  const a = ans.slice();
  for (const q of DATA.reversed) a[q] = 6 - a[q];

  const ss = new Array(31).fill(0);            // facet raw sums, 1..30
  for (let j = 0; j < 30; j++)
    for (let i = 0; i < 10; i++)
      ss[1+j] += a[1 + i*30 + j];

  const b5 = {N:[0],E:[0],O:[0],A:[0],C:[0]};  // facet raw by domain, 1..6
  for (let i = 1; i <= 6; i++){
    b5.N[i] = ss[5*i-4]; b5.E[i] = ss[5*i-3]; b5.O[i] = ss[5*i-2];
    b5.A[i] = ss[5*i-1]; b5.C[i] = ss[5*i];
  }

  const dom = {};
  for (const k of OCEAN) dom[k] = b5[k].slice(1,7).reduce((x,y)=>x+y, 0);

  const g = cohortKey(sex, age);
  const out = {};
  for (const k of OCEAN){
    const t = PCT.tscore(g, k, dom[k]);
    const p = PCT.lookup(g, k, dom[k]);
    const facets = [];
    for (let i = 1; i <= 6; i++){
      const sc = k + i;
      const ft = PCT.tscore(g, sc, b5[k][i]);
      const fp = PCT.lookup(g, sc, b5[k][i]);
      facets.push({i, raw:b5[k][i], t:ft, pct:fp, level:level(fp), ci:ci95(g, sc, b5[k][i])});
    }
    out[k] = {raw:dom[k], t, pct:p, level:level(p), ci:ci95(g, k, dom[k]), facets};
  }
  return out;
}

'''
sub(old_scoring, new_scoring, "replace cubic+rails percentile map with empirical tables")

# ------------------------------------------------------------------ 3. copy: norm sample
sub(
    '<p class="sub">百分位对照的是 Johnson 的 IPIP-NEO 英文在线样本——以欧美英语母语者为主的网络自选样本，不是中国人群常模。',
    '<p class="sub">百分位对照的是 Johnson 的 IPIP-NEO-300 英文在线样本，共 <b>145,388 份作答</b>，收集于 2001–2011 年。'
    '这个样本的构成值得你先知道：<b>69.2% 来自美国</b>，连同英国、加拿大、澳大利亚、新西兰、爱尔兰合计 86.3%，欧洲大陆只占约 6%；'
    '中国大陆、香港、台湾、新加坡加起来 2,117 人，占 <b>1.46%</b>（其中新加坡一地 1,149 人，就多过前三者之和）。'
    '样本也偏年轻、偏女性：中位年龄 22 岁，43.1% 不满 21 岁，58.3% 为女性。'
    '所以它<b>既不是中国人群常模，也不是一般成年人常模</b>。',
    "norm-sample description -> measured composition")

# ------------------------------------------------------------------ 4. copy: how to read
sub(
    '下面所有数字都是<b>百分位</b>：50 代表和常模人群的中位数持平，80 代表高于 80% 的人。'
    '30 和 70 附近是模糊边界，不要把相邻的“中等”和“偏高／偏低”理解成截然不同的人格。',
    '下面所有数字都是<b>百分位</b>，直接数出来的：80 就表示常模样本里有 80% 的人分数比你低，50 就是正好落在中位数。'
    '（早先的版本用一条多项式去近似这个百分位，两端还会被压平成 1 和 99；现在是查表，不再有近似和截断。）'
    '「低／中等／高」切在 30 和 70，但这两处是模糊边界，不要把相邻的两档理解成截然不同的人格。',
    "percentile explanation -> empirical, 30/70")

# ------------------------------------------------------------------ 5. copy: footer
sub(
    '常模来自 Johnson 的 IPIP-NEO 英文在线样本（以欧美英语母语者为主的网络自选样本），按性别和年龄段（&lt;21 / ≥21）分组，'
    '<b>不是中国人群常模</b>。中文语境下分数会有系统性偏移，百分位请当作粗略的参考刻度，更值得看的是你 30 个子面向之间的相对高低。',
    '常模来自 Johnson 的 IPIP-NEO-300 英文在线样本（n=145,388，2001–2011 年，69.2% 美国、86.3% 英语圈、中港台新合计 1.46%，'
    '中位年龄 22 岁、58.3% 女性），按性别和年龄段（&lt;21 / ≥21）分成 6 组，百分位在每组内直接由样本数出来。'
    '它<b>不是中国人群常模</b>：中文语境下分数会有系统性偏移，百分位请当作粗略的参考刻度，更值得看的是你 30 个子面向之间的相对高低。',
    "footer norm paragraph -> measured composition")

# ------------------------------------------------------------------ 6. copy: validity warning
sub(
    '"。Johnson (2005) 用这个阈值筛掉「没读题就连点」的作答，被筛掉的约占 3.5%。'
    '如果这确实是你的真实作答，忽略即可；如果是快速点选留下的，建议重测。";',
    '"。这套阈值来自 Johnson (2005)，用来筛出「没读题就连点」的作答。"\n'
    '      + "但请把它当作提示而不是判决：把同一套规则跑在 145,388 份常模样本上，也有 2.99% 被标记，"\n'
    '      + "而且这些标记全部来自「很不符合」一个选项——因为本量表第 238–300 题恰好全是反向题，'
    '真心一贯的人在这一段本来就会连着按同一个键（被标记的连击有 97% 起始于第 150 题之后）。"\n'
    '      + "所以：如果这确实是你的真实作答，忽略即可；如果是快速点选留下的，建议重测。";',
    "careless-responding warning -> measured, and explains the false-positive mechanism")

# (`const REV = new Set(DATA.reversed)` was declared and never used; it lived inside the
#  scoring block replaced above, so it is already gone.)

# ------------------------------------------------------------------ 7. provenance comment
sub(
    " 计分算法与常模移植自 five-factor-e，以下为其许可证全文：",
    " 计分算法与常模移植自 five-factor-e，以下为其许可证全文。\n"
    " 注：面向/维度的聚合与 T 分与 five-factor-e 等价（已用 Johnson 的 145,388 份常模样本\n"
    " 逐值核对，5,088,580 个百分位全部精确复现）；「原始分 -> 百分位」一步已改为直接查\n"
    " 同一样本的经验百分位表，不再使用原版的三次多项式近似与 T<32/T>73 硬截断。\n"
    " 148 道反向计分题的清单已与 IPIP 官方公布的 NEO Facets Key 按题目文本逐条比对\n"
    " （https://ipip.ori.org/newNEOFacetsKey.htm）：300/300 匹配，键控与面向归属各 0 处不符。",
    "provenance comment -> note the percentile-map divergence")

# ------------------------------------------------------------------ 8. tail display
# Without the old rails the tails now carry real values (0.0005 .. 99.9995), so
# Math.round would print "0" or "100" -- both misleading. Print "<1" / ">99" instead,
# which is honest about the direction without claiming a precision the tail lacks.
sub("const OCEAN = [\"O\",\"C\",\"E\",\"A\",\"N\"];\nconst PCT = decodePctTables(PCT_PAYLOAD);",
    "const OCEAN = [\"O\",\"C\",\"E\",\"A\",\"N\"];\nconst PCT = decodePctTables(PCT_PAYLOAD);\n\n"
    "/* 显示用：查表后两端不再被截断成 1 / 99，最低可到 0.0005。\n"
    "   直接四舍五入会印出「0」或「100」，两者都在暗示一个不存在的确定性。 */\n"
    "const fmtPct = p => p < 0.5 ? \"<1\" : (p > 99.5 ? \">99\" : String(Math.round(p)));",
    "add fmtPct for the tails")

for old, new, what in [
    ("'<span class=\"pct\">' + Math.round(r.pct) + '</span></div>' +",
     "'<span class=\"pct\">' + fmtPct(r.pct) + '</span></div>' +", "domain headline pct"),
    ("'|' + r.t.toFixed(1) + '|' + Math.round(r.pct) + '\">' +",
     "'|' + r.t.toFixed(1) + '|' + fmtPct(r.pct) + '\">' +", "domain tooltip pct"),
    ("'|' + f.t.toFixed(1) + '|' + Math.round(f.pct) + '|' + m[2] + '\">' +",
     "'|' + f.t.toFixed(1) + '|' + fmtPct(f.pct) + '|' + m[2] + '\">' +", "facet tooltip pct"),
    ("'<span class=\"fpct\">' + Math.round(f.pct) + '</span></div>';",
     "'<span class=\"fpct\">' + fmtPct(f.pct) + '</span></div>';", "facet bar pct"),
    ("'</h3><span class=\"muted\">总分百分位 ' + Math.round(r.pct) + '</span></div>' +",
     "'</h3><span class=\"muted\">总分百分位 ' + fmtPct(r.pct) + '</span></div>' +", "facet card header"),
    # keep the numeric pct (the ↑/↓ arrow compares it) and carry the display string separately
    ("key: d.key, name: DATA.facets[d.key][i][0], pct: Math.round(f.pct), dev: Math.abs(f.pct - 50)",
     "key: d.key, name: DATA.facets[d.key][i][0], pct: f.pct, disp: fmtPct(f.pct), dev: Math.abs(f.pct - 50)",
     "hero chip: carry both the number and its display form"),
    ("c.name + ' <b>' + c.pct + '</b><span class=\"muted\">' + (c.pct >= 50 ? \"↑\" : \"↓\") + '</span></span>').join(\"\");",
     "c.name + ' <b>' + c.disp + '</b><span class=\"muted\">' + (c.pct >= 50 ? \"↑\" : \"↓\") + '</span></span>').join(\"\");",
     "hero chip: render the display form"),
    ("'</td><td class=\"n\"><b>' + Math.round(r.pct) + '</b></td><td>' + r.level + '</td></tr>';",
     "'</td><td class=\"n\"><b>' + fmtPct(r.pct) + '</b></td><td>' + r.level + '</td></tr>';",
     "table view domain pct"),
    ("'</td><td class=\"n\">' + Math.round(f.pct) + '</td><td>' + f.level + '</td></tr>';",
     "'</td><td class=\"n\">' + fmtPct(f.pct) + '</td><td>' + f.level + '</td></tr>';",
     "table view facet pct"),
    # the radar printed the geometry-clamped value (floor 2) as if it were the score
    ("const v = Math.max(2, Math.min(100, res[d.key].pct));\n    return {d, ang, v,",
     "const v = Math.max(2, Math.min(100, res[d.key].pct));\n    return {d, ang, v, pct: res[d.key].pct,",
     "radar: carry the true pct alongside the clamped geometry"),
    ("font-family=\"inherit\">' + Math.round(p.v) + '</text>';",
     "font-family=\"inherit\">' + fmtPct(p.pct) + '</text>';", "radar label uses the true pct"),
    # JSON export keeps precision rather than rounding a 0.07 to 0
    ("raw:f.raw, t:+f.t.toFixed(2), percentile:Math.round(f.pct)}))",
     "raw:f.raw, t:+f.t.toFixed(2), percentile:+f.pct.toFixed(2)}))", "JSON export: facet precision"),
    ("raw:r[d.key].raw, t:+r[d.key].t.toFixed(2), percentile:Math.round(r[d.key].pct),",
     "raw:r[d.key].raw, t:+r[d.key].t.toFixed(2), percentile:+r[d.key].pct.toFixed(2),",
     "JSON export: domain precision"),
]:
    sub(old, new, what)

# ------------------------------------------------------------------ 8b. China gap
# Two copy fixes, both from re-deriving the numbers off Johnson's raw OSF files
# (IPIP120.dat n=410,376 and IPIP300.dat) rather than trusting a summary.
#
# (1) The page pointed readers at a Mandarin IPIP-NEO-120 "with Chinese norms". Checked:
#     that is a one-paragraph registration notice on IPIP's translations page -- no paper,
#     no item text, no norm values, nothing downloadable. Sending users to look for it is
#     misleading, so the pointer goes.
# (2) In its place, the actual measured gap. Greater China n=3,676 vs USA n=296,766:
#     mean |d| = 0.207, SD ratio 0.861 (Chinese respondents are ~14% less spread out).
#     But the correction is NOT stable: estimating the same gap from the 300-item file
#     (n=983) disagrees by 0.136 SD on average -- 66% of the signal -- with 5/30 facets
#     flipping sign and 20/30 disagreements exceeding sampling error (r = 0.741).
#     So: disclose the direction, refuse to "correct" the scores. Only 3 facets replicate
#     at |d|>0.3 with a consistent sign, and those are named.
sub(
    "如果你需要有中国样本常模的版本，华东师范大学 Zhongyang Xu 等人已经做过 IPIP-NEO-120 的普通话译本"
    "并提供了中国样本常模，登记在 IPIP 官网的翻译页上。",
    "这个偏差有多大，可以直接量出来。Johnson 公开了原始作答数据，其中用英文作答的"
    "大中华区被试有 3,676 人。拿他们和 296,766 名美国被试比：30 个子面向的平均差距是 "
    "0.21 个标准差，而且这批人的分数<b>比美国样本集中约 14%</b>——极端选项选得少。"
    "两者叠加的后果是<b>高分被压低</b>：一个在自己人群里排到第 84 百分位的人，"
    "在本站大约只会看到 77。"
    "<br><br>"
    "那为什么不直接换一套常模？因为<b>这个修正量本身不可靠</b>。用 Johnson 另一份数据"
    "（同一批年份、同一个网站、300 题版）独立估一遍，两次结果平均差 0.14 个标准差，"
    "相当于要修正的偏差的三分之二；30 个面向里有 5 个连方向都相反，20 个的分歧超出抽样误差。"
    "拿一个误差和它本身一样大的修正量去改你的分数，只会让结果更不可信。"
    "<br><br>"
    "两份数据都稳定指向同一方向的只有三个面向：<b>寻求刺激、想象力、放纵</b>——"
    "中文用户在这三项上的分数会被系统性显示得偏低。其余 27 个面向，"
    "我们只能告诉你偏差存在，说不准偏多少。"
    "<br><br>"
    "还有一层这些数字碰不到：上面那 3,676 人都是<b>用英文作答</b>的，"
    "他们是英语能力筛出来的人群。用中文作答会不会另有偏移，没有任何数据能回答。",
    "replace the misleading Mandarin-norms pointer with the measured, non-correctable gap")

# ------------------------------------------------------------------ 8c. confidence bands
# The one survivor of the paradata research round: put a 95% interval on every printed
# percentile. Effect size dwarfs every validity-detector proposal (facet intervals are
# tens of points wide), the derivation is short enough to print (SEM = SD*sqrt(1-alpha),
# both inputs already ship in the page), and it extends the site's existing honesty about
# the 47.2% cell-reproduction rate to every individual number.
sub("'|' + r.t.toFixed(1) + '|' + fmtPct(r.pct) + '\">' +",
    "'|' + r.t.toFixed(1) + '|' + fmtPct(r.pct) + '（95% 区间 ' + fmtPct(r.ci[0]) + '–' + fmtPct(r.ci[1]) + '）\">' +",
    "CI in the domain tooltip")
sub("'<i style=\"background:' + COLOR(d.key) + ';width:' + Math.max(1.2, r.pct) + '%\"></i><u></u></div>' +",
    "'<i style=\"background:' + COLOR(d.key) + ';width:' + Math.max(1.2, r.pct) + '%\"></i>' + ciBand(r.ci, COLOR(d.key)) + '<u></u></div>' +",
    "CI band on the domain track")
sub("'|' + f.t.toFixed(1) + '|' + fmtPct(f.pct) + '|' + m[2] + '\">' +",
    "'|' + f.t.toFixed(1) + '|' + fmtPct(f.pct) + '（95% 区间 ' + fmtPct(f.ci[0]) + '–' + fmtPct(f.ci[1]) + '）|' + m[2] + '\">' +",
    "CI in the facet tooltip")
sub("'<span class=\"ftrack\"><i style=\"background:' + COLOR(d.key) + ';width:' + Math.max(1.2, f.pct) + '%\"></i><u></u></span>' +",
    "'<span class=\"ftrack\"><i style=\"background:' + COLOR(d.key) + ';width:' + Math.max(1.2, f.pct) + '%\"></i>' + ciBand(f.ci, COLOR(d.key)) + '<u></u></span>' +",
    "CI band on the facet track")
sub(".ftrack>u{position:absolute;top:-2px;bottom:-2px;left:50%;width:1px;background:var(--axis)}",
    ".ftrack>u{position:absolute;top:-2px;bottom:-2px;left:50%;width:1px;background:var(--axis)}\n"
    ".track>s,.ftrack>s{position:absolute;top:0;bottom:0;opacity:.22;border-radius:3px;pointer-events:none}",
    "CI band styles")
sub("「低／中等／高」切在 30 和 70，但这两处是模糊边界，不要把相邻的两档理解成截然不同的人格。",
    "「低／中等／高」切在 30 和 70，但这两处是模糊边界，不要把相邻的两档理解成截然不同的人格。"
    "横条上颜色较浅的一段是 <b>95% 置信区间</b>：同一个人换一天再测，分数大概率落在这段里。"
    "区间由量表信度算出（SEM = SD·√(1−α)，α 为常模样本实测值），子面向只有 10 道题，区间普遍不窄。"
    "这不是这份测评独有的毛病，是所有短量表共同的物理现实。看方向，别抠精确值。",
    "explain the CI band in the guide")

# ------------------------------------------------------------------ 9. broken share card
# saveCard() calls levelWord(p), which is never defined anywhere in the page. Clicking
# 「保存分享卡片」 throws ReferenceError: levelWord is not defined at the first domain bar,
# so no PNG is ever produced. Pre-existing on the deployed site; verified in-browser.
if "levelWord =" in html or "function levelWord" in html:
    sys.exit("levelWord now has a definition upstream -- revisit this patch step")
sub("/* --- 分享卡片：纯前端 canvas 生成 PNG，只含分数概览 --- */",
    "/* --- 分享卡片：纯前端 canvas 生成 PNG，只含分数概览 --- */\n"
    "/* levelWord 原本被 saveCard 调用却从未定义，点「保存分享卡片」会抛\n"
    "   ReferenceError 并且什么都存不下来。这里补上，分界与结果页的 level() 一致。 */\n"
    "const levelWord = p => level(p);",
    "define the missing levelWord (share card was throwing)")

# share card: the bar label and the caption
sub('const p = Math.round(res[d.key].pct);', 'const p = res[d.key].pct;', "share card: keep precision")
sub("x.font = \"700 30px \" + F; x.textAlign = \"right\"; x.fillText(String(p), 1008, y);",
    "x.font = \"700 30px \" + F; x.textAlign = \"right\"; x.fillText(fmtPct(p), 1008, y);",
    "share card: format the tail")

# ------------------------------------------------------------------ 9a. break card copy
# The rest prompt cited Masuda et al. (2017) for three claims the paper does not make.
# Verified: that paper is "Respondents with low motivation tend to choose middle category:
# survey questions on happiness in Japan" (Behaviormetrika) -- a BETWEEN-person finding
# about motivation in Japanese wellbeing surveys. No item position, no fatigue over the
# course of a questionnaire, no Big Five, no split administration.
# And the direction is wrong here anyway: in the norm sample the midpoint rate FALLS with
# position (positive items 19.02% -> 14.99%, reversed 21.54% -> 15.23%) while extreme
# responding rises. The slopes match across both keyings (-1.11 vs -1.13 %/block), so it
# is a position effect, not a keying artefact.
# The break feature stays; only the unsupported mechanism goes.
sub("/* 每 5 页（75 题）提示一次休息。依据 Masuda 等 (2017)：大五问卷上题目位置越靠后，\n"
    "   中间档背书率越高；分次施测能重置这个漂移。只提示，不强制。 */",
    "/* 每 5 页（75 题）提示一次休息。只提示，不强制。\n"
    "   这里原本引 Masuda 等 (2017) 说「越往后越容易往中间档靠」，那是误引：该文讲的是\n"
    "   低动机受访者更爱选中间档（人与人之间的差异），不涉及题目位置、疲劳或分次施测。\n"
    "   而且方向相反——在 Johnson 的常模样本上，中间档比例随位置下降（正向题 19.0%→15.0%，\n"
    "   反向题 21.5%→15.2%），走极端的比例上升。正反向题的斜率几乎相同（-1.11 与 -1.13\n"
    "   每 30 题），所以这是位置效应而非键控假象。既然机制说不清楚，就不说。 */",
    "break card: drop the misattributed Masuda citation")

sub('"研究发现，连着答长问卷时越往后越容易往中间档靠——这是疲劳，不是你对后面的题真的更没想法。" +\n'
    '    "歇一会儿再回来，这个漂移会被重置。进度已经存好了，关掉网页也不会丢。" +',
    '"长问卷答到后面，注意力和刚开始不会一样。要不要歇，你自己判断。" +\n'
    '    "进度已经存好了，关掉网页也不会丢，明天再接着答也可以。" +',
    "break card: replace the unsupported mechanism with a plain prompt")

# ------------------------------------------------------------------ 9b. combination profile
# 3^5 = 243 cells over the 低<=30 / 中 / 高>=70 bands. All 243 are occupied in the norm
# sample (rarest has 24 people), but the cell only reproduces on a parallel form 47.2% of
# the time, because 66.8% of people sit within 5 percentile points of a 30/70 cut.
# So: no type names, tendency wording, and the page itself flags which dimensions are
# borderline and offers the neighbouring profile.
profiles_path = os.path.join(OUT, "profiles_ordered.json")
if os.path.exists(profiles_path):
    profiles_json = io.open(profiles_path, encoding="utf-8").read().strip()
    # Hard stop, not a warning: an earlier build shipped the placeholder text into
    # site/index.optimized.html and only a QA agent caught it. Match the exact stub
    # markers, not the bare word -- "不占位置" is ordinary Chinese and appears in two
    # genuine profiles.
    STUB_MARKERS = ["占位文本 ·", "占位 summary", "占位优点", "占位缺点", "占位练习",
                    "真实文案由写作工作流产出后替换"]
    hit = [m for m in STUB_MARKERS if m in profiles_json]
    if hit:
        sys.exit("REFUSING TO BUILD: profiles_ordered.json still holds placeholder text %s\n"
                 "Run tools/extract_profiles.py to land the real 243 profiles first." % hit)
    if len(json.loads(profiles_json)) != 243:
        sys.exit("REFUSING TO BUILD: profiles_ordered.json does not hold exactly 243 entries")

    sub('  <h2>30 个子面向</h2>',
        '  <h2>你的组合画像</h2>\n'
        '  <p class="sub" style="margin-top:-6px">把五个维度各切成低／中／高，一共 243 种组合。'
        '下面是你这一格。</p>\n'
        '  <div id="profile"></div>\n\n'
        '  <h2>30 个子面向</h2>',
        "add the combination-profile section")

    sub("  buildTable(res);\n  show(\"result\");",
        "  renderProfile(res);\n  buildTable(res);\n  show(\"result\");",
        "call renderProfile from showResult")

    sub("/* --- 分享卡片：纯前端 canvas 生成 PNG，只含分数概览 --- */",
        '''/* --- 组合画像：243 格 --- */
const PROFILES = ''' + profiles_json + ''';
const PF_KEYS = ["O","C","E","A","N"];
const PF_LV = ["低","中","高"];
const PF_CUTS = [30, 70];

/* 画像文本是数据，走 innerHTML 前一律转义。当前 243 篇里没有 &lt; &amp; 这类字符，
   但以后改一个字就可能有，届时不转义会直接坏掉页面。 */
const ESC = {"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"};
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ESC[c]);

const bandOf = p => p <= PF_CUTS[0] ? 0 : (p < PF_CUTS[1] ? 1 : 2);
const profileIndex = b => ((((b[0]*3 + b[1])*3 + b[2])*3 + b[3])*3 + b[4]);

/* 离最近一条分界线还有多远。实测 66.8% 的人至少有一个维度在 5 分以内，
   这种时候档位是随机的，必须告诉用户，而不是让他以为自己被精确归了类。 */
const cutDistance = p => Math.min(Math.abs(p - PF_CUTS[0]), Math.abs(p - PF_CUTS[1]));

function cellLabel(b){
  return PF_KEYS.map((k, i) => DATA.domains.find(d => d.key === k).name + PF_LV[b[i]]).join(" · ");
}

function renderProfile(res){
  const box = $("#profile");
  if (!box || !PROFILES || PROFILES.length !== 243){ if (box) box.innerHTML = ""; return; }

  const bands = PF_KEYS.map(k => bandOf(res[k].pct));
  const p = PROFILES[profileIndex(bands)];
  if (!p){ box.innerHTML = ""; return; }

  /* 贴近分界的维度，按贴得多近排序 */
  const border = PF_KEYS.map((k, i) => ({k, i, d: cutDistance(res[k].pct), pct: res[k].pct}))
    .filter(x => x.d < 5).sort((a, b) => a.d - b.d);

  const sect = (t, body) => '<div class="pf-sect"><b>' + t + '</b><p>' + esc(body) + '</p></div>';
  const list = (t, arr, cls) => '<div class="pf-list ' + cls + '"><b>' + t + '</b><ul>' +
    (arr || []).map(x => '<li>' + esc(x) + '</li>').join("") + '</ul></div>';

  let warn = "";
  if (border.length){
    const near = border.map(x => {
      const d = DATA.domains.find(dd => dd.key === x.k);
      return d.name + " " + fmtPct(x.pct);
    }).join("、");
    /* 邻格：把最贴边的那个维度挪到分界另一侧 */
    const alt = bands.slice();
    const t = border[0];
    alt[t.i] = res[t.k].pct <= PF_CUTS[0] ? 1
             : (res[t.k].pct >= PF_CUTS[1] ? 1
             : (Math.abs(res[t.k].pct - PF_CUTS[0]) < Math.abs(res[t.k].pct - PF_CUTS[1]) ? 0 : 2));
    const ap = PROFILES[profileIndex(alt)];
    warn = '<div class="pf-warn"><b>先看这个：你有维度正好压在分界线上</b>' +
      '<p>' + near + ' 离「低／中／高」的分界不到 5 分。这不是精确的归类——' +
      '同一个人再测一次，落回同一格的概率实测只有 47.2%。下面这段请当作倾向来读。</p>' +
      (ap ? '<details><summary>看看紧挨着的那一格（' + cellLabel(alt) + '）</summary>' +
            '<p style="margin:8px 0 0"><i>' + esc(ap.lead) + '</i></p><p>' + esc(ap.summary) + '</p></details>' : "") +
      '</div>';
  }

  box.innerHTML =
    '<div class="card pf">' +
      '<div class="pf-head"><span class="pf-cell">' + cellLabel(bands) + '</span>' +
        '<h3>' + esc(p.lead) + '</h3></div>' +
      warn +
      '<p class="pf-summary">' + esc(p.summary) + '</p>' +
      '<div class="pf-grid">' +
        sect("生活", p.life) + sect("交友与朋友", p.friends) +
        sect("恋爱", p.love) + sect("工作", p.work) +
      '</div>' +
      '<div class="pf-lists">' +
        list("优点", p.pros, "pf-pro") + list("缺点", p.cons, "pf-con") +
      '</div>' +
      list("可以练的", p.practice, "pf-do") +
    '</div>';
}

/* --- 分享卡片：纯前端 canvas 生成 PNG，只含分数概览 --- */''',
        "add the 243-profile data and renderer")

    sub("/* charts */",
        '''/* combination profile */
.pf{margin:0}
.pf-head{margin-bottom:12px}
.pf-cell{display:inline-block;font-size:12px;letter-spacing:.06em;color:var(--text-muted);
  border:1px solid var(--border);border-radius:20px;padding:3px 11px;margin-bottom:9px}
.pf-head h3{font-size:19px;line-height:1.45;margin:0}
.pf-summary{font-size:15px;line-height:1.75;margin:0 0 18px}
.pf-warn{border:1px solid var(--accent);background:var(--wash);border-radius:10px;
  padding:12px 15px;margin:0 0 16px;font-size:13px;line-height:1.6}
.pf-warn p{margin:6px 0 0;color:var(--text-secondary)}
.pf-warn summary{cursor:pointer;margin-top:9px;color:var(--accent);font-size:12.5px}
.pf-warn details p{margin:6px 0 0}
.pf-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 22px;margin-bottom:18px}
@media (max-width:620px){.pf-grid{grid-template-columns:1fr}}
.pf-sect b{display:block;font-size:13px;color:var(--accent);margin-bottom:4px}
.pf-sect p{margin:0;font-size:14px;line-height:1.7;color:var(--text-secondary)}
.pf-lists{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 22px;margin-bottom:16px}
@media (max-width:620px){.pf-lists{grid-template-columns:1fr}}
.pf-list b{display:block;font-size:13px;margin-bottom:5px}
.pf-list ul{margin:0;padding-left:18px}
.pf-list li{font-size:13.5px;line-height:1.7;color:var(--text-secondary)}
.pf-pro b{color:#1baf7a}
.pf-con b{color:#eb6834}
.pf-do{border-top:1px solid var(--grid);padding-top:14px}
.pf-do b{color:var(--text-primary)}

/* charts */''',
        "add the profile styles")
else:
    print("  !! tools/out/profiles_ordered.json not found -- profile section skipped")

# ------------------------------------------------------------------ 10. drop the RUM beacon
# The source we patch was captured from the live response, so it carries Cloudflare's
# auto-injected Web Analytics tag. Two reasons to strip it:
#   - if the dashboard toggle is still on, deploying this file loads the beacon twice;
#   - the page invites the reader to open the network panel and verify nothing is sent,
#     and a third-party request is exactly what they would find.
# Turning the dashboard toggle off is still required; this only cleans the file.
beacon = re.search(r'\n?<script[^>]*cloudflareinsights\.com[^>]*></script>', html)
if beacon:
    html = html.replace(beacon.group(0), "")
    edits.append(("strip the Cloudflare Web Analytics beacon tag",
                  -len(beacon.group(0).encode("utf-8"))))
else:
    print("note: no beacon tag found (already clean)")

io.open(DST, "w", encoding="utf-8", newline="").write(html)

print("wrote %s" % DST)
print("\nedits:")
for what, delta in edits:
    print("  %+7d bytes   %s" % (delta, what))
src_b = os.path.getsize(SRC)
dst_b = os.path.getsize(DST)
print("\n  %s : %d bytes" % (os.path.basename(SRC), src_b))
print("  %s : %d bytes  (%+d, %+.1f%%)" % (os.path.basename(DST), dst_b, dst_b - src_b,
                                           100.0 * (dst_b - src_b) / src_b))
