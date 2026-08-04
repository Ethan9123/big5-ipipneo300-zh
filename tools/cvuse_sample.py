# -*- coding: utf-8 -*-
"""cvuse_* : content-usefulness audit. READ ONLY."""
import json, sys, random, os
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'out', 'profiles_raw.json'), encoding='utf-8'))
LV = {'低': 0, '中': 1, '高': 2}
DIMS = ['O', 'C', 'E', 'A', 'N']

def parse(cell):
    return [LV[cell[i * 2 + 1]] for i in range(5)]

def idx(cell):
    v = parse(cell)
    return v[0] * 81 + v[1] * 27 + v[2] * 9 + v[3] * 3 + v[4]

BY = {p['cell']: p for p in D}
assert len(BY) == 243

# ---------- sample selection ----------
common = ['O中C中E中A中N中', 'O中C高E高A高N低', 'O高C高E高A高N低']
rare   = ['O低C低E高A高N高', 'O低C高E高A高N高', 'O低C中E高A高N高']

extreme_all = [c for c in BY if all(x in (0, 2) for x in parse(c))]
random.seed(20260803)
extreme = ['O低C低E低A低N低', 'O高C高E高A高N高', 'O高C低E高A低N高',
           'O低C高E低A高N低', 'O高C高E低A低N低', 'O低C低E高A高N高']
extreme = [c for c in extreme if c not in common + rare]
extreme = extreme[:6]
while len(extreme) < 6:
    c = random.choice(extreme_all)
    if c not in extreme + common + rare:
        extreme.append(c)

mid_heavy_all = [c for c in BY if sum(1 for x in parse(c) if x == 1) >= 4 and c not in common + rare + extreme]
mid_heavy = sorted(random.sample(mid_heavy_all, 6))

pool = [c for c in BY if c not in common + rare + extreme + mid_heavy]
rnd = sorted(random.sample(pool, 6))

SAMPLE = [('常见', c) for c in common] + [('稀有', c) for c in rare] + \
         [('极端', c) for c in extreme] + [('多中', c) for c in mid_heavy] + [('随机', c) for c in rnd]

if __name__ == '__main__':
    what = sys.argv[1] if len(sys.argv) > 1 else 'list'
    if what == 'list':
        for tag, c in SAMPLE:
            print(f'{tag}\t{c}\tidx={idx(c)}')
        print('total', len(SAMPLE), 'unique', len(set(c for _, c in SAMPLE)))
    elif what == 'dump':
        lo = int(sys.argv[2]); hi = int(sys.argv[3])
        for tag, c in SAMPLE[lo:hi]:
            p = BY[c]
            print('=' * 70)
            print(f'[{tag}] {c}  (idx={idx(c)})')
            print(f'lead    : {p["lead"]}  <{len(p["lead"])}字>')
            for k in ['summary', 'life', 'friends', 'love', 'work']:
                print(f'{k:8s}: {p[k]}  <{len(p[k])}字>')
            for k in ['pros', 'cons', 'practice']:
                print(f'{k:8s}:')
                for it in p[k]:
                    print(f'          - {it}  <{len(it)}>')
            print()
