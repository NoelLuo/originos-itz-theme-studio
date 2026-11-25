---
name: originos-itz-theme
description: >-
  Build, debug, validate, and deploy vivo / iQOO OriginOS 6 and OriginOS 7 (.itz)
  system themes using OriginOS .itz Theme Studio, including SuperCard AAPT2
  obfuscated assets, 0-npTc nine-patch dialogs/SMS cards, VMoveBoolButton switches,
  Volume seekbar theming, full-color animated-WebP Control Center QS icons, and
  automated replacement-pack packaging + ADB push. Use when creating, editing,
  auditing, or troubleshooting OriginOS .itz themes or maintaining this repository.
---

# OriginOS 7 `.itz` Theme Engineering Skill

End-to-end runbook for authoring, auditing, packaging, and testing vivo / iQOO OriginOS 6 & 7 (Android 17) `.itz` themes with this repository.

## Core Iron Rules (Verified on Real OriginOS 7 Hardware)

1. **Zero binary `npTc` in `.9.png`**: All nine-patch assets (`vigour_dialog_full_light.9.png`, `sms_card_view_bg.9.png`, `vigour_bool_btn_hand_normal_light.9.png`, chat bubbles) MUST be **1px transparent outer border + 1px pure-black (`#000000`) stretch/content guide source `.9.png`** (`0` binary `npTc` chunks). Hand-compiled binary `npTc` causes OriginOS 7 global theme application to fail silently.
2. **Never bundle `fonts/` inside the main theme `.itz`**: Keep `fonts/` out of the main theme archive unless the user explicitly asks for an embedded font; export fonts separately via `ThemeProject.export_font_itz()`.
3. **SuperCard (`com.vivo.card`) requires AAPT2 obfuscated filenames**: `SuperCard.apk` is NOT in OriginOS's `mSupportDrawableOptimSet`, so readable names alone are ignored. Always write both readable names and all 141 AAPT2-shortened names via `write_supercard_assets()` / `supercard_obf_map.json`.
4. **Volume 4-bar expanded seekbars require `<bool name="new_style">true</bool>`**: Setting `vivo_volume_whole_theme_progress_color_*` alone falls back to stock `#007AFF` blue. Always write `<bool name="new_style">true</bool>`, `<bool name="is_color_style">true</bool>`, `vigour_color_track_gradient_startcolor`, and `vivo_volume_seekbar_bg_color_for_expand_dialog_row_*_new` via `ThemeProject.set_systemui_colors()`. Note: OriginOS 7's side-key volume dialog uses hardware frosted blur + `<color>` (not a static PNG background).
5. **Control Center Wi-Fi / Data / Bluetooth tint bypass**: `VivoQSIconViewImpl.updateIcon()` unconditionally calls `drawable.setTint(WHITE)` (`SRC_IN`) on static PNG `BitmapDrawable`s. Either:
   - Ship an **animated WebP (`RIFF....WEBP` with `ANIM` chunk)** stored under the `.png` filename (decoded by Android as `AnimatedImageDrawable` implementing `Animatable2`, preserving **full color** after `setTint`), OR
   - Use **pure white solid-fill + thick 6–8px transparent negative-space cutout** monochrome PNGs.
6. **Clean single replacement pack on phone**: When pushing an automated replacement pack via ADB, delete old `*.itz` files in the target phone folder first so only one `主题替换包.itz` exists and the user never picks a stale archive.
7. **Keep GitHub clean**: Never commit `.itz`, `.apk`, `.zip`, copyrighted artwork, or personal build scripts.

## Workflow

### 1. Choose Entry Point
- **Visual editing / showcase / quick edits**: Launch Web Studio (`python server.py` or `start.bat` at `http://127.0.0.1:18765/`) and load a `.itz` via UI or `POST /api/load-path`.
- **Repeatable batch builds**: Import `ThemeProject` and helpers from `itz_engine.py` (`build_replacement_pack`, `write_supercard_assets`, `make_source_nine_patch`, `set_systemui_colors`, `write_volume_glyphs`).

### 2. Produce & Integrate Assets
- Read [references/asset-specs.md](./references/asset-specs.md) for exact pixel sizes, safe margins, and art guidelines before commissioning or generating artwork.
- Read [references/originos7-architecture.md](./references/originos7-architecture.md) when debugging why a specific OriginOS 7 module (SuperCard, SystemUIPlugin, BBKLauncher2, VMoveBoolButton, MMS, BBKClock, Lockscreen) ignores a resource.

### 3. Validate Before Pushing
Always run the bundled validator on both the source `.itz` and the merged replacement pack:

```bash
python .agents/skills/originos-itz-theme/scripts/verify_itz.py path/to/theme.itz
python .agents/skills/originos-itz-theme/scripts/verify_itz.py path/to/replacement_pack.itz --replacement-pack
```

Confirm:
- `binary_npTc_count == 0`
- `font_files == 0` (unless intentionally building a standalone font pack)
- `supercard_obf_files > 0` (141 for full card suite)
- `volume_new_style == True` and `volume_track_gradient == True`
- Replacement pack contains both `themeicon/icons.zip` and updated `preview/` + `wallpaper/` inside `.dwd/.../T/*.itz`.

### 4. Automated Replacement Pack & ADB Push
- Use `build_replacement_pack(theme_bytes, base_pack_path)` (or Web Studio's `📦 导出替换包` / `📲 直推替换包到手机`) so the user never has to perform manual 7-step MT Manager archive merges.
- Treat the user's base replacement template as **read-only**.
- Before `adb push`, remove stale `*.itz` in the phone's destination folder and verify with `adb shell ls -lh`.

### 5. Maintaining This GitHub Repository
Before committing changes to `originos-itz-theme-studio`:
1. Run `git status` and verify no copyrighted art, `.itz`, `.apk`, `.zip`, or personal scripts are tracked.
2. Check frontend JS syntax (`node --check` on extracted `<script>` from `static/index.html`) and run a round-trip smoke test on `itz_engine.py` (`export_bytes` + `verify_itz.py`).
3. Verify `server.py` `/api/asset` returns `image/webp` when magic bytes match `RIFF....WEBP` (for full-color animated-WebP QS previews).
4. Commit and push cleanly to `main`.
