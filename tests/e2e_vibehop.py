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
