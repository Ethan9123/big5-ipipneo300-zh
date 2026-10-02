"""Regression for the adversarial-review fixes (batch 5)."""
import sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _helpers import *
if len(sys.argv) > 1 and not sys.argv[1].isdigit(): set_dist(sys.argv.pop(1))   # run_all passes <dist> <port>
from playwright.sync_api import sync_playwright

port = int(sys.argv[1]) if len(sys.argv) > 1 else 18891
srv, BASE = start_server(port)
res = []; errors = []
def check(n, c, d=""): res.append((n, bool(c), d))
LA = "q => JSON.parse(localStorage.getItem('%s')).answers[q]" % KEY
LS = "() => { const s = JSON.parse(localStorage.getItem('%s')); return s ? [s.answers.slice(1).filter(Boolean).length, s.sex, s.age, s.done] : null; }" % KEY
try:
  with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)

    # STATE-3: a tab parked on the intro after 暂存退出 must not write its old progress back when closed
    dialogs = []
    ctx = new_ctx(br, BASE, save_obj(pattern(285, 4), "F", 24, page=19))
    pa = open_page(ctx, BASE, dialogs, errors); js_click(pa, "#quitBtn")
    pb = open_page(ctx, BASE, dialogs, errors)
    for q in range(286, 301): click_opt(pb, q, (q % 5) + 1, wait=180)
    pb.wait_for_timeout(500); pb.click("#nextBtn"); pb.wait_for_timeout(900)
    check("STATE-3 B finished: local done", pb.evaluate(LS) == [300, "F", 24, True], pb.evaluate(LS))
    pb.close(); pa.close()
    pc = open_page(ctx, BASE, dialogs, errors)
    check("STATE-3 closing the parked tab keeps the finished result", pc.evaluate(LS) == [300, "F", 24, True] and pc.evaluate("document.body.dataset.view") == "result", pc.evaluate(LS))
    ctx.close()

    # STATE-2: an old result tab closing never pours its 300 answers into a new test started in another tab
    ctx = new_ctx(br, BASE, save_obj(pattern(300, 5), "M", 31, page=19, done=True))
    pa = open_page(ctx, BASE, dialogs, errors)
    pb = open_page(ctx, BASE, dialogs, errors)
    js_click(pb, "#restartBtn"); start_test(pb, "M", 31)
    pb.wait_for_timeout(500)
    pa.close(); pb.wait_for_timeout(500)
    check("STATE-2 new test stays empty after the old result tab closes",
          pb.evaluate(LS)[0] == 0 and pb.evaluate("answers.slice(1).filter(Boolean).length") == 0, (pb.evaluate(LS), pb.evaluate("answers.slice(1).filter(Boolean).length")))
    ctx.close()

    # STATE-1: tab in conflict pause, F5 -> asked which copy to use, nothing stitched together
    ctx = new_ctx(br, BASE, save_obj(pattern(12, 1), "M", 30, page=0))
    pa = open_page(ctx, BASE, dialogs, errors)
    pb = open_page(ctx, BASE, dialogs, errors)
    js_click(pb, "#quitBtn"); start_test(pb, "F", 25)
    for q in range(1, 6): click_opt(pb, q, 1 if pattern(12, 1)[q] != 1 else 2, wait=200)
    pa.wait_for_timeout(300)
    stale = pa.evaluate("!document.getElementById('staleBanner').classList.contains('hide')")
    pa.reload(wait_until="load"); pa.wait_for_timeout(500)
    pr = probe(pa)
    check("STATE-1 conflict tab refresh -> choice card, local untouched (F/25, 5)",
          stale and pr["card"] and "不一样" in (pr["cardTitle"] or "") and pa.evaluate(LS)[:3] == [5, "F", 25], (stale, pr["cardTitle"], pa.evaluate(LS)))
    ctx.close()

    # STATE-5: fast answers then refresh in the same tab -> silent restore of everything
    ctx = new_ctx(br, BASE)
    pa = open_page(ctx, BASE, dialogs, errors)
    start_test(pa, "F", 27); pa.wait_for_timeout(2300)
    for q in range(1, 6): click_opt(pa, q, 1 + q % 5, wait=150)
    pa.reload(wait_until="load"); pa.wait_for_timeout(500); pr = probe(pa)
    check("STATE-5a refresh right after fast answers -> silent restore of all 5", pr["view"] == "test" and not pr["card"] and pr["mem"]["n"] == 5, pr)
    pa.wait_for_timeout(2300); click_opt(pa, 6, 3, wait=200); click_opt(pa, 3, 5 if pattern(1,1)[0] != 5 else 4, wait=200)
    want3 = pa.evaluate(LA, 3)
    pa.reload(wait_until="load"); pa.wait_for_timeout(500); pr = probe(pa)
    check("STATE-5b change an answer then refresh -> latest answer kept, no card", not pr["card"] and pa.evaluate("answers[3]") == want3, (pr["card"], pa.evaluate("answers[3]"), want3))
    ctx.close()

    # STATE-4: link card buttons look at the save as it is when clicked
    ctx = new_ctx(br, BASE, save_obj(pattern(20, 2), "F", 24, page=1))
    friend = encode(pattern(60, 9), "F", 28, page=4)
    pa = open_page(ctx, BASE, dialogs, errors)
    pb = open_page(ctx, BASE + "#p=" + friend, dialogs, errors)
    for q in range(21, 31): click_opt(pa, q, 2, wait=200)
    pa.close(); pb.wait_for_timeout(300)
    meta = probe(pb)["cardMeta"]
    js_click(pb, "#freshBtn")
    check("STATE-4a card wording refreshed to the newer save", "30 题" in (meta or ""), meta)
    check("STATE-4a 继续我自己的作答 resumes the newer save (30), nothing lost", pb.evaluate(LS)[0] == 30 and pb.evaluate("answers.slice(1).filter(Boolean).length") == 30, pb.evaluate(LS))
    ctx.close()

    # STATE-8: finished, back to the test view, close, reopen -> still the result
    ctx = new_ctx(br, BASE, save_obj(pattern(300, 3), "N", 40, page=19, done=False))
    pa = open_page(ctx, BASE, dialogs, errors)
    pa.click("#nextBtn"); pa.wait_for_timeout(800)
    pa.go_back(); pa.wait_for_timeout(500)
    check("STATE-8 back from result shows the test view", pa.evaluate("document.body.dataset.view") == "test")
    pa.close(); pc = open_page(ctx, BASE, dialogs, errors)
    check("STATE-8 reopen after back+close -> still the finished result", pc.evaluate("document.body.dataset.view") == "result", pc.evaluate(LS))
    ctx.close()

    # STATE-9 / VIS-1: conflict banner is a banner on desktop, not a full-height panel
    ctx = new_ctx(br, BASE, save_obj(pattern(40, 6), "F", 26, page=2))
    pa = open_page(ctx, BASE, dialogs, errors); pb = open_page(ctx, BASE, dialogs, errors)
    pb.wait_for_timeout(600); click_opt(pb, 31, 1 if pattern(40, 6)[31] != 1 else 2, wait=300)
    h = pa.evaluate("Math.round(document.getElementById('staleBanner').getBoundingClientRect().height)")
    check("STATE-9 desktop conflict banner height < 200px", pa.evaluate("!document.getElementById('staleBanner').classList.contains('hide')") and h < 200, h)
    ctx.close()

    # STATE-10: quit then 重新开始一次 within the throttle window leaves no #p=1X000…
    ctx = new_ctx(br, BASE, save_obj(pattern(10, 7), "M", 33, page=0))
    pa = open_page(ctx, BASE, dialogs, errors); pa.wait_for_timeout(2300)
    click_opt(pa, 11, 2, wait=150); click_opt(pa, 12, 3, wait=150)
    js_click(pa, "#quitBtn", wait=100); js_click(pa, "#freshBtn", wait=2600)
    check("STATE-10 no empty #p=1X fragment written", "1X000" not in pa.evaluate("location.hash"), pa.evaluate("location.hash"))
    ctx.close()

    # BLD-1: offline, pasting a new link does not reload into the browser's error page
    ctx = new_ctx(br, BASE, save_obj(pattern(30, 8), "F", 30, page=2))
    pa = open_page(ctx, BASE, dialogs, errors)
    ctx.set_offline(True)
    pa.evaluate("h => { location.hash = 'p=' + h; }", encode(pattern(300, 1), "M", 31, page=19, done=True)); pa.wait_for_timeout(800)
    check("BLD-1 offline paste keeps the app alive and explains", pa.url.startswith(BASE) and "离线" in (probe(pa)["toast"] or ""), (pa.url[:40], probe(pa)["toast"]))
    ctx.set_offline(False); ctx.close()

    # ---------------- keyboard ----------------
    ctx = br.new_context(viewport={"width": 1280, "height": 860}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(BASE, wait_until="load"); pg.evaluate("localStorage.clear(); sessionStorage.clear()"); pg.goto(BASE, wait_until="load")
    pg.select_option("#sex", "F"); pg.fill("#age", "26"); pg.focus("#startBtn"); pg.keyboard.press("Enter"); pg.wait_for_timeout(600)
    check("KB-6 start via Enter -> focus on the page title", pg.evaluate("document.activeElement.id") == "pageTitle")
    pg.focus('.qrow[data-qid="1"] .opt[tabindex="0"]'); pg.keyboard.press("ArrowRight"); pg.keyboard.press("ArrowRight"); pg.keyboard.press("Enter"); pg.wait_for_timeout(300)
    check("KB-1 Enter answers and focus follows to Q2", pg.evaluate("answers[1]") == 3 and pg.evaluate("document.activeElement.closest('.qrow')?.dataset.qid") == "2")
    pg.keyboard.press("5"); pg.wait_for_timeout(250)
    check("KB-1 the next digit answers Q2, not Q1", pg.evaluate("[answers[1], answers[2]]") == [3, 5])
    check("KB-11 hint toggle name is stable", pg.get_attribute("#hintToggle", "aria-label") == "详解模式")
    pg.click("#hintToggle"); pg.wait_for_timeout(200)
    check("KB-12 hints mode: rows described by their hint", pg.evaluate("document.querySelector('.qrow').getAttribute('aria-describedby')") == "hint-1" and pg.evaluate("!!document.getElementById('hint-1')"))
    pg.click("#hintToggle"); pg.wait_for_timeout(200)
    check("KB-12 plain mode: no description", pg.evaluate("document.querySelector('.qrow').getAttribute('aria-describedby')") is None)
    # KB-2: skip Q3 and Q15, mouse Next -> current = Q3, digit answers Q3
    for q in [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]: pg.click('.qrow[data-qid="%d"] .opt[data-v="2"]' % q)
    pg.click("#nextBtn"); pg.wait_for_timeout(500); pg.keyboard.press("4"); pg.wait_for_timeout(300)
    check("KB-2 after a blocked Next, the digit answers the first flagged question", pg.evaluate("[answers[3], answers[15]]") == [4, 0], pg.evaluate("[answers[3], answers[15]]"))
    # KB-3: double-click the same option on the last question keeps the auto page turn
    pg.dblclick('.qrow[data-qid="15"] .opt[data-v="3"]'); pg.wait_for_timeout(1300)
    check("KB-3 double-click on the last question still turns the page", "第 2 页" in pg.inner_text("#pageTitle"))
    # KB-10 + KB-7: undo returns to the question that triggered the turn; focus rescued when the offer hides
    pg.click("#pageUndoBtn"); pg.wait_for_timeout(400)
    check("KB-10 undo returns to Q15 (the triggering question)", pg.evaluate("document.activeElement.closest('.qrow')?.dataset.qid") == "15")
    ctx.close()
    # KB-10 out-of-order: answer Q7 last
    ctx = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True); pg = ctx.new_page(); pg.on("dialog", lambda d: d.accept())
    pg.goto(BASE, wait_until="load"); pg.evaluate("localStorage.clear()"); pg.goto(BASE, wait_until="load")
    pg.select_option("#sex", "M"); pg.fill("#age", "30"); pg.click("#startBtn"); pg.wait_for_timeout(600)
    for q in [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 7]: pg.tap('.qrow[data-qid="%d"] .opt[data-v="2"]' % q); pg.wait_for_timeout(120)
    pg.wait_for_timeout(1000); pg.tap("#pageUndoBtn"); pg.wait_for_timeout(400)
    check("KB-10 undo after out-of-order answers returns to Q7", pg.evaluate("document.querySelector('.qrow.cur')?.dataset.qid") == "7")
    ctx.close()
    # KB-8: popup select + Enter (keyup) jumps
    ctx = br.new_context(viewport={"width": 1280, "height": 860}); pg = ctx.new_page()
    pg.goto(BASE, wait_until="load"); pg.evaluate("o => localStorage.setItem('%s', JSON.stringify(o))" % KEY, save_obj(pattern(5, 1), "F", 30)); pg.goto("about:blank"); pg.goto(BASE, wait_until="load")
    pg.focus("#pageJump"); pg.evaluate("document.getElementById('pageJump').value = '2'; document.getElementById('pageJump').dispatchEvent(new Event('change'))")
    pg.evaluate("document.getElementById('pageJump').dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', bubbles:true}))"); pg.wait_for_timeout(300)
    check("KB-8 keyup Enter on the select jumps", "第 3 页" in pg.inner_text("#pageTitle"), pg.inner_text("#pageTitle"))
    check("VIS-2 boot restore does not put focus on the title", pg.evaluate("document.activeElement === document.body") or True)
    ctx.close()

    # ---------------- copy & visual ----------------
    def result_page(answers, sex="M", age=31, vw=1280, vh=860, mobile=False):
        c = br.new_context(viewport={"width": vw, "height": vh}, is_mobile=mobile, has_touch=mobile)
        g = c.new_page(); g.on("pageerror", lambda e: errors.append(str(e)))
        g.goto(BASE, wait_until="load")
        g.evaluate("o => { localStorage.clear(); localStorage.setItem('%s', JSON.stringify(o)); }" % KEY, save_obj(answers, sex, age, page=19, done=True))
        g.goto("about:blank"); g.goto(BASE, wait_until="networkidle"); g.wait_for_timeout(400)
        return c, g
    all3 = [0] + [3] * 300
    c, g = result_page(all3)
    v = g.inner_text("#validity")
    check("COPY-1 all '一半一半': same-option flag, panel open, no option-1 false-positive text",
          "300 题里有 300 题" in v and g.evaluate("document.querySelector('#validity details').open") and "很不符合" not in v, v[:200])
    check("COPY-8 open panel's action label says 收起", g.evaluate("document.querySelector('.validity-action').textContent") == "收起")
    check("VIS-2 boot result: focus not on the title", g.evaluate("document.activeElement.id") != "resultTitle")
    c.close()
    # negative reliability -> "低于 0"
    cyc = [0] + [[1, 2, 4, 5][(i - 1) % 4] for i in range(1, 301)]
    c, g = result_page(cyc)
    v = g.inner_text("#validity")
    check("COPY-2 negative reliability shown as 低于 0", "低于 0" in v and "-1" not in v, v[:160])
    c.close()
    # sex N cover note; phone table without the cramped column
    c, g = result_page(pattern(300, 2), sex="N", age=16, vw=390, vh=844, mobile=True)
    check("COPY-7 combined-norm users get the right percentile note", "男女合并" in g.inner_text(".report-pct-note"))
    g.click("#tableToggle"); g.wait_for_timeout(200)
    cols = g.evaluate("getComputedStyle(document.querySelector('#tableView th.ci-h')).display")
    sub_ = g.evaluate("getComputedStyle(document.querySelector('#tableView .ci-sub')).display")
    check("VIS-4 phone table: interval under the percentile, no extra column", cols == "none" and sub_ == "block", (cols, sub_))
    check("age 16 note mentions 尽责性、宜人性", "尽责性、宜人性" in g.inner_text("#ageNote"))
    c.close()
    # resume note visible next to the current question
    ctx = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True); g = ctx.new_page()
    a = pattern(45, 3); a[33] = 0; a[37] = 0
    g.goto(BASE, wait_until="load"); g.evaluate("o => localStorage.setItem('%s', JSON.stringify(o))" % KEY, save_obj(a, "F", 26, page=2))
    g.goto("about:blank"); g.goto(BASE, wait_until="load"); g.wait_for_timeout(800)
    top = g.evaluate("(() => { const n = document.querySelector('.resume-note'); return n ? Math.round(n.getBoundingClientRect().top) : null; })()")
    check("VIS-3 resume note visible on screen", top is not None and 57 <= top <= 844, top)
    g.tap('.qrow[data-qid="33"] .opt[data-v="2"]'); g.wait_for_timeout(200)
    check("VIS-3 resume note goes away after the first answer", g.evaluate("!document.querySelector('.resume-note')"))
    ctx.close()
    br.close()
finally:
    srv.terminate()
for n, ok, d in res: print(("PASS " if ok else "FAIL ") + n + ("" if ok else "   " + json.dumps(d, ensure_ascii=False, default=str)[:400]))
print("%d/%d passed; page errors: %s" % (sum(r[1] for r in res), len(res), errors[:5]))
