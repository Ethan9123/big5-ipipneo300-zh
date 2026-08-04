# -*- coding: utf-8 -*-
"""Assemble dist/ -- exactly what gets uploaded to Cloudflare Pages, nothing else.

site/ is a working directory: it holds the captured production page, the patched build,
and scratch. Uploading it verbatim would publish index.optimized.html as its own URL and
leave the OLD index.html as the home page. dist/ is the deployable set.
"""
import filecmp
import hashlib
import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = os.path.join(ROOT, "site")
DIST = os.path.join(ROOT, "dist")

# source in site/  ->  name in dist/
FILES = [
    ("index.optimized.html", "index.html"),
    ("og.png", "og.png"),
    ("_headers", "_headers"),
    ("robots.txt", "robots.txt"),
    ("sitemap.xml", "sitemap.xml"),
]

missing = [s for s, _ in FILES if not os.path.exists(os.path.join(SITE, s))]
if missing:
    raise SystemExit("missing from site/: %s" % ", ".join(missing))

# The corpus gate runs BEFORE anything is written, so dist/ is never left holding a
# build that failed acceptance. An earlier ordering populated dist/ and only then
# refused, which is worse than not building at all.
print("corpus gate (tools/verify_corpus.py):")
gate = subprocess.run([sys.executable, os.path.join(HERE, "verify_corpus.py")],
                      capture_output=True, text=True, encoding="utf-8", errors="replace")
tail = [ln.strip() for ln in (gate.stdout or "").splitlines()
        if ln.startswith("   x ") or ln.startswith("   ! ")]
for ln in tail:
    print("  " + ln)
if gate.returncode != 0:
    raise SystemExit("\ncorpus gate FAILED -- nothing written. Run "
                     "`python tools/verify_corpus.py` for the full report.")
if not tail:
    print("  clean")
print()

if os.path.isdir(DIST):
    shutil.rmtree(DIST)
os.makedirs(DIST)

print("dist/ contents:")
for src, dst in FILES:
    s, d = os.path.join(SITE, src), os.path.join(DIST, dst)
    shutil.copy2(s, d)
    digest = hashlib.sha256(io.open(d, "rb").read()).hexdigest()[:16]
    label = src if src == dst else "%s  (from %s)" % (dst, src)
    print("  %9d bytes  %s  %s" % (os.path.getsize(d), digest, label))

# guard: the deployed index must be the patched one, not the captured production copy
if filecmp.cmp(os.path.join(DIST, "index.html"), os.path.join(SITE, "index.html"), shallow=False):
    raise SystemExit("dist/index.html is identical to the OLD site/index.html -- patch did not apply")

body = io.open(os.path.join(DIST, "index.html"), encoding="utf-8").read()
STUB_MARKERS = ["占位文本 ·", "占位 summary", "占位优点", "占位缺点", "占位练习",
                "真实文案由写作工作流产出后替换"]
checks = {
    "empirical tables present": "decodePctTables" in body,
    "cubic percentile map gone": "210.335958661391" not in body,
    "levelWord defined": "const levelWord" in body,
    "beacon tag gone": "cloudflareinsights" not in body,
    "fmtPct present": "const fmtPct" in body,
    "30/70 bands": 'p <= 30 ? "低"' in body,
    "243 profiles present": body.count('"practice":') >= 243 or body.count('"practice":[') >= 243,
    "no placeholder text": not any(m in body for m in STUB_MARKERS),
}
print("\npre-flight:")
ok = True
for k, v in checks.items():
    print("  %-28s %s" % (k, "OK" if v else "FAIL"))
    ok = ok and v
if not ok:
    raise SystemExit("pre-flight failed -- do not deploy")

total = sum(os.path.getsize(os.path.join(DIST, d)) for _, d in FILES)
print("\n  %d files, %.1f KB total" % (len(FILES), total / 1024))
print("\ndeploy with (after `npx wrangler login`):")
print("  npx wrangler pages deploy dist --project-name=big5-ipipneo300-zh --branch=preview")
print("then, once the preview URL looks right:")
print("  npx wrangler pages deploy dist --project-name=big5-ipipneo300-zh --branch=main")
