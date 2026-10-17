<div align="center">

<img src="https://raw.githubusercontent.com/bigknoxy/vibehop/main/icon.svg" width="128" height="128" alt="VibeHop Neon Icon" />

# 🎧 VibeHop

**A chill, zero-dependency 115 BPM Lo-Fi Neon Rhythm-Runner & Progressive Web App**

[![Play Live on GitHub Pages](https://img.shields.io/badge/%E2%96%B6%EF%B8%8F_PLAY_NOW-bigknoxy.github.io%2Fvibehop-4ef0d0?style=for-the-badge&labelColor=0d0e1e)](https://bigknoxy.github.io/vibehop/)
[![Deploy PWA to GitHub Pages](https://img.shields.io/github/actions/workflow/status/bigknoxy/vibehop/deploy-pages.yml?branch=main&style=for-the-badge&label=CI%2FCD&color=ffd166&labelColor=0d0e1e)](https://github.com/bigknoxy/vibehop/actions)
[![PWA Installable](https://img.shields.io/badge/PWA-Installable_Offline-ff5376?style=for-the-badge&labelColor=0d0e1e)](https://bigknoxy.github.io/vibehop/)

<h3>👉 <a href="https://bigknoxy.github.io/vibehop/">Launch VibeHop Live (https://bigknoxy.github.io/vibehop/)</a> 👈</h3>

</div>

---

## ✨ The Vibe

**VibeHop** is a pocket-sized, flow-state arcade runner crafted entirely in vanilla HTML5 Canvas and the Web Audio API. No external assets, no CDNs, no bloat—just pure synthesized lo-fi beats, glowing geometry, and forgiving rhythm-platforming designed for mobile and desktop.

- 🎹 **100% Procedural 115 BPM Lo-Fi Audio** — Real-time Web Audio synthesizer generating warm `Cm7 → Abmaj7 → Fm7 → Gm7` triangle pad progressions, lo-fi kick/snare/hat grooves, and C-minor pentatonic jump chimes on the fly.
- 🛡️ **Flow-First 3-Pip Shield Pool** — No frustrating instant deaths. Clipping an obstacle shatters it in a neon burst, docks 1 shield pip, and grants **1.5s of invulnerability** without breaking your momentum.
- 💎 **Neon Prism Orbs** — Collect floating mint prisms to heal **+1 Shield Pip** and level up your **Vibe Score Multiplier** (up to `8x VIBE`).
- ⭕ **Mid-Air Dash Rings** — Tap while inside pulsing amber rings to launch into a high-speed aerial dash across hazards.
- 🎮 **Butter-Smooth Platforming** — 70% inner forgiving hitboxes, 6-frame coyote time, 6-frame jump buffering, hold-to-auto-hop, and 60/120Hz delta-time physics.
- 📲 **Installable Offline PWA** — Works offline via Service Worker caching with one-tap **Install App** support on Android/Desktop and full-screen standalone mode on iOS.

---

## 🎨 Neon Palette

| Swatch | Role | Hex |
| :--- | :--- | :--- |
| 🌌 **Deep Night** | Midnight Horizon & Backdrop | `#0d0e1e` |
| 🧪 **Soft Mint** | Avatar, Shield Pips & Prism Orbs | `#4ef0d0` |
| 🌸 **Warm Magenta** | Obstacles & Parallax Neon Pillars | `#ff5376` |
| 🍯 **Amber Glow** | Dash Rings, Dust Motes & Multiplier | `#ffd166` |

---

## 🕹️ Controls

| Device | Action |
| :--- | :--- |
| **Mobile (Android / iOS)** | **Tap anywhere** to Jump / Mid-Air Ring Dash • **Hold** to Auto-Hop |
| **Desktop** | **`Spacebar`** / **`↑ Up Arrow`** / **Click** to Jump or Dash |

---

## 📲 Install as an App (PWA)

1. Open **[https://bigknoxy.github.io/vibehop/](https://bigknoxy.github.io/vibehop/)** on your phone or desktop browser.
2. **Android / Desktop Chrome:** Tap the glowing **📲 Install App** button at the bottom of the screen.
3. **iOS Safari:** Tap **Share `[⎋]` → Add to Home Screen** for a full-screen, status-bar-free arcade experience.

---

## 🛠️ Architecture & CI/CD

```text
vibehop/
├── index.html                        # Single-file 60/120Hz Canvas engine + Web Audio lo-fi synth
├── manifest.json                     # Standalone PWA manifest + maskable vector icon
├── sw.js                             # Stale-while-revalidate offline Service Worker
├── icon.svg                          # Crisp neon SVG emblem
├── deploy.sh                         # One-command gh CLI setup & deployment script
└── .github/workflows/deploy-pages.yml # Automated validation & GitHub Pages deployment
```

### Run Locally

```bash
git clone https://github.com/bigknoxy/vibehop.git
cd vibehop
python3 -m http.server 8080
```

Then open `http://localhost:8080` in your browser.
