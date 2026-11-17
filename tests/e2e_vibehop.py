#!/usr/bin/env python3
"""Deterministic E2E & Falsifier Test Suite for VibeHop PWA."""
import functools
import http.server
import os
import socketserver
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


def run_tests():
    httpd = None
    url = os.environ.get("TEST_URL")
    if not url:
        httpd, url = start_ephemeral_server()

    print(f"🧪 Launching VibeHop Deterministic E2E + Falsifier Suite against {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path="/usr/bin/google-chrome",
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--autoplay-policy=no-user-gesture-required"],
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
                twCard: document.querySelector('meta[name="twitter:card"]')?.content
            })""")
            assert meta_res["ogTitle"] and "VibeHop" in meta_res["ogTitle"]
            assert meta_res["ogUrl"] and "bigknoxy.github.io/vibehop" in meta_res["ogUrl"]
            assert meta_res["twCard"] == "summary_large_image"
            print("  ✅ [VH-16] Social OpenGraph & Twitter Card metadata verified")

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

            # 9. VH-18: Best score persisted once on pause — never per frame during PLAY
            storage_res = page.evaluate("""() => {
                const api = window.__VIBEHOP__;
                localStorage.setItem('vibehop_best', '1');
                api.setZenMode(true);  // zen: run can never end mid-loop, so every frame below is PLAY
                api.setDailyMode(true);
                api.resetGame();
                api.state.score = 9000;  // > best: the old code persisted vibehop_best on every updateHUD()
                let bestWrites = 0;
                const realSetItem = localStorage.setItem.bind(localStorage);
                localStorage.setItem = (key, val) => { if (key === 'vibehop_best') bestWrites++; return realSetItem(key, val); };
                for (let i = 0; i < 150 && api.state.mode === 'PLAY'; i++) api.update(1.0);
                const writesDuringPlay = bestWrites;
                bestWrites = 0;
                api.togglePause();  // entering PAUSED is the persistence point
                const writesOnPause = bestWrites;
                api.togglePause();  // resume → PLAY
                bestWrites = 0;
                api.setZenMode(false);
                api.resetGame();
                api.state.score = 12000;  // beat the paused best
                api.state.pips = 1;       // next obstacle hit ends the run
                for (let i = 0; i < 600 && api.state.mode === 'PLAY'; i++) api.update(1.0);
                const writesOnGameOver = bestWrites;
                const modeAfterDie = api.state.mode;
                localStorage.setItem = realSetItem;
                api.setDailyMode(false);
                return { writesDuringPlay, writesOnPause, writesOnGameOver, modeAfterDie };
            }""")
            assert storage_res["writesDuringPlay"] == 0, \
                f"VH-18 FALSIFIER: best persisted {storage_res['writesDuringPlay']}x during PLAY frames"
            assert storage_res["writesOnPause"] == 1, "VH-18: best must persist exactly once when the run pauses"
            assert storage_res["writesOnGameOver"] == 1 and storage_res["modeAfterDie"] == "OVER", \
                f"VH-18: best must persist exactly once at game over: {storage_res}"
            print("  ✅ [VH-18] No per-frame best-score storage writes; persisted once on pause and on game over")

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
