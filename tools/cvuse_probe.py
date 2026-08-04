# -*- coding: utf-8 -*-
"""cvuse_probe: openness-drive + thin-profile concentration + barnum swap test. READ ONLY."""
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
def name(v): return ''.join(f'{DIMS[k]}{"低中高"[v[k]]}' for k in range(5))

O_LOW = ['熟悉','务实','老办法','跑通','原样','新东西','新工具','新流程','嫌麻烦','具体怎么做','用了很多年','验证过','不追新','换新']
O_HIGH = ['新想法','抽象','好奇','审美','新方向','点子','想法多','被新','兴趣广','开新','新鲜','琢磨新','概念']
print('### 1. 开放性到底有没有被写出来')
for lv, kws, lab in [(0, O_LOW, 'O低'), (2, O_HIGH, 'O高')]:
    cs = [c for c in CELLS if VEC[c][0] == lv]
    hit = [c for c in cs if any(k in blob(BY[c]) for k in kws)]
    print(f'  {lab}: {len(hit)}/{len(cs)} 篇出现该档位的行为标记词 ({len(hit)/len(cs)*100:.0f}%)')
    miss = [c for c in cs if c not in hit]
    print(f'     完全没有 O 内容的: {len(miss)} 例, 前6:', miss[:6])

print()
print('### 2. 只差 O 一档的三元组：三篇是否真的不同')
def bg(t):
    t = re.sub(r'[^一-鿿]', '', t); return Counter(t[i:i+2] for i in range(len(t)-1))
BG = {c: bg(blob(BY[c])) for c in CELLS}
def cos(a, b):
    A, B = BG[a], BG[b]
    return sum(A[k]*B[k] for k in set(A)&set(B)) / (math.sqrt(sum(v*v for v in A.values()))*math.sqrt(sum(v*v for v in B.values())))
trip = []
seen = set()
for c in CELLS:
    v = VEC[c]; key = v[1:]
    if key in seen: continue
    seen.add(key)
    ts = [name((lv,)+v[1:]) for lv in range(3)]
    trip.append((ts, cos(ts[0], ts[1]), cos(ts[1], ts[2]), cos(ts[0], ts[2])))
print(f'  共 {len(trip)} 组。O低~O中 平均相似 {sum(t[1] for t in trip)/len(trip):.3f}，'
      f'O中~O高 {sum(t[2] for t in trip)/len(trip):.3f}，O低~O高 {sum(t[3] for t in trip)/len(trip):.3f}')
print('  O低~O中 最难区分的 5 组：')
for ts, a, b, cc in sorted(trip, key=lambda t: -t[1])[:5]:
    print(f'    {a:.3f}  {ts[0]}  vs  {ts[1]}')

print()
print('### 3. 单薄画像的分布：是不是集中在某类格子')
short = [p['cell'] for p in D if sum(1 for f in ['life','friends','love','work'] if len(p[f]) < 80) >= 3]
print(f'  >=3段不足80字的画像 {len(short)} 篇')
for i, d in enumerate(DIMS):
    print(f'    按 {d} 分布:', Counter('低中高'[VEC[c][i]] for c in short).most_common())
print('  全部名单:'); print('   ', ' '.join(sorted(short)))
oc = [c for c in CELLS if VEC[c][0]==2 and VEC[c][1]==2]
print(f'  O高C高 共 {len(oc)} 格，其中单薄 {sum(1 for c in oc if c in short)} 格')
tot = {c: sum(len(BY[c][f]) for f in ['life','friends','love','work']) for c in CELLS}
print(f'  O高C高 四段均字数 {sum(tot[c] for c in oc)/len(oc):.0f}  其余 {sum(tot[c] for c in CELLS if c not in oc)/(243-len(oc)):.0f}')

print()
print('### 4. 巴纳姆交叉测试：拿 A 格的句子去 B 格找同义claim')
# 选 3 段做交叉测试：把句子的 claim 抽象成关键词组，看有多少个别的格子也成立
PROBES = [
 ('O中C中E中A中N中/friends', ['高估','主动性','半年没'],
  '你觉得我们常联系的朋友，可能已经半年没收到你消息了'),
 ('O高C高E高A高N低/love', ['太少提要求','不提要求','没有需求','以为一切都好','以为你没有'],
  '你太少提要求，对方会长期以为一切都好'),
 ('O低C高E低A低N高/friends', ['不主动修复','默认他知道','没说出口','一次次记下'],
  '你不主动修复，也不解释，默认他知道自己做了什么'),
]
for tag, kws, txt in PROBES:
    hits = [c for c in CELLS if any(k in blob(BY[c]) for k in kws)]
    print(f'  探针 [{tag}] "{txt[:26]}…"')
    print(f'     在 {len(hits)}/243 格里出现同义说法 = {len(hits)/243*100:.0f}%')
    byd = {}
    for i, d in enumerate(DIMS):
        cnt = Counter('低中高'[VEC[c][i]] for c in hits)
        byd[d] = dict(cnt)
    print(f'     命中格子的维度分布: {byd}')

print()
print('### 5. summary 是否真的写了维度交互')
INTER = ['加','让','使','同时','两者','三股','叠','互相','这一组','合起来','凑在一起','而']
pat = re.compile(r'(高|低|中等)?(开放|尽责|外向|宜人|神经质)')
cnt2 = 0
for p in D:
    ms = set(m.group(0) for m in pat.finditer(p['summary']))
    if len(ms) >= 2: cnt2 += 1
print(f'  summary 里同时点名 >=2 个维度的画像: {cnt2}/243 = {cnt2/243*100:.0f}%')
cnt3 = sum(1 for p in D if len(set(m.group(0) for m in pat.finditer(blob(p)))) >= 3)
print(f'  全文点名 >=3 个维度的画像: {cnt3}/243')
none_ = [p['cell'] for p in D if len(set(m.group(0) for m in pat.finditer(p['summary']))) < 2]
print(f'  summary 只点名 <2 个维度的: {len(none_)} 例', none_[:8])
