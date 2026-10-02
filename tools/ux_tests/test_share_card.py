import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18831

def wait_port(port, timeout=15):
    import socket, time as _t
    end = _t.time() + timeout
    while _t.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close(); return
        except OSError:
            _t.sleep(0.2)
    raise SystemExit("test server did not start on port %d" % port)
import sys, subprocess, time, os, json, random
from playwright.sync_api import sync_playwright
import tempfile
OUT = tempfile.mkdtemp(prefix='ux_card_')
srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "csp_test_server.py"), str(PORT), SRC], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
wait_port(PORT); base = "http://127.0.0.1:%d/" % PORT
R = ("1M031H19Dpvpadvdzavwtebwvwe8vwdz8tdhhtypvsbaqzn8dvpgbsvvyd7ppzadphhdpwyptqdwz"
     "gyaz87phwqxzzsaqpr7ta8tabpbzfdvdb7yavhb8wbhg7qbdbw7pbahvbnqdwet7wqvbeqyga7dxstpwxq")
SEED = """r => { localStorage.clear(); sessionStorage.clear();
  const A = '0123456789abcdefghijklmnopqrstuvwxyz', a = new Array(301).fill(0);
  for (let k = 0; k < 150; k++){ const v = A.indexOf(r[9 + k]); a[2*k+1] = Math.floor(v/6); a[2*k+2] = v % 6; }
  localStorage.setItem('ipipneo300_zh_v1', JSON.stringify({v:1, answers:a, sex:r[1], age:+r.slice(2,5), page:19, mode:'plain', done:true, savedAt:Date.now()})); }"""
out = {}
try:
  with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width":390,"height":844}, device_scale_factor=2, is_mobile=True, has_touch=True, accept_downloads=True)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
    pg.goto(base, wait_until="networkidle"); pg.evaluate(SEED, R); pg.goto("about:blank"); pg.goto(base, wait_until="networkidle")
    pg.wait_for_selector("#result:not(.hide)")
    pg.click("#cardBtn"); pg.wait_for_selector("#cardSheet:not(.hide)", timeout=5000); pg.wait_for_timeout(400)
    out["sheet_open"] = True
    out["focus_in_sheet"] = pg.evaluate("document.activeElement.classList.contains('card-sheet-close')")
    out["main_inert"] = pg.evaluate("document.querySelector('main').inert")
    out["img_loaded"] = pg.evaluate("(() => { const i = document.querySelector('#cardSheet img'); return [i.naturalWidth, i.naturalHeight]; })()")
    pg.screenshot(path=os.path.join(OUT, "card-sheet.png"))
    # pull the PNG out to inspect it
    data = pg.evaluate("""async () => { const i = document.querySelector('#cardSheet img'); const r = await fetch(i.src).catch(() => null);
        if (!r) { const c = document.createElement('canvas'); c.width = i.naturalWidth; c.height = i.naturalHeight; c.getContext('2d').drawImage(i, 0, 0); return c.toDataURL(); }
        const bl = await r.blob(); return await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(bl); }); }""")
    import base64; open(os.path.join(OUT, "card.png"), "wb").write(base64.b64decode(data.split(",")[1]))
    with pg.expect_download() as dl: pg.click("#cardSheet a")
    out["download_name"] = dl.value.suggested_filename
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    out["closed_by_esc"] = pg.evaluate("document.getElementById('cardSheet').classList.contains('hide') && !document.querySelector('main').inert")
    out["focus_back"] = pg.evaluate("document.activeElement.id")
    out["errors"] = errs
    b.close()
finally: srv.terminate()

_checks = [("sheet opens with the 1080x1400 card", out.get("img_loaded") == [1080, 1400]),
           ("focus moves into the sheet; page behind is inert", out.get("focus_in_sheet") and out.get("main_inert")),
           ("download keeps the file name", out.get("download_name") == "大五人格画像-IPIP300.png"),
           ("Esc closes and returns focus to the button", out.get("closed_by_esc") and out.get("focus_back") == "cardBtn"),
           ("no app errors", not [e for e in out.get("errors", []) if "Fetch API" not in e and "Connecting to" not in e])]
for n, g in _checks: print(("PASS " if g else "FAIL ") + n)
print("%d/%d passed" % (sum(bool(g) for _, g in _checks), len(_checks)))
