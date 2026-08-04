# -*- coding: utf-8 -*-
"""Strip machine-specific absolute paths out of the tooling before the repo goes public.

Hardcoded C:\\Users\\<name>\\... paths leak the account name and make every script
unrunnable on anyone else's machine. Replace them with paths derived at runtime.
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")

PY_ROOT = 'os.path.dirname(os.path.dirname(os.path.abspath(__file__)))'

SUBS = [
    # project root, python
    (re.compile(r"r?['\"]C:\\+Users\\+[^\\'\"]+\\+Downloads\\+bigfive\\+tools\\+out['\"]"),
     "os.path.join(%s, 'tools', 'out')" % PY_ROOT),
    (re.compile(r"r?['\"]C:\\+Users\\+[^\\'\"]+\\+Downloads\\+bigfive\\+tools['\"]"),
     "os.path.join(%s, 'tools')" % PY_ROOT),
    (re.compile(r"r?['\"]C:\\+Users\\+[^\\'\"]+\\+Downloads\\+bigfive['\"]"), PY_ROOT),
    # anything still pointing at a user profile -> env override with a clear error
    (re.compile(r"\(\s*r['\"]C:\\+Users\\+[^\\'\"]+\\+\.claude[^'\"]*['\"]\s*\n?\s*r?['\"][^'\"]*['\"]\s*\n?\s*r?['\"][^'\"]*['\"]\s*\)", re.S),
     'os.environ.get("CLAUDE_WORKFLOW_JOURNAL", "")'),
]

USERPATH = re.compile(r"C:\\+Users\\+[A-Za-z0-9_.-]+")

changed = []
for name in sorted(os.listdir(TOOLS)):
    if not name.endswith((".py", ".js", ".ps1", ".md")) or name == "depersonalise.py":
        continue
    path = os.path.join(TOOLS, name)
    src = io.open(path, encoding="utf-8").read()
    orig = src
    for rx, rep in SUBS:
        src = rx.sub(rep, src)
    # js: derive from __dirname
    if name.endswith(".js"):
        src = re.sub(r"['\"]C:\\\\+Users\\\\+[^'\"]*bigfive\\\\+tools\\\\+out['\"]",
                     "path.join(__dirname, 'out')", src)
        src = re.sub(r"['\"]C:\\\\+Users\\\\+[^'\"]*bigfive\\\\+site\\\\+([A-Za-z0-9_.]+)['\"]",
                     r"path.join(__dirname, '..', 'site', '\1')", src)
    if src != orig:
        io.open(path, "w", encoding="utf-8", newline="").write(src)
        changed.append(name)

print("rewritten: %d files" % len(changed))
for c in changed:
    print("   " + c)

print("\nremaining hardcoded user paths:")
left = 0
for name in sorted(os.listdir(TOOLS)):
    if not name.endswith((".py", ".js", ".ps1", ".md")) or name == "depersonalise.py":
        continue
    src = io.open(os.path.join(TOOLS, name), encoding="utf-8").read()
    hits = USERPATH.findall(src)
    if hits:
        left += len(hits)
        print("   %-32s %d" % (name, len(hits)))
print("total: %d" % left)
