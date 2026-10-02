# -*- coding: utf-8 -*-
"""Browser regression suite for the UI: link ownership, answering, keyboard, results, share card, full 300-item run.

  python tools/ux_tests/run_all.py [dist_dir]

Needs Playwright for Python and a local Chrome (p.chromium.launch(channel="chrome")). Each test serves the
build with the real _headers (CSP included) via tools/csp_test_server.py on its own port.
"""
import os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
TESTS = ["test_full_run.py", "test_link_ownership.py", "test_keyboard_interval.py", "test_focus_landmarks.py",
         "test_interaction.py", "test_result_robustness.py", "test_share_card.py", "test_review_fixes.py"]
env = dict(os.environ, PYTHONIOENCODING="utf-8")
bad = 0
for i, t in enumerate(TESTS):
    p = subprocess.run([sys.executable, os.path.join(HERE, t), SRC, str(18870 + i * 3)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=900)
    out = p.stdout + p.stderr
    fails = [l for l in out.splitlines() if l.startswith("FAIL")]
    m = re.search(r"(\d+)/(\d+) passed", out)
    ok = p.returncode == 0 and m and m.group(1) == m.group(2) and not fails
    bad += not ok
    print("%-30s %s" % (t, m.group(0) if m else "no summary (exit %d)" % p.returncode))
    for l in fails: print("    " + l)
    if not m: print(out[-1500:])
print("\nALL PASSED" if not bad else "\n%d test file(s) failed" % bad)
sys.exit(1 if bad else 0)
