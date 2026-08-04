# -*- coding: utf-8 -*-
"""cvuse_harm: negative-superlative scan + practice<->cons coupling. READ ONLY."""
import json, os, re, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'out', 'profiles_raw.json'), encoding='utf-8'))
LV = {'低': 0, '中': 1, '高': 2}
TF = ['lead', 'summary', 'life', 'friends', 'love', 'work']
LF = ['pros', 'cons', 'practice']
BY = {p['cell']: p for p in D}

print('### 1. 全局负面排名措辞（暗示"你这格是243里最糟的"）')
PAT = [r'最(差|糟|糟糕|麻烦|难|苦|吃力|危险|极端)的?(一格|一类|组合|格)',
       r'破坏(面积|力)最大', r'最(难|不)(相处|讨喜)', r'(243|所有格子)里最',
       r'最(消耗|折磨|痛苦)的一格', r'代价最大的一格', r'最吃力的']
seen = {}
for p in D:
    for f in TF + LF:
        vals = [p[f]] if isinstance(p[f], str) else p[f]
        for v in vals:
            for pt in PAT:
                for m in re.finditer(pt, v):
                    seen.setdefault((p['cell'], f, m.group(0)), v)
for (c, f, g), v in seen.items():
    print(f'  [{c}/{f}] «{g}»  → {v[:56]}')
print(f'  合计 {len(seen)} 处')

print()
print('### 2. "这一格最X" 类自我定位句（中性/正面也算）总量')
n = sum(1 for p in D for f in TF for m in re.finditer(r'这一格', p[f]))
cells = sum(1 for p in D if any('这一格' in p[f] for f in TF))
print(f'  出现 {n} 次，覆盖 {cells}/243 篇')

print()
print('### 3. practice 是否针对本格的 cons（关键词耦合）')
def toks(s):
    return set(re.findall(r'[一-鿿]{2,4}', s))
cov = []
for p in D:
    ct = set()
    for x in p['cons']: ct |= toks(x)
    pt = set()
    for x in p['practice']: pt |= toks(x)
    # 用单字重合估计主题耦合
    cch = set(''.join(p['cons'])); pch = set(''.join(p['practice']))
    cov.append((len(cch & pch) / max(len(cch), 1), p['cell']))
cov.sort()
m = sum(x[0] for x in cov) / len(cov)
print(f'  cons 与 practice 的字符重合率 平均 {m*100:.1f}%')
print('  最低的 8 篇（practice 可能没对准自己的 cons）:')
for r, c in cov[:8]:
    print(f'    {r*100:4.1f}%  {c}')
    print(f'        cons: {" / ".join(BY[c]["cons"])}')
    print(f'        prac: {" / ".join(BY[c]["practice"])}')

print()
print('### 4. 第二人称"你"的密度（是否过度定性）')
d = [(''.join(p[f] for f in TF).count('你'), len(''.join(p[f] for f in TF)), p['cell']) for p in D]
print(f'  平均每百字出现 "你" {sum(a for a,_,_ in d)/sum(b for _,b,_ in d)*100:.1f} 次')

print()
print('### 5. lead 里出现负面词的比例（首屏印象）')
NEG = ['差','糟','不','没','难','怨','伤','拖','收不','耗','塌','爆发','失','缺']
neg = [p['cell'] for p in D if sum(p['lead'].count(x) for x in NEG) >= 3]
print(f'  lead 含 >=3 个负面词的画像: {len(neg)}/243')
print('  例:', neg[:10])
onlyneg = [p['cell'] for p in D if all(x in p['lead'] for x in []) ]
pos = ['稳','靠','可靠','强','好','准','早','能','敢','真']
both = sum(1 for p in D if any(x in p['lead'] for x in pos))
print(f'  lead 含至少一个正面词的画像: {both}/243')
