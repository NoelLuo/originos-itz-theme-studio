# OriginOS 7 Theme Asset Production Specifications

Quick-reference dimension and format table for designers and AI image-generation workflows.

| Module / Slot | Target Path in `.itz` | Resolution & Format | Key Production Rules |
| :--- | :--- | :--- | :--- |
| **Home Wallpaper** | `wallpaper/default_wallpaper.jpg` | `1440×3200` (or `1080×2400`) JPG, high quality (`subsampling=0`) | Vertical composition; keep top clock/status area clean |
| **Lockscreen Wallpaper** | `wallpaper/default_lock_wallpaper.jpg` | `1440×3200` JPG | Leave upper-middle breathing room for lockscreen clock |
| **Store / Manager Previews** | `preview/preview_launcher_0.jpg`, `preview_lockscreen_0.jpg`, etc. | `720×1600` JPG | Synced into both source `.itz` and replacement pack `T/*.itz` |
| **Settings Light / Dark BG** | `vivo/vigour_window_bg_light.png`, `vigour_window_settting_background_light.png` (+ `_dark`) | `1080×2400` RGBA PNG | Add soft light veil (`alpha ~110–125`) for light mode and dark veil for dark mode so list text stays legible |
| **Desktop App Icons** | `icons/<package>.png` | `192×192` RGBA PNG | Rounded-square safe margin; include Dialer aliases (`com.android.dialer.png`, `com.android.dialer.TwelveKeyDialer.png`, `com.android.dialer.BBKTwelveKeyDialer.png`, `com.android.contacts.TwelveKeyDialer.png`) |
| **Unthemed Icon Frame** | `launcher/icon_mask.png`, `icon_bg_default.png`, `icon_cover.png` | `168×168` / `192×192` RGBA PNG | Keep mask center opaque and corners smoothly antialiased |
| **Settings Cooling Fan** | `com.android.settings/ic_cooling_fan_image.png` (+ `set_fan_light_layer0.png`) | `144×144` RGBA PNG | Transparent background, centered fan blade art |
| **Uninstall Bottom Dialog** | `vivo/vigour_dialog_full_light.9.png` (+ `_os2`, `_dark`) | `1034×552` (+1px border = `1036×554`) source `.9.png` (**0 `npTc`**) | Place character decorations near top/bottom corners away from the stretch ticks; keep central text area bright/legible |
| **SMS Smart Notification Card** | `com.android.mms/sms_card_view_bg.9.png` (+ `_pressed.9.png`) | ~`372×424` source `.9.png` (**0 `npTc`**) | Put stretch marks only on flat middle bands so corner illustrations never warp |
| **Global Toggle Switches** | `vivo/vigour_bool_btn_bg_on_light.png`, `_off_light.png` | `150×90` RGBA PNG (draw at 2× `300×180` and downsample) | Pill bbox `x:12..138, y:12..78`; place ON chibi at `cx=45`, OFF chibi at `cx=105`; transparent `handleft`/`handright` |
| **Control Center QS Icons (Full Color)** | `com.vivo.systemuiplugin/vivo_super_qs_{wifi,data_switch,bluetooth}_on.png` (+ `on2..on4`, `run_on*`) | `144×144` **Animated WebP** (`ANIM` chunk) saved with `.png` filename | Center within `116×116` safe area; use static clean PNG for `_off` states |
| **Control Center QS Icons (Monochrome Fallback)** | Same as above | `144×144` RGBA PNG | Pure `#FFFFFF` solid shapes (35%–50% opaque) + 6–8px transparent negative-space cutouts; avoid thin 2px line art |
| **Volume Icons** | `com.vivo.systemuiplugin/vivo_volume_ic_audio_*_new.png` (+ `_dark`) | `84×84` RGBA PNG | Crisp single-color rounded glyphs on transparent background |
| **SuperCard (Payment & Camera Kits)** | `com.vivo.card/<readable>` + 141 AAPT2 obfuscated `.webp`/`.png` via `supercard_obf_map.json` | Master vertical art `1152×1864` (auto-scaled to `864×1398`, `576×932`, and small thumbs) | Leave bottom ~28% clean/uncluttered for WeChat/Alipay QR buttons or camera controls |
| **World Clock Dial & Hands** | `com.android.BBKClock/clock_plate_bg_circle.png`, `clock_plate_day_6_0.png`, `clock_hand_*` | Dial `600×600` circular RGBA PNG; Hands `60×600` RGBA PNG | Use a distinct illustration from Settings BG; keep contrast high enough for hour/minute hands |
| **Lockscreen Native UI** | `com.android.systemui` + `com.vivo.systemuiplugin` | PIN key `240×240`, PIN dots `44×44`, Shortcut badge `200×200`, Charge icon `80×80` | Soft frosted fill with high contrast against lockscreen wallpaper |
