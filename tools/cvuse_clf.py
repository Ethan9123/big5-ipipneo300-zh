# -*- coding: utf-8 -*-
"""cvuse_clf: leave-one-out re-identification test (pure python). READ ONLY."""
import json, os, re, sys, math, random
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

# tf-idf on char bigrams
docs = {}
for c in CELLS:
    t = re.sub(r'[^一-鿿]', '', blob(BY[c]))
    docs[c] = Counter(t[i:i+2] for i in range(len(t)-1))
df = Counter()
for c in CELLS: df.update(docs[c].keys())
N = len(CELLS)
TFIDF = {}
for c in CELLS:
    v = {k: (1+math.log(n)) * math.log(N/df[k]) for k, n in docs[c].items() if df[k] >= 2}
    nrm = math.sqrt(sum(x*x for x in v.values())) or 1
    TFIDF[c] = {k: x/nrm for k, x in v.items()}
def dot(a, b):
    if len(a) > len(b): a, b = b, a
    return sum(x*b[k] for k, x in a.items() if k in b)

print('### 1. 留一法「盲猜档位」：只看文字能不能还原出这一维是低/中/高')
print('    (随机基线 33.3%。分数越高 = 文字越是真的按这个维度写的)')
overall = []
for i, d in enumerate(DIMS):
    correct = 0; adj = 0
    conf = [[0]*3 for _ in range(3)]
    for c in CELLS:
        cent = []
        for lv in range(3):
            grp = [x for x in CELLS if VEC[x][i] == lv and x != c]
            acc = defaultdict(float)
            for x in grp:
                for k, val in TFIDF[x].items(): acc[k] += val
            nrm = math.sqrt(sum(v*v for v in acc.values())) or 1
            cent.append({k: v/nrm for k, v in acc.items()})
        scores = [dot(TFIDF[c], cent[lv]) for lv in range(3)]
        pred = max(range(3), key=lambda l: scores[l])
        true = VEC[c][i]
        conf[true][pred] += 1
        if pred == true: correct += 1
        if abs(pred-true) <= 1: adj += 1
    overall.append(correct/N)
    print(f'  {d}: 准确率 {correct}/{N} = {correct/N*100:5.1f}%   (±1档内 {adj/N*100:5.1f}%)')
    print(f'     混淆矩阵 真低[{conf[0]}] 真中[{conf[1]}] 真高[{conf[2]}]  (列=预测低/中/高)')
print(f'  五维平均 {sum(overall)/5*100:.1f}%')
allc = 0
for c in CELLS:
    ok = True
    for i in range(5):
        cent = []
        for lv in range(3):
            grp = [x for x in CELLS if VEC[x][i] == lv and x != c]
            acc = defaultdict(float)
            for x in grp:
                for k, val in TFIDF[x].items(): acc[k] += val
            nrm = math.sqrt(sum(v*v for v in acc.values())) or 1
            cent.append({k: v/nrm for k, v in acc.items()})
        if max(range(3), key=lambda l: dot(TFIDF[c], cent[l])) != VEC[c][i]: ok = False; break
    allc += ok
print(f'  五个维度全部猜对的画像: {allc}/243 = {allc/243*100:.1f}% (随机基线 0.4%)')

print()
print('### 2. 最近邻测试：跟自己文字最像的那一格，档位差几档')
def cos(a, b): return dot(TFIDF[a], TFIDF[b])
h = []
for c in CELLS:
    best = max((x for x in CELLS if x != c), key=lambda x: cos(c, x))
    h.append(sum(1 for i in range(5) if VEC[c][i] != VEC[best][i]))
print(f'  最近邻的平均汉明距离 {sum(h)/len(h):.2f} 档  (随机基线约 3.33)')
print('  分布:', dict(sorted(Counter(h).items())))

print()
print('### 3. 句子级「无锚点」比例（可能换格也成立的句子）')
MARK = ('新东西 新方向 新想法 抽象 好奇 审美 熟悉 老办法 跑通 务实 原样 新流程 新工具 嫌麻烦 '
 '拖 收尾 截止 清单 计划 日程 守时 条理 完不成 兑现 交付 规律 待办 '
 '独处 一个人 人群 社交 热闹 局 主动约 话少 充电 安静 张罗 召集 '
 '冲突 让步 迁就 拒绝 顶回去 照顾 体谅 怼 直率 说话冲 不好意思 委屈 边界 '
 '反刍 回放 复盘 焦虑 不安 放大 起伏 平静 担心 琢磨 重放 内耗 稳 敏感 '
 '开放性 尽责性 外向 宜人 神经质').split()
tot = 0; anch = 0; noanchor = []
for p in D:
    for f in TF[1:]:
        for s in re.split(r'[。！？]', p[f]):
            s = s.strip()
            if len(s) < 8: continue
            tot += 1
            if any(m in s for m in MARK): anch += 1
            else: noanchor.append((p['cell'], f, s))
print(f'  含维度锚点的句子 {anch}/{tot} = {anch/tot*100:.1f}%')
print(f'  无锚点句子 {len(noanchor)} 条 = {len(noanchor)/tot*100:.1f}%  抽样 10 条：')
random.seed(7)
for c, f, s in random.sample(noanchor, 10): print(f'    [{c}/{f}] {s[:44]}')
