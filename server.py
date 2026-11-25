"""Local Web GUI server for OriginOS / vivo .itz Theme Studio."""

from __future__ import annotations

import base64
import json
import mimetypes
import subprocess
import tempfile
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from apk_icon_extractor import extract_phone_icons_zip
from itz_engine import (
    APP_NAME_MAP,
    LAUNCHER_ICON_LABELS,
    SETTINGS_ICON_LABELS,
    SUPERCARD_CAMERA_SLOTS,
    SUPERCARD_PAY_SLOTS,
    SYSTEMUI_ICON_LABELS,
    ThemeProject,
    build_replacement_pack,
    find_adb,
    find_base_replacement_pack,
    generate_launcher_kit,
    make_card_crop,
    make_circle_avatar,
    make_clean_dialog_9patch,
    make_clean_mms_card_9patch,
    make_lockscreen_charge_icon,
    make_lockscreen_pin_dot,
    make_lockscreen_pin_key_bg,
    make_lockscreen_quick_bg,
    make_lockscreen_unlock_indicator,
    make_nine_patch_bubble,
    make_qs_glyph_icon,
    make_switch_thumb_9patch,
    make_switch_track_png,
    make_volume_glyph_icon,
    process_icon_image,
    wrap_nine_patch,
    write_supercard_assets,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

PROJECT = ThemeProject()
UPLOADED_BASE_REPL_BYTES: bytes | None = None


def _auto_load_sample() -> None:
    """Start with a fresh solid-color OriginOS 7 theme project by default."""
    PROJECT.new_blank(title="我的 OriginOS 7 主题", author="Designer", sysromver="17.0")


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "OriginOSThemeStudio/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            from urllib.parse import quote

            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{quote(filename)}",
            )
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            index_file = STATIC_DIR / "index.html"
            if not index_file.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "index.html not found")
                return
            self._send_bytes(index_file.read_bytes(), "text/html; charset=utf-8")
            return

        if path == "/api/summary":
            self._send_json(PROJECT.get_summary())
            return

        if path == "/api/icons":
            q = qs.get("q", [""])[0].strip().lower()
            filter_mode = qs.get("filter", ["all"])[0]
            page = max(1, int(qs.get("page", ["1"])[0]))
            size = min(200, max(1, int(qs.get("size", ["60"])[0])))

            existing_set = set(PROJECT.list_icons())
            all_names = list(existing_set)
            for pkg in APP_NAME_MAP:
                fname = f"{pkg}.png"
                if fname not in existing_set:
                    all_names.append(fname)

            all_icons = []
            for n in sorted(all_names):
                pkg = n[:-4] if n.lower().endswith(".png") else n
                custom = n in existing_set
                if filter_mode == "custom" and not custom:
                    continue
                if filter_mode == "default" and custom:
                    continue
                all_icons.append(
                    {
                        "name": n,
                        "label": APP_NAME_MAP.get(pkg, ""),
                        "customized": custom,
                    }
                )

            # Put customized icons first when showing all
            all_icons.sort(key=lambda x: (not x["customized"], x["name"]))
            if q:
                all_icons = [
                    it for it in all_icons if q in it["name"].lower() or q in it["label"].lower()
                ]
            total = len(all_icons)
            start = (page - 1) * size
            items = all_icons[start : start + size]
            self._send_json(
                {
                    "total": total,
                    "custom_total": len(existing_set),
                    "page": page,
                    "size": size,
                    "items": items,
                }
            )
            return

        if path == "/api/launcher-icons":
            existing_set = set(PROJECT.list_launcher_icons())
            all_names = sorted(existing_set | set(LAUNCHER_ICON_LABELS.keys()))
            items = [
                {
                    "name": n,
                    "label": LAUNCHER_ICON_LABELS.get(n, n.split("/")[-1]),
                    "customized": n in existing_set,
                }
                for n in all_names
            ]
            items.sort(key=lambda x: (not x["customized"], x["name"]))
            self._send_json(
                {
                    "items": items,
                    "custom_total": len(existing_set),
                    "config": PROJECT.get_launcher_config(),
                }
            )
            return

        if path == "/api/settings-icons":
            existing_set = set(PROJECT.list_settings_icons())
            all_names = sorted(existing_set | set(SETTINGS_ICON_LABELS.keys()))
            items = [
                {
                    "name": n,
                    "label": SETTINGS_ICON_LABELS.get(n, ""),
                    "customized": n in existing_set,
                }
                for n in all_names
            ]
            items.sort(key=lambda x: (not x["customized"], x["name"]))
            self._send_json({"items": items, "custom_total": len(existing_set)})
            return

        if path == "/api/module-detail":
            mod_name = qs.get("name", ["vivo"])[0].strip()
            self._send_json(PROJECT.get_module_detail(mod_name))
            return

        if path == "/api/systemui-icons":
            q = qs.get("q", [""])[0].strip().lower()
            existing_set = set(PROJECT.list_systemui_icons())
            all_names = sorted(existing_set | set(SYSTEMUI_ICON_LABELS.keys()))
            items = []
            for n in all_names:
                label = SYSTEMUI_ICON_LABELS.get(n, "")
                if not label:
                    if "meditation" in n:
                        label = "冥想模式"
                    elif "personal" in n:
                        label = "个人 / 请勿打扰"
                    elif "read" in n:
                        label = "阅读模式"
                    elif "sleep" in n:
                        label = "睡眠模式"
                    elif "work" in n:
                        label = "工作模式"
                    elif "sport" in n:
                        label = "运动模式"
                    elif "zen" in n:
                        label = "专注模式"
                custom = n in existing_set
                if q and q not in n.lower() and q not in label.lower():
                    continue
                items.append({"name": n, "label": label, "customized": custom})
            items.sort(key=lambda x: (not x["customized"], x["name"]))
            self._send_json(
                {
                    "items": items,
                    "custom_total": len(existing_set),
                    "colors": PROJECT.get_systemui_colors(),
                }
            )
            return

        if path == "/api/asset":
            scope = qs.get("scope", ["root"])[0]
            name = qs.get("name", [""])[0]
            data: bytes | None = None
            if scope == "root":
                data = PROJECT.entries.get(name)
            elif scope == "icons":
                data = PROJECT.entries.get(f"icons/{name}")
            elif scope in PROJECT.modules:
                data = PROJECT.modules[scope].get(name)

            if data is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Asset not found")
                return
            ctype, _ = mimetypes.guess_type(name)
            self._send_bytes(data, ctype or "application/octet-stream")
            return

        if path == "/api/export-checklist":
            import csv
            import io

            ctype = qs.get("type", ["icons"])[0]
            buf = io.StringIO()
            writer = csv.writer(buf)

            if ctype == "icons":
                writer.writerow(["程序名称", "包名", "目标文件名", "来源", "当前状态", "建议尺寸"])
                existing_set = set(PROJECT.list_icons())
                phone_pkgs: set[str] = set()
                adb = find_adb()
                if adb:
                    try:
                        res = subprocess.run(
                            [
                                adb,
                                "shell",
                                "cmd",
                                "package",
                                "query-activities",
                                "-a",
                                "android.intent.action.MAIN",
                                "-c",
                                "android.intent.category.LAUNCHER",
                                "--brief",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=6,
                        )
                        phone_pkgs = {
                            line.split("/")[0].strip()
                            for line in res.stdout.splitlines()
                            if "/" in line and line.split("/")[0].strip()
                        }
                    except Exception:
                        pass

                all_pkgs = sorted(
                    {n[:-4] for n in existing_set if n.lower().endswith(".png")}
                    | set(APP_NAME_MAP.keys())
                    | phone_pkgs
                )
                rows = []
                for pkg in all_pkgs:
                    fname = f"{pkg}.png"
                    drawn = fname in existing_set
                    sources = []
                    if pkg in phone_pkgs:
                        sources.append("手机已安装")
                    if pkg in APP_NAME_MAP:
                        sources.append("默认模板")
                    if drawn and not sources:
                        sources.append("主题已有")
                    rows.append(
                        (
                            not (pkg in phone_pkgs),
                            drawn,
                            [
                                APP_NAME_MAP.get(pkg, ""),
                                pkg,
                                f"icons/{fname}",
                                " / ".join(sources),
                                "已绘制" if drawn else "未绘制",
                                "192x192",
                            ],
                        )
                    )
                rows.sort(key=lambda r: (r[0], r[1], r[2][1]))
                for _, _, row in rows:
                    writer.writerow(row)
                fname_out = "桌面应用图标清单.csv"

            elif ctype == "settings":
                writer.writerow(["设置项名称", "目标文件名", "当前状态", "建议尺寸"])
                existing_set = set(PROJECT.list_settings_icons())
                for name in sorted(existing_set | set(SETTINGS_ICON_LABELS.keys())):
                    drawn = name in existing_set
                    writer.writerow(
                        [
                            SETTINGS_ICON_LABELS.get(name, ""),
                            f"com.android.settings/{name}",
                            "已绘制" if drawn else "未绘制",
                            "84x84",
                        ]
                    )
                fname_out = "设置页图标清单.csv"

            else:
                writer.writerow(["开关/状态名称", "目标文件名", "当前状态", "说明"])
                existing_set = set(PROJECT.list_systemui_icons())
                for name in sorted(existing_set | set(SYSTEMUI_ICON_LABELS.keys())):
                    drawn = name in existing_set
                    writer.writerow(
                        [
                            SYSTEMUI_ICON_LABELS.get(name, ""),
                            name,
                            "已绘制" if drawn else "未绘制",
                            "同时写入 com.android.systemui 与 com.vivo.systemuiplugin",
                        ]
                    )
                fname_out = "控制中心与状态栏图标清单.csv"

            data = buf.getvalue().encode("utf-8-sig")
            self._send_bytes(data, "text/csv; charset=utf-8", filename=fname_out)
            return

        if path == "/api/export":
            if not (PROJECT.entries or PROJECT.modules):
                self._send_json({"error": "No theme loaded"}, status=400)
                return
            title = PROJECT.metadata.get("title", "custom_theme").strip() or "custom_theme"
            safe_name = "".join(c for c in title if c not in r'\/:*?"<>|') + ".itz"
            data = PROJECT.export_bytes()
            self._send_bytes(data, "application/octet-stream", filename=safe_name)
            return

        if path == "/api/export-replacement-pack":
            if not (PROJECT.entries or PROJECT.modules):
                self._send_json({"error": "No theme loaded"}, status=400)
                return
            if UPLOADED_BASE_REPL_BYTES is None and find_base_replacement_pack() is None:
                self._send_json({"error": "NEED_BASE_PACK", "msg": "未找到基础替换底包，请先选择本地 主题替换包.itz 底包"}, status=400)
                return
            try:
                theme_data = PROJECT.export_bytes()
                repl_data = build_replacement_pack(theme_data, base_repl_bytes=UPLOADED_BASE_REPL_BYTES)
            except Exception as exc:
                self._send_json({"error": f"构建替换包失败: {exc}"}, status=500)
                return
            self._send_bytes(repl_data, "application/octet-stream", filename="主题替换包.itz")
            return

        if path == "/api/export-font-itz":
            title = (qs.get("title", [""])[0].strip() or PROJECT.metadata.get("title", "自定义字体") + "_字体")
            data = PROJECT.export_font_itz(font_title=title)
            if data is None:
                self._send_json({"error": "尚未上传字体文件 (.ttf/.otf)"}, status=400)
                return
            safe_name = "".join(c for c in title if c not in r'\/:*?"<>|') + ".itz"
            self._send_bytes(data, "application/octet-stream", filename=safe_name)
            return

        if path == "/api/adb/status":
            adb = find_adb()
            if not adb:
                self._send_json({"available": False, "devices": [], "error": "ADB executable not found"})
                return
            try:
                res = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=6)
                devices = []
                for line in res.stdout.splitlines()[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[1] == "device":
                        devices.append(parts[0])
                self._send_json({"available": True, "adb": adb, "devices": devices})
            except Exception as exc:
                self._send_json({"available": False, "devices": [], "error": str(exc)})
            return

        if path == "/api/adb/export-raw-icons":
            adb = find_adb()
            if not adb:
                self._send_json({"error": "ADB not found"}, status=400)
                return
            try:
                zip_bytes, extracted, total = extract_phone_icons_zip(adb, APP_NAME_MAP)
                self._send_bytes(
                    zip_bytes,
                    "application/zip",
                    filename=f"手机原始图标参考包_{extracted}个.zip",
                )
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        if path == "/api/adb/scan-missing":
            adb = find_adb()
            if not adb:
                self._send_json({"error": "ADB not found"}, status=400)
                return
            try:
                res = subprocess.run(
                    [
                        adb,
                        "shell",
                        "cmd",
                        "package",
                        "query-activities",
                        "-a",
                        "android.intent.action.MAIN",
                        "-c",
                        "android.intent.category.LAUNCHER",
                        "--brief",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=12,
                )
                pkgs = sorted(
                    {
                        line.split("/")[0].strip()
                        for line in res.stdout.splitlines()
                        if "/" in line and line.split("/")[0].strip()
                    }
                )
                existing = {n[:-4] for n in PROJECT.list_icons() if n.lower().endswith(".png")}
                missing = [
                    {"pkg": p, "label": APP_NAME_MAP.get(p, "")}
                    for p in pkgs
                    if p not in existing
                ]
                self._send_json(
                    {"total_installed": len(pkgs), "missing_count": len(missing), "missing": missing}
                )
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=500)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/new":
                body = self._read_json()
                title = (body.get("title") or "我的 OriginOS 主题").strip()
                author = (body.get("author") or "Designer").strip()
                sysromver = (body.get("sysromver") or "17.0").strip()
                PROJECT.new_blank(title=title, author=author, sysromver=sysromver)
                self._send_json(PROJECT.get_summary())
                return

            if path == "/api/load-upload":
                body = self._read_json()
                filename = body.get("filename", "theme.itz")
                b64 = body.get("data", "")
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                raw = base64.b64decode(b64)
                PROJECT.load_bytes(raw, name=filename)
                self._send_json(PROJECT.get_summary())
                return

            if path == "/api/load-path":
                body = self._read_json()
                p = Path(body.get("path", "").strip())
                if not p.is_file():
                    self._send_json({"error": f"File not found: {p}"}, status=404)
                    return
                PROJECT.load_bytes(p.read_bytes(), name=p.name)
                self._send_json(PROJECT.get_summary())
                return

            if path == "/api/metadata":
                body = self._read_json()
                for key in ("title", "author", "designer", "version", "sysromver", "description", "id"):
                    if key in body:
                        PROJECT.metadata[key] = str(body[key])
                self._send_json({"ok": True, "metadata": PROJECT.metadata})
                return

            if path == "/api/asset":
                body = self._read_json()
                scope = body.get("scope", "root")
                name = body.get("name", "").strip()
                b64 = body.get("data", "")
                if not name or not b64:
                    self._send_json({"error": "Missing name or data"}, status=400)
                    return
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                raw = base64.b64decode(b64)

                if body.get("process_icon"):
                    size = int(body.get("size", 192))
                    radius = float(body.get("radius", 0.22))
                    raw = process_icon_image(raw, size=size, radius_ratio=radius)

                if scope == "root":
                    PROJECT.entries[name] = raw
                elif scope == "icons":
                    if not name.lower().endswith(".png"):
                        name += ".png"
                    PROJECT.entries[f"icons/{name}"] = raw
                elif scope == "systemui_both":
                    PROJECT.modules.setdefault("com.android.systemui", {})[name] = raw
                    PROJECT.modules.setdefault("com.vivo.systemuiplugin", {})[name] = raw
                else:
                    PROJECT.modules.setdefault(scope, {})[name] = raw

                self._send_json({"ok": True, "summary": PROJECT.get_summary()})
                return

            if path == "/api/launcher-config":
                body = self._read_json()
                PROJECT.set_launcher_config(body)
                self._send_json({"ok": True, "config": PROJECT.get_launcher_config()})
                return

            if path == "/api/module-quick":
                body = self._read_json()
                action = body.get("action", "")
                if action == "mms_bubble":
                    color = str(body.get("color", "#98D7E1"))
                    mms = PROJECT.modules.setdefault("com.android.mms", {})
                    mms["sms_left_bg.9.png"] = make_nine_patch_bubble(color, right=False)
                    mms["sms_left_pressed_bg.9.png"] = mms["sms_left_bg.9.png"]
                    mms["sms_right_bg.9.png"] = make_nine_patch_bubble(color, right=True)
                    mms["sms_right_bg_night.9.png"] = mms["sms_right_bg.9.png"]
                    mms["sms_right_pressed_bg.9.png"] = mms["sms_right_bg.9.png"]
                    card9 = make_clean_mms_card_9patch(color)
                    mms["sms_card_view_bg.9.png"] = card9
                    mms["sms_card_view_bg_pressed.9.png"] = card9
                    self._send_json({"ok": True, "msg": "已生成 OriginOS 7 短信左右气泡 + 防变形智能通知卡片 (.9.png)"})
                    return

                if action == "dialog_color":
                    color = str(body.get("color", "#7AC8D8"))
                    dlg_l = make_clean_dialog_9patch(color, dark=False)
                    dlg_d = make_clean_dialog_9patch(color, dark=True)
                    vivo_mod = PROJECT.modules.setdefault("vivo", {})
                    vivo_mod["vigour_dialog_full_light.9.png"] = dlg_l
                    vivo_mod["vigour_dialog_full_light_os2.9.png"] = dlg_l
                    vivo_mod["vigour_dialog_full_dark.9.png"] = dlg_d
                    vivo_mod["vigour_dialog_bottom_light.9.png"] = dlg_l
                    vivo_mod["vigour_dialog_bottom_dark.9.png"] = dlg_d
                    ln_mod = PROJECT.modules.setdefault("com.bbk.launcher2", {})
                    ln_mod["launcher_vigour_popup_background.9.png"] = dlg_l
                    ln_mod["launcher_vigour_popup_background_night.9.png"] = dlg_d
                    self._send_json({"ok": True, "msg": "已生成 OriginOS 7 防变形卸载底部弹窗 (vivo/vigour_dialog_full_light.9.png)"})
                    return

                if action == "qs_glyphs":
                    wifi_ic = make_qs_glyph_icon("wifi", (255, 255, 255, 255), size=144)
                    data_ic = make_qs_glyph_icon("data", (255, 255, 255, 255), size=144)
                    bt_ic = make_qs_glyph_icon("bt", (255, 255, 255, 255), size=144)
                    vol_l = make_volume_glyph_icon("media", (38, 108, 124, 255), size=84)
                    vol_d = make_volume_glyph_icon("media", (228, 247, 250, 255), size=84)
                    vol_ml = make_volume_glyph_icon("media_mute", (38, 108, 124, 255), size=84)
                    vol_md = make_volume_glyph_icon("media_mute", (228, 247, 250, 255), size=84)
                    vol_rl = make_volume_glyph_icon("ring", (38, 108, 124, 255), size=84)
                    vol_rd = make_volume_glyph_icon("ring", (228, 247, 250, 255), size=84)
                    vol_nl = make_volume_glyph_icon("noti", (38, 108, 124, 255), size=84)
                    vol_nd = make_volume_glyph_icon("noti", (228, 247, 250, 255), size=84)
                    vol_cl = make_volume_glyph_icon("clock", (38, 108, 124, 255), size=84)
                    vol_cd = make_volume_glyph_icon("clock", (228, 247, 250, 255), size=84)
                    for mod_name in ("com.vivo.systemuiplugin", "com.android.systemui"):
                        mod = PROJECT.modules.setdefault(mod_name, {})
                        for fn in (
                            "vivo_super_qs_wifi_on.png", "vivo_super_qs_wifi_on2.png", "vivo_super_qs_wifi_on3.png",
                            "vivo_super_qs_wifi_on4.png", "vivo_super_qs_wifi_off.png",
                            "vivo_super_qs_wifi_run_on.png", "vivo_super_qs_wifi_run_on2.png",
                            "vivo_super_qs_wifi_run_on3.png", "vivo_super_qs_wifi_run_on4.png",
                            "vivo_super_qs_wifi_run_off.png", "vivo_super_qs_wifi_run_off2.png",
                            "vivo_super_qs_wifi_run_off3.png", "vivo_super_qs_wifi_run_off4.png",
                        ):
                            mod[fn] = wifi_ic
                        for fn in (
                            "vivo_super_qs_data_switch_on.png", "vivo_super_qs_data_switch_off.png",
                            "vivo_super_qs_cellular_on.png", "vivo_super_qs_cellular_off.png",
                        ):
                            mod[fn] = data_ic
                        for fn in (
                            "vivo_super_qs_bluetooth_on.png", "vivo_super_qs_bluetooth_off.png",
                            "vivo_super_qs_bluetooth_run_on.png", "vivo_super_qs_bluetooth_run_off.png",
                        ):
                            mod[fn] = bt_ic
                        mod["vivo_volume_ic_audio_vol_new.png"] = vol_l
                        mod["vivo_volume_ic_audio_vol_new_dark.png"] = vol_d
                        mod["vivo_volume_ic_audio_vol_mute_new.png"] = vol_ml
                        mod["vivo_volume_ic_audio_vol_mute_new_dark.png"] = vol_md
                        mod["vivo_volume_ic_audio_ring_notif_new.png"] = vol_rl
                        mod["vivo_volume_ic_audio_ring_notif_new_dark.png"] = vol_rd
                        mod["vivo_volume_ic_audio_noti_new.png"] = vol_nl
                        mod["vivo_volume_ic_audio_noti_new_dark.png"] = vol_nd
                        mod["vivo_volume_ic_audio_clock_new.png"] = vol_cl
                        mod["vivo_volume_ic_audio_clock_new_dark.png"] = vol_cd
                    self._send_json({"ok": True, "msg": "已生成透明底防纯色球控制中心字形 (Wi-Fi/数据/蓝牙 + 音量图标)"})
                    return

                if action == "lockscreen_ui":
                    color = str(body.get("color", "#98D7E1"))
                    b64_av = body.get("data", "")
                    av_raw = None
                    if b64_av:
                        if "," in b64_av:
                            b64_av = b64_av.split(",", 1)[1]
                        av_raw = base64.b64decode(b64_av)
                    pin_key_bg = make_lockscreen_pin_key_bg(color, size=240)
                    pin_dot_on = make_lockscreen_pin_dot(color, filled=True, size=44)
                    pin_dot_off = make_lockscreen_pin_dot(color, filled=False, size=44)
                    unlock_ind = make_lockscreen_unlock_indicator(color)
                    sysui_mod = PROJECT.modules.setdefault("com.android.systemui", {})
                    for fn in ("vivo_keyguard_num_view_shape_bg.png", "vivo_keyguard_global_pin_key.png", "vivo_pin_key.png", "num_pad_key_background.png"):
                        sysui_mod[fn] = pin_key_bg
                    for fn in ("vivo_pin_scr.png", "vivo_keyguard_pin_input_bg.png", "vivo_keyguard_global_pin_input_bg.png"):
                        sysui_mod[fn] = pin_dot_on
                    for fn in ("vivo_pin_bg.png", "vivo_keyguard_pin_un_input_bg.png", "vivo_keyguard_global_pin_uninput_bg.png"):
                        sysui_mod[fn] = pin_dot_off
                    sysui_mod["vivo_keyguard_nature_unlock_indicator_white.png"] = unlock_ind
                    quick_bg = make_lockscreen_quick_bg(av_raw, hex_color=color, size=200)
                    plugin_mod = PROJECT.modules.setdefault("com.vivo.systemuiplugin", {})
                    plugin_mod["vivo_keyguard_quick_tool_default_bg_view.png"] = quick_bg
                    plugin_mod["vivo_keyguard_shortcut_light_frame_bac.png"] = quick_bg
                    plugin_mod["vivo_keyguard_shortcut_dark_frame_bac.png"] = quick_bg
                    plugin_mod["vivo_ic_keyguard_charge_director_light.png"] = make_lockscreen_charge_icon(color, dark=False, size=80)
                    plugin_mod["vivo_ic_keyguard_charge_director_dark.png"] = make_lockscreen_charge_icon(color, dark=True, size=80)
                    self._send_json({"ok": True, "msg": "已生成锁屏原生组件（密码键盘/星芒圆点/底部快捷圆底/充电图标/上滑指示符）"})
                    return

                if action == "volume_color":
                    cur = PROJECT.get_systemui_colors()
                    cur["volume_progress_color"] = str(body.get("progress", cur["volume_progress_color"]))
                    cur["volume_bg_color"] = str(body.get("bg", cur["volume_bg_color"]))
                    cur["volume_icon_color"] = str(body.get("icon", cur["volume_icon_color"]))
                    PROJECT.set_systemui_colors(cur)
                    self._send_json({"ok": True, "msg": "已写入 OriginOS 7 音量条全局主题配色 (vivo_volume_whole_theme_*)"})
                    return

                b64 = body.get("data", "")
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                raw = base64.b64decode(b64)

                if action == "mms_left_img":
                    png = wrap_nine_patch(raw)
                    mod = PROJECT.modules.setdefault("com.android.mms", {})
                    mod["sms_left_bg.9.png"] = png
                    mod["sms_left_pressed_bg.9.png"] = png
                    self._send_json({"ok": True, "msg": "已上传自定义左侧短信气泡"})
                    return
                if action == "mms_right_img":
                    png = wrap_nine_patch(raw)
                    mod = PROJECT.modules.setdefault("com.android.mms", {})
                    mod["sms_right_bg.9.png"] = png
                    mod["sms_right_bg_night.9.png"] = png
                    mod["sms_right_pressed_bg.9.png"] = png
                    self._send_json({"ok": True, "msg": "已上传自定义右侧短信气泡"})
                    return
                if action == "dialog_bg":
                    plain_png = make_card_crop(raw, w=960, h=720, radius=56)
                    light_bg = wrap_nine_patch(plain_png)
                    vivo_mod = PROJECT.modules.setdefault("vivo", {})
                    vivo_mod["vigour_dialog_full_light.9.png"] = light_bg
                    vivo_mod["vigour_dialog_full_light_os2.9.png"] = light_bg
                    vivo_mod["vigour_dialog_full_dark.9.png"] = light_bg
                    vivo_mod["vigour_dialog_bottom_light.9.png"] = light_bg
                    vivo_mod["vigour_dialog_bottom_dark.9.png"] = light_bg
                    vivo_mod["vigour_dialog_full_light_drawable_os2.png"] = plain_png
                    ln_mod = PROJECT.modules.setdefault("com.bbk.launcher2", {})
                    ln_mod["launcher_vigour_popup_background.9.png"] = light_bg
                    ln_mod["launcher_vigour_popup_background_night.9.png"] = light_bg
                    self._send_json({"ok": True, "msg": "已生成 OriginOS 7 卸载底部弹窗 (vivo/vigour_dialog_full_light.9.png)"})
                    return
                if action == "switch_avatar":
                    import io as _io
                    from PIL import Image as _Image
                    color = str(body.get("color", "#6AC4D4"))
                    tr_on = make_switch_track_png(raw, state="on", hex_color=color)
                    tr_off = make_switch_track_png(raw, state="off", hex_color=color)
                    th9 = make_switch_thumb_9patch(color, nine_patch=True)
                    thp = make_switch_thumb_9patch(color, nine_patch=False)
                    lb, rb = _io.BytesIO(), _io.BytesIO()
                    _Image.new("RGBA", (6, 36), (0, 0, 0, 0)).save(lb, format="PNG")
                    _Image.new("RGBA", (31, 31), (0, 0, 0, 0)).save(rb, format="PNG")
                    tl, tr = lb.getvalue(), rb.getvalue()
                    vivo_mod = PROJECT.modules.setdefault("vivo", {})
                    for fn in ("vigour_bool_btn_bg_on_light.png", "vigour_bool_btn_bg_on_dark.png", "vigour_bool_btn_bg_press.png", "vigour_switch_btn_bg_on_light.png"):
                        vivo_mod[fn] = tr_on
                    for fn in ("vigour_bool_btn_bg_off_light.png", "vigour_bool_btn_bg_off_dark.png", "vigour_bool_btn_bg_normal.png", "vigour_switch_btn_bg_off_light.png"):
                        vivo_mod[fn] = tr_off
                    for fn in ("vigour_bool_btn_hand_normal_light.9.png", "vigour_bool_btn_hand_normal_dark.9.png", "vigour_switch_btn_hand_normal_light.9.png"):
                        vivo_mod[fn] = th9
                    for fn in ("vigour_bool_btn_hand_disabled_light.png", "vigour_bool_btn_hand_disabled_dark.png"):
                        vivo_mod[fn] = thp
                    for fn in ("vigour_bool_btn_handleft_normal_light.png", "vigour_bool_btn_handleft_normal_dark.png", "vigour_bool_btn_handleft_disabled_light.png", "vigour_bool_btn_handleft_disabled_dark.png"):
                        vivo_mod[fn] = tl
                    for fn in ("vigour_bool_btn_handright_normal_light.png", "vigour_bool_btn_handright_normal_dark.png", "vigour_bool_btn_handright_disabled_light.png", "vigour_bool_btn_handright_disabled_dark.png"):
                        vivo_mod[fn] = tr
                    self._send_json({"ok": True, "msg": "已生成全系统头像开关按钮 (vivo/vigour_bool_btn_*)"})
                    return
                if action == "wifi_avatar":
                    png = make_circle_avatar(raw, size=144)
                    for mod_name in ("com.vivo.systemuiplugin", "com.android.systemui"):
                        mod = PROJECT.modules.setdefault(mod_name, {})
                        for fn in (
                            "vivo_super_qs_wifi_on.png",
                            "vivo_super_qs_wifi_on2.png",
                            "vivo_super_qs_wifi_on3.png",
                            "vivo_super_qs_wifi_on4.png",
                            "vivo_super_qs_wifi_off.png",
                            "vivo_super_qs_wifi_run_on.png",
                            "vivo_super_qs_wifi_run_on2.png",
                            "vivo_super_qs_wifi_run_on3.png",
                            "vivo_super_qs_wifi_run_on4.png",
                            "vivo_super_qs_wifi_run_off.png",
                            "vivo_super_qs_wifi_run_off2.png",
                            "vivo_super_qs_wifi_run_off3.png",
                            "vivo_super_qs_wifi_run_off4.png",
                        ):
                            mod[fn] = png
                    self._send_json({"ok": True, "msg": "已写入控制中心 SuperQS Wi-Fi 大头图标"})
                    return
                if action == "data_avatar":
                    png = make_circle_avatar(raw, size=144)
                    for mod_name in ("com.vivo.systemuiplugin", "com.android.systemui"):
                        mod = PROJECT.modules.setdefault(mod_name, {})
                        for fn in (
                            "vivo_super_qs_data_switch_on.png",
                            "vivo_super_qs_data_switch_off.png",
                            "vivo_super_qs_cellular_on.png",
                            "vivo_super_qs_cellular_off.png",
                        ):
                            mod[fn] = png
                    self._send_json({"ok": True, "msg": "已写入控制中心 SuperQS 移动数据图标"})
                    return
                if action == "bt_avatar":
                    png = make_circle_avatar(raw, size=144)
                    for mod_name in ("com.vivo.systemuiplugin", "com.android.systemui"):
                        mod = PROJECT.modules.setdefault(mod_name, {})
                        for fn in (
                            "vivo_super_qs_bluetooth_on.png",
                            "vivo_super_qs_bluetooth_off.png",
                            "vivo_super_qs_bluetooth_run_on.png",
                            "vivo_super_qs_bluetooth_run_off.png",
                        ):
                            mod[fn] = png
                    self._send_json({"ok": True, "msg": "已写入控制中心 SuperQS 蓝牙图标"})
                    return
                if action in ("supercard_pay", "supercard_camera"):
                    target_slot = body.get("slot", "all")
                    mod = PROJECT.modules.setdefault("com.vivo.card", {})
                    slot_list = SUPERCARD_PAY_SLOTS if action == "supercard_pay" else SUPERCARD_CAMERA_SLOTS
                    kind_name = "付款卡" if action == "supercard_pay" else "镜头套件"
                    cnt, obf_cnt = write_supercard_assets(mod, raw, slot_list, target_slot=target_slot)
                    self._send_json(
                        {
                            "ok": True,
                            "msg": f"已写入 {cnt} 组超级卡包{kind_name}（并自动同步 {obf_cnt} 枚 OriginOS 7 混淆名素材）",
                        }
                    )
                    return
                if action == "wallet_card":
                    target_slot = body.get("slot", "all")
                    png = make_card_crop(raw, w=960, h=600, radius=36)
                    mod = PROJECT.modules.setdefault("com.vivo.wallet", {})
                    all_slots = (
                        "card_bag_open_card_bg.png",
                        "bank_card_add_card_bg.png",
                        "bank_card_bg_blue.png",
                        "bank_card_bg_green.png",
                        "bank_card_bg_red.png",
                        "bank_card_bg_yellow.png",
                        "bank_card_bg_gray.png",
                        "buscard_select_card_bg.png",
                        "ic_nfccard_bg.png",
                    )
                    if target_slot == "all":
                        for fn in all_slots:
                            mod[fn] = png
                        self._send_json({"ok": True, "msg": f"已写入全部 {len(all_slots)} 张卡包背景"})
                    else:
                        mod[target_slot] = png
                        self._send_json({"ok": True, "msg": f"已更新卡面 {target_slot}"})
                    return
                if action == "clock_dial":
                    dial = make_circle_avatar(raw, size=600)
                    mod = PROJECT.modules.setdefault("com.android.BBKClock", {})
                    mod["clock_plate_bg_circle.png"] = dial
                    mod["clock_plate_normal_bg_circle.png"] = dial
                    mod["clock_plate_day_6_0.png"] = dial
                    mod["clock_plate_day_2_0.png"] = dial
                    self._send_json({"ok": True, "msg": "已写入世界时钟表盘 (clock_plate_*)"})
                    return
                if action == "volume_bg":
                    bg = make_card_crop(raw, w=640, h=480, radius=36)
                    bg9 = wrap_nine_patch(bg)
                    for mod_name in ("com.android.systemui", "com.vivo.systemuiplugin"):
                        mod = PROJECT.modules.setdefault(mod_name, {})
                        mod["volume_dialog_background.9.png"] = bg9
                        mod["vivo_footer_volume_bg.png"] = bg
                    self._send_json({"ok": True, "msg": "已编译 npTc 点九图并写入音量面板背景"})
                    return
                if action == "dialer_bg":
                    bg = make_card_crop(raw, w=1080, h=1920, radius=0)
                    PROJECT.modules.setdefault("com.android.contacts", {})["dialpad_bg.png"] = bg
                    PROJECT.modules.setdefault("com.android.incallui", {})["incall_bg.png"] = bg
                    self._send_json({"ok": True, "msg": "已写入拨号盘与通话背景"})
                    return
                if action == "calc_bg":
                    bg = make_card_crop(raw, w=1080, h=1920, radius=0)
                    PROJECT.modules.setdefault("com.android.bbkcalculator", {})["calculator_bg.png"] = bg
                    self._send_json({"ok": True, "msg": "已写入计算器背景"})
                    return
                if action == "weather_bg":
                    bg = make_card_crop(raw, w=1080, h=1920, radius=0)
                    PROJECT.modules.setdefault("com.vivo.weather", {})["weather_bg.png"] = bg
                    self._send_json({"ok": True, "msg": "已写入天气背景"})
                    return
                self._send_json({"error": "Unknown quick action"}, status=400)
                return

            if path == "/api/lockscreen/save":
                body = self._read_json()
                xml = PROJECT.save_lockscreen_config(body)
                self._send_json({"ok": True, "xml": xml, "summary": PROJECT.get_summary()})
                return

            if path == "/api/lockscreen/xml":
                body = self._read_json()
                xml = str(body.get("xml", ""))
                PROJECT.entries["lockscreen/manifest.xml"] = xml.encode("utf-8")
                self._send_json({"ok": True, "summary": PROJECT.get_summary()})
                return

            if path == "/api/extras/upload":
                import zipfile
                import io

                body = self._read_json()
                kind = body.get("kind", "")
                filename = body.get("filename", "")
                b64 = body.get("data", "")
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                raw = base64.b64decode(b64)

                if kind == "font":
                    for k in list(PROJECT.entries.keys()):
                        if k.startswith("fonts/"):
                            del PROJECT.entries[k]
                    PROJECT.entries["fonts/DroidSansFallback.ttf"] = raw
                    self._send_json({"ok": True, "msg": f"已加载全局字体 ({filename})", "summary": PROJECT.get_summary()})
                    return

                if kind == "ringtone":
                    slot = body.get("slot", "ringtone")
                    ext = Path(filename).suffix.lower() or ".ogg"
                    for k in list(PROJECT.entries.keys()):
                        if k.startswith(f"ringtones/{slot}."):
                            del PROJECT.entries[k]
                    PROJECT.entries[f"ringtones/{slot}{ext}"] = raw
                    self._send_json({"ok": True, "msg": f"已写入铃声 {slot}{ext}", "summary": PROJECT.get_summary()})
                    return

                if kind == "lockscreen_fg":
                    PROJECT.entries["lockscreen/fg.png"] = raw
                    self._send_json({"ok": True, "msg": "已上传锁屏前景立绘 (lockscreen/fg.png)", "summary": PROJECT.get_summary()})
                    return

                if kind == "lockscreen_bg":
                    PROJECT.entries["lockscreen/bg.jpg"] = raw
                    self._send_json({"ok": True, "msg": "已上传锁屏包背景 (lockscreen/bg.jpg)", "summary": PROJECT.get_summary()})
                    return

                if kind == "lockscreen_zip":
                    for k in list(PROJECT.entries.keys()):
                        if k.startswith("lockscreen/"):
                            del PROJECT.entries[k]
                    cnt = 0
                    with zipfile.ZipFile(io.BytesIO(raw), "r") as zin:
                        for item in zin.infolist():
                            if item.is_dir():
                                continue
                            name = item.filename.lstrip("/")
                            if not name.startswith("lockscreen/"):
                                name = f"lockscreen/{name}"
                            PROJECT.entries[name] = zin.read(item.filename)
                            cnt += 1
                    self._send_json({"ok": True, "msg": f"已导入锁屏包，共 {cnt} 个文件", "summary": PROJECT.get_summary()})
                    return

                self._send_json({"error": "Unknown extras kind"}, status=400)
                return

            if path == "/api/module-xml":
                body = self._read_json()
                mod_name = str(body.get("module", "")).strip()
                xml_text = str(body.get("xml", ""))
                if not mod_name:
                    self._send_json({"error": "Missing module name"}, status=400)
                    return
                PROJECT.set_module_xml(mod_name, xml_text)
                self._send_json({"ok": True, "summary": PROJECT.get_summary()})
                return

            if path == "/api/launcher-generate":
                body = self._read_json()
                hex_color = str(body.get("color", "#98D7E1"))
                ornament = str(body.get("ornament", "feather"))
                kit = generate_launcher_kit(hex_color=hex_color, ornament=ornament)
                for k, v in kit.items():
                    PROJECT.entries[k] = v
                self._send_json({"ok": True, "count": len(kit), "summary": PROJECT.get_summary()})
                return

            if path == "/api/settings-strings":
                body = self._read_json()
                PROJECT.set_settings_strings(body)
                self._send_json({"ok": True, "settings_strings": PROJECT.get_settings_strings()})
                return

            if path == "/api/systemui-colors":
                body = self._read_json()
                PROJECT.set_systemui_colors(body)
                self._send_json({"ok": True, "colors": PROJECT.get_systemui_colors()})
                return

            if path == "/api/fix/map-vivo-icons":
                added = PROJECT.map_vivo_system_icons()
                self._send_json({"ok": True, "added": added, "summary": PROJECT.get_summary()})
                return

            if path == "/api/fix/origin6-settings":
                res = PROJECT.patch_origin6_settings_icons()
                self._send_json({"ok": True, **res, "summary": PROJECT.get_summary()})
                return

            if path == "/api/fix/dark-bg":
                body = self._read_json()
                brightness = float(body.get("brightness", 0.26))
                contrast = float(body.get("contrast", 1.12))
                updated = PROJECT.apply_dark_backgrounds(brightness=brightness, contrast=contrast)
                self._send_json({"ok": True, "updated": updated, "summary": PROJECT.get_summary()})
                return

            if path == "/api/upload-base-replacement-pack":
                global UPLOADED_BASE_REPL_BYTES
                body = self._read_json()
                b64 = body.get("data", "")
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                UPLOADED_BASE_REPL_BYTES = base64.b64decode(b64)
                self._send_json({"ok": True, "bytes": len(UPLOADED_BASE_REPL_BYTES)})
                return

            if path == "/api/adb/push-replacement-pack":
                adb = find_adb()
                if not adb:
                    self._send_json({"error": "ADB not found"}, status=400)
                    return
                if UPLOADED_BASE_REPL_BYTES is None and find_base_replacement_pack() is None:
                    self._send_json({"error": "NEED_BASE_PACK", "msg": "未找到基础替换底包，请先上传本地 主题替换包.itz 底包"}, status=400)
                    return
                try:
                    repl_data = build_replacement_pack(PROJECT.export_bytes(), base_repl_bytes=UPLOADED_BASE_REPL_BYTES)
                except Exception as exc:
                    self._send_json({"error": f"构建替换包失败: {exc}"}, status=500)
                    return
                with tempfile.NamedTemporaryFile(suffix=".itz", delete=False) as tf:
                    tf.write(repl_data)
                    tmp_path = Path(tf.name)
                try:
                    remote = "/sdcard/_共享/OriginOS7主题/主题替换包.itz"
                    res = subprocess.run(
                        [adb, "push", str(tmp_path), remote],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if res.returncode != 0:
                        self._send_json({"error": res.stderr or res.stdout}, status=500)
                        return
                    self._send_json({"ok": True, "remote": remote, "bytes": len(repl_data)})
                finally:
                    tmp_path.unlink(missing_ok=True)
                return

            if path == "/api/adb/push":
                adb = find_adb()
                if not adb:
                    self._send_json({"error": "ADB not found"}, status=400)
                    return
                title = PROJECT.metadata.get("title", "custom_theme").strip() or "custom_theme"
                safe_name = "".join(c for c in title if c not in r'\/:*?"<>|') + ".itz"
                data = PROJECT.export_bytes()
                with tempfile.NamedTemporaryFile(suffix=".itz", delete=False) as tf:
                    tf.write(data)
                    tmp_path = Path(tf.name)
                try:
                    remote = f"/sdcard/Download/{safe_name}"
                    res = subprocess.run(
                        [adb, "push", str(tmp_path), remote],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if res.returncode != 0:
                        self._send_json({"error": res.stderr or res.stdout}, status=500)
                        return
                    self._send_json({"ok": True, "remote": remote, "bytes": len(data)})
                finally:
                    tmp_path.unlink(missing_ok=True)
                return

            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/api/icon":
            name = qs.get("name", [""])[0]
            PROJECT.entries.pop(f"icons/{name}", None)
            self._send_json({"ok": True, "summary": PROJECT.get_summary()})
            return
        if parsed.path == "/api/extras":
            prefix = qs.get("prefix", [""])[0]
            if prefix in ("fonts/", "ringtones/", "lockscreen/"):
                for k in list(PROJECT.entries.keys()):
                    if k.startswith(prefix):
                        del PROJECT.entries[k]
                self._send_json({"ok": True, "summary": PROJECT.get_summary()})
                return
        self.send_error(HTTPStatus.NOT_FOUND)


def run_server(host: str = "127.0.0.1", port: int = 18765, open_browser: bool = True) -> None:
    _auto_load_sample()
    ThreadingHTTPServer.allow_reuse_address = False
    server = ThreadingHTTPServer((host, port), StudioHandler)
    url = f"http://{host}:{port}/"
    print(f"OriginOS Theme Studio running at {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


if __name__ == "__main__":
    run_server()
