# -*- coding: utf-8 -*-
"""Pull headline / verdict / proposals / deadEnds out of the paradata research journal."""
import io
import json
import os
import sys

JOURNAL = os.environ.get("CLAUDE_WORKFLOW_JOURNAL") or (
    os.path.join(os.path.expanduser("~"), ".claude", "projects",
                 "C--Users-kids1-Downloads-bigfive",
                 "3f3dea16-3b73-4559-8359-8360df8000b2",
                 "subagents", "workflows", "wf_7af839e5-c05", "journal.jsonl"))

want = sys.argv[1] if len(sys.argv) > 1 else None
mode = sys.argv[2] if len(sys.argv) > 2 else "summary"

for line in io.open(JOURNAL, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    if rec.get("type") != "result":
        continue
    v = rec.get("result")
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            continue
    if not isinstance(v, dict) or "headline" not in v:
        continue
    aid = rec.get("agentId", "?")[:12]
    if want and want not in aid:
        continue
    print("\n" + "#" * 78)
    print("# " + aid)
    print("#" * 78)
    print("\n【结论】" + v.get("headline", ""))
    if mode in ("summary", "full"):
        print("\n【判断】" + (v.get("verdict") or "")[:1800])
    if mode == "full":
        for f in (v.get("findings") or [])[:14]:
            print("\n  - %s" % f.get("claim", "")[:300])
            print("    效应量: %s" % (f.get("effectSize") or "")[:220])
            print("    可行性: %s" % (f.get("feasibleHere") or "")[:180])
            print("    出处  : %s" % (f.get("source") or "")[:200])
    for p in (v.get("proposals") or [])[:10]:
        print("\n  ▸ %s" % p.get("change", "")[:300])
        print("    理由  : %s" % (p.get("rationale") or "")[:300])
        print("    预期  : %s" % (p.get("expectedGain") or "")[:200])
        print("    成本  : %s" % (p.get("cost") or "")[:160])
        print("    风险  : %s" % (p.get("risk") or "")[:220])
        print("    可验证: %s" % (p.get("validatable") or "")[:160])
    for d in (v.get("deadEnds") or [])[:10]:
        print("\n  x %s" % d[:300])
