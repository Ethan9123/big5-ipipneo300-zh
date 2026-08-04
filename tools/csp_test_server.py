# -*- coding: utf-8 -*-
"""Serve site/ with the exact headers from site/_headers, so the CSP can be tested
before it ever reaches production. A CSP that blocks the inline script would leave a
blank page, which is not something to discover on the live site."""
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8792
SITE = os.path.join(ROOT, sys.argv[2] if len(sys.argv) > 2 else "site")


def parse_headers(path):
    """Minimal Cloudflare Pages _headers parser: rule lines at col 0, headers indented."""
    rules, current = [], None
    for line in open(path, encoding="utf-8"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            current = (line.strip(), [])
            rules.append(current)
        elif current is not None:
            name, _, value = line.strip().partition(":")
            current[1].append((name.strip(), value.strip()))
    return rules


RULES = parse_headers(os.path.join(SITE, "_headers"))
print("parsed %d rule(s) from _headers:" % len(RULES))
for pattern, hdrs in RULES:
    print("  %s -> %d header(s)" % (pattern, len(hdrs)))


def matches(pattern, path):
    rx = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.match(rx, path) is not None


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SITE, **kw)

    def end_headers(self):
        for pattern, hdrs in RULES:
            if matches(pattern, self.path.split("?")[0]):
                for name, value in hdrs:
                    self.send_header(name, value)
        super().end_headers()

    def log_message(self, *a):
        pass


print("serving %s on http://localhost:%d with _headers applied" % (SITE, PORT))
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
