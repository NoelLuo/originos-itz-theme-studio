---
name: originos-itz-theme
description: >-
  Build, debug, validate, and deploy vivo / iQOO OriginOS 6 and OriginOS 7 (.itz)
  system themes using OriginOS .itz Theme Studio, including SuperCard AAPT2
  obfuscated assets, 0-npTc nine-patch dialogs/SMS cards, VMoveBoolButton switches,
  Volume seekbar theming, full-color animated-WebP Control Center QS icons, and
  replacement-pack packaging and hardware verification. Use for .itz assembly,
  cross-module troubleshooting, validation, and local theme handoff.
---

# OriginOS 7 `.itz` Theme Engineering Skill

End-to-end runbook for authoring, auditing, packaging, and testing vivo / iQOO OriginOS 6 & 7 (Android 17) `.itz` themes with this repository.

## OriginOS 7 compatibility

1. **Zero binary `npTc` in `.9.png`**: All nine-patch assets (`vigour_dialog_full_light.9.png`, `sms_card_view_bg.9.png`, `vigour_bool_btn_hand_normal_light.9.png`, chat bubbles) MUST be **1px transparent outer border + 1px pure-black (`#000000`) stretch/content guide source `.9.png`** (`0` binary `npTc` chunks). Hand-compiled binary `npTc` causes OriginOS 7 global theme application to fail silently.
2. **Never bundle `fonts/` inside the main theme `.itz`**: Keep `fonts/` out of the main theme archive unless the user explicitly asks for an embedded font; export fonts separately via `ThemeProject.export_font_itz()`.
3. **SuperCard (`com.vivo.card`) requires AAPT2 obfuscated filenames**: `SuperCard.apk` is NOT in OriginOS's `mSupportDrawableOptimSet`, so readable names alone are ignored. Always write both readable names and all 141 AAPT2-shortened names via `write_supercard_assets()` / `supercard_obf_map.json`.
4. **Volume 4-bar expanded seekbars require `<bool name="new_style">true</bool>`**: Setting `vivo_volume_whole_theme_progress_color_*` alone falls back to stock `#007AFF` blue. Always write `<bool name="new_style">true</bool>`, `<bool name="is_color_style">true</bool>`, `vigour_color_track_gradient_startcolor`, and `vivo_volume_seekbar_bg_color_for_expand_dialog_row_*_new` via `ThemeProject.set_systemui_colors()`. Note: OriginOS 7's side-key volume dialog uses hardware frosted blur + `<color>` (not a static PNG background).
5. **Control Center Wi-Fi / Data / Bluetooth tint**: `VivoQSIconViewImpl.updateIcon()` unconditionally calls `drawable.setTint(WHITE)` (`SRC_IN`) on static PNG `BitmapDrawable`s. Either:
   - Ship an **animated WebP (`RIFF....WEBP` with `ANIM` chunk)** stored under the `.png` filename (decoded on the test device as `AnimatedImageDrawable` and retained color in the tint probe). Verify the actual Control Center rendering after applying the pack.
   - Use **pure white solid-fill + thick 6–8px transparent negative-space cutout** monochrome PNGs.
6. **Device test packs**: Use a distinct versioned filename for a test pack. Push to the requested location and record whether the archive was transferred, applied, and visually checked.
7. **Keep GitHub clean**: Never commit `.itz`, `.apk`, `.zip`, copyrighted artwork, or personal build scripts.

## Workflow

### 1. Choose Entry Point

Check the selected source `.itz`, the read-only replacement template, and the current local handoff if available. Use the active build script to confirm which assets and variants it consumes. Record the selected source and replacement versions and whether each affected component has been applied on the target device.
- **Visual editing / showcase / quick edits**: Launch Web Studio (`python server.py` or `start.bat` at `http://127.0.0.1:18765/`) and load a `.itz` via UI or `POST /api/load-path`.
- **Repeatable batch builds**: Import `ThemeProject` and helpers from `itz_engine.py` (`build_replacement_pack`, `write_supercard_assets`, `make_source_nine_patch`, `set_systemui_colors`, `write_volume_glyphs`).

### 2. Produce & Integrate Assets
Use the shared [asset specifications](references/asset-specs.md) and [OriginOS 7 architecture notes](references/originos7-architecture.md) for packaging and compatibility. For component-specific art and verification, use the corresponding skill.

- [Launcher icons](../originos-launcher-icons/SKILL.md) covers brand shapes, package mappings, and preview.
- [SMS cards and uninstall dialogs](../originos-theme-nine-patch/SKILL.md) covers character placement and stretch guides.
- [Settings switches](../originos-settings-switches/SKILL.md) covers the paired chibi portraits and track resources.
- [Control Center and volume icons](../originos-system-ui-icons/SKILL.md) covers animated WebP verification and volume glyph contrast.

### 3. Validate Before Pushing
Run the bundled validator on the source `.itz` and its merged replacement pack when building both.

```bash
python .agents/skills/originos-itz-theme/scripts/verify_itz.py path/to/theme.itz
python .agents/skills/originos-itz-theme/scripts/verify_itz.py path/to/replacement_pack.itz --replacement-pack
```

Confirm the results relevant to the package being built.
- `binary_npTc_count == 0`
- `font_files == 0` (unless intentionally building a standalone font pack)
- `supercard_obf_files > 0` (141 for full card suite)
- `volume_new_style == True` and `volume_track_gradient == True`
- Replacement pack contains both `themeicon/icons.zip` and updated `preview/` + `wallpaper/` inside `.dwd/.../T/*.itz`.

### 4. Automated Replacement Pack & ADB Push
- Use `build_replacement_pack(theme_bytes, base_pack_path)` (or Web Studio's `📦 导出替换包` / `📲 直推替换包到手机`) so the user never has to perform manual 7-step MT Manager archive merges.
- Treat the user's base replacement template as **read-only**.
- Verify the pushed filename and size in the requested folder. Preserve existing device packages unless their removal is part of the request.

### 5. Maintaining This GitHub Repository
Before publishing, inspect the Git diff for theme archives, private build scripts and artwork. For code changes, run the checks relevant to the affected path, such as a package round trip for export changes or an `/api/asset` MIME check for animated WebP preview changes.
