# -*- coding: utf-8 -*-
"""cvuse_semantic: Barnum / specificity / harm probes. READ ONLY."""
import json, os, re, sys, math, itertools
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'out', 'profiles_raw.json'), encoding='utf-8'))
LV = {'低': 0, '中': 1, '高': 2}
DIMS = ['O', 'C', 'E', 'A', 'N']
TF = ['lead', 'summary', 'life', 'friends', 'love', 'work']
LF = ['pros', 'cons', 'practice']
BY = {p['cell']: p for p in D}
VEC = {c: tuple(LV[c[i * 2 + 1]] for i in range(5)) for c in BY}
CELLS = list(BY)
def blob(p): return ''.join(p[f] for f in TF) + ''.join(''.join(p[f]) for f in LF)

# ---------- A. 语义级邻居相似度（字 bigram cosine，比 5-gram 宽松） ----------
def bg(t):
    t = re.sub(r'[^一-鿿]', '', t)
    return Counter(t[i:i+2] for i in range(len(t)-1))
BG = {c: bg(blob(BY[c])) for c in CELLS}
def cos(a, b):
    A, B = BG[a], BG[b]
    num = sum(A[k]*B[k] for k in set(A) & set(B))
    return num / (math.sqrt(sum(v*v for v in A.values())) * math.sqrt(sum(v*v for v in B.values())))
print('### A. 字 bigram 余弦：邻居 vs 随机基线')
per_dim = defaultdict(list)
for c in CELLS:
    v = VEC[c]
    for i, d in enumerate(DIMS):
        if v[i] < 2:
            w = list(v); w[i] += 1
            nb = ''.join(f'{DIMS[k]}{"低中高"[w[k]]}' for k in range(5))
            per_dim[d].append((cos(c, nb), c, nb))
for d in DIMS:
    vals = [x[0] for x in per_dim[d]]
    print(f'  {d}: mean={sum(vals)/len(vals):.3f} max={max(vals):.3f} min={min(vals):.3f}')
base = [cos(a, b) for a, b in itertools.combinations(CELLS[:80], 2)]
print(f'  随机对基线 mean={sum(base)/len(base):.3f}')
alln = sorted([x for d in DIMS for x in per_dim[d]], reverse=True)
print('  最像的 8 对邻居:')
for s, a, b in alln[:8]:
    print(f'    {s:.3f}  {a} ~ {b}')

# ---------- B. 维度信号强度：标记词是否随该维度档位单调变化 ----------
MARK = {
 'O': ['新东西','新方向','新想法','抽象','好奇','审美','熟悉','老办法','跑通','务实','原样','新流程','新工具'],
 'C': ['拖','收尾','截止','清单','计划表','日程','守时','条理','完不成','兑现','交付','规律'],
 'E': ['独处','一个人','人群','社交','热闹','局','主动约','话少','充电','安静'],
 'A': ['冲突','让步','迁就','拒绝','直','顶回去','照顾','体谅','对方的感受','不客气','怼'],
 'N': ['反刍','回放','复盘','焦虑','不安','放大','起伏','稳','平静','担心','琢磨','重放'],
}
print()
print('### B. 维度标记词密度 vs 该维度档位（每千字次数）')
for i, d in enumerate(DIMS):
    row = []
    for lv in range(3):
        cs = [c for c in CELLS if VEC[c][i] == lv]
        tot = sum(len(blob(BY[c])) for c in cs)
        hit = sum(blob(BY[c]).count(m) for c in cs for m in MARK[d])
        row.append(hit / tot * 1000)
    mono = '单调' if (row[0] < row[1] < row[2] or row[0] > row[1] > row[2]) else 'U/倒U'
    print(f'  {d}: 低={row[0]:5.1f} 中={row[1]:5.1f} 高={row[2]:5.1f}  跨度={max(row)/max(min(row),0.01):4.1f}x  {mono}')

# ---------- C. 矛盾泄漏：不该出现的说法出现在相反档位 ----------
print()
print('### C. 泄漏检查（某档位不该有的措辞）')
LEAK = [
 ('N低', 'N', 0, ['反刍','回放到','失眠','焦虑得','越想越糟','夜里反复']),
 ('N高', 'N', 2, ['情绪几乎不占','几乎不内耗','不太上火','情绪成本低']),
 ('E高', 'E', 2, ['独处补充能量','很少主动联系','从不主动发起','不主动约']),
 ('E低', 'E', 0, ['人群中补充能量','局多','是召集人','张罗']),
 ('C高', 'C', 1, ['收不了尾','一路拖到最后','完不成']),
 ('C低', 'C', 0, ['守时','有条理','交付稳']),
 ('A高', 'A', 2, ['不肯先退','顶回去','说话冲','敢冲突']),
 ('A低', 'A', 0, ['过度让步','不忍心拒绝','怕伤害对方']),
]
for name, d, lv, pats in LEAK:
    i = DIMS.index(d)
    cs = [c for c in CELLS if VEC[c][i] == lv]
    hits = [(c, m) for c in cs for m in pats if m in blob(BY[c])]
    print(f'  {name}: {len(set(h[0] for h in hits))}/{len(cs)} 篇出现矛盾措辞', hits[:4])

# ---------- D. practice 具体性 ----------
print()
print('### D. practice 具体性打分')
CONC = [r'每周', r'每天', r'每月', r'每季度', r'每年', r'每半年', r'当天', r'隔一天', r'二十四小时', r'\d+',
        r'三个', r'两个', r'一天', r'半小时', r'二十分钟', r'十分钟', r'三十分钟', r'写进日历', r'写下', r'列', r'发一条']
QUOTE = ['「', '"', '“', '：']
VAGUE = ['多沟通', '学会', '试着更', '保持', '注意', '提升自己', '增强', '培养', '要更加']
n = 0; conc = 0; quoted = 0; vague = []
for p in D:
    for x in p['practice']:
        n += 1
        if any(re.search(r, x) for r in CONC): conc += 1
        if any(q in x for q in QUOTE): quoted += 1
        if any(v in x for v in VAGUE): vague.append((p['cell'], x))
print(f'  含时间/频次/数量锚点: {conc}/{n} = {conc/n*100:.1f}%')
print(f'  含可照读的台词/引号: {quoted}/{n} = {quoted/n*100:.1f}%')
print(f'  含空泛动词("多沟通/学会/保持"等): {len(vague)}/{n} = {len(vague)/n*100:.1f}%')
for c, x in vague[:8]: print(f'     {c}: {x}')

# ---------- E. 每个维度的代价是否都写了（规格要求每一档都有代价） ----------
print()
print('### E. 低神经质/高宜人 的代价是否写出')
n_low = [c for c in CELLS if VEC[c][4] == 0]
cost_kw = ['迟钝','不敏感','察觉不到','读成冷','接收不到','低估别人','冷酷','没有刹车','不觉得需要']
hit = sum(1 for c in n_low if any(k in blob(BY[c]) for k in cost_kw))
print(f'  N低 {hit}/{len(n_low)} 篇写了低神经质的代价')
a_high = [c for c in CELLS if VEC[c][3] == 2]
ck2 = ['被占','不敢提','不提要求','让步','退让','不拒绝','委屈','边界']
hit2 = sum(1 for c in a_high if any(k in blob(BY[c]) for k in ck2))
print(f'  A高 {hit2}/{len(a_high)} 篇写了高宜人的代价')

# ---------- F. 伤害风险：cons 措辞 ----------
print()
print('### F. cons 措辞伤害扫描')
HARSH = ['废','没用','失败','懒','幼稚','自私','软弱','病','不成熟','差劲','糟糕','缺陷','不行','弱点','无能']
PERSON = ['你是个','你这种人','本质上','根本上','性格有']
for grp, i, lv in [('N高', 4, 2), ('C低', 1, 0), ('A低', 3, 0)]:
    cs = [c for c in CELLS if VEC[c][i] == lv]
    txt = [(c, x) for c in cs for x in BY[c]['cons']]
    h = [(c, x) for c, x in txt if any(w in x for w in HARSH)]
    pp = [(c, x) for c, x in txt if any(w in x for w in PERSON)]
    print(f'  {grp}: cons {len(txt)} 条，含贬损词 {len(h)}，含人格定性 {len(pp)}')
    for c, x in h[:5]: print(f'     {c}: {x}')
# 全局人格定性扫描
gp = [(p['cell'], f, x) for p in D for f in TF+LF
      for x in ([p[f]] if isinstance(p[f], str) else p[f]) if any(w in x for w in PERSON)]
print(f'  全库"你是个/你这种人/本质上"等定性句: {len(gp)}', gp[:5])

# ---------- G. 短文本画像（内容量不足） ----------
print()
print('### G. 内容量不足的画像（life/friends/love/work 有几段 <80 字）')
short = []
for p in D:
    k = sum(1 for f in ['life','friends','love','work'] if len(p[f]) < 80)
    if k: short.append((k, sum(len(p[f]) for f in ['life','friends','love','work']), p['cell']))
short.sort(reverse=True)
print(f'  至少一段不足80字的画像: {len(short)}/243')
print(f'  4段全部不足80字: {sum(1 for k,_,_ in short if k==4)}')
print(f'  >=3段不足: {sum(1 for k,_,_ in short if k>=3)}')
print('  最单薄的 12 篇 (不足段数, 四段总字数, cell):')
for k, t, c in short[:12]: print(f'    {k}段 总{t}字  {c}')
