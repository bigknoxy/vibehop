#!/usr/bin/env python3
"""Deterministic E2E & Falsifier Test Suite for VibeHop PWA."""
import functools
import http.server
import os
import socketserver
import struct
import sys
import threading
from playwright.sync_api import sync_playwright

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_ephemeral_server():
    handler = functools.partial(QuietHandler, directory=REPO_ROOT)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{port}/"


def check_repo_assets():
    """VH-24: static repo asset checks — valid 1200x630 PNG plus sw.js/workflow wiring (no browser)."""
    png_path = os.path.join(REPO_ROOT, 'og-card.png')
    assert os.path.isfile(png_path), "VH-24 FALSIFIER: og-card.png missing at repo root"
    with open(png_path, 'rb') as f:
        header = f.read(24)
    assert header[:8] == b'\x89PNG\r\n\x1a\n' and header[12:16] == b'IHDR', "og-card.png is not a valid PNG"
    width, height = struct.unpack('>II', header[16:24])
    assert (width, height) == (1200, 630), f"og-card.png must be 1200x630, got {width}x{height}"

    sw_text = open(os.path.join(REPO_ROOT, 'sw.js')).read()
    assert 'vibehop-pwa-v8' in sw_text, "VH-24: sw.js cache name must be bumped past v7 so new assets are cached"
    assert "'./icon.svg'" in sw_text and "'./og-card.png'" in sw_text, \
        "VH-24 FALSIFIER: sw.js ASSETS must cache ./icon.svg and ./og-card.png"

    deploy_yml = open(os.path.join(REPO_ROOT, '.github/workflows/deploy-pages.yml')).read()
    assert 'icon.svg' in deploy_yml and 'og-card.png' in deploy_yml, \
        "VH-24: deploy-pages.yml must stage icon.svg and og-card.png into _site/"
    print("  ✅ [VH-24] og-card.png is a valid 1200x630 PNG; sw.js ASSETS & deploy workflow wired")


def run_tests():
    httpd = None
    url = os.environ.get("TEST_URL")
    if not url:
        httpd, url = start_ephemeral_server()

    print(f"🧪 Launching VibeHop Deterministic E2E + Falsifier Suite against {url}")
    check_repo_assets()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path="/usr/bin/google-chrome",
                headless=True,
                args=["--headless=new", "--disable-gpu", "--no-sandbox", "--disable-setuid-sandbox", "--autoplay-policy=no-user-gesture-required"],
            )
            context = browser.new_context(
                viewport={"width": 375, "height": 667},
                device_scale_factor=2,
                is_mobile=True,
                has_touch=True,
            )
            page = context.new_page()

            errors = []
            page.on("pageerror", lambda err: errors.append(str(err)))
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

            page.goto(url, wait_until="networkidle")
            assert len(errors) == 0, f"Page load console errors: {errors}"
            assert page.evaluate("typeof window.__VIBEHOP__ === 'object'"), "FALSIFIER: __VIBEHOP__ missing"

            # 1. Viewport Overflow Falsifier
            clip = page.evaluate("""() => {
                const card = document.getElementById('overlay-card');
                const rect = card.getBoundingClientRect();
                return {
                    fitsH: rect.left >= 4 && rect.right <= window.innerWidth - 4,
                    fitsV: rect.top >= 4 && rect.bottom <= window.innerHeight - 4
                };
            }""")
            assert clip["fitsH"] and clip["fitsV"], f"FALSIFIER: Start card overflows 375x667 viewport: {clip}"
            print("  ✅ [Viewport] Start overlay fits cleanly inside 375x667")

            # 2. VH-16: OpenGraph / Twitter Card Meta
            meta_res = page.evaluate("""() => ({
                ogTitle: document.querySelector('meta[property="og:title"]')?.content,
                ogUrl: document.querySelector('meta[property="og:url"]')?.content,
                ogImage: document.querySelector('meta[property="og:image"]')?.content,
                twImage: document.querySelector('meta[name="twitter:image"]')?.content,
                twCard: document.querySelector('meta[name="twitter:card"]')?.content
            })""")
            assert meta_res["ogTitle"] and "VibeHop" in meta_res["ogTitle"]
            assert meta_res["ogUrl"] and "bigknoxy.github.io/vibehop" in meta_res["ogUrl"]
            assert meta_res["twCard"] == "summary_large_image"
            OG_CARD_URL = "https://bigknoxy.github.io/vibehop/og-card.png"
            assert meta_res["ogImage"] == OG_CARD_URL, \
                f"VH-24 FALSIFIER: og:image must be the 1200x630 og-card.png, got {meta_res['ogImage']}"
            assert meta_res["twImage"] == OG_CARD_URL, \
                f"VH-24 FALSIFIER: twitter:image must be the 1200x630 og-card.png, got {meta_res['twImage']}"
            print("  ✅ [VH-16 & VH-24] Social OpenGraph & Twitter Card metadata verified")

            # 3. VH-11: Progression Gating
            gating_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.setVibeRank(1);
                const blockedTheme = api.selectTheme(2);
                const themeAtRank1 = api.state.themeIdx;
                const blockedAvatar = api.selectAvatar(3);
                const avatarAtRank1 = api.state.avatarIdx;
                api.setVibeRank(4);
                const allowedTheme = api.selectTheme(2);
                const themeAtRank4 = api.state.themeIdx;
                const allowedAvatar = api.selectAvatar(3);
                const avatarAtRank4 = api.state.avatarIdx;
                api.selectTheme(0);
                api.selectAvatar(0);
                return { blockedTheme, themeAtRank1, blockedAvatar, avatarAtRank1, allowedTheme, themeAtRank4, allowedAvatar, avatarAtRank4 };
            }""")
            assert gating_res["blockedTheme"] is False and gating_res["themeAtRank1"] == 0
            assert gating_res["blockedAvatar"] is False and gating_res["avatarAtRank1"] == 0
            assert gating_res["allowedTheme"] is True and gating_res["themeAtRank4"] == 2
            assert gating_res["allowedAvatar"] is True and gating_res["avatarAtRank4"] == 3
            print("  ✅ [VH-11] Progression Gating verified")

            # 4. VH-09 & VH-15: Mute, Pause/Resume & Master Filter
            lifecycle_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.triggerPress();
                api.triggerRelease();
                document.getElementById('mute-btn').click();
                const gainMuted = api.audio.getMasterGainValue();
                const savedMute = localStorage.getItem('vibehop_muted');
                document.getElementById('mute-btn').click();
                const gainUnmuted = api.audio.getMasterGainValue();
                const distBefore = api.state.distance;
                const filterPlay = api.audio.getMasterFilterTarget('PLAY');
                api.togglePause();
                const modePaused = api.state.mode;
                const filterPaused = api.audio.getMasterFilterTarget('PAUSED');
                api.update(1.0);
                const distDuring = api.state.distance;
                api.triggerPress();
                api.triggerRelease();
                return { gainMuted, savedMute, gainUnmuted, modePaused, distBefore, distDuring, modeAfter: api.state.mode, filterPlay, filterPaused };
            }""")
            assert lifecycle_res["gainMuted"] == 0 and lifecycle_res["savedMute"] == "1"
            assert lifecycle_res["gainUnmuted"] > 0.5
            assert lifecycle_res["modePaused"] == "PAUSED" and lifecycle_res["distDuring"] == lifecycle_res["distBefore"]
            assert lifecycle_res["filterPaused"] < 600 and lifecycle_res["filterPlay"] > 3000
            print("  ✅ [VH-09 & VH-15] Mute, Pause/Resume & Master Filter verified")

            # 5. VH-10 & VH-12: Zero-Latency Tap Jump, Hold Glide, Squash/Stretch & Graze
            physics_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.resetGame();
                api.player.grounded = true;
                api.state.coyoteFrames = 6;
                api.triggerPress();
                const instantVy = api.player.vy;
                const stretch = { sx: api.player.scaleX, sy: api.player.scaleY };
                api.triggerRelease();
                const vyAfterRelease = api.player.vy;
                let minTapY = api.player.y;
                for (let i = 0; i < 35; i++) { api.update(1.0); if (api.player.y < minTapY) minTapY = api.player.y; }
                const quickTapH = api.groundY - minTapY;

                api.resetGame();
                api.player.grounded = true;
                api.state.coyoteFrames = 6;
                api.triggerPress();
                let minHoldY = api.player.y;
                for (let i = 0; i < 35; i++) { api.update(1.0); if (api.player.y < minHoldY) minHoldY = api.player.y; }
                api.triggerRelease();
                const holdGlideH = api.groundY - minHoldY;

                api.resetGame();
                api.floatingTexts.length = 0;
                const ob = { x: api.player.x - 18, y: api.groundY - 40, w: 36, h: 40, kind: 'spike', shattered: false, grazed: false };
                api.obstacles.push(ob);
                api.player.y = ob.y - api.player.r * 0.72;
                api.player.vy = 0;
                const pipsBefore = api.state.pips;
                api.update(1.0);
                return { instantVy, vyAfterRelease, stretch, quickTapH, holdGlideH, hasGraze: api.floatingTexts.some(t => t.text.includes('GRAZE')), pipsSame: api.state.pips === pipsBefore };
            }""")
            assert physics_res["instantVy"] <= -13.0 and physics_res["vyAfterRelease"] == physics_res["instantVy"]
            assert physics_res["quickTapH"] >= 125 and physics_res["holdGlideH"] > physics_res["quickTapH"] + 8
            assert physics_res["stretch"]["sy"] > 1.15 and physics_res["hasGraze"] and physics_res["pipsSame"]
            print("  ✅ [VH-10 & VH-12] Zero-latency tap jump, Hold Glide, Squash/Stretch & Graze verified")

            # 6. VH-13: Daily Seeded Run
            seed_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.setDailyMode(true);
                api.resetGame();
                for (let i = 0; i < 120; i++) api.update(1.0);
                const run1 = api.obstacles.map(o => `${Math.round(o.x)}:${Math.round(o.h)}`).join(',');
                api.resetGame();
                for (let i = 0; i < 120; i++) api.update(1.0);
                const run2 = api.obstacles.map(o => `${Math.round(o.x)}:${Math.round(o.h)}`).join(',');
                api.setDailyMode(false);
                return { run1, run2, count: api.obstacles.length };
            }""")
            assert seed_res["count"] >= 1 and seed_res["run1"] == seed_res["run2"]
            print("  ✅ [VH-13] Daily Seeded Run deterministic layout verified")

            # 7. VH-14: PNG Share Card
            card_res = page.evaluate("""async () => {
                const api = window.__VIBEHOP__;
                api.state.score = 6420;
                api.state.maxMult = 8;
                const blob = await api.generateShareCardBlob();
                return { isBlob: blob instanceof Blob, type: blob?.type, size: blob?.size || 0 };
            }""")
            assert card_res["isBlob"] and card_res["type"] == "image/png" and card_res["size"] > 2000
            print(f"  ✅ [VH-14] PNG Cassette Share Card verified ({card_res['size']} bytes)")

            # 8. Anti-AFK & Overhead Drone Gate Falsifier
            reg_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.setZenMode(false);
                api.setDailyMode(true);
                api.resetGame();
                api.triggerPress();
                let frames = 0;
                for (let i = 0; i < 1500; i++) {
                    api.update(1.0);
                    frames++;
                    if (api.state.mode === 'OVER') break;
                }
                const diedHolding = api.state.mode === 'OVER';
                api.triggerRelease();
                api.setDailyMode(false);

                api.resetGame();
                const gate = { x: api.player.x - 10, y: api.groundY - 108, w: 60, h: 56, kind: 'drone', shattered: false, grazed: false };
                api.obstacles.push(gate);
                api.update(1.0);
                const safeGrounded = !gate.shattered && api.state.pips === 3;
                gate.x = api.player.x - 10;
                api.player.y = api.groundY - 75;
                api.update(1.0);
                const hitJumping = gate.shattered && api.state.pips === 2;
                return { diedHolding, frames, safeGrounded, hitJumping };
            }""")
            assert reg_res["diedHolding"] and reg_res["safeGrounded"] and reg_res["hitJumping"]
            print(f"  ✅ [Anti-AFK & Pacing] AFK hold defeated in {reg_res['frames']} frames; Drone Gate verified")

            # 9. VH-18/VH-19: best persisted once per run exit — and never across the daily/endless split
            storage_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                localStorage.setItem('vibehop_best', '1');
                localStorage.removeItem(`vibehop_daily_best_${api.utcDateInt()}`);
                api.setZenMode(true);  // zen: run can never end mid-loop, so every frame below is PLAY
                api.setDailyMode(true);
                api.resetGame();
                api.state.score = 9000;  // the old code persisted vibehop_best on every updateHUD()
                let bestWrites = 0, dailyWrites = 0;
                const dailyKey = `vibehop_daily_best_${api.utcDateInt()}`;
                const realSetItem = localStorage.setItem.bind(localStorage);
                localStorage.setItem = (key, val) => {
                    if (key === 'vibehop_best') bestWrites++;
                    if (key === dailyKey) dailyWrites++;
                    return realSetItem(key, val);
                };
                for (let i = 0; i < 150 && api.state.mode === 'PLAY'; i++) api.update(1.0);
                const writesDuringPlay = { best: bestWrites, daily: dailyWrites };
                bestWrites = 0; dailyWrites = 0;
                api.togglePause();  // entering PAUSED is the persistence point
                const writesOnPause = { best: bestWrites, daily: dailyWrites };
                const pausedDailyVal = localStorage.getItem(dailyKey);
                localStorage.setItem = realSetItem;
                api.togglePause();  // resume → PLAY

                // phase 2: endless run — an endless game-over must persist only the endless best
                api.setDailyMode(false);
                api.setZenMode(false);
                api.resetGame();
                api.state.score = 12000;
                api.state.pips = 1;
                const gate = { x: api.player.x - 10, y: api.groundY - 108, w: 60, h: 56, kind: 'drone', shattered: false, grazed: false };
                api.obstacles.push(gate);
                api.player.y = api.groundY - 75;  // airborne gate pass → pip loss → OVER
                api.player.vy = 0;
                bestWrites = 0; dailyWrites = 0;
                localStorage.setItem = (key, val) => {
                    if (key === 'vibehop_best') bestWrites++;
                    if (key === dailyKey) dailyWrites++;
                    return realSetItem(key, val);
                };
                for (let i = 0; i < 30; i++) {
                    api.update(1.0);
                    if (api.state.mode === 'OVER') break;
                }
                localStorage.setItem = realSetItem;
                return {
                    writesDuringPlay, writesOnPause, pausedDailyVal,
                    dailyBestInMemory: api.dailyBest,  // live in-memory daily best read back through the getter
                    writesOnGameOver: { best: bestWrites, daily: dailyWrites },
                    modeAfterDie: api.state.mode,
                    endlessVal: localStorage.getItem('vibehop_best'),
                    dailyValAfterEndless: localStorage.getItem(dailyKey)
                };
            }""")
            assert storage_res["writesDuringPlay"]["best"] == 0 and storage_res["writesDuringPlay"]["daily"] == 0, \
                f"VH-18 FALSIFIER: best persisted {storage_res['writesDuringPlay']}x during PLAY frames"
            assert storage_res["writesOnPause"]["best"] == 0, \
                f"VH-19 FALSIFIER: a daily-mode run persisted the endless best on pause: {storage_res}"
            assert storage_res["writesOnPause"]["daily"] == 1 \
                and storage_res["pausedDailyVal"] == str(storage_res["dailyBestInMemory"]) \
                and int(storage_res["pausedDailyVal"]) >= 9000, \
                f"VH-18/VH-19: daily best must persist exactly once on pause into today's key: {storage_res}"
            assert storage_res["writesOnGameOver"]["best"] == 1 and storage_res["modeAfterDie"] == "OVER", \
                f"VH-18: endless best must persist exactly once at game over: {storage_res}"
            assert storage_res["endlessVal"] == "12000" and storage_res["dailyValAfterEndless"] == storage_res["pausedDailyVal"] \
                and storage_res["writesOnGameOver"]["daily"] == 0, \
                f"VH-19 FALSIFIER: endless game-over must touch only vibehop_best, never the daily key: {storage_res}"
            print("  ✅ [VH-18/VH-19] Best persistence: once per run exit; daily & endless records fully isolated")
            # 10. VH-18: HUD dirty-check still reflects every displayed value change
            hud_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.setDailyMode(false);
                api.resetGame();
                api.state.mult = 4;
                api.updateHUD();
                const multText = document.getElementById('mult-el').textContent;
                api.state.pips = 1;
                api.state.zenMode = false;
                api.updateHUD();
                const activePips = [...document.querySelectorAll('.pip')].filter((el) => el.classList.contains('active')).length;
                api.state.score = 321;
                api.updateHUD();
                const scoreText = document.getElementById('score-el').textContent;
                const bestText = document.getElementById('best-el').textContent;
                return { multText, activePips, scoreText, bestText };
            }""")
            assert "4x" in hud_res["multText"], f"VH-18: mult HUD stale: {hud_res['multText']}"
            assert hud_res["activePips"] == 1, f"VH-18: pips HUD stale: {hud_res['activePips']}"
            assert hud_res["scoreText"] == "0321", f"VH-18: score HUD stale: {hud_res['scoreText']}"
            assert "BEST" in hud_res["bestText"]
            print("  ✅ [VH-18] Dirty-checked HUD still paints every changed value")

            # 11. VH-18: Dust motes drift dt-scaled in update(), freeze on PAUSED, never mutate in draw()
            dust_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.setDailyMode(true);
                api.resetGame();  // PLAY
                const x0 = api.dustMotes[0].x;
                api.update(1.0);
                const x1 = api.dustMotes[0].x;
                const movedWithDt = x1 !== x0;
                api.togglePause();  // PAUSED
                const p0 = api.dustMotes[0].x;
                api.update(1.0);    // must early-return on PAUSED
                api.draw();         // must never mutate motes
                const p1 = api.dustMotes[0].x;
                const frozenWhilePaused = p1 === p0;
                api.togglePause();  // back to PLAY
                api.update(1.0);
                const movedAgain = api.dustMotes[0].x !== p1;
                const d = api.dustMotes[0].x;
                api.draw();
                const drawMutates = api.dustMotes[0].x !== d;
                return { movedWithDt, frozenWhilePaused, movedAgain, drawMutates };
            }""")
            assert dust_res["movedWithDt"] and dust_res["movedAgain"], \
                f"VH-18: dust must drift dt-scaled during PLAY: {dust_res}"
            assert dust_res["frozenWhilePaused"], "VH-18: dust must freeze while PAUSED"
            assert not dust_res["drawMutates"], "VH-18: draw() must never mutate dust motes"
            print("  ✅ [VH-18] Dust motes: dt-scaled drift, frozen on pause, draw() side-effect free")

            # 12. VH-18: Multi-touch — only the tracked active pointer may clear state.holdingInput
            touch_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.setZenMode(true);
                api.setDailyMode(false);
                api.resetGame();  // PLAY, grounded
                const gameCanvas = document.getElementById('game');
                gameCanvas.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 11, bubbles: true, cancelable: true }));
                const heldAfterDown = api.state.holdingInput;
                window.dispatchEvent(new PointerEvent('pointerup', { pointerId: 22, bubbles: true }));
                const heldAfterForeignUp = api.state.holdingInput;
                const vyAtForeignUp = api.player.vy;
                gameCanvas.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 33, bubbles: true, cancelable: true }));
                window.dispatchEvent(new PointerEvent('pointercancel', { pointerId: 44, bubbles: true }));
                const heldAfterForeignCancel = api.state.holdingInput;
                window.dispatchEvent(new PointerEvent('pointerup', { pointerId: 11, bubbles: true }));
                const heldAfterActiveUp = api.state.holdingInput;
                gameCanvas.dispatchEvent(new PointerEvent('pointerdown', { pointerId: 55, bubbles: true, cancelable: true }));
                const heldAfterRepress = api.state.holdingInput;
                window.dispatchEvent(new PointerEvent('pointercancel', { pointerId: 55, bubbles: true }));
                const releasedByActiveCancel = !api.state.holdingInput;
                return { heldAfterDown, heldAfterForeignUp, vyAtForeignUp, heldAfterForeignCancel, heldAfterActiveUp, heldAfterRepress, releasedByActiveCancel };
            }""")
            assert touch_res["heldAfterDown"], "VH-18: pointer press must set holdingInput"
            assert touch_res["vyAtForeignUp"] < 0, "VH-18: foreign pointerup must arrive mid-glide (airborne vy)"
            assert touch_res["heldAfterForeignUp"], "VH-18 FALSIFIER: foreign pointerup dropped holdingInput mid-glide"
            assert touch_res["heldAfterForeignCancel"], "VH-18: foreign pointercancel dropped holdingInput"
            assert not touch_res["heldAfterActiveUp"], "VH-18: the active pointer's own pointerup must release the hold"
            assert touch_res["heldAfterRepress"] and touch_res["releasedByActiveCancel"], \
                "VH-18: the active pointer's own pointercancel must release the hold"
            print("  ✅ [VH-18] Multi-touch: foreign pointerup/cancel no longer drop the hold; active cancel releases")

            # 13. VH-20: Master Glue Compressor — every synth voice routes through a DynamicsCompressorNode
            comp_res = page.evaluate("""() => {
                const comp = window.__VIBEHOP__.audio.compressor;
                return {
                    isCompressor: comp instanceof window.DynamicsCompressorNode,
                    threshold: comp ? comp.threshold.value : null,
                    ratio: comp ? comp.ratio.value : null
                };
            }""")
            assert comp_res["isCompressor"], "VH-20 FALSIFIER: audio.compressor is not a DynamicsCompressorNode"
            assert -30 <= comp_res["threshold"] <= -10 and comp_res["ratio"] >= 4, \
                f"VH-20: compressor must actually grip the mix: {comp_res}"
            print(f"  ✅ [VH-20] DynamicsCompressorNode grips the master bus (threshold {comp_res['threshold']}dB, ratio {comp_res['ratio']})")

            # 14. VH-24: 3-Beat Resume Count-In — PAUSED → RESUMING freezes the world, then lands on PLAY
            count_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.resetGame();                        // fresh PLAY run
                const gate = { x: api.player.x - 10, y: api.groundY - 108, w: 60, h: 56, kind: 'drone', shattered: false, grazed: false };
                api.obstacles.push(gate);
                api.togglePause();                      // PLAY → PAUSED
                api.togglePause();                      // PAUSED → RESUMING count-in, never instant PLAY
                const modeOnUnpause = api.state.mode;
                const resumeFramesAtStart = api.state.resumeFrames;
                const expectedCountFrames = Math.round(3 * 3600 / api.audio.bpm);
                api.player.grounded = false;            // airborne snapshot — physics must hold still
                api.player.vy = -6;
                api.state.distance = 0;
                const gateX0 = gate.x, playerY0 = api.player.y, vy0 = api.player.vy, dist0 = api.state.distance;
                api.update(1.0);                        // one frozen count-in frame
                const frozen = {
                    gate: gate.x === gateX0,
                    player: api.player.y === playerY0 && api.player.vy === vy0,
                    distance: api.state.distance === dist0
                };
                for (let i = 0; i < 200 && api.state.mode === 'RESUMING'; i++) api.update(1.0);
                return { modeOnUnpause, resumeFramesAtStart, expectedCountFrames, frozen, finishedMode: api.state.mode };
            }""")
            assert count_res["modeOnUnpause"] == "RESUMING", \
                "VH-24 FALSIFIER: unpausing must enter RESUMING, not instant PLAY"
            assert count_res["resumeFramesAtStart"] > 0, "VH-24: RESUMING must carry a positive resumeFrames countdown"
            assert count_res["resumeFramesAtStart"] == count_res["expectedCountFrames"], \
                f"VH-24: count-in must be exactly 3 beats long: {count_res}"
            assert count_res["frozen"]["gate"] and count_res["frozen"]["player"] and count_res["frozen"]["distance"], \
                f"VH-24: obstacles and physics must freeze during the count-in: {count_res['frozen']}"
            assert count_res["finishedMode"] == "PLAY", "VH-24: countdown must land on PLAY with physics live again"
            print(f"  ✅ [VH-24] 3-beat resume count-in: PAUSED → RESUMING ({count_res['resumeFramesAtStart']} frames frozen) → PLAY")

            # 15. VH-24: og-card.png is a real, browser-decodable 1200x630 PNG on the served site
            png_res = page.evaluate("""async () => {
                const img = new Image();
                img.src = 'og-card.png';
                await img.decode();
                return { w: img.naturalWidth, h: img.naturalHeight };
            }""")
            assert png_res["w"] == 1200 and png_res["h"] == 630, \
                f"VH-24 FALSIFIER: served og-card.png decodes as {png_res}, want 1200x630"
            print("  ✅ [VH-24] Served og-card.png decodes in-browser at 1200x630")

            # 16. VH-19: Daily best fully isolated — endless vibehop_best (9999) is never overwritten by daily runs
            daily_isolation_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.setDailyMode(false);
                api.setZenMode(false);
                localStorage.setItem('vibehop_best', '9999');
                localStorage.removeItem(`vibehop_daily_best_${api.utcDateInt()}`);
                api.setDailyMode(true);
                api.resetGame();
                api.state.score = 5000;
                api.updateHUD();
                const hudBest = document.getElementById('best-el').textContent;  // must read DAILY BEST
                api.state.pips = 1;
                const gate = { x: api.player.x - 10, y: api.groundY - 108, w: 60, h: 56, kind: 'drone', shattered: false, grazed: false };
                api.obstacles.push(gate);
                api.player.y = api.groundY - 75;  // airborne gate pass (VH-9 falsifier pattern) → pip loss → OVER
                api.player.vy = 0;
                for (let i = 0; i < 30 && api.state.mode === 'PLAY'; i++) api.update(1.0);
                const res = {
                    mode: api.state.mode,
                    hudBest,
                    badge: document.getElementById('ov-badge').textContent,
                    endlessBest: localStorage.getItem('vibehop_best'),
                    dailyBest: localStorage.getItem(`vibehop_daily_best_${api.utcDateInt()}`)
                };
                api.setDailyMode(false);
                return res;
            }""")
            assert daily_isolation_res["mode"] == "OVER", f"VH-19: daily run should reach game over: {daily_isolation_res}"
            assert daily_isolation_res["endlessBest"] == "9999", \
                f"VH-19 FALSIFIER: daily-mode run overwrote the endless best: {daily_isolation_res}"
            assert daily_isolation_res["dailyBest"] == "5000", \
                f"VH-19: a daily run must persist into today's per-UTC-date key: {daily_isolation_res}"
            assert daily_isolation_res["badge"] == "★ NEW HIGH VIBE ★", \
                f"VH-19: daily runs must medal independently against today's daily best: {daily_isolation_res}"
            assert daily_isolation_res["hudBest"].startswith("DAILY BEST"), \
                f"VH-19: HUD must label the daily record while dailyMode is on: {daily_isolation_res}"
            print("  ✅ [VH-19] Daily best isolated: endless 9999 intact; DAILY BEST HUD + independent medal")

            # 17. VH-22: streak — consecutive UTC days chain, same-day replays hold, gaps restart
            streak_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.setDailyMode(false);
                const today = api.utcDateInt();
                const dMinus1 = api.utcDateInt(-1);
                localStorage.removeItem('vibehop_seen_tips');
                localStorage.setItem('vibehop_streak', '4');
                localStorage.setItem('vibehop_last_play_date', String(dMinus1));
                api.state.streak = 4;               // runtime state mirrors storage in the real client
                api.state.lastPlayDate = dMinus1;
                api.resetGame();                    // today's run: the day before chains 4 → 5
                const chained = api.state.streak;
                const persistedStreak = localStorage.getItem('vibehop_streak');
                const persistedDate = localStorage.getItem('vibehop_last_play_date');
                api.resetGame();                    // replaying the same day must not double-bump
                const sameDay = api.state.streak;
                const dMinus2 = api.utcDateInt(-2);
                localStorage.setItem('vibehop_streak', '7');
                localStorage.setItem('vibehop_last_play_date', String(dMinus2));
                api.state.streak = 7;
                api.state.lastPlayDate = dMinus2;
                api.resetGame();                    // 2-day gap: the chain restarts at 1
                const restarted = api.state.streak;
                api.showOverlay('START');
                const pill = document.getElementById('streak-el');
                const pillText = pill.textContent;
                const pillShown = pill.style.display === 'inline-block';
                api.state.streak = 0;
                api.showOverlay('START');
                const pillHidden = pill.style.display === 'none';
                return { chained, persistedStreak, persistedDate, sameDay, restarted, pillText, pillShown, pillHidden, today: String(today) };
            }""")
            assert streak_res["chained"] == 5 and streak_res["persistedStreak"] == "5", \
                f"VH-22 FALSIFIER: running the day after must chain streak 4 → 5: {streak_res}"
            assert streak_res["persistedDate"] == streak_res["today"], \
                f"VH-22: last play date must advance to today's UTC YYYYMMDD: {streak_res}"
            assert streak_res["sameDay"] == 5, f"VH-22: same-day runs must not double the streak: {streak_res}"
            assert streak_res["restarted"] == 1, f"VH-22: a skipped UTC day must restart the streak at 1: {streak_res}"
            assert streak_res["pillText"] == "🔥 1-DAY FLOW" and streak_res["pillShown"], \
                f"VH-22: Start/Share UI must show the N-day flow pill: {streak_res}"
            assert streak_res["pillHidden"], f"VH-22: pill must hide when the streak sits at 0: {streak_res}"
            print("  ✅ [VH-22] Streak: chains consecutive UTC days, holds same-day, restarts on gap; pill paints")

            # 18. VH-19: first-encounter diegetic callouts — teach-once, persisted to vibehop_seen_tips
            tips_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                api.setDailyMode(false);
                api.resetGame();
                api.seenTips.clear();
                localStorage.removeItem('vibehop_seen_tips');
                api.floatingTexts.length = 0;
                const gate = { x: api.player.x - 10, y: api.groundY - 108, w: 60, h: 56, kind: 'drone', shattered: false, grazed: false };
                api.obstacles.push(gate);
                api.update(1.0);  // grounded pass through the gate: the first encounter
                const droneSpawned = api.floatingTexts.some((t) => t.text === 'STAY LOW!');
                const droneRecorded = localStorage.getItem('vibehop_seen_tips') === 'drone';
                const gatePassed = !gate.shattered && api.state.pips === 3;
                api.floatingTexts.length = 0;
                api.update(1.0);  // gate still on screen: the callout must stay once-only
                const droneRepeated = api.floatingTexts.some((t) => t.text === 'STAY LOW!');

                api.rings.length = 0;
                api.floatingTexts.length = 0;
                api.rings.push({ x: api.player.x, y: api.groundY - 120, r: 24, pulse: 0 });
                api.update(1.0);
                const ringSpawned = api.floatingTexts.some((t) => t.text === 'TAP IN RING!');

                api.rails.length = 0;
                api.floatingTexts.length = 0;
                api.rails.push({ x: api.player.x - 60, y: api.groundY - 96, w: 220, h: 6, grinded: false });
                api.update(1.0);
                const railSpawned = api.floatingTexts.some((t) => t.text === 'LAND ON RAIL!');
                const tipKeys = (localStorage.getItem('vibehop_seen_tips') || '').split(',');
                const allRecorded = ['drone', 'ring', 'rail'].every((k) => tipKeys.includes(k));
                return { droneSpawned, droneRecorded, gatePassed, droneRepeated, ringSpawned, railSpawned, allRecorded };
            }""")
            assert tips_res["droneSpawned"] and tips_res["droneRecorded"] and tips_res["gatePassed"], \
                f"VH-19: the first drone-gate encounter must spawn STAY LOW! and record it: {tips_res}"
            assert not tips_res["droneRepeated"], f"VH-19 FALSIFIER: callout repeated within the same session: {tips_res}"
            assert tips_res["ringSpawned"] and tips_res["railSpawned"] and tips_res["allRecorded"], \
                f"VH-19: ring/rail first encounters must call out and record too: {tips_res}"
            print("  ✅ [VH-19] First-encounter callouts: STAY LOW!/TAP IN RING!/LAND ON RAIL! teach once and persist")

            # 18b. VH-19: cross-session persistence — a new session must not re-teach the callouts
            page.evaluate("navigator.serviceWorker.getRegistrations().then((rs) => Promise.all(rs.map((r) => r.unregister())))")
            page.reload(wait_until="networkidle")
            assert len(errors) == 0, f"Page reload console errors: {errors}"
            fresh_tips_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                const loadedFromStorage = api.seenTips.has('drone');
                api.resetGame();
                api.floatingTexts.length = 0;
                const gate = { x: api.player.x - 10, y: api.groundY - 108, w: 60, h: 56, kind: 'drone', shattered: false, grazed: false };
                api.obstacles.push(gate);
                api.update(1.0);
                return {
                    loadedFromStorage,
                    reSpawned: api.floatingTexts.some((t) => t.text === 'STAY LOW!'),
                    gatePassed: !gate.shattered
                };
            }""")
            assert fresh_tips_res["loadedFromStorage"], \
                "VH-19 FALSIFIER: vibehop_seen_tips must be read back into seenTips at session start"
            assert not fresh_tips_res["reSpawned"] and fresh_tips_res["gatePassed"], \
                f"VH-19 FALSIFIER: callouts must never repeat across sessions: {fresh_tips_res}"
            print("  ✅ [VH-19] Callout teach-once survives a page reload via vibehop_seen_tips")
            assert len(errors) == 0, f"Runtime console errors detected: {errors}"
            browser.close()
            print("🎉 ALL DETERMINISTIC E2E & FALSIFIER CHECKS PASSED!")
    finally:
        if httpd:
            httpd.shutdown()


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as exc:
        print(f"❌ E2E TEST SUITE FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
