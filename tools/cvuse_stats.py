# -*- coding: utf-8 -*-
"""cvuse_stats: quantify reuse / Barnum / dimension-drive. READ ONLY."""
import json, os, re, sys, itertools
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'out', 'profiles_raw.json'), encoding='utf-8'))
LV = {'低': 0, '中': 1, '高': 2}
DIMS = ['O', 'C', 'E', 'A', 'N']
TEXT_FIELDS = ['lead', 'summary', 'life', 'friends', 'love', 'work']
LIST_FIELDS = ['pros', 'cons', 'practice']

def parse(c):
    return tuple(LV[c[i * 2 + 1]] for i in range(5))

BY = {p['cell']: p for p in D}
VEC = {c: parse(c) for c in BY}
CELLS = list(BY)

def blob(p):
    return ''.join(p[f] for f in TEXT_FIELDS) + ''.join(''.join(p[f]) for f in LIST_FIELDS)

def sents(p):
    out = []
    for f in TEXT_FIELDS:
        for s in re.split(r'[。！？\n]', p[f]):
            s = s.strip()
            if len(s) >= 8:
                out.append((f, s))
    return out

def ngrams(t, n=5):
    t = re.sub(r'[^一-鿿]', '', t)
    return set(t[i:i + n] for i in range(len(t) - n + 1))

print('### 1. 段落长度 vs 规格')
spec = {'lead': (18, 28), 'summary': (110, 160), 'life': (80, 120), 'friends': (80, 120),
        'love': (80, 120), 'work': (80, 120)}
for f, (lo, hi) in spec.items():
    L = [len(p[f]) for p in D]
    under = sum(1 for x in L if x < lo); over = sum(1 for x in L if x > hi)
    print(f'  {f:8s} min={min(L):3d} max={max(L):3d} mean={sum(L)/len(L):5.1f} '
          f'低于下限={under:3d} 高于上限={over:3d} 合规={243-under-over:3d}/243')
for f, (lo, hi) in [('pros', (8, 20)), ('cons', (8, 20)), ('practice', (20, 45))]:
    L = [len(x) for p in D for x in p[f]]
    under = sum(1 for x in L if x < lo); over = sum(1 for x in L if x > hi)
    print(f'  {f:8s} min={min(L):3d} max={max(L):3d} n={len(L)} 低于下限={under:3d} 高于上限={over:3d}')

print()
print('### 2. 句子级复用（同一句话出现在几个格子）')
sent2cells = defaultdict(set)
for p in D:
    for f, s in sents(p):
        sent2cells[s].add(p['cell'])
tot_sent_inst = sum(len(sents(p)) for p in D)
dup = {s: cs for s, cs in sent2cells.items() if len(cs) > 1}
dup_inst = sum(len(cs) for cs in dup.values())
print(f'  句子实例总数 {tot_sent_inst}，去重后 {len(sent2cells)}')
print(f'  出现在>=2格的句子 {len(dup)} 种，占用 {dup_inst} 个实例 = {dup_inst/tot_sent_inst*100:.1f}% 的句子位')
buckets = Counter(len(cs) for cs in sent2cells.values())
print('  复用度分布(格数:句种数):', dict(sorted(buckets.items())[:12]))
print('  复用最广的 12 句：')
for s, cs in sorted(dup.items(), key=lambda kv: -len(kv[1]))[:12]:
    print(f'    [{len(cs):3d}格] {s[:46]}')

print()
print('### 3. practice / pros / cons 条目复用')
for f in LIST_FIELDS:
    item2cells = defaultdict(set)
    for p in D:
        for x in p[f]:
            item2cells[x].add(p['cell'])
    n = sum(len(p[f]) for p in D)
    reused = sum(len(cs) for cs in item2cells.values() if len(cs) > 1)
    print(f'  {f}: {n} 条，去重 {len(item2cells)} 种，重复条目占 {reused/n*100:.1f}%')
    top = sorted(item2cells.items(), key=lambda kv: -len(kv[1]))[:4]
    for x, cs in top:
        print(f'     [{len(cs):3d}格] {x[:40]}')

print()
print('### 4. 邻居相似度：哪个维度没有真正驱动内容')
G = {c: ngrams(blob(BY[c])) for c in CELLS}
def jac(a, b):
    A, B = G[a], G[b]
    return len(A & B) / len(A | B)
per_dim = defaultdict(list)
for c in CELLS:
    v = VEC[c]
    for i, d in enumerate(DIMS):
        for nv in (v[i] - 1, v[i] + 1):
            if 0 <= nv <= 2:
                w = list(v); w[i] = nv
                nb = ''.join(f'{DIMS[k]}{"低中高"[w[k]]}' for k in range(5))
                if nb in BY and c < nb:
                    per_dim[d].append(jac(c, nb))
print('  只差该维度一档的两格，文本 5-gram Jaccard 相似度（越高=该维度越没驱动内容）:')
for d in DIMS:
    v = per_dim[d]
    print(f'    {d}: n={len(v):3d}  mean={sum(v)/len(v):.3f}  max={max(v):.3f}  '
          f'>0.5的对数={sum(1 for x in v if x > .5)}')
allpairs = [jac(a, b) for a, b in itertools.combinations(CELLS, 2)]
print(f'  全部 {len(allpairs)} 对随机基线 mean={sum(allpairs)/len(allpairs):.3f}')

print()
print('  相似度最高的 10 对邻居：')
flat = []
for c in CELLS:
    v = VEC[c]
    for i, d in enumerate(DIMS):
        w = list(v)
        if v[i] < 2:
            w[i] = v[i] + 1
            nb = ''.join(f'{DIMS[k]}{"低中高"[w[k]]}' for k in range(5))
            flat.append((jac(c, nb), d, c, nb))
for s, d, a, b in sorted(flat, reverse=True)[:10]:
    print(f'    {s:.3f} [{d}] {a}  ~  {b}')

print()
print('### 5. 维度在文本里被显式提及的比例')
kw = {'O': ['开放'], 'C': ['尽责'], 'E': ['外向'], 'A': ['宜人'], 'N': ['神经质']}
for i, d in enumerate(DIMS):
    for lv in range(3):
        cs = [c for c in CELLS if VEC[c][i] == lv]
        hit = sum(1 for c in cs if any(k in blob(BY[c]) for k in kw[d]))
        print(f'  {d}{"低中高"[lv]}: {hit}/{len(cs)} 篇显式提到该维度名 ({hit/len(cs)*100:.0f}%)')

print()
print('### 6. 规格红线扫描')
bans = ['天生', '注定', '你就是', '内向者', '外向者', '抑郁', '焦虑症', '多动', '自闭', '障碍', '人格类型', '型人格']
for b in bans:
    hits = [(p['cell'], f) for p in D for f in TEXT_FIELDS + LIST_FIELDS
            if b in (p[f] if isinstance(p[f], str) else ''.join(p[f]))]
    if hits:
        print(f'  "{b}": {len(hits)} 处 ->', hits[:6])
soft = ['你目前', '这个组合', '大概率', '往往', '通常', '多半']
print('  软化措辞覆盖：', {s: sum(1 for p in D if s in blob(p)) for s in soft})
print('  含至少一个软化词的画像:', sum(1 for p in D if any(s in blob(p) for s in soft)), '/243')
retest = sum(1 for p in D if '重测' in blob(p) or '再测' in blob(p))
print('  正文提到重测/再测的画像:', retest, '/243')
