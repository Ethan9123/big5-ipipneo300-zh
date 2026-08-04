# -*- coding: utf-8 -*-
"""cvuse_share: per-profile reader-visible differentiation count. READ ONLY."""
import json, os, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'out', 'profiles_raw.json'), encoding='utf-8'))
LV = {'低': 0, '中': 1, '高': 2}
DIMS = ['O', 'C', 'E', 'A', 'N']
TF = ['lead', 'summary', 'life', 'friends', 'love', 'work']
LF = ['pros', 'cons', 'practice']
BY = {p['cell']: p for p in D}
VEC = {c: tuple(LV[c[i*2+1]] for i in range(5)) for c in BY}
def blob(p): return ''.join(p[f] for f in TF) + ''.join(''.join(p[f]) for f in LF)

# 每个维度每个档位：读者能看见的行为标记（不含维度名本身，避免"提了名字就算写了"）
M = {
 ('O',0): '熟悉 老办法 跑通 务实 原样 嫌麻烦 用了很多年 验证过 不追新 具体怎么做 旧流程 换新 新工具 新流程 新方向 一成不变'.split(),
 ('O',1): '既接受新 也需要熟悉 新东西也 看场合 熟悉感'.split(),
 ('O',2): '新想法 抽象 好奇 审美 新方向 点子 想法多 兴趣广 新鲜 概念 开新 想得远 什么都想开始 兴趣'.split(),
 ('C',0): '拖 收不了尾 完不成 落空 计划性 随性 最后一刻 截止 失约 半途 堆着'.split(),
 ('C',1): '有条理但 不苛刻 关键事情 大体规律 一部分 中等尽责'.split(),
 ('C',2): '守时 有序 条理 清单 计划表 交付稳 兑现 收尾 提前准备 规律 不用追 可靠'.split(),
 ('E',0): '独处 一个人待 不主动 话少 恢复 充电 安静 少见到人 不发起 圈子小'.split(),
 ('E',1): '既能社交也能独处 能社交 不排斥 看场合 能进能出 社交和独处'.split(),
 ('E',2): '人群 热闹 局 张罗 召集 主动约 话多 社交量 气氛 能量高 圈子大'.split(),
 ('A',0): '直 冲突 顶回去 不肯先退 说话冲 怼 不留余地 立场 不迎合 锋利 得罪'.split(),
 ('A',1): '有底线 大体合作 守得住 不无限退让 能谈'.split(),
 ('A',2): '让步 迁就 照顾 体谅 不好意思拒绝 委屈 不提要求 为别人 温和 关系为先'.split(),
 ('N',0): '不内耗 情绪平稳 抗压 不焦虑 睡得好 恢复快 不太当回事 不痛苦 迟钝 察觉不到 情绪成本低 不上火'.split(),
 ('N',1): '有起伏 可控 一两天 过得去 缓过来 不至于失控'.split(),
 ('N',2): '反刍 回放 重播 复盘 放大 不安 睡不 琢磨 敏感 起伏大 焦虑 担心 夜里'.split(),
}
rows = []
for p in D:
    b = blob(p); v = VEC[p['cell']]
    anch = [1 if any(k in b for k in M[(DIMS[i], v[i])]) else 0 for i in range(5)]
    rows.append((sum(anch), tuple(anch), p['cell']))
print('### 每篇画像里，有多少个维度写出了读者看得见的行为特征（0-5）')
c = Counter(r[0] for r in rows)
for k in sorted(c, reverse=True):
    print(f'  {k}/5 个维度有锚点: {c[k]:3d} 篇 = {c[k]/243*100:4.1f}%')
print(f'  >=4 个维度有锚点: {sum(v for k,v in c.items() if k>=4)}/243 = {sum(v for k,v in c.items() if k>=4)/243*100:.1f}%')
print(f'  <=2 个维度有锚点: {sum(v for k,v in c.items() if k<=2)}/243 = {sum(v for k,v in c.items() if k<=2)/243*100:.1f}%')
print()
print('### 各维度单独的"写出来了"覆盖率')
for i, d in enumerate(DIMS):
    for lv in range(3):
        cs = [r for r in rows if VEC[r[2]][i] == lv]
        hit = sum(r[1][i] for r in cs)
        print(f'  {d}{"低中高"[lv]}: {hit:2d}/{len(cs)} = {hit/len(cs)*100:5.1f}%')
print()
print('### 锚点最少的 12 篇')
for n, a, c_ in sorted(rows)[:12]:
    miss = [DIMS[i]+'低中高'[VEC[c_][i]] for i in range(5) if not a[i]]
    print(f'  {n}/5  {c_}   缺: {" ".join(miss)}')
