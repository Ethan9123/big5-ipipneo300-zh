"""Shared Playwright helpers for the UI regression tests (portable: paths are relative to the repo)."""
import os, sys, json, time, subprocess, socket

OUT = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(OUT))
DIST = os.path.join(ROOT, "dist")
SERVER = os.path.join(ROOT, "tools", "csp_test_server.py")


def set_dist(path):
    global DIST
    DIST = path
KEY = "ipipneo300_zh_v1"
A36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def start_server(port):
    p = subprocess.Popen([sys.executable, SERVER, str(port), DIST], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError:
            time.sleep(0.1)
    return p, "http://127.0.0.1:%d/" % port


def pattern(n, k, start=1):
    """answers[start..start+n-1] = deterministic values from seed k (1..5)."""
    a = [0] * 301
    for i in range(start, start + n):
        a[i] = (i * 7 + k * 3) % 5 + 1
    return a


def encode(a, sex, age, page=0, done=False, mode="P"):
    body = "".join(A36[a[i] * 6 + a[i + 1]] for i in range(1, 301, 2))
    return "1" + (sex or "X") + str(age).zfill(3) + mode + str(page).zfill(2) + ("D" if done else "-") + body


def save_obj(a, sex, age, page=0, done=False, mode="plain"):
    return {"v": 1, "answers": a, "sex": sex, "age": age, "page": page, "mode": mode, "done": done, "savedAt": 1750000000000}


PROBE = r"""(() => {
  const S = o => o ? {n: o.answers.slice(1).filter(Boolean).length, sex: o.sex, age: o.age, done: o.done, page: o.page,
                      q: o.answers.slice(1, 16).join(''), q16_45: o.answers.slice(16, 46).join(''), q286_300: o.answers.slice(286).join('')} : null;
  let L = null, own = null;
  try { L = JSON.parse(localStorage.getItem('%(K)s')); } catch(e) { L = 'ERR ' + e.name; }
  try { own = sessionStorage.getItem('%(K)s:own'); } catch(e) { own = 'ERR ' + e.name; }
  let M = null;
  try { M = {n: answers.slice(1).filter(Boolean).length, sex, age, done, page, viewOnly, staleTab,
             q: answers.slice(1, 16).join(''), q16_45: answers.slice(16, 46).join(''), q286_300: answers.slice(286).join('')}; } catch(e) { M = String(e); }
  const vis = id => { const e = document.getElementById(id); return !!e && !e.classList.contains('hide'); };
  const txt = sel => { const e = document.querySelector(sel); return e ? e.textContent.trim() : null; };
  return {view: document.body.dataset.view, hash: location.hash, own,
          local: typeof L === 'string' ? L : S(L), mem: M,
          stale: vis('staleBanner'), staleMeta: txt('#staleMeta'), card: vis('resumeCard'),
          cardTitle: txt('#resumeTitle'), cardMeta: txt('#resumeMeta'), resumeBtn: txt('#resumeBtn'), freshBtn: txt('#freshBtn'),
          viewBanner: vis('viewBanner'), status: txt('.report-status'), h1: txt('.report-cover h1'), saveNote: txt('#resultSaveNote'),
          feedback: txt('#pageFeedback'), pageTitle: txt('#pageTitle'), pcount: txt('#pcount'),
          okRows: document.querySelectorAll('#qlist .qrow.ok').length,
          toast: vis('restoreToast') ? (txt('#restoreToastTitle') + ' / ' + txt('#restoreToastMeta')) : null,
          storageWarn: txt('#storageWarn')};
})()""" % {"K": KEY}


def probe(pg, wait=200):
    pg.wait_for_timeout(wait)
    return pg.evaluate(PROBE)


def raw_local(pg):
    return pg.evaluate("localStorage.getItem('%s')" % KEY)


def new_ctx(browser, base, local=None, vw=1280, vh=900, dialogs=None, errors=None):
    """Fresh context; preset localStorage on a stateless page, then leave it."""
    ctx = browser.new_context(viewport={"width": vw, "height": vh})
    pg = ctx.new_page()
    pg.goto(base, wait_until="load")
    pg.evaluate("localStorage.clear(); sessionStorage.clear()")
    if local is not None:
        pg.evaluate("o => localStorage.setItem('%s', JSON.stringify(o))" % KEY, local)
    pg.goto("about:blank")
    pg.close()
    return ctx


def open_page(ctx, url, dialogs=None, errors=None, wait=500):
    pg = ctx.new_page()
    def on_dialog(d):
        if dialogs is not None: dialogs.append(d.message)
        d.accept()
    pg.on("dialog", on_dialog)
    if errors is not None:
        pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(url, wait_until="load")
    pg.wait_for_timeout(wait)
    return pg


def click_opt(pg, qid, v, wait=520):
    pg.click('.qrow[data-qid="%d"] .opt[data-v="%d"]' % (qid, v))
    pg.wait_for_timeout(wait)


def js_click(pg, sel, wait=300):
    pg.evaluate("s => document.querySelector(s).click()", sel)
    pg.wait_for_timeout(wait)


def start_test(pg, sex, age, wait=700):
    pg.select_option("#sex", sex)
    pg.fill("#age", str(age))
    pg.click("#startBtn")
    pg.wait_for_timeout(wait)


def dump(name, obj):
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path
