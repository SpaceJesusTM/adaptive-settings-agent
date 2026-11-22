# Game settings audit — VALORANT and Counter-Strike 2 (PC), as of 2026-11-20/21

This document records how the two simulated settings menus were researched, what each implemented setting is
based on, what remains uncertain, and what was deliberately left out. The per-setting table (ID, canonical path,
control, values/range, default status, verification level, primary source and date) is generated from the
catalogues: **[CATALOG_REPORT.md](CATALOG_REPORT.md)** (`python scripts/catalog_report.py`).

Research was carried out on **2026-11-21**. Every setting carries `sourceURL`, `sourceDate`, `verificationStatus`,
`lastReviewed` and a stable `canonicalPath` in `data/catalogs/*.json`; catalogue integrity is enforced by the loader
and by `backend/tests/test_catalog.py`.

## 1. Verification levels

| Level | Meaning | VALORANT | CS2 |
|---|---|---|---|
| `verified-game-files` | Label, options/range and (usually) default read from the CS2 client's own UI layout, localization and config files | – | **121** |
| `verified-official-doc` | Label and location stated in a dated Riot support article or patch note | **22** | – |
| `verified-official-screenshot` | Label, control type and options visible in a menu screenshot published by Riot | **32** | – |
| `partially-verified` | Some aspects official, others from dated secondary sources (noted per setting) | **6** | – |
| `secondary-only` | Only dated third-party sources; rendered with a † marker and never presented as official | **14** | – |

Section placement is marked separately (`pathVerification`): **19** VALORANT settings have an *inferred* section
(see §3.2). Slider ranges that are not documented are flagged `rangeVerified: false`, shown with a ≈ marker, and are
never AI-proposable. Defaults are only stated when verified (CS2: 93 verified from the registered convar defaults;
VALORANT: 5 verified, 2 reported by secondary sources, the rest *unknown*). `sampleInitialValue` is synthetic demo
data and is never presented as a factory default.

## 2. Counter-Strike 2

### 2.1 Sources

| Key | Source | Date | Kind |
|---|---|---|---|
| `cs2-layout` | CS2 settings UI layouts `panorama/layout/settings/*.xml` (build 2000948), via [SteamDatabase GameTracking-CS2 @ 694f81f](https://github.com/SteamDatabase/GameTracking-CS2/tree/694f81f05cfcd1994ea9ef6baa31d4583dc1d63b/game/csgo/pak01_dir/panorama/layout/settings) | 2026-11-20 | game files |
| `cs2-loc` | English localization `resource/csgo_english.txt` (same commit) | 2026-11-20 | game files |
| `cs2-convars` | Registered console variables and defaults `DumpSource2/convars.txt` (same commit) | 2026-11-20 | game files |
| `cs2-video-presets` | Video presets `cfg/video_defaults_0..3.txt` (same commit) | 2026-11-20 | game files |
| `cs2-keys-default` | Default key bindings `cfg/user_keys_default.vcfg` (same commit) | 2026-11-20 | game files |
| `cs2-update-2026-09-22` | Valve CS2 update: new **Crosshair/Scopes** tab, new styles, default crosshair “Dynamic Quad” | 2026-09-22 | official notes |
| `cs2-update-2026-09-23` | Valve CS2 update: crosshair thickness/length/gap in **pixels**, half outlines, static square style, Dynamic Spread Limit | 2026-09-23 | official notes |
| `cs2-update-2026-10-28` | Valve CS2 update: **Silent Reload Mode** (Hold/Toggle) | 2026-10-28 | official notes |

All 300 CS2 announcements from 2025-01 to 2026-11-19 were retrieved from the public Steam News API (app 730) and
scanned for settings changes. The Valve news links given in the specification
(counter-strike.net newsentry 674006995886407685 / …408819) correspond to the 22 and 23 September 2026 updates whose
text is cited above. The Steam Support page *CS2 – Video Settings Recommendations*
(help.steampowered.com/en/faqs/view/418E-7A04-B0DA-9032) renders its body client-side; its content could not be
retrieved, so nothing in the catalogue depends on it.

### 2.2 Menu structure (from `settings.xml` and the per-tab layouts)

* Top navigation: **search icon**, **New** (promoted settings), **Video**, **Audio**, **Game**, **Keyboard / Mouse**,
  **Crosshair / Scopes** (tab added 2026-09-22).
* Video: page sub-tabs **Video**, **Advanced Video**, and a **HUD Edge Positions** button. Advanced Video is a
  split view (live preview left, settings right) with sections **Advanced Video**, **Frame Pacing**, **Presets**.
  Video changes are applied with **Apply Changes** / **Discard Changes** (action bar) — simulated faithfully as an
  explicit-apply page.
* Audio, Game, Keyboard / Mouse: one scrolling page with anchor sub-tabs (Audio / Voice / Music / Game Mode EQ;
  Game / Hud / Team / Communication / Spectator / Scoreboard / Item / Radar / Damage Prediction / Telemetry;
  Keyboard & Mouse Settings / Movement Keys / Weapon Keys / UI Keys / Communication Options / Chat Wheel Keys).
* Crosshair / Scopes: crosshair preview, then **Style Settings**, **Crosshair Settings**, **Grenade Line-up**,
  **Sniper Sights**.
* No separate *Raw Input* option exists in CS2 and none is simulated (a CS:GO-era setting).

### 2.3 Verified 2026 details worth noting

* Default crosshair style is **Dynamic Quadrant** (`cl_crosshairstyle` default 7), matching Valve’s note.
* The current style list has 10 entries (Static Cross, Static Circle, Static Square, Dot Only, Static Quadrant,
  Dynamic Cross, Dynamic Circle, Dynamic Cross (Classic), Dynamic Cross (Legacy/Shot Feedback), Dynamic Quadrant).
* Thickness 0–32 px, Length 0–255 px, Gap 0–128 px (−10–128 for the classic dynamic style), Dynamic Spread Limit 0–255.
* Advanced Video “V-Sync” (label is *V-Sync*, not “Wait for Vertical Sync”), NVIDIA G-Sync, NVIDIA Reflex Low Latency
  (Disabled / Enabled / Enabled + Boost), Maximum FPS In Game (64–1000), and the four video presets (Low/Medium/High/
  Very High) whose exact member values come from `video_defaults_*.txt`; the preset row shows *Custom* otherwise.
* Silent Reload Mode (Hold/Toggle, 2026-10-28), per-game-mode music volumes (2026-09-22), Main Menu Ambience Volume
  (2025-05-07), Glow Weapon with Rarity Color (2025-05-13), radar dynamic zoom (2025-01-28).

### 2.4 Conflicts and how they were handled

| Item | Conflict | Handling |
|---|---|---|
| Perspective Correction default | Tooltip says “Yes (default)”; convar `snd_steamaudio_enable_perspective_correction` registers `false` | Default marked **conflicting** |
| Maximum FPS In Game | Convar default 120, `0` = no limit, but the slider range is 64–1000 | Default 120 recorded with the note; unlimited not simulated |
| MSAA mode | Labels verified (None, 2x/4x/8x MSAA, CMAA2); the client fills the option **order** at runtime | Order marked unverified |
| Max Acceptable Game Traffic Bandwidth | Registered default (80000) is not one of the 8 menu options | Default **unknown** |
| Boost Player Contrast | Likely backed by `r_player_visibility_mode` (default 1) but the layout does not name the convar | Default **inferred** |

### 2.5 Not simulated (and why)

New tab (dynamic contents unpublished) · HUD Edge Positions (on-screen tool) · Brightness (inverted gamma-to-percent
mapping not verified) · Display selector, Resolution/Refresh/Audio device lists (runtime lists; *simulated* option
lists are used and labelled) · Maximum FPS In Menus (0 = unlimited cannot be represented) · crosshair colour pickers ·
music volumes for modes other than Competitive · Microphone Trigger Threshold (unit unclear) · controller/Steam Input ·
chat-wheel phrases · most keybinds (18 representative ones are simulated).

## 3. VALORANT

### 3.1 Sources

| Key | Source | Date | Used for |
|---|---|---|---|
| `riot-gfx-2026-10` | [Optimize Graphics Settings for Better FPS – Windows & Mac](https://support.riotgames.com/en-us/riot/performance/optimize-graphics-settings-for-better-fps-windows-and-mac) | 2026-10-07 | Video > Graphics Quality labels and performance guidance; Video > General *Fullscreen*; VSync trade-off |
| `riot-crash-2026-05` | [Troubleshooting Game Crashes](https://support.riotgames.com/en-us/valorant/support-tools/troubleshooting-game-crashes-in-valorant) | 2026-05-24 | Full Graphics Quality list incl. Multithreaded Rendering, Vignette, Anisotropic Filtering 1x; *Limit FPS Always* |
| `riot-ui-faq-2026-01` | [VALORANT UI Settings FAQ](https://support.riotgames.com/en-us/valorant/gameplay/valorant-ui-settings-faq) — text **and embedded menu screenshots** | 2026-01-12 | General > Map, General > Other rows, Controls > Interface keybinds, control types, layout |
| `riot-voice-2026-05` | [VALORANT Voice Chat Troubleshooting](https://support.riotgames.com/en-us/valorant/gameplay/valorant-voice-chat-troubleshooting) — text and Audio > Voice Chat screenshot | 2026-05-25 | All Voice Chat rows, PTT defaults |
| `riot-mtr-2024-04`, `riot-vsync-2024-01` | Riot articles on Multithreaded Rendering and VSync (Graphics Quality screenshot) | 2024 | Segment style (High/Med/Low), min specs |
| `val-patch-11-06` … `val-patch-13-10` | Official patch notes **11.00–13.10** (all fetched and scanned) | 2025-06 → 2026-11-10 | See §3.2 |
| `turbosmurfs-2026-09`, `neuralboost-2026-11`, `dotesports-ehc` | Dated third-party guides | 2026 | Secondary corroboration only |

### 3.2 2026 menu changes that matter

* **Patch 12.07 (2026-04-14, PC):** settings screens revamped — parent-child association, hover tooltips, visual
  refresh, and *“Settings previously under General – Other are broken into 3 sections: User Interface, Content
  Filtering, Network”*. Riot did **not** publish which setting moved to which section, and the January 2026 FAQ still
  uses the old *General > Other* paths. The 17 former *Other* settings are therefore placed by topic and marked
  **inferred** (ⓘ marker in the menu).
* **Patch 12.09 (2026-05-12):** AMD Anti-Lag 2 support (compatible hardware + drivers from 2026-03-09). Riot gave no
  label or location; the label/placement (bottom of Graphics Quality) come from a third-party guide → partially
  verified, and it is *unavailable* on the default simulated NVIDIA PC (available in the `amd_pc` scenario).
* **Patch 13.10 (2026-11-10):** new **Replay Bookmarking** keybind at *Settings → Controls → Interface*, blank by default.
* **Patch 11.06 (2025-09-16):** the *RawInputBuffer* setting was **removed** — Riot’s FAQ screenshots still show
  “[Beta] RawInputBuffer” and a Sept-2026 third-party guide still mentions it; it is not simulated.
* **Patch 11.04 (2025-08-19):** move to Unreal Engine 5 reset resolution/display settings once; no new graphics
  options were announced.

### 3.3 Conflicts and how they were handled

| Item | Conflict | Handling |
|---|---|---|
| Improve Clarity | Oct 2026 guide: *Improve Clarity*; May 2026 crash guide: *Improve Quality* | Newest official label used, conflict noted |
| Cast Shadows | Oct 2026 guide: *Cast Shadows*; May 2026 crash guide: *First Person Shadows* | Newest official label used, conflict noted |
| Anti-Aliasing | Riot writes “Anti Aliasing: Off”; secondary guide lists None / MSAA 2x / MSAA 4x | Only those three options simulated (FXAA unconfirmed, omitted) |
| NVIDIA Reflex Low Latency | Riot has not published option names or location | Off / On / On + Boost under Video > General, **secondary-only, inferred location** |
| Former *General > Other* rows | Pre-12.07 paths only | Section placement **inferred** (see §3.2) |
| Slider scales (Minimap Size/Zoom, voice volumes) | Riot screenshots show labels but not ranges | Prototype bounds, `rangeVerified=false`, never AI-proposable |

### 3.4 Not simulated (and why)

**Crosshair tab** (no current Riot source documents the crosshair editor’s exact labels/ranges after the 2026
updates — shown as a labelled “not simulated” page rather than invented) · Video > Stats · Audio > Voice-Over ·
Controls > Actions / Equipment / Communication (keybind labels unconfirmed) · numeric “Max FPS …” fields under the
Limit FPS toggles · Speaker Configuration (option list unknown) · in-match *Match* tab.

## 4. Visual fidelity

* **VALORANT** layout follows Riot’s own screenshots (UI FAQ, Multithreaded Rendering and Voice Chat articles):
  centred uppercase tab bar on a hairline rule with diamond markers, pale-yellow active tab, centred sub-tabs,
  uppercase section headings, banded translucent rows (~52 px), equal-width On/Off and High/Med/Low segments,
  value-then-track sliders, dropdown with right caret, Primary/Alternate key columns, dimmed dependent rows
  (e.g. *Fixed Orientation* until *Rotate = Fixed*).
* **CS2** layout follows the panorama layout files: top navigation with search icon and *New*, dark sub-navigation,
  50/50 Advanced Video split with a preview panel, section panels with title labels and row separators,
  half-width labels with dropdown (“PopupButton”) controls, slider + value box, and the Reset defaults / Discard Changes
  / Apply Changes action bar.
* **Deliberate differences:** fonts are open-licence substitutes (Barlow / Barlow Semi Condensed for VALORANT, Saira
  Semi Condensed for CS2) bundled locally; no logos, art, icons or textures from either game; backgrounds and the
  central ornament are original CSS/SVG; CS2’s live preview panel is a static illustration; tooltips use the
  catalogue description; a neutral research bar sits above the game surface, and the adaptive layer uses its own
  visual language so it is never mistaken for part of the game menu. Post-12.07 VALORANT visual refresh details were
  not available in any retrievable source; the pre-12.07 official screenshots were used as the visual reference.
* The local screenshot script generates comparison images at 1440×900. Run `npm --prefix frontend run screenshots` to reproduce the images with the offline fallback.

## 5. Keeping the catalogues current

1. CS2: pull the latest GameTracking-CS2 commit, re-run the extraction (layouts, localization, `convars.txt`,
   `video_defaults_*.txt`, `user_keys_default.vcfg`) and diff labels/options/defaults; update `catalogVersion`.
2. VALORANT: scan new patch notes for *Settings*, *PC only* and *Quality of life* sections; prefer Riot support
   articles with screenshots for labels and paths.
3. Re-run `pytest` (catalogue tests) and `python scripts/catalog_report.py`.
