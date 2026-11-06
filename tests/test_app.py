"""End-to-end test in real Chrome with touch input. No participant data is produced.

    pip install playwright
    python tests/test_app.py [output_folder]

Part 1 checks the counterbalancing and that every clip exists.
Part 2 checks that the HRTF output really is louder on the expected side.
Part 3 plays a whole session with a scripted user, including the awkward paths: early swipes,
diagonal swipes, replays, a wrong answer, a timeout, an interruption and a reload mid-block.
It writes screenshots and the two CSVs to output_folder. Those CSVs are test output, not data.
"""
import csv
import functools
import http.server
import io
import os
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="earrepair_test_")
os.makedirs(OUT, exist_ok=True)


PLAYS_BEFORE_RELOAD = []  # a reload wipes the page's own record


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/index.html"


PLAN_CHECK = """() => {
  const problems = [], seen = {};
  for (let n = 1; n <= 18; n++) {
    const plan = EarPlan.buildPlan('P' + String(n).padStart(2, '0'), STIMULI);
    const again = EarPlan.buildPlan('P' + String(n).padStart(2, '0'), STIMULI);
    if (JSON.stringify(plan) !== JSON.stringify(again)) problems.push('plan not reproducible ' + n);
    const items = new Set();
    plan.blocks.forEach(b => {
      seen[b.condition + '@' + b.position] = (seen[b.condition + '@' + b.position] || 0) + 1;
      seen['set' + b.set + ':' + b.condition] = (seen['set' + b.set + ':' + b.condition] || 0) + 1;
      if (b.trials.length !== 15) problems.push('block size ' + b.trials.length);
      if (b.practice.length !== 4) problems.push('practice size ' + b.practice.length);
      const present = b.trials.filter(t => !t.absent);
      if (present.length !== 12) problems.push('present ' + present.length);
      for (const sim of ['confusable', 'distinct']) for (const pos of [0, 1, 2]) {
        const c = present.filter(t => t.similarity === sim && t.target_pos === pos).length;
        if (c !== 2) problems.push(`n=${n} ${sim} pos ${pos}: ${c}`);
      }
      for (const t of b.trials.concat(b.practice)) {
        if (t.absent ? t.options.includes(t.target) : t.options[t.target_pos] !== t.target) problems.push('target ' + t.item_id);
        if (new Set(t.options).size !== 3) problems.push('options ' + t.item_id);
      }
      b.trials.forEach(t => { if (items.has(t.item_id)) problems.push('item repeated ' + t.item_id); items.add(t.item_id); });
    });
    if (items.size !== 45) problems.push('items ' + items.size);
  }
  return { problems, seen };
}"""

CLIP_CHECK = """async () => {
  const ids = new Set(['a_which', 'a_one', 'a_two', 'a_three', 'a_correct', 'a_wrong', 'a_none_right', 'a_none_wrong']);
  for (let n = 1; n <= 18; n++) EarPlan.buildPlan('P' + n, STIMULI).blocks.forEach(b => EarPlan.clipsFor(b).forEach(i => ids.add(i)));
  const missing = [];
  for (const id of ids) { const r = await fetch('audio/' + id + '.wav', { method: 'HEAD' }); if (!r.ok) missing.push(id); }
  return { total: ids.size, missing };
}"""

# Renders a clip through the same panner settings as playAt and measures each ear.
EAR_CHECK = """async () => {
  const bytes = await (await fetch('audio/n_riya_shah.wav')).arrayBuffer();
  const out = {};
  for (const az of [-90, 0, 90]) {
    const sr = 44100, off = new OfflineAudioContext(2, sr * 2, sr);
    const buffer = await off.decodeAudioData(bytes.slice(0));
    const a = az * Math.PI / 180, p = off.createPanner();
    p.panningModel = 'HRTF';
    p.positionX.value = Math.sin(a); p.positionY.value = 0; p.positionZ.value = -Math.cos(a);
    const s = off.createBufferSource();
    s.buffer = buffer; s.connect(p); p.connect(off.destination); s.start(0.05);
    const r = await off.startRendering();
    const L = r.getChannelData(0), R = r.getChannelData(1);
    const rms = d => Math.sqrt(d.reduce((sum, v) => sum + v * v, 0) / d.length);
    // Interaural time difference: the lag that best lines up the ears. Positive = left ear leads.
    let best = -Infinity, lag = 0;
    for (let k = -66; k <= 66; k++) {
      let c = 0;
      for (let i = 100; i < L.length - 100; i += 2) c += L[i] * R[i + k];
      if (c > best) { best = c; lag = k; }
    }
    out[az] = { ild_db: 20 * Math.log10(rms(L) / rms(R)), itd_us: lag / sr * 1e6 };
  }
  return out;
}"""

HOOKS = """() => {
  window.__plays = window.__plays || [];
  const play = window.playAt, schedule = window.scheduleOptions, run = window.runTrial;
  window.playAt = (b, az, when) => { window.__plays.push({ az, trial: window.__trial && window.__trial.item_id, dur: b.duration }); return play(b, az, when); };
  window.scheduleOptions = (...a) => { const r = schedule(...a); window.__list = r; return r; };
  window.runTrial = (trial, block, phase) => {
    window.__trial = trial; window.__block = block; window.__phase = phase; window.__list = null;
    window.__fresh = true;
    return run(trial, block, phase);
  };
}"""

VISIBLE = """() => {
  if (!document.getElementById('pad').hidden) return 'pad';
  for (const id of ['setup','check','intro','ready','paused','tlx','final','done'])
    if (!document.getElementById(id).hidden) return id;
  return '?';
}"""


class Driver:
    def __init__(self, page, cdp):
        self.page, self.cdp = page, cdp
        self.vw, self.vh = page.viewport_size["width"], page.viewport_size["height"]

    def swipe(self, dx, dy):
        x, y = self.vw / 2, self.vh / 2
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        self.page.wait_for_timeout(15)
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x + dx / 2, "y": y + dy / 2}]})
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x + dx, "y": y + dy}]})
        self.page.wait_for_timeout(15)
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

    def direction(self, name):
        self.swipe(*{"left": (-140, 0), "right": (140, 0), "up": (0, -140), "down": (0, 140)}[name])

    def wait_list(self):
        self.page.wait_for_function("window.__list && performance.now() > window.__list.first + 150", timeout=20000)


def info(page):
    return page.evaluate("""() => ({ phase: window.__phase, block: session.blockIndex + 1, index: session.trialIndex + 1,
      pos: window.__trial && window.__trial.target_pos, fresh: window.__fresh })""")


def play_session(page, d, url):
    shots, did = set(), set()
    gesture_of = {0: "left", 1: "up", 2: "right", -1: "down"}

    def shot(name):
        if name not in shots:
            shots.add(name)
            page.screenshot(path=os.path.join(OUT, f"{name}.png"))

    while True:
        screen = page.evaluate(VISIBLE)
        if screen == "setup":
            if page.locator("#resumeBox").is_visible():
                shot("resume")
                page.click("#resumeBtn")
                page.wait_for_function("session !== null")
                page.evaluate(HOOKS)
            else:
                shot("setup")
                page.fill("#pid", "P01")
                page.fill("#earphones", "test")
                page.fill("#lapM", "40")
                page.fill("#lapS", "30")
                page.click("#startBtn")
                page.wait_for_function("document.getElementById('check').hidden === false")
        elif screen == "check":
            shot("check")
            page.click("#checkPlay")
            page.wait_for_timeout(30)
            side = page.evaluate("() => null")  # the answer is private: keep guessing until 3 in a row
            page.click("#checkLeft" if page.evaluate("Math.random() < .5") else "#checkRight")
        elif screen == "intro":
            shot("intro_" + page.evaluate("plan.blocks[session.blockIndex].condition"))
            page.click("#introBtn")
            page.wait_for_function("document.getElementById('intro').hidden || document.getElementById('loadMsg').classList.contains('bad')", timeout=60000)
            assert not page.locator("#loadMsg.bad").is_visible(), page.inner_text("#loadMsg")
        elif screen == "ready":
            shot("ready")
            page.click("#readyBtn")
            page.wait_for_timeout(100)
        elif screen == "paused":
            shot("paused")
            page.evaluate("Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })")
            page.click("#pausedBtn")
            page.wait_for_timeout(100)
        elif screen == "tlx":
            shot("tlx")
            page.evaluate("""() => { document.querySelectorAll('#tlxItems input').forEach((el, i) => {
                el.value = 20 + 10 * i; el.dispatchEvent(new Event('input')); }); }""")
            page.fill("#laps", "4.5")
            page.click("#tlxBtn")
            page.wait_for_timeout(100)
        elif screen == "final":
            shot("final")
            page.select_option("#best", "spatial")
            page.select_option("#worst", "numbered")
            page.fill("#comments", 'scripted, with a comma and a "quote"')
            page.click("#finalBtn")
            page.wait_for_timeout(100)
        elif screen == "done":
            shot("done")
            return
        elif screen == "pad":
            state = info(page)
            if not state["fresh"]:
                page.wait_for_timeout(40)
                continue
            key = (state["block"], state["index"]) if state["phase"] == "test" else None
            if state["phase"] == "practice":
                shot("practice_pad")
            if key == (1, 1) and "early" not in did:           # swipe during the request: must be ignored
                did.add("early")
                page.wait_for_function("window.__list", timeout=5000)
                d.direction("left")
            d.wait_list()
            if key == (1, 2) and "diag" not in did:            # diagonal: must buzz and wait
                did.add("diag")
                d.swipe(100, 100)
                page.wait_for_timeout(100)
            if key == (1, 3) and "tap" not in did:             # tap: must replay the options
                did.add("tap")
                d.swipe(0, 0)
                page.wait_for_timeout(100)
                d.wait_list()
            if key == (2, 5) and "timeout" not in did:         # no answer at all
                did.add("timeout")
                page.evaluate("window.__fresh = false")
                page.wait_for_function("session.trialIndex === 5", timeout=40000)
                continue
            if key == (3, 2) and "hide" not in did:            # phone call, app switch
                did.add("hide")
                page.evaluate("""() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
                                         document.dispatchEvent(new Event('visibilitychange')); }""")
                page.wait_for_function("document.getElementById('paused').hidden === false")
                continue
            if key == (3, 6) and "reload" not in did:          # page lost mid-block
                did.add("reload")
                PLAYS_BEFORE_RELOAD.extend(page.evaluate("window.__plays"))
                page.reload()
                page.wait_for_selector("#resumeBtn")
                continue
            gesture = gesture_of[state["pos"]]
            if key == (2, 4):                                  # a wrong answer
                gesture = "down" if gesture != "down" else "left"
            page.evaluate("window.__fresh = false")
            d.direction(gesture)
        page.wait_for_timeout(30)


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def main():
    server, url = serve()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--autoplay-policy=no-user-gesture-required"])
        context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True,
                                      device_scale_factor=2)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("response", lambda r: errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)
        page.goto(url)

        plan = page.evaluate(PLAN_CHECK)
        assert not plan["problems"], plan["problems"][:10]
        for c in ("numbered", "plain", "spatial"):
            assert all(plan["seen"][f"{c}@{k}"] == 6 for k in (1, 2, 3)), plan["seen"]
            assert all(plan["seen"][f"set{s}:{c}"] == 6 for s in (1, 2, 3)), plan["seen"]
        print("plan: 18 ids; every condition 6x in each position and 6x with each item set; positions balanced")

        clips = page.evaluate(CLIP_CHECK)
        assert not clips["missing"], clips["missing"][:10]
        print(f"clips: all {clips['total']} planned clips exist")

        ears = page.evaluate(EAR_CHECK)
        print("ears:", {k: {m: round(x, 1) for m, x in v.items()} for k, v in ears.items()})
        # Speech energy is mostly low, so level differs little; arrival time carries the side.
        # A real head at 90 degrees gives roughly 600-700 microseconds.
        assert ears["-90"]["ild_db"] > 2 and ears["90"]["ild_db"] < -2, "level difference is on the wrong side"
        assert 400 < ears["-90"]["itd_us"] < 1000, "left source does not reach the left ear first"
        assert -1000 < ears["90"]["itd_us"] < -400, "right source does not reach the right ear first"
        assert abs(ears["0"]["ild_db"]) < 1 and abs(ears["0"]["itd_us"]) < 60, "front source is not balanced"

        page.evaluate(HOOKS)
        cdp = context.new_cdp_session(page)
        play_session(page, Driver(page, cdp), url)

        trials_text = page.evaluate("trialsCsv()")
        blocks_text = page.evaluate("blocksCsv()")
        plays = PLAYS_BEFORE_RELOAD + page.evaluate("window.__plays")
        with open(os.path.join(OUT, "test_trials.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(trials_text)
        with open(os.path.join(OUT, "test_blocks.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(blocks_text)
        browser.close()
    server.shutdown()

    t, b = rows(trials_text), rows(blocks_text)
    test = [r for r in t if r["phase"] == "test"]
    real = [r for r in test if r["status"] != "interrupted"]
    by = lambda block, trial: [r for r in test if r["block"] == str(block) and r["trial"] == str(trial)]
    print(f"session: {len(t)} rows, {len(test)} test rows, statuses {sorted({r['status'] for r in t})}")

    assert len(b) == 3 and {r["condition"] for r in b} == {"numbered", "plain", "spatial"}
    assert b[0]["pref_best"] == "spatial" and "quote" in b[0]["comments"]
    assert all(r["tlx_mental"] and r["laps"] == "4.5" for r in b)
    assert sum(r["phase"] == "practice" for r in t) == 12, "practice rows"
    keys = {(r["block"], r["trial"]) for r in real}
    assert len(keys) == 45, f"expected 45 distinct trials, got {len(keys)}"

    first = by(1, 1)[-1]
    assert int(first["early_gestures"]) >= 1 and first["status"] == "ok", first
    assert int(by(1, 2)[-1]["ambiguous"]) == 1, by(1, 2)
    assert int(by(1, 3)[-1]["replays"]) == 1, by(1, 3)
    assert by(2, 4)[-1]["correct"] == "0", by(2, 4)
    assert by(2, 5)[-1]["status"] == "timeout" and by(2, 5)[-1]["correct"] == "0", by(2, 5)
    assert any(r["status"] == "interrupted" for r in by(3, 2)) and by(3, 2)[-1]["status"] == "ok", by(3, 2)
    assert by(3, 6)[-1]["status"] == "ok", by(3, 6)
    wrong = [r for r in real if r["correct"] != "1"]
    assert {(r["block"], r["trial"]) for r in wrong} == {("2", "4"), ("2", "5")}, wrong
    assert all(r["input"] == "touch" for r in real if r["status"] == "ok"), "input was not touch"
    assert all(int(r["rt_from_list_ms"]) >= 0 for r in real if r["status"] == "ok")

    # Conditions must differ only in position: 3 azimuths for spatial options, centre for the rest.
    condition_of = {r["item_id"]: r["condition"] for r in test}
    az = {}
    for play in plays:
        if play["trial"] in condition_of:
            az.setdefault(condition_of[play["trial"]], set()).add(play["az"])
    print("azimuths used:", {k: sorted(v) for k, v in az.items()})
    assert az["numbered"] == {0} and az["plain"] == {0} and az["spatial"] == {-90, 0, 90}

    for c in ("numbered", "plain", "spatial"):
        ms = [int(r["list_ms"]) for r in real if r["condition"] == c]
        print(f"list length {c}: mean {sum(ms) / len(ms) / 1000:.2f} s")
    print("page errors:", errors or "none")
    assert not errors
    print("ALL CHECKS PASSED ->", OUT)


if __name__ == "__main__":
    main()
