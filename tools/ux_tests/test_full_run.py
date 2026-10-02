import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18841

def wait_port(port, timeout=15):
    import socket, time as _t
    end = _t.time() + timeout
    while _t.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close(); return
        except OSError:
            _t.sleep(0.2)
    raise SystemExit("test server did not start on port %d" % port)
import sys, subprocess, time, json, os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "csp_test_server.py"), str(PORT), SRC],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
wait_port(PORT)
base = "http://127.0.0.1:%d/" % PORT
RESULT = ("1M031H19Dpvpadvdzavwtebwvwe8vwdz8tdhhtypvsbaqzn8dvpgbsvvyd7ppzadphhdpwyptqdwz"
          "gyaz87phwqxzzsaqpr7ta8tabpbzfdvdb7yavhb8wbhg7qbdbw7pbahvbnqdwet7wqvbeqyga7dxstpwxq")
A36 = "0123456789abcdefghijklmnopqrstuvwxyz"
ans = [0] * 301
for k, ch in enumerate(RESULT[9:]):
    v = A36.index(ch); ans[2*k+1] = v // 6; ans[2*k+2] = v % 6
SNAP = """(()=>({pcts:[...document.querySelectorAll('#domains .pct')].map(e=>e.textContent),
  ci:[...document.querySelectorAll('#domains .ci-txt')].map(e=>e.textContent),
  fp:[...document.querySelectorAll('.fpct')].map(e=>e.textContent).join(','),
  prof:(document.querySelector('#profile h3, #profile .pf-cell, #profile b')||{}).textContent||'',
  rows:document.querySelectorAll('#tableView tr').length}))()"""
out = {}
try:
  with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    for vp_name, kw in (("desktop", dict(viewport={"width":1280,"height":860})),
                        ("phone", dict(viewport={"width":390,"height":844}, device_scale_factor=2, is_mobile=True, has_touch=True))):
      r = out[vp_name] = {}
      ctx = b.new_context(**kw); pg = ctx.new_page(); errs = []; foreign = []
      pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
      pg.on("pageerror", lambda e: errs.append(str(e)))
      pg.on("request", lambda q: urlparse(q.url).netloc not in ("", "127.0.0.1:%d" % PORT) and not q.url.startswith(("data:", "blob:", "about:")) and foreign.append(q.url))
      pg.goto(base, wait_until="networkidle"); pg.evaluate("localStorage.clear(); sessionStorage.clear()")
      pg.goto(base, wait_until="networkidle")
      pg.select_option("#sex", "M"); pg.fill("#age", "31"); pg.click("#startBtn")
      pg.wait_for_selector("#test:not(.hide)")
      t0 = time.time()
      for pgno in range(20):
        pg.wait_for_function("n => document.getElementById('pageTitle').textContent.startsWith('第 ' + n + ' 页')", arg=pgno + 1, timeout=10000)
        pg.wait_for_timeout(480)   # taps within 450 ms of a page turn are treated as ghost taps
        for q in range(pgno * 15 + 1, pgno * 15 + 16):
          sel = '.qrow[data-qid="%d"] .opt[data-v="%d"]' % (q, ans[q])
          if vp_name == "phone": pg.tap(sel)
          else: pg.click(sel)
        if pgno == 19:
          pg.click("#nextBtn")
      pg.wait_for_selector("#result:not(.hide)", timeout=15000)
      r["secs"] = round(time.time() - t0, 1)
      pg.click("#tableToggle")
      r["run"] = pg.evaluate(SNAP)
      r["hash_len"] = len(pg.evaluate("location.hash"))
      r["hash_body_equal"] = pg.evaluate("location.hash").split("p=")[1][9:] == RESULT[9:]
      # round-trip: open the reference link fresh
      pg2 = ctx.new_page(); pg2.goto("about:blank"); pg2.goto(base + "#p=" + RESULT, wait_until="networkidle")
      pg2.wait_for_selector("#result:not(.hide)"); pg2.click("#tableToggle")
      ref = pg2.evaluate(SNAP)
      r["matches_reference"] = {k: r["run"][k] == ref[k] for k in ref}
      r["errors"] = errs; r["foreign_requests"] = foreign
      ctx.close()
    b.close()
finally:
    srv.terminate()

_checks = []
for vp, v in out.items():
    _checks += [("%s: same scores, intervals, facets and profile as the reference link" % vp, all(v["matches_reference"].values())),
                ("%s: result link encodes exactly these answers" % vp, v["hash_body_equal"]),
                ("%s: no page errors, no requests to other hosts" % vp, not v["errors"] and not v["foreign_requests"])]
for n, g in _checks: print(("PASS " if g else "FAIL ") + n)
print("%d/%d passed" % (sum(g for _, g in _checks), len(_checks)))
