# OriginOS 7 (Android 17) Theme Architecture Reference

All findings below were reverse-engineered and verified on real OriginOS 7 (Android 17) hardware (iQOO / vivo).

---

## 1. `.itz` Container Layout

An `.itz` file is a standard ZIP archive containing:
- `description.xml`: Theme metadata (`id`, `title`, `author`, `designer`, `version`, `edition`).
- `wallpaper/`: `default_wallpaper.jpg`, `default_lock_wallpaper.jpg`.
- `preview/`: Store/theme-manager preview images (`preview_launcher_0.jpg`, `preview_lockscreen_0.jpg`, etc.).
- `icons/`: App icons named `<package_name>.png` (plus activity aliases such as `com.android.dialer.TwelveKeyDialer.png`).
- `launcher/`: Un-themed icon mask/background/cover (`icon_mask.png`, `icon_bg_default.png`, `icon_cover.png`, folder backgrounds, `iconsize.xml`).
- **Nested module ZIPs (no `.zip` extension)** at root:
  - `vivo` (framework Vigour UI: Settings BG, Uninstall dialog, global toggle switches)
  - `com.android.systemui` & `com.vivo.systemuiplugin` (Control Center, Status Bar, Volume, Lockscreen)
  - `com.vivo.card` (SuperCard: payment cards & camera kits)
  - `com.android.settings` (Settings icons + cooling fan `ic_cooling_fan_image.png`)
  - `com.android.mms` (SMS bubbles + smart notification card `sms_card_view_bg.9.png`)
  - `com.android.BBKClock` (World Clock dial & hands)
  - `com.android.contacts`, `com.android.incallui`, `com.android.bbkcalculator`, `com.vivo.weather`
  - `originui` / `com.vivo.originui` / `originui.aar` (OriginUI dialog colors & fallback backgrounds)

---

## 2. Nine-Patch (`.9.png`) Rule — Zero Binary `npTc`

- OriginOS 7's theme loader reads **source `.9.png` files** (standard 32-bit RGBA PNG with a 1px transparent outer border containing pure-black `#000000` top/left stretch guides and optional bottom/right content guides).
- **Never** embed AAPT2-compiled binary `npTc` chunks in `.itz` `.9.png` files; hand-compiled `npTc` chunks cause OriginOS 7 global theme application to fail.
- Helper: `itz_engine.make_source_nine_patch(...)` (and `wrap_nine_patch(...)`).

---

## 3. SuperCard (`com.vivo.card`) — AAPT2 Obfuscated Filenames

- `SuperCard.apk` declares `android.vivo_globaltheme_supportmode = 1` (mounted by `VivoResourcesImplImpl.initPackageSupportAar()`), **but** `com.vivo.card` is NOT in `mSupportDrawableOptimSet` (only 5 packages are: `contacts`, `settings`, `originui.aar`, `originui`, `systemuiplugin`).
- Therefore, `VivoThemeZipFile` looks up the **raw AAPT2-shortened filenames** inside `com.vivo.card` (e.g., `bg_paycard14` → `CA.webp`, `t7.webp`, `wq.webp`; `bg_camera_card01` → `2W.webp`, `lm.webp`, `eM.webp`).
- All 49 card groups / 141 obfuscated filenames and their exact pixel dimensions are stored in `supercard_obf_map.json`. Always write both readable names and obfuscated names via `write_supercard_assets()`.

---

## 4. Uninstall Bottom Dialog (`BBKLauncher2`)

- `BBKLauncher2.apk`'s `VCustomRoundRectLayout` loads `vivo/vigour_dialog_full_light.9.png` (and `_os2.9.png`, `_dark.9.png`, `vigour_dialog_bottom_light.9.png`).
- Must be 0-`npTc` source `.9.png` (recommended `1034×552` inner canvas + 1px guide border).
- Pair with matching dialog text/button colors in `vivo/theme_values.xml` and `originui/theme_values.xml`.
- **Shared-resource trade-off (`VHotspotButton`)**: Some OriginUI bottom sheets (e.g., `com.originui.widget.sheet.w0$a.m()`) reuse `vivo/drawable/vigour_dialog_full_light` as the background of a small top-right dismiss/collapse button. Adding an illustration to `vigour_dialog_full_light.9.png` will also appear miniaturized inside that button—this is a framework-level resource reuse and cannot be split via `.itz` alone.

---

## 5. Global Toggle Switches (`VMoveBoolButton`)

- Settings and SuperCard toggle switches (`VMoveBoolButton`) read from the `vivo` module:
  - `vigour_bool_btn_bg_on_light.png` / `_off_light.png` (and `_dark.png`): `150×90` RGBA PNG. Visible rounded pill track occupies `x: 12..138, y: 12..78`.
  - When ON, the thumb sits on the right (`cx ≈ 105`), exposing the **left** side (`cx ≈ 45`) for a character/Q-chibi decal.
  - When OFF, the thumb sits on the left (`cx ≈ 45`), exposing the **right** side (`cx ≈ 105`).
  - `vigour_bool_btn_hand_normal_light.9.png`: `60×60` thumb (0-`npTc` source `.9.png`).
  - Make `vigour_bool_btn_handleft_*.png` and `handright_*.png` transparent so stock `|`/`O` indicators do not cover custom artwork.

---

## 6. Volume Seekbar & Dialog (`com.vivo.systemuiplugin`)

- In `SystemUIPlugin.apk`:
  - `VivoVolumeUtils.setNewWholeThemeAndColor` reads `bool/new_style` and `bool/is_color_style`.
  - Without `<bool name="new_style">true</bool>`, `VivoVolumeSeekbarProgress.getProgressColor` skips `vivo_volume_whole_theme_progress_color_*` and falls back to `color/vigour_color_track_gradient_startcolor` (stock `#007AFF` blue).
  - Expanded 4-bar track backgrounds read `vivo_volume_seekbar_bg_color_for_expand_dialog_row_blur_new` and `vivo_volume_seekbar_bg_color_for_expand_dialog_row_no_blur_new`.
- **Panel background**: OriginOS 7's side-key volume dialog has **no static background PNG drawable** — the dialog panel uses real-time frosted blur + `<color>` (`vivo_volume_dialog_color_normal_new`, `vivo_volume_dialog_color_night_mode_new`, `vivo_volume_whole_theme_sheet_bg_color_light/dark`). `vivo_footer_volume_bg.png` only affects legacy footer volume bars.

---

## 7. Control Center QS Icons (`com.vivo.systemuiplugin`)

- In `SystemUIPlugin.apk` `VivoQSIconViewImpl.updateIcon()`:
  - Tiles with `useTint() == true` (Wi-Fi, Mobile Data, Bluetooth) unconditionally execute `drawable.setTint(iconTintColor)` (`SRC_IN` solid white when ON) on static `BitmapDrawable` PNGs.
  - Only `Animatable2` (such as `AnimatedImageDrawable`) or `FontSymbolIcon` avoids getting flattened into a monochrome white silhouette.
- **Full-color test package**: Encode the `144×144` icon as a looping **animated WebP** (`RIFF....WEBP` containing `ANIM` chunk, e.g., 2 identical or subtle-animation frames) and store it inside `com.vivo.systemuiplugin` under the expected `.png` resource name (e.g., `vivo_super_qs_wifi_on.png`). The device probe decoded the WebP as `AnimatedImageDrawable` and kept its colors after `setTint(WHITE)`. Apply the test `.itz` and toggle the actual tiles to check the Control Center rendering.
- **Fallback monochrome technique**: If using static PNGs, draw pure `#FFFFFF` solid shapes (35%–50% opaque area) with **6–8px transparent negative-space cutouts** so facial details remain crisp at ~30dp.

---

## 8. Automated Replacement Pack (`主题替换包.itz`) Merge

To eliminate manual file-manager steps on the phone, `itz_engine.build_replacement_pack(theme_bytes, base_pack_path)` takes a read-only base replacement template and produces a ready-to-apply `.itz`:
1. Merges **all files** of the target theme `.itz` into `themeicon/icons.zip`.
2. Copies the target theme's `preview/` and `wallpaper/` directories into the nested base theme archive (`.dwd/.../T/*.itz`).
3. Leaves all other template entries intact.
4. **Known replacement-pack limitation (`com.bbk.launcher2`)**: When applying via the DIY / replacement-pack icon slot (`themeicon/icons.zip`), `BBKTheme.apk`'s `ApplyThemeHelper.copyDiyResFiles()` unpacks `icons.zip` and immediately calls `ApplyThemeUtils.rmFile(DATA_LAUNCHER2_ZIP_PATH)` (deleting `/data/bbkcore/theme/com.bbk.launcher2`), and `copyDiyEntrysFile(..., false, ...)` also skips `com.bbk.launcher2*`. Consequently, `com.bbk.launcher2/theme_values.xml` overrides (such as unread badge `badge_bg_color`) do not take effect through the replacement-pack path; only full-package application via `copyResInfo()` preserves `com.bbk.launcher2`.

---

## 9. Contacts Dialpad & Section Headers (`com.android.contacts`)

- Legacy `com.android.contacts/dialpad_bg.png` is not used by the OriginOS 7 dialpad surface. Real `Contacts.apk` dialpad assets are:
  - `dialer_bbk_dialpad_background.png` & `dialer_bbk_dialpad_background_stroke.png` (main keypad backdrop)
  - `dialer_bbk_dialer_bottom_bg.png`, `dialer_bbk_dialer_edittext_bg.png`
  - 12 pressed-key states: `dialer_bbk_dialer_{0..9,star,pound}_sel.png` (plus `_stroke` variants if needed)
- Contact list alphabetical group header bars load `com.android.contacts/list_section_header.9.png` (use a transparent or subtle frosted 0-`npTc` source `.9.png` to avoid solid white stripes over custom window backgrounds).
- Pair with `com.android.contacts/theme_values.xml` keys such as `dialer_call_bg` and `vivo_contacts_list_and_index_header_bg_color`.

---

## 10. Settings Preference Cards, VToolbar & About Phone Banner (`vivo` & `com.android.settings`)

- **Settings preference cards**: Opaque white card strips in Settings sub-pages (e.g., App Info, About Phone) come from 16 source `.9.png` files in `vivo`:
  - `vigour_preference_{round,top,bottom,unround}_bg_{light,selected_light,dark,selected_dark}.9.png` (must be 0-`npTc` source `.9.png`).
  - Pair with `com.android.settings/theme_values.xml` keys `preference_card_background_rom15_0` and `originui_vtoolbar_aiosbg_color_*` (for the top-left `VToolbar` circular back button backdrop).
- **About Phone OriginOS 7 top banner**: `Settings.apk` uses AAPT2-shortened filenames for the About Phone OS card:
  - `CJo.webp` (`1248×824`, main OS banner card)
  - `To8.webp` (`1440×995`, backdrop glow layer behind the card)
  - Write both `.webp` and `.png` variants into `com.android.settings` (alongside readable `rom14..17` fallback names) for reliable matching across builds.
