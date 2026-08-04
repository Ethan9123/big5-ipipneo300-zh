# -*- coding: utf-8 -*-
"""cvuse_rank: shortlist best/worst + harm read. READ ONLY."""
import json, os, re, sys, math
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'out', 'profiles_raw.json'), encoding='utf-8'))
LV = {'低': 0, '中': 1, '高': 2}
DIMS = ['O', 'C', 'E', 'A', 'N']
TF = ['lead', 'summary', 'life', 'friends', 'love', 'work']
LF = ['pros', 'cons', 'practice']
BY = {p['cell']: p for p in D}
VEC = {c: tuple(LV[c[i*2+1]] for i in range(5)) for c in BY}
CELLS = list(BY)
def blob(p): return ''.join(p[f] for f in TF) + ''.join(''.join(p[f]) for f in LF)

CONC = [r'每周', r'每天', r'每月', r'每季度', r'每年', r'每半年', r'当天', r'隔一天', r'二十四小时',
        r'\d+', r'三个', r'两个', r'一天', r'半小时', r'分钟', r'写进日历', r'写下', r'发一条', r'列出']
QUOTE = ['「', '"', '“']
TEXTURE = ['凌晨','洗澡','睡前','聊天记录','未读','待办','日历','群里','第三周','半年','两天','消息',
           '语气','回复速度','会上','周末','清单','纸上','截止','名单']

rows = []
for p in D:
    c = p['cell']; b = blob(p)
    seclen = [len(p[f]) for f in ['life','friends','love','work']]
    short = sum(1 for x in seclen if x < 80)
    conc = sum(1 for x in p['practice'] if any(re.search(r, x) for r in CONC))
    quo = sum(1 for x in p['practice'] if any(q in x for q in QUOTE))
    tex = sum(b.count(t) for t in TEXTURE)
    dimnamed = len(set(m.group(0) for m in re.finditer(r'(高|低|中等)?(开放|尽责|外向|宜人|神经质)', b)))
    score = (sum(seclen)/40) + conc*3 + quo*2 + tex*1.2 + dimnamed*1.5 - short*8
    rows.append((score, c, sum(seclen), short, conc, quo, tex, dimnamed))
rows.sort()
print('### 综合分最低的 18 篇 (总字/不足段/practice具体条/带台词/细节词/点名维度)')
for r in rows[:18]:
    print(f'  {r[0]:7.1f}  {r[1]}  字{r[2]:4d} 短{r[3]} 具体{r[4]} 台词{r[5]} 细节{r[6]:2d} 维度{r[7]}')
print()
print('### 综合分最高的 15 篇')
for r in rows[-15:][::-1]:
    print(f'  {r[0]:7.1f}  {r[1]}  字{r[2]:4d} 短{r[3]} 具体{r[4]} 台词{r[5]} 细节{r[6]:2d} 维度{r[7]}')

print()
print('### 非 O高C高 里最差的 10 篇（排除已知的整块偏短问题）')
nonhc = [r for r in rows if not (VEC[r[1]][0] == 2 and VEC[r[1]][1] == 2)]
for r in nonhc[:10]:
    print(f'  {r[0]:7.1f}  {r[1]}  字{r[2]:4d} 短{r[3]} 具体{r[4]} 台词{r[5]} 细节{r[6]:2d} 维度{r[7]}')

print()
print('### 伤害风险精读：N高 且 C低 且 A低 的全部 9 格 cons')
for c in sorted(CELLS):
    v = VEC[c]
    if v[4] == 2 and v[1] == 0 and v[3] == 0:
        print(f'  [{c}] lead: {BY[c]["lead"]}')
        for x in BY[c]['cons']: print(f'      cons - {x}')
        for x in BY[c]['pros']: print(f'      pros - {x}')
print()
print('### 全库 cons 里最重的措辞抽查（含否定性强词）')
STRONG = ['最容易被读成','伤','毁','拖垮','塌','崩','爆发','断交','消耗','失控','废掉','伤人','树敌','没人','孤立']
hit = [(p['cell'], x) for p in D for x in p['cons'] if any(s in x for s in STRONG)]
print(f'  {len(hit)} 条 / 729')
for c, x in hit[:20]: print(f'    {c}: {x}')
