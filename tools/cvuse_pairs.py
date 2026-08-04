# -*- coding: utf-8 -*-
"""cvuse_pairs: side-by-side neighbor reads. READ ONLY."""
import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(BASE, 'out', 'profiles_raw.json'), encoding='utf-8'))
BY = {p['cell']: p for p in D}
sets = {
 'O三元组 A (C高E低A高N低)': ['O低C高E低A高N低', 'O中C高E低A高N低', 'O高C高E低A高N低'],
 'O三元组 B (C低E高A低N高)': ['O低C低E高A低N高', 'O中C低E高A低N高', 'O高C低E高A低N高'],
 'E低/中/高 (O中C中A中N中)': ['O中C中E低A中N中', 'O中C中E中A中N中', 'O中C中E高A中N中'],
 'E低/中 (O中C中A低N高)': ['O中C中E低A低N高', 'O中C中E中A低N高'],
 'C中→C高 (O高E中A中N中)': ['O高C中E中A中N中', 'O高C高E中A中N中'],
}
which = sys.argv[1] if len(sys.argv) > 1 else None
for k, cs in sets.items():
    if which and which not in k: continue
    print('#' * 72); print('##', k)
    for f in ['lead', 'summary', 'life', 'work']:
        print(f'-- {f} --')
        for c in cs:
            print(f'  [{c}] ({len(BY[c][f])}字) {BY[c][f]}')
    print('-- practice --')
    for c in cs:
        print(f'  [{c}]')
        for x in BY[c]['practice']: print(f'      - {x}')
    print()
