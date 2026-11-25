"""Core engine for reading, editing, previewing, and exporting vivo .itz themes."""

from __future__ import annotations

import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageEnhance

# Common MIUI / generic package names -> OriginOS / vivo / iQOO package names
VIVO_ICON_MAPPING: dict[str, str] = {
    "com.miui.calculator.png": "com.android.bbkcalculator.png",
    "com.miui.compass.png": "com.vivo.compass.png",
    "com.miui.gallery.png": "com.vivo.gallery.png",
    "com.miui.notes.png": "com.android.notes.png",
    "com.miui.huanji.png": "com.vivo.easyshare.png",
    "com.miui.userguide.png": "com.vivo.Tips.png",
    "com.mi.health.png": "com.vivo.health.png",
    "com.mipay.wallet.png": "com.vivo.wallet.png",
    "com.xiaomi.market.png": "com.bbk.appstore.png",
    "com.xiaomi.gamecenter.png": "com.vivo.game.png",
    "com.xiaomi.mibrain.speech.png": "com.vivo.ai.copilot.png",
    "com.xiaomi.smarthome.png": "com.vivo.vhome.png",
    "com.duokan.phone.remotecontroller.png": "com.vivo.smartremote.png",
    "com.android.browser.png": "com.vivo.browser.png",
    "com.android.fileexplorer.png": "com.android.filemanager.png",
    "com.android.thememanager.png": "com.bbk.theme.png",
    "com.android.soundrecorder.png": "com.android.bbksoundrecorder.png",
    "com.android.providers.calendar.png": "com.bbk.calendar.png",
    "com.android.providers.contacts.png": "com.android.contacts.png",
    "com.android.phone.png": "com.android.dialer.png",
}

APP_NAME_MAP: dict[str, str] = {
    # System / vivo / iQOO
    "com.android.settings": "设置",
    "com.android.camera": "相机",
    "com.android.mms": "信息",
    "com.android.contacts": "联系人",
    "com.android.dialer": "电话（拨号）",
    "com.android.phone": "电话（备用）",
    "com.android.incallui": "通话界面",
    "com.android.BBKClock": "时钟",
    "com.android.bbkcalculator": "计算器",
    "com.android.bbksoundrecorder": "录音机",
    "com.android.filemanager": "文件管理",
    "com.android.notes": "便签",
    "com.bbk.appstore": "vivo 应用商店",
    "com.bbk.calendar": "日历",
    "com.bbk.theme": "i主题",
    "com.bbk.iqoo.feedback": "反馈与服务",
    "com.vivo.browser": "vivo 浏览器",
    "com.vivo.compass": "指南针",
    "com.vivo.easyshare": "互传",
    "com.vivo.gallery": "相册",
    "com.vivo.game": "游戏中心",
    "com.vivo.health": "健康",
    "com.vivo.smartremote": "智慧遥控",
    "com.vivo.space": "vivo 空间",
    "com.vivo.Tips": "使用技巧",
    "com.vivo.translator": "翻译",
    "com.vivo.vhome": "智慧生活",
    "com.vivo.wallet": "钱包",
    "com.vivo.weather": "天气",
    "com.vivo.ai.copilot": "蓝心小V",
    "com.vivo.familycare.local": "家人守护",
    # MIUI / Generic aliases
    "com.android.browser": "浏览器",
    "com.android.fileexplorer": "文件管理",
    "com.android.thememanager": "主题壁纸",
    "com.android.soundrecorder": "录音机",
    "com.android.providers.calendar": "日历",
    "com.android.providers.contacts": "联系人",
    "com.android.email": "电子邮件",
    "com.android.updater": "系统更新",
    "com.android.vending": "Google Play",
    "com.miui.calculator": "计算器 (MIUI)",
    "com.miui.compass": "指南针 (MIUI)",
    "com.miui.gallery": "相册 (MIUI)",
    "com.miui.notes": "笔记 (MIUI)",
    "com.miui.video": "视频 (MIUI)",
    "com.miui.screenrecorder": "录屏 (MIUI)",
    "com.miui.securitycenter": "安全中心 (MIUI)",
    "com.mi.health": "小米运动健康",
    "com.mipay.wallet": "小米钱包",
    "com.xiaomi.market": "小米应用商店",
    "com.xiaomi.gamecenter": "小米游戏中心",
    "com.xiaomi.smarthome": "米家",
    "com.duokan.phone.remotecontroller": "万能遥控",
    # Popular 3rd party apps
    "com.tencent.mm": "微信",
    "com.tencent.mobileqq": "QQ",
    "com.tencent.tim": "TIM",
    "com.tencent.wework": "企业微信",
    "com.tencent.wemeet.app": "腾讯会议",
    "com.tencent.qqmusic": "QQ音乐",
    "com.tencent.qqlive": "腾讯视频",
    "com.tencent.androidqqmail": "QQ邮箱",
    "com.tencent.tmgp.sgame": "王者荣耀",
    "com.tencent.tmgp.pubgmhd": "和平精英",
    "com.tencent.gamehelper.smoba": "王者营地",
    "com.eg.android.AlipayGphone": "支付宝",
    "com.taobao.taobao": "淘宝",
    "com.tmall.wireless": "天猫",
    "com.jingdong.app.mall": "京东",
    "com.jd.jrapp": "京东金融",
    "com.xunmeng.pinduoduo": "拼多多",
    "com.achievo.vipshop": "唯品会",
    "com.alibaba.android.rimet": "钉钉",
    "com.alibaba.wireless": "阿里巴巴",
    "com.alicloud.databox": "阿里云盘",
    "com.aliyun.tongyi": "通义千问",
    "com.ss.android.ugc.aweme": "抖音",
    "com.ss.android.ugc.livelite": "抖音极速版",
    "com.ss.android.article.news": "今日头条",
    "com.ss.android.article.video": "西瓜视频",
    "com.ss.android.lark": "飞书",
    "com.smile.gifmaker": "快手",
    "tv.danmaku.bili": "哔哩哔哩",
    "tv.acfundanmaku.video": "AcFun",
    "com.xingin.xhs": "小红书",
    "com.zhihu.android": "知乎",
    "com.sina.weibo": "微博",
    "com.tieba.baidu": "百度贴吧",
    "com.baidu.tieba": "百度贴吧",
    "com.baidu.BaiduMap": "百度地图",
    "com.baidu.searchbox": "百度",
    "com.baidu.netdisk": "百度网盘",
    "com.autonavi.minimap": "高德地图",
    "com.sankuai.meituan": "美团",
    "me.ele": "饿了么",
    "com.dianping.v1": "大众点评",
    "com.ctrip.android.view": "携程旅行",
    "ctrip.android.view": "携程旅行",
    "com.Qunar": "去哪儿旅行",
    "com.MobileTicket": "铁路12306",
    "com.sdu.didi.psnger": "滴滴出行",
    "cn.caocaokeji.user": "曹操出行",
    "com.netease.cloudmusic": "网易云音乐",
    "com.kugou.android": "酷狗音乐",
    "cn.kuwo.player": "酷我音乐",
    "com.ximalaya.ting.android": "喜马拉雅",
    "cn.missevan": "猫耳FM",
    "com.qiyi.video": "爱奇艺",
    "com.youku.phone": "优酷视频",
    "com.hunantv.imgo.activity": "芒果TV",
    "com.dragon.read": "番茄免费小说",
    "com.quark.browser": "夸克",
    "com.UCMobile": "UC浏览器",
    "com.coolapk.market": "酷安",
    "bin.mt.plus": "MT管理器",
    "bin.mt.termex": "MT终端扩展",
    "moe.shizuku.privileged.api": "Shizuku",
    "com.shizuku.uninstaller": "Shizuku 卸载器",
    "com.github.android": "GitHub",
    "com.openai.chatgpt": "ChatGPT",
    "com.anthropic.claude": "Claude",
    "ai.x.grok": "Grok",
    "com.google.android.apps.bard": "Gemini",
    "com.google.android.youtube": "YouTube",
    "com.twitter.android": "X (Twitter)",
    "com.valvesoftware.android.steam.community": "Steam",
    "jp.pxv.android": "Pixiv",
    "com.perol.pixez": "PixEz",
    "com.picacg.picacomic": "哔咔漫画",
    "cn.wps.moffice_eng": "WPS Office",
    "com.microsoft.office.onenote": "OneNote",
    "com.microsoft.todos": "Microsoft To Do",
    "com.microsoft.rdc.androidx": "Windows App / RD",
    "com.miHoYo.Yuanshen": "原神",
    "com.miHoYo.hkrpg": "崩坏：星穹铁道",
    "bluearchive": "碧蓝档案",
    "com.and.games505.TerrariaPaid": "泰拉瑞亚",
    "com.taptap": "TapTap",
    "com.smzdm.client.android": "什么值得买",
    "com.icbc": "中国工商银行",
    "com.cmbchina.pb": "招商银行",
    "cmb.pb": "招商银行",
    "com.android.bankabc": "中国农业银行",
    "com.chinamworld.main": "中国建设银行",
    "com.boc.bocsoft.bocmbovsa.buss": "中国银行",
    "com.greenpoint.android.mc10086.activity": "中国移动",
    "com.sinovatech.unicom.ui": "中国联通",
    "com.ct.client": "中国电信",
    "cn.gov.tax.its": "个人所得税",
    "com.tmri.app.main": "交管12123",
    "cn.com.chsi.chsiapp": "学信网",
    "cn.xuexi.android": "学习强国",
    "com.v2ray.ang": "v2rayNG",
    "com.hpbr.bosszhipin": "BOSS直聘",
    "com.zhaopin.social": "智联招聘",
}

SETTINGS_ICON_LABELS: dict[str, str] = {
    "ic_settings_account_item.png": "用户与账号",
    "ic_settings_airplane_item.png": "飞行模式",
    "ic_settings_wifi_bbk_item.png": "Wi-Fi",
    "ic_settings_bluetooth_item.png": "蓝牙",
    "ic_settings_network.png": "双卡与移动网络",
    "ic_settings_network_disable.png": "移动网络（禁用态）",
    "ic_extra_network_connection_settings.png": "更多连接",
    "ic_settings_satellite_communication.png": "卫星通信",
    "com_android_systemui.png": "通知与状态栏",
    "ic_settings_sound_item.png": "声音与振动",
    "ic_settings_light_item.png": "显示、亮度与护眼",
    "ic_settings_theme_item.png": "桌面、锁屏与壁纸",
    "ic_application_permission_settings.png": "应用与权限",
    "ic_settings_finger.png": "指纹与密码",
    "ic_settings_finger_face.png": "指纹、面部与密码",
    "ic_settings_security.png": "安全",
    "ic_vivo_privacy.png": "隐私",
    "ic_settings_ram_item.png": "运存与存储空间",
    "com_iqoo_powersaving.png": "电池",
    "ic_cooling_fan_image.png": "散热风扇（首页真图标）",
    "set_fan_light_layer0.png": "散热风扇灯效（层0）",
    "set_fan_light_layer1.png": "散热风扇灯效（层1）",
    "set_fan_light_layer2.png": "散热风扇灯效（层2）",
    "set_fan_layer1.png": "散热风扇灯效（通用）",
    "ic_ai_settings.png": "蓝心AI",
    "ic_settings_game.png": "游戏魔盒",
    "ic_settings_screentime.png": "健康使用设备",
    "ic_wallet_and_payment.png": "钱包与付款",
    "ic_shortcut_accessibility_settings.png": "快捷与辅助",
    "ic_system_management_settings.png": "系统管理（旧版）",
    "ic_system_update.png": "系统管理与升级（主）",
    "ic_system_update_1.png": "系统管理与升级（层1）",
    "ic_system_update_2.png": "系统管理与升级（层2）",
    "ic_about_phone.png": "关于手机",
    "about_phone_origin_os_rom14.png": "关于手机横幅 (ROM14)",
    "about_phone_origin_os_rom14_land.png": "关于手机横幅横屏 (ROM14)",
    "about_phone_origin_os_rom15.png": "关于手机横幅 (ROM15)",
    "about_phone_origin_os_rom15_land.png": "关于手机横幅横屏 (ROM15)",
    "about_phone_origin_os_rom16.png": "关于手机横幅 (OS6/7 前景)",
    "about_phone_origin_os_rom16_bg.png": "关于手机横幅 (OS6/7 真底图)",
    "about_phone_origin_os_rom16_land.png": "关于手机横幅横屏 (ROM16)",
    "about_phone_origin_os_rom17.png": "关于手机横幅 (ROM17 备用)",
    "about_phone_origin_os_rom17_land.png": "关于手机横幅横屏 (ROM17 备用)",
    "regulatory_compliances.png": "入网/认证标识",
}

SETTINGS_EDITABLE_STRINGS: list[dict[str, str]] = [
    {"key": "vivo_search_settings", "label": "设置搜索框提示", "default": "搜索设置项"},
    {"key": "settings_label", "label": "设置首页标题", "default": "设置"},
    {"key": "vivo_settings_label_launcher", "label": "桌面“设置”应用名", "default": "设置"},
    {"key": "vivo_search_history_title", "label": "搜索历史标题", "default": "搜索历史"},
    {"key": "vivo_search_suggestion_title", "label": "搜索建议标题", "default": "搜索建议"},
    {"key": "vivo_search_apps", "label": "搜索应用提示", "default": "搜索应用"},
    {"key": "vivo_bluetooth_settings_title", "label": "蓝牙设置标题", "default": "蓝牙"},
    {"key": "vivo_system_and_upgrade_title", "label": "系统管理与升级标题", "default": "系统管理与升级"},
]


def build_systemui_default_labels() -> dict[str, str]:
    """Return default SystemUI / Control Center & Power Menu icon labels."""
    labels: dict[str, str] = {
        "vivo_reboot_image.png": "电源菜单 - 重启图标",
        "vivo_shutdown_image.png": "电源菜单 - 关机图标",
        "vivo_shutdown_sos_button.png": "电源菜单 - SOS 紧急呼叫",
        "vivo_shutdown_dialog_update.png": "电源菜单 - 更新并重启",
    }
    modes = {
        "personal": "个人 / 请勿打扰",
        "meditation": "冥想模式",
        "read": "阅读模式",
        "sleep": "睡眠模式",
        "sport": "运动模式",
        "work": "工作模式",
        "zen": "专注 / 禅定模式",
    }
    for mode_key, mode_name in modes.items():
        for state, state_name in (("on", "开启"), ("off", "关闭")):
            for suffix in ("", "2", "3", "_bmw", "_run", "_run2", "_run3", "_run_bmw"):
                fname = f"vivo_qs_focus_mode_{mode_key}_{state}{suffix}.png"
                extra = f" ({suffix.lstrip('_')})" if suffix else ""
                labels[fname] = f"{mode_name} - {state_name}{extra}"
                if mode_key in ("personal", "sport"):
                    detail_name = f"vivo_qs_focus_mode_{mode_key}_{state}{suffix}_for_detail.png"
                    labels[detail_name] = f"{mode_name}详情 - {state_name}{extra}"
    return labels


SYSTEMUI_ICON_LABELS: dict[str, str] = build_systemui_default_labels()

LAUNCHER_ICON_LABELS: dict[str, str] = {
    "launcher/icon_mask.png": "统一形状遮罩 (168×168)",
    "launcher/icon_bg_default.png": "默认统一底衬 (168×168)",
    "launcher/icon_cover.png": "统一前景边框/角标 (240×240)",
    "launcher/icon_pattern.png": "底层纹理图 (168×168)",
    "launcher/icon_bg_one.png": "轮换底衬 1 (168×168)",
    "launcher/icon_bg_two.png": "轮换底衬 2 (168×168)",
    "launcher/icon_bg_three.png": "轮换底衬 3 (168×168)",
    "launcher/icon_bg_four.png": "轮换底衬 4 (168×168)",
    "launcher/icon_bg_five.png": "轮换底衬 5 (168×168)",
    "launcher/icon_bg_six.png": "轮换底衬 6 (168×168)",
    "launcher/icon_bg_seven.png": "轮换底衬 7 (168×168)",
    "launcher/folder_icon.png": "文件夹图标 (168×168)",
    "launcher/app_folder_icon.png": "应用文件夹图标 (168×168)",
    "launcher/icon_folder.png": "文件夹背景-深 (168×168)",
    "launcher/icon_folder_light.png": "文件夹背景-浅 (168×168)",
    "launcher/folder_icon_cover_01.png": "文件夹前景边框 1 (240×240)",
    "launcher/folder_icon_cover_02.png": "文件夹前景边框 2 (240×240)",
    "launcher/folder_icon_cover_03.png": "文件夹前景边框 3 (240×240)",
    "launcher/folder_icon_cover_04.png": "文件夹前景边框 4 (240×240)",
    "launcher/folder_icon_cover_05.png": "文件夹前景边框 5 (240×240)",
    "launcher/folder_icon_cover_06.png": "文件夹前景边框 6 (240×240)",
}


def find_adb() -> str | None:
    """Locate adb executable from PATH or common Windows WinGet/SDK paths."""
    found = shutil.which("adb")
    if found:
        # Verify WinGet shim actually works
        try:
            res = subprocess.run([found, "version"], capture_output=True, timeout=3)
            if res.returncode == 0:
                return found
        except Exception:
            pass

    candidates = [
        Path.home()
        / "AppData/Local/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe",
        Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
        Path("C:/platform-tools/adb.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    winget_root = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    if winget_root.exists():
        for p in winget_root.rglob("adb.exe"):
            return str(p)
    return None


def make_transparent_png(size: tuple[int, int] = (84, 84)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, (0, 0, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def make_fan_icon(color: tuple[int, int, int, int] = (182, 209, 159, 255), size: int = 84) -> bytes:
    """Generate a clean anti-aliased cooling fan icon matching OriginOS Settings style."""
    scale = 4
    s = size * scale
    cx, cy = s / 2, s / 2
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    r_outer = s * 0.34
    ring_w = int(s * 0.055)
    draw.ellipse(
        [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
        outline=color,
        width=ring_w,
    )

    r_in = s * 0.06
    r_out = s * 0.25
    for k in range(4):
        ang = k * (math.pi / 2) + math.pi / 6
        a1 = ang - 0.38
        a2 = ang + 0.42
        pts = [
            (cx + r_in * math.cos(a1), cy + r_in * math.sin(a1)),
            (cx + r_out * 0.72 * math.cos(a1 + 0.12), cy + r_out * 0.72 * math.sin(a1 + 0.12)),
            (cx + r_out * math.cos(ang + 0.22), cy + r_out * math.sin(ang + 0.22)),
            (cx + r_out * 0.85 * math.cos(a2 + 0.15), cy + r_out * 0.85 * math.sin(a2 + 0.15)),
            (cx + r_in * math.cos(a2), cy + r_in * math.sin(a2)),
        ]
        draw.polygon(pts, fill=color)

    r_hub = s * 0.065
    draw.ellipse([cx - r_hub, cy - r_hub, cx + r_hub, cy + r_hub], fill=color)

    out = img.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def process_icon_image(raw_bytes: bytes, size: int = 192, radius_ratio: float = 0.22) -> bytes:
    """Resize/crop an uploaded image to a square PNG with optional rounded corners."""
    im = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    im = im.crop((left, top, left + side, top + side))
    im = im.resize((size, size), Image.Resampling.LANCZOS)

    if radius_ratio > 0:
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        r = int(size * radius_ratio)
        draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
        r_ch, g_ch, b_ch, a_ch = im.split()
        # Combine existing alpha with rounded mask
        combined_alpha = Image.composite(a_ch, Image.new("L", (size, size), 0), mask)
        im = Image.merge("RGBA", (r_ch, g_ch, b_ch, combined_alpha))

    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()



def generate_dark_background(
    light_png_bytes: bytes, brightness: float = 0.26, contrast: float = 1.12
) -> bytes:
    """Create a dark-mode background from a light-mode illustration."""
    im = Image.open(io.BytesIO(light_png_bytes)).convert("RGBA")
    rgb = im.convert("RGB")
    rgb = ImageEnhance.Brightness(rgb).enhance(brightness)
    rgb = ImageEnhance.Contrast(rgb).enhance(contrast)
    r, g, b = rgb.split()
    _, _, _, a = im.split()
    out = Image.merge("RGBA", (r, g, b, a))
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 6:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 152, 215, 225  # #98D7E1


def _draw_feather_badge(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, rgb: tuple[int, int, int]) -> None:
    """Draw a clean angled feather ornament on a high-res canvas."""
    r, g, b = rgb
    dark = (max(0, int(r * 0.68)), max(0, int(g * 0.72)), max(0, int(b * 0.78)), 255)
    main = (r, g, b, 245)
    light = (min(255, int(r + (255 - r) * 0.65)), min(255, int(g + (255 - g) * 0.65)), min(255, int(b + (255 - b) * 0.65)), 255)

    ang = -math.pi / 4.2
    ca, sa = math.cos(ang), math.sin(ang)

    def rot(x: float, y: float) -> tuple[float, float]:
        return cx + x * ca - y * sa, cy + x * sa + y * ca

    # Feather vane outline points (local coords, length ~ size)
    pts_local = [
        (-size * 0.55, 0),
        (-size * 0.25, -size * 0.20),
        (-size * 0.05, -size * 0.24),
        (size * 0.02, -size * 0.14),  # tiny notch
        (size * 0.14, -size * 0.23),
        (size * 0.42, -size * 0.16),
        (size * 0.58, 0),
        (size * 0.42, size * 0.16),
        (size * 0.12, size * 0.21),
        (-size * 0.12, size * 0.18),
        (-size * 0.35, size * 0.13),
    ]
    pts = [rot(x, y) for x, y in pts_local]
    # Soft white halo behind feather so it pops over any icon
    draw.polygon(pts, fill=main, outline=(255, 255, 255, 235), width=max(3, int(size * 0.05)))

    # Highlight upper half of vane
    hi_local = [
        (-size * 0.45, -size * 0.02),
        (-size * 0.05, -size * 0.18),
        (size * 0.45, -size * 0.08),
        (size * 0.50, 0),
        (-size * 0.45, 0),
    ]
    draw.polygon([rot(x, y) for x, y in hi_local], fill=light)

    # Central quill / shaft
    q1 = rot(-size * 0.68, size * 0.04)
    q2 = rot(size * 0.50, -size * 0.01)
    draw.line([q1, q2], fill=dark, width=max(2, int(size * 0.045)))


def generate_launcher_kit(
    hex_color: str = "#98D7E1",
    ornament: str = "feather",
    corner_ratio: float = 0.24,
) -> dict[str, bytes]:
    """Generate a cohesive launcher/ uniform icon kit (mask, bg, cover, folder)."""
    r, g, b = _hex_to_rgb(hex_color)
    scale = 4

    # 1. icon_mask.png (168x168)
    ms = 168 * scale
    mask_im = Image.new("RGBA", (ms, ms), (0, 0, 0, 0))
    mdraw = ImageDraw.Draw(mask_im)
    pad = int(ms * 0.045)
    rad = int((ms - 2 * pad) * corner_ratio)
    mdraw.rounded_rectangle([pad, pad, ms - pad, ms - pad], radius=rad, fill=(255, 255, 255, 255))
    buf = io.BytesIO()
    mask_im.resize((168, 168), Image.Resampling.LANCZOS).save(buf, format="PNG")
    mask_bytes = buf.getvalue()

    # 2. icon_bg_default.png (168x168) - soft tinted gradient rounded card
    bg_im = Image.new("RGBA", (ms, ms), (0, 0, 0, 0))
    grad = Image.new("RGBA", (ms, ms), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    top_c = (min(255, int(r + (255 - r) * 0.82)), min(255, int(g + (255 - g) * 0.82)), min(255, int(b + (255 - b) * 0.82)), 240)
    bot_c = (min(255, int(r + (255 - r) * 0.52)), min(255, int(g + (255 - g) * 0.52)), min(255, int(b + (255 - b) * 0.52)), 245)
    for y in range(ms):
        t = y / (ms - 1)
        cr = int(top_c[0] + (bot_c[0] - top_c[0]) * t)
        cg = int(top_c[1] + (bot_c[1] - top_c[1]) * t)
        cb = int(top_c[2] + (bot_c[2] - top_c[2]) * t)
        ca = int(top_c[3] + (bot_c[3] - top_c[3]) * t)
        gdraw.line([(0, y), (ms, y)], fill=(cr, cg, cb, ca))
    bg_mask = Image.new("L", (ms, ms), 0)
    ImageDraw.Draw(bg_mask).rounded_rectangle([pad, pad, ms - pad, ms - pad], radius=rad, fill=255)
    bg_im.paste(grad, (0, 0), bg_mask)
    buf = io.BytesIO()
    bg_im.resize((168, 168), Image.Resampling.LANCZOS).save(buf, format="PNG")
    bg_bytes = buf.getvalue()

    # Dark folder background
    fdark_im = Image.new("RGBA", (ms, ms), (0, 0, 0, 0))
    ImageDraw.Draw(fdark_im).rounded_rectangle(
        [pad, pad, ms - pad, ms - pad],
        radius=rad,
        fill=(max(20, int(r * 0.2)), max(24, int(g * 0.22)), max(30, int(b * 0.25)), 220),
        outline=(r, g, b, 190),
        width=int(ms * 0.022),
    )
    buf = io.BytesIO()
    fdark_im.resize((168, 168), Image.Resampling.LANCZOS).save(buf, format="PNG")
    fdark_bytes = buf.getvalue()

    # 3. icon_cover.png (240x240) - crisp theme frame + optional ornament
    cs = 240 * scale
    cov_im = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
    cdraw = ImageDraw.Draw(cov_im)
    cpad = int(cs * 0.045)
    crad = int((cs - 2 * cpad) * corner_ratio)
    # Outer accent border + subtle inner white highlight
    cdraw.rounded_rectangle(
        [cpad, cpad, cs - cpad, cs - cpad],
        radius=crad,
        outline=(r, g, b, 245),
        width=int(cs * 0.028),
    )
    ipad = cpad + int(cs * 0.022)
    cdraw.rounded_rectangle(
        [ipad, ipad, cs - ipad, cs - ipad],
        radius=max(8, crad - int(cs * 0.02)),
        outline=(255, 255, 255, 190),
        width=int(cs * 0.012),
    )

    if ornament == "feather":
        _draw_feather_badge(cdraw, cs * 0.77, cs * 0.77, cs * 0.23, (r, g, b))
    elif ornament == "sparkle":
        sx, sy, sr = cs * 0.78, cs * 0.22, cs * 0.09
        star = [
            (sx, sy - sr), (sx + sr * 0.28, sy - sr * 0.28),
            (sx + sr, sy), (sx + sr * 0.28, sy + sr * 0.28),
            (sx, sy + sr), (sx - sr * 0.28, sy + sr * 0.28),
            (sx - sr, sy), (sx - sr * 0.28, sy - sr * 0.28),
        ]
        cdraw.polygon(star, fill=(r, g, b, 250), outline=(255, 255, 255, 230))

    buf = io.BytesIO()
    cov_im.resize((240, 240), Image.Resampling.LANCZOS).save(buf, format="PNG")
    cover_bytes = buf.getvalue()

    kit: dict[str, bytes] = {
        "launcher/icon_mask.png": mask_bytes,
        "launcher/icon_bg_default.png": bg_bytes,
        "launcher/icon_pattern.png": bg_bytes,
        "launcher/icon_cover.png": cover_bytes,
        "launcher/folder_icon.png": bg_bytes,
        "launcher/app_folder_icon.png": bg_bytes,
        "launcher/icon_folder_light.png": bg_bytes,
        "launcher/icon_folder.png": fdark_bytes,
    }
    for n in ("one", "two", "three", "four", "five", "six", "seven"):
        kit[f"launcher/icon_bg_{n}.png"] = bg_bytes
    for i in range(1, 7):
        kit[f"launcher/folder_icon_cover_0{i}.png"] = cover_bytes
    return kit


def compile_nine_patch(
    raw_bytes: bytes,
    x_divs: tuple[int, int] | None = None,
    y_divs: tuple[int, int] | None = None,
    padding: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> bytes:
    """Compile a PNG into an Android binary .9.png with a valid npTc PNG chunk."""
    im = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    w, h = im.size

    # Detect source 9-patch (1px black guides on top & left) and strip 1px border
    top_black = [x for x in range(1, max(2, w - 1)) if im.getpixel((x, 0)) == (0, 0, 0, 255)]
    left_black = [y for y in range(1, max(2, h - 1)) if im.getpixel((0, y)) == (0, 0, 0, 255)]
    if top_black and left_black and w > 4 and h > 4:
        im = im.crop((1, 1, w - 1, h - 1))
        w, h = im.size
        if x_divs is None:
            x_divs = (max(1, top_black[0] - 1), min(w - 1, top_black[-1]))
        if y_divs is None:
            y_divs = (max(1, left_black[0] - 1), min(h - 1, left_black[-1]))
    else:
        if x_divs is None:
            x_divs = (max(1, w // 3), min(w - 1, max(w // 3 + 1, (w * 2) // 3)))
        if y_divs is None:
            y_divs = (max(1, h // 3), min(h - 1, max(h // 3 + 1, (h * 2) // 3)))

    png_buf = io.BytesIO()
    im.save(png_buf, format="PNG")
    png_data = png_buf.getvalue()

    # Build standard Android Res_png_9patch npTc chunk (84 bytes for 2x2 divs, 9 colors)
    # Match aapt2 exact offset fields (0x20000000, 0x28000000, 0x30000000)
    pl, pr, pt, pb = padding
    header = struct.pack(">BBBBIIIIIII", 0, 2, 2, 9, 0x20000000, 0x28000000, pl, pr, pt, pb, 0x30000000)
    divs = struct.pack(">IIII", x_divs[0], x_divs[1], y_divs[0], y_divs[1])
    colors = struct.pack(">9I", *([1] * 9))  # 1 = NO_COLOR
    payload = header + divs + colors
    nptc_chunk = struct.pack(">I", len(payload)) + b"npTc" + payload + struct.pack(">I", zlib.crc32(b"npTc" + payload) & 0xFFFFFFFF)

    # Insert npTc chunk right before IDAT
    pos = 8
    out = bytearray(png_data[:8])
    inserted = False
    while pos + 8 <= len(png_data):
        clen = struct.unpack_from(">I", png_data, pos)[0]
        ctype = png_data[pos + 4 : pos + 8]
        chunk_total = png_data[pos : pos + 12 + clen]
        if ctype == b"npTc":
            pos += 12 + clen
            continue
        if ctype == b"IDAT" and not inserted:
            out.extend(nptc_chunk)
            inserted = True
        out.extend(chunk_total)
        pos += 12 + clen
    return bytes(out)


def make_source_nine_patch(raw_bytes: bytes) -> bytes:
    """Wrap a PNG with OriginOS-safe 1px transparent border + 1px black stretch guides (NO binary npTc)."""
    im = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    w, h = im.size
    # If already a source 9-patch (has 1px black guides on top & left), normalize to RGBA and return
    top_black = [x for x in range(1, max(2, w - 1)) if im.getpixel((x, 0)) == (0, 0, 0, 255)]
    left_black = [y for y in range(1, max(2, h - 1)) if im.getpixel((0, y)) == (0, 0, 0, 255)]
    if top_black and left_black and w > 4 and h > 4:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    canvas = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    canvas.paste(im, (1, 1))
    px = canvas.load()
    for x in range(max(1, w // 3), min(w, max(w // 3 + 1, (w * 2) // 3)) + 1):
        px[x, 0] = (0, 0, 0, 255)
    for y in range(max(1, h // 3), min(h, max(h // 3 + 1, (h * 2) // 3)) + 1):
        px[0, y] = (0, 0, 0, 255)
    pad_x = min(18, max(2, w // 6))
    pad_y = min(14, max(2, h // 6))
    for x in range(pad_x, max(pad_x + 1, w - pad_x + 1)):
        px[x, h + 1] = (0, 0, 0, 255)
    for y in range(pad_y, max(pad_y + 1, h - pad_y + 1)):
        px[w + 1, y] = (0, 0, 0, 255)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def make_nine_patch_bubble(hex_color: str = "#98D7E1", right: bool = True) -> bytes:
    """Create an OriginOS-safe 1px source .9.png rounded SMS bubble (0 binary npTc)."""
    r, g, b = _hex_to_rgb(hex_color)
    w, h = 96, 72
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    fill = (r, g, b, 238) if right else (255, 255, 255, 240)
    outline = (max(0, r - 20), max(0, g - 20), max(0, b - 20), 220) if right else (r, g, b, 200)
    draw.rounded_rectangle([2, 2, w - 3, h - 3], radius=22, fill=fill, outline=outline, width=2)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return make_source_nine_patch(buf.getvalue())


def wrap_nine_patch(raw_bytes: bytes) -> bytes:
    """Wrap any uploaded PNG into an OriginOS-safe 1px source .9.png (0 binary npTc)."""
    return make_source_nine_patch(raw_bytes)



def make_circle_avatar(raw_bytes: bytes, size: int = 128) -> bytes:
    """Crop an image to a clean circle PNG (e.g. for Control Center Wi-Fi avatar)."""
    im = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    w, h = im.size
    side = min(w, h)
    im = im.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    r_ch, g_ch, b_ch, a_ch = im.split()
    im = Image.merge("RGBA", (r_ch, g_ch, b_ch, Image.composite(a_ch, Image.new("L", (size, size), 0), mask)))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()



def make_card_crop(raw_bytes: bytes, w: int = 960, h: int = 600, radius: int = 36) -> bytes:
    """Center-crop and round-corner an image for Wallet cards or Clock dial backgrounds."""
    im = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    iw, ih = im.size
    target_ratio = w / h
    cur_ratio = iw / ih
    if cur_ratio > target_ratio:
        nw = int(ih * target_ratio)
        im = im.crop(((iw - nw) // 2, 0, (iw + nw) // 2, ih))
    else:
        nh = int(iw / target_ratio)
        im = im.crop((0, (ih - nh) // 2, iw, (ih + nh) // 2))
    im = im.resize((w, h), Image.Resampling.LANCZOS)
    if radius > 0:
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        r_ch, g_ch, b_ch, a_ch = im.split()
        im = Image.merge("RGBA", (r_ch, g_ch, b_ch, Image.composite(a_ch, Image.new("L", (w, h), 0), mask)))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()



DEFAULT_VOLUME_ICON_LIGHT = "#54253e"
DEFAULT_VOLUME_ICON_DARK = "#9c6480"


def make_volume_glyph_icon(
    kind: str = "media",
    color: tuple[int, int, int, int] = (*_hex_to_rgb(DEFAULT_VOLUME_ICON_LIGHT), 255),
    size: int = 84,
) -> bytes:
    """Draw a rounded, single-color glyph for the system's SRC_IN tint."""
    s = size * 4
    unit = s / 24
    mask = Image.new("L", (s, s))
    draw = ImageDraw.Draw(mask)
    opacity = color[3]
    width = max(1, round(2.15 * unit))
    cap = width / 2

    def dot(x: float, y: float) -> None:
        x, y = x * unit, y * unit
        draw.ellipse((x - cap, y - cap, x + cap, y + cap), fill=opacity)

    def stroke(*points: tuple[float, float]) -> None:
        draw.line([(x * unit, y * unit) for x, y in points], fill=opacity, width=width)
        for x, y in points:
            dot(x, y)

    def arc(cx: float, cy: float, radius: float, start: int, end: int) -> None:
        outer = radius + cap / unit
        draw.arc(
            tuple(v * unit for v in (cx - outer, cy - outer, cx + outer, cy + outer)),
            start, end, fill=opacity, width=width,
        )
        for angle in (math.radians(start), math.radians(end)):
            dot(cx + radius * math.cos(angle), cy + radius * math.sin(angle))

    if kind in ("media", "media_mute"):
        stroke((4, 9), (7.5, 9), (12, 5.5), (12, 18.5), (7.5, 15), (4, 15), (4, 9))
        if kind == "media":
            arc(12, 12, 4.9, -38, 38)
            arc(12, 12, 8.6, -43, 43)
        else:
            stroke((16, 9.5), (21, 14.5))
            stroke((21, 9.5), (16, 14.5))
    elif kind in ("ring", "ring_mute"):
        arc(12, 10, 5, 180, 360)
        stroke((7, 10), (7, 13), (4.5, 17), (19.5, 17), (17, 13), (17, 10))
        stroke((12, 4), (12, 5))
        dot(12, 20.5)
        if kind == "ring_mute":
            draw.line([(3 * unit, 3 * unit), (21 * unit, 21 * unit)], fill=0, width=width * 2)
            stroke((3.5, 3.5), (20.5, 20.5))
    elif kind in ("noti", "noti_mute"):
        arc(6.5, 7.5, 3, 180, 270)
        arc(17.5, 7.5, 3, 270, 360)
        arc(17.5, 14.5, 3, 0, 90)
        stroke((6.5, 4.5), (17.5, 4.5))
        stroke((20.5, 7.5), (20.5, 14.5))
        stroke((3.5, 7.5), (3.5, 20), (8, 17.5), (17.5, 17.5))
        stroke((8, 9), (16, 9))
        stroke((8, 13), (13, 13))
    else:
        draw.ellipse(tuple(v * unit for v in (4.5, 5.5, 19.5, 20.5)), outline=opacity, width=width)
        stroke((12, 9.5), (12, 13), (14.5, 14.5))
        stroke((3.5, 6), (6.5, 3.5))
        stroke((17.5, 3.5), (20.5, 6))
        stroke((7.8, 18.7), (6.5, 21))
        stroke((16.2, 18.7), (17.5, 21))

    out = Image.new("RGBA", (size, size), color)
    out.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def make_qs_glyph_icon(kind: str = "wifi", color: tuple[int, int, int, int] = (255, 255, 255, 255), size: int = 144) -> bytes:
    """Draw a crisp transparent-BG Control Center glyph (survives Android SRC_IN tint without turning into a solid ball)."""
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(12, int(s * 0.068))
    cx, cy = s * 0.5, s * 0.5

    if kind == "wifi":
        # Crisp 3-arc Wi-Fi with 4-point star center dot (proportioned to system icon scale)
        cy_w = s * 0.68
        for rad in (s * 0.34, s * 0.23, s * 0.13):
            d.arc([cx - rad, cy_w - rad, cx + rad, cy_w + rad], start=226, end=314, fill=color, width=lw)
        # 4-point star dot at base
        sr = s * 0.06
        star = [
            (cx, cy_w - sr), (cx + sr * 0.35, cy_w - sr * 0.35),
            (cx + sr, cy_w), (cx + sr * 0.35, cy_w + sr * 0.35),
            (cx, cy_w + sr), (cx - sr * 0.35, cy_w + sr * 0.35),
            (cx - sr, cy_w), (cx - sr * 0.35, cy_w - sr * 0.35),
        ]
        d.polygon(star, fill=color)
    elif kind == "data":
        # Crisp twin up/down cellular arrows (proportioned to system icon scale)
        x1, x2 = s * 0.39, s * 0.61
        top, bot = s * 0.29, s * 0.71
        ah = s * 0.11
        # Up arrow (left)
        d.line([(x1, bot), (x1, top + lw * 0.4)], fill=color, width=lw)
        d.line([(x1 - ah, top + ah), (x1, top), (x1 + ah, top + ah)], fill=color, width=lw, joint="curve")
        # Down arrow (right)
        d.line([(x2, top), (x2, bot - lw * 0.4)], fill=color, width=lw)
        d.line([(x2 - ah, bot - ah), (x2, bot), (x2 + ah, bot - ah)], fill=color, width=lw, joint="curve")
    elif kind == "bt":
        # Crisp geometric Bluetooth rune (proportioned to system icon scale)
        bx = cx - s * 0.02
        top, bot = s * 0.24, s * 0.76
        rx = bx + s * 0.16
        lx = bx - s * 0.15
        d.line([(bx, top), (bx, bot)], fill=color, width=lw)
        d.line([(bx, top), (rx, s * 0.38), (lx, s * 0.62)], fill=color, width=lw, joint="curve")
        d.line([(lx, s * 0.38), (rx, s * 0.62), (bx, bot)], fill=color, width=lw, joint="curve")
    else:
        # 4-point star
        sr = s * 0.34
        star = [
            (cx, cy - sr), (cx + sr * 0.28, cy - sr * 0.28),
            (cx + sr, cy), (cx + sr * 0.28, cy + sr * 0.28),
            (cx, cy + sr), (cx - sr * 0.28, cy + sr * 0.28),
            (cx - sr, cy), (cx - sr * 0.28, cy - sr * 0.28),
        ]
        d.polygon(star, fill=color)

    out = im.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def make_clean_mms_card_9patch(hex_color: str = "#98D7E1") -> bytes:
    """Create a distortion-proof 1px source .9.png SMS smart card with non-stretch corner feather."""
    r, g, b = _hex_to_rgb(hex_color)
    w, h = 240, 180
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Soft frosted ice-white card + crisp theme border
    d.rounded_rectangle([4, 4, w - 5, h - 5], radius=28, fill=(244, 251, 253, 245), outline=(r, g, b, 235), width=4)
    # Subtle inner highlight
    d.rounded_rectangle([10, 10, w - 11, h - 11], radius=22, outline=(255, 255, 255, 210), width=2)
    # Small decorative feather strictly in top-right non-stretchable corner
    _draw_feather_badge(d, w - 34, 34, 34, (r, g, b))

    # Wrap with 1px transparent border + tight stretch guides ONLY in uniform center-left / lower-middle band
    canvas = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    canvas.paste(im, (1, 1))
    px = canvas.load()
    # Top stretch (X): x in [70..100] (completely away from top-right feather!)
    for x in range(70, 101):
        px[x, 0] = (0, 0, 0, 255)
    # Left stretch (Y): y in [90..120] (completely below top-right feather!)
    for y in range(90, 121):
        px[0, y] = (0, 0, 0, 255)
    # Content padding (bottom & right)
    for x in range(24, w - 22):
        px[x, h + 1] = (0, 0, 0, 255)
    for y in range(24, h - 22):
        px[w + 1, y] = (0, 0, 0, 255)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def make_clean_dialog_9patch(hex_color: str = "#7AC8D8", dark: bool = False) -> bytes:
    """Distortion-proof 1px source .9.png for vivo/vigour_dialog_full_light.9.png (BBKLauncher2 uninstall dialog)."""
    r, g, b = _hex_to_rgb(hex_color)
    w, h = 240, 240
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fill_rgba = (26, 36, 44, 246) if dark else (232, 248, 252, 248)
    inner_rgba = (255, 255, 255, 36) if dark else (255, 255, 255, 220)
    d.rounded_rectangle([6, 6, w - 7, h - 7], radius=52, fill=fill_rgba, outline=(r, g, b, 240), width=5)
    d.rounded_rectangle([14, 14, w - 15, h - 15], radius=44, outline=inner_rgba, width=2)
    # Corner feather badge safely outside center stretch strip
    _draw_feather_badge(d, w - 42, 42, 36, (r, g, b))

    canvas = Image.new("RGBA", (w + 2, h + 2), (0, 0, 0, 0))
    canvas.paste(im, (1, 1))
    px = canvas.load()
    # Stretch ONLY in the flat center-left strip so rounded corners & top-right feather never distort
    for x in range(88, 128):
        px[x, 0] = (0, 0, 0, 255)
    for y in range(110, 150):
        px[0, y] = (0, 0, 0, 255)
    for x in range(36, w - 34):
        px[x, h + 1] = (0, 0, 0, 255)
    for y in range(36, h - 34):
        px[w + 1, y] = (0, 0, 0, 255)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def make_switch_track_png(
    avatar_bytes: bytes | None,
    state: str = "on",
    hex_color: str = "#68C4D4",
) -> bytes:
    """Create 150x90 OriginOS VMoveBoolButton track PNG (matches vivo-res.apk bbox 12,12,138,78)."""
    r, g, b = _hex_to_rgb(hex_color)
    scale = 2
    W, H = 150 * scale, 90 * scale
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = 12 * scale, 12 * scale, 138 * scale, 78 * scale
    rad = (y1 - y0) // 2
    if state == "on":
        track_fill = (r, g, b, 255)
        border_col = (max(0, r - 25), max(0, g - 25), max(0, b - 25), 255)
    else:
        track_fill = (206, 222, 228, 255)
        border_col = (176, 198, 206, 255)
    d.rounded_rectangle([x0, y0, x1, y1], radius=rad, fill=track_fill, outline=border_col, width=3)

    if avatar_bytes:
        try:
            av_sz = 56 * scale
            av = Image.open(io.BytesIO(make_circle_avatar(avatar_bytes, size=av_sz))).convert("RGBA")
            # ON -> thumb sits on right, so avatar peeks on LEFT; OFF -> thumb on left, avatar peeks on RIGHT
            ax = (18 * scale) if state == "on" else (76 * scale)
            ay = 17 * scale
            im.alpha_composite(av, (ax, ay))
            d.ellipse([ax, ay, ax + av_sz, ay + av_sz], outline=(255, 255, 255, 220), width=3)
        except Exception:
            pass

    out = im.resize((150, 90), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def make_switch_thumb_9patch(hex_color: str = "#68C4D4", nine_patch: bool = True) -> bytes:
    """Create 60x60 crisp circular white switch thumb (0 npTc 1px .9.png or plain PNG)."""
    r, g, b = _hex_to_rgb(hex_color)
    scale = 2
    s = 60 * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Soft drop shadow + pure white thumb circle + delicate theme rim
    d.ellipse([8, 10, s - 8, s - 6], fill=(r, g, b, 55))
    d.ellipse([8, 8, s - 8, s - 8], fill=(255, 255, 255, 255), outline=(r, g, b, 110), width=3)
    thumb = im.resize((60, 60), Image.Resampling.LANCZOS)
    if not nine_patch:
        buf = io.BytesIO()
        thumb.save(buf, format="PNG")
        return buf.getvalue()
    canvas = Image.new("RGBA", (62, 62), (0, 0, 0, 0))
    canvas.paste(thumb, (1, 1))
    px = canvas.load()
    px[30, 0] = (0, 0, 0, 255)
    px[31, 0] = (0, 0, 0, 255)
    px[0, 30] = (0, 0, 0, 255)
    px[0, 31] = (0, 0, 0, 255)
    for i in range(6, 56):
        px[i, 61] = (0, 0, 0, 255)
        px[61, i] = (0, 0, 0, 255)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


BASE_REPLACEMENT_PACK_CANDIDATES = [
    Path(__file__).resolve().parent / "base_replacement_pack.itz",
    Path(__file__).resolve().parent / "vivo第三方主题工具应用等4个文件" / "vivo第三方主题工具应用" / "主题替换包.itz",
]
BASE_REPLACEMENT_PACK_PATH = BASE_REPLACEMENT_PACK_CANDIDATES[1]
SUPERCARD_OBF_MAP_PATH = Path(__file__).resolve().parent / "supercard_obf_map.json"


def find_base_replacement_pack(override_path: Path | None = None) -> Path | None:
    if override_path and override_path.exists():
        return override_path
    for p in BASE_REPLACEMENT_PACK_CANDIDATES:
        if p.exists():
            return p
    return None


def _to_webp_bytes(png_bytes: bytes, quality: int = 86) -> bytes:
    im = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    buf = io.BytesIO()
    im.save(buf, format="WEBP", quality=quality)
    return buf.getvalue()


def write_supercard_assets(
    mod: dict[str, bytes],
    raw_img: bytes,
    slot_list: list[tuple[str, str, str]],
    target_slot: str = "all",
) -> tuple[int, int]:
    """Write SuperCard assets for both readable filenames AND OriginOS 7 AAPT2 obfuscated filenames."""
    obf_map: dict[str, dict[str, list[int]]] = {}
    if SUPERCARD_OBF_MAP_PATH.exists():
        try:
            obf_map = json.loads(SUPERCARD_OBF_MAP_PATH.read_text(encoding="utf-8"))
        except Exception:
            obf_map = {}

    big_png = make_card_crop(raw_img, w=864, h=1398, radius=0)
    sml_png = make_card_crop(raw_img, w=216, h=328, radius=0)

    selected: list[tuple[str, str]] = []
    if target_slot == "all":
        selected = [(b, s) for b, s, _ in slot_list]
    else:
        matched = next(((b, s) for b, s, _ in slot_list if b == target_slot), None)
        if matched:
            selected = [matched]
        else:
            mod[target_slot] = big_png
            return 1, 0

    obf_count = 0
    for big_fn, sml_fn in selected:
        mod[big_fn] = big_png
        mod[sml_fn] = sml_png
        for key_name in (big_fn[:-4], sml_fn[:-4]):
            for obf_name, dims in obf_map.get(key_name, {}).items():
                tw, th = int(dims[0]), int(dims[1])
                crop = make_card_crop(raw_img, w=tw, h=th, radius=0)
                mod[obf_name] = _to_webp_bytes(crop) if obf_name.lower().endswith(".webp") else crop
                obf_count += 1
    return len(selected), obf_count


def make_lockscreen_pin_key_bg(hex_color: str = "#98D7E1", size: int = 240) -> bytes:
    """Create a crisp frosted glass circular PIN keypad button background."""
    r, g, b = _hex_to_rgb(hex_color)
    scale = 2
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = int(s * 0.05)
    d.ellipse([pad, pad, s - pad, s - pad], fill=(r, g, b, 68), outline=(255, 255, 255, 195), width=max(4, int(s * 0.018)))
    ipad = pad + max(6, int(s * 0.025))
    d.ellipse([ipad, ipad, s - ipad, s - ipad], outline=(r, g, b, 150), width=max(2, int(s * 0.01)))
    out = im.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def make_lockscreen_pin_dot(hex_color: str = "#98D7E1", filled: bool = True, size: int = 44) -> bytes:
    """Create a themed 4-point star/circle PIN entry dot (filled vs hollow)."""
    r, g, b = _hex_to_rgb(hex_color)
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = s * 0.5, s * 0.5
    if filled:
        sr = s * 0.42
        star = [
            (cx, cy - sr), (cx + sr * 0.34, cy - sr * 0.34),
            (cx + sr, cy), (cx + sr * 0.34, cy + sr * 0.34),
            (cx, cy + sr), (cx - sr * 0.34, cy + sr * 0.34),
            (cx - sr, cy), (cx - sr * 0.34, cy - sr * 0.34),
        ]
        d.polygon(star, fill=(r, g, b, 255), outline=(255, 255, 255, 240))
    else:
        pad = int(s * 0.14)
        d.ellipse([pad, pad, s - pad, s - pad], fill=(255, 255, 255, 36), outline=(r, g, b, 235), width=max(6, int(s * 0.09)))
    out = im.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def make_lockscreen_quick_bg(avatar_bytes: bytes | None = None, hex_color: str = "#98D7E1", size: int = 200) -> bytes:
    """Create circular frosted themed badge for lockscreen bottom-left/right quick shortcuts."""
    r, g, b = _hex_to_rgb(hex_color)
    scale = 2
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = int(s * 0.06)
    d.ellipse([pad, pad, s - pad, s - pad], fill=(r, g, b, 115), outline=(255, 255, 255, 215), width=max(5, int(s * 0.024)))
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(make_circle_avatar(avatar_bytes, size=s - pad * 4))).convert("RGBA")
            # Keep soft translucent veil so white shortcut icon stays legible on top
            veil = Image.new("RGBA", av.size, (r, g, b, 80))
            av = Image.alpha_composite(av, veil)
            im.alpha_composite(av, (pad * 2, pad * 2))
            d.ellipse([pad, pad, s - pad, s - pad], outline=(255, 255, 255, 225), width=max(5, int(s * 0.024)))
        except Exception:
            pass
    out = im.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def make_lockscreen_charge_icon(hex_color: str = "#98D7E1", dark: bool = False, size: int = 80) -> bytes:
    """Create a crisp themed lightning-feather charging indicator icon (80x80)."""
    r, g, b = _hex_to_rgb(hex_color)
    scale = 4
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    bolt_fill = (r, g, b, 255) if not dark else (min(255, r + 40), min(255, g + 35), min(255, b + 30), 255)
    bolt = [
        (s * 0.56, s * 0.08),
        (s * 0.24, s * 0.54),
        (s * 0.48, s * 0.54),
        (s * 0.42, s * 0.92),
        (s * 0.76, s * 0.44),
        (s * 0.52, s * 0.44),
    ]
    d.polygon(bolt, fill=bolt_fill, outline=(255, 255, 255, 230))
    out = im.resize((size, size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def make_lockscreen_unlock_indicator(hex_color: str = "#98D7E1") -> bytes:
    """Create 96x36 delicate chevron-star swipe-up unlock indicator."""
    r, g, b = _hex_to_rgb(hex_color)
    scale = 4
    w, h = 96 * scale, 36 * scale
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(8, int(h * 0.16))
    d.line([(w * 0.18, h * 0.72), (w * 0.50, h * 0.28), (w * 0.82, h * 0.72)], fill=(r, g, b, 240), width=lw, joint="curve")
    d.line([(w * 0.20, h * 0.72), (w * 0.50, h * 0.30), (w * 0.80, h * 0.72)], fill=(255, 255, 255, 235), width=max(4, lw // 2), joint="curve")
    out = im.resize((96, 36), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def build_replacement_pack(
    theme_itz_bytes: bytes,
    base_repl_path: Path | None = None,
    base_repl_bytes: bytes | None = None,
) -> bytes:
    """Automate the exact 7-step MT Manager workflow to produce a ready-to-use OriginOS 7 主题替换包.itz:
    1. Merge ALL entries of theme_itz_bytes into themeicon/icons.zip
    2. Merge preview/ and wallpaper/ of theme_itz_bytes into .dwd/c/o/m/b/b/k/t/h/e/m/e/T/简单白.itz
    3. Preserve all other entries of base 主题替换包.itz untouched.
    """
    if base_repl_bytes is None:
        resolved = find_base_replacement_pack(base_repl_path)
        if not resolved:
            raise FileNotFoundError("未找到基础底包 主题替换包.itz，请先在网页端上传底包或放置为 base_replacement_pack.itz")
        base_bytes = resolved.read_bytes()
    else:
        base_bytes = base_repl_bytes

    with zipfile.ZipFile(io.BytesIO(theme_itz_bytes), "r") as z_theme:
        theme_files = {
            info.filename: z_theme.read(info.filename)
            for info in z_theme.infolist()
            if not info.is_dir()
        }

    out_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base_bytes), "r") as z_base, zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as z_out:
        for info in z_base.infolist():
            fn = info.filename
            if fn == "themeicon/icons.zip":
                # Step 1-4: keep any untouched base files + overwrite/add ALL theme .itz entries
                icons_buf = io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(z_base.read(fn)), "r") as z_orig_icons, zipfile.ZipFile(icons_buf, "w", compression=zipfile.ZIP_DEFLATED) as z_new_icons:
                    written = set()
                    for k, v in theme_files.items():
                        z_new_icons.writestr(k, v)
                        written.add(k)
                    for oi in z_orig_icons.infolist():
                        if not oi.is_dir() and oi.filename not in written:
                            z_new_icons.writestr(oi.filename, z_orig_icons.read(oi.filename))
                z_out.writestr(fn, icons_buf.getvalue())
            elif fn.endswith("/T/简单白.itz"):
                # Step 5-7: keep non-preview/wallpaper base entries + overwrite/add preview/ and wallpaper/ from theme .itz
                jb_buf = io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(z_base.read(fn)), "r") as z_orig_jb, zipfile.ZipFile(jb_buf, "w", compression=zipfile.ZIP_DEFLATED) as z_new_jb:
                    written = set()
                    for k, v in theme_files.items():
                        if k.startswith(("preview/", "wallpaper/")):
                            z_new_jb.writestr(k, v)
                            written.add(k)
                    for oi in z_orig_jb.infolist():
                        if not oi.is_dir() and oi.filename not in written and not oi.filename.startswith(("preview/", "wallpaper/")):
                            z_new_jb.writestr(oi.filename, z_orig_jb.read(oi.filename))
                z_out.writestr(fn, jb_buf.getvalue())
            else:
                z_out.writestr(info, z_base.read(fn))

    return out_buf.getvalue()


SUPERCARD_PAY_SLOTS: list[tuple[str, str, str]] = [
    ("bg_paycard00.png", "bg_paycard_small_00.png", "付款卡 00"),
    ("bg_paycard01.png", "bg_paycard_small_01.png", "付款卡 01 (默认)"),
    ("bg_paycard01_iqoo.png", "bg_paycard_small_01_iqoo.png", "付款卡 01 (iQOO)"),
    ("bg_paycard02.png", "bg_paycard_small_02.png", "付款卡 02"),
    ("bg_paycard03.png", "bg_paycard_small_03.png", "付款卡 03"),
    ("bg_paycard04.png", "bg_paycard_small_04.png", "付款卡 04"),
    ("bg_paycard05.png", "bg_paycard_small_05.png", "付款卡 05"),
    ("bg_paycard06_iqoo.png", "bg_paycard_small_06_iqoo.png", "付款卡 06 (iQOO)"),
    ("bg_paycard07.png", "bg_paycard_small_07.png", "付款卡 07"),
    ("bg_paycard08.png", "bg_paycard_small_08.png", "付款卡 08 (OS7默认)"),
    ("bg_paycard09.png", "bg_paycard_small_09.png", "付款卡 09"),
    ("bg_paycard10.png", "bg_paycard_small_10.png", "付款卡 10"),
    ("bg_paycard11.png", "bg_paycard_small_11.png", "付款卡 11"),
    ("bg_paycard12.png", "bg_paycard_small_12.png", "付款卡 12"),
    ("bg_paycard13.png", "bg_paycard_small_13.png", "付款卡 13"),
    ("bg_paycard14.png", "bg_paycard_small_14.png", "付款卡 14"),
    ("bg_paycard15.png", "bg_paycard_small_15.png", "付款卡 15"),
]

SUPERCARD_CAMERA_SLOTS: list[tuple[str, str, str]] = [
    ("bg_camera_card01.png", "bg_camera_small_01.png", "镜头套件 01"),
    ("bg_camera_card02.png", "bg_camera_small_02.png", "镜头套件 02"),
    ("bg_camera_card03.png", "bg_camera_small_03.png", "镜头套件 03"),
    ("bg_camera_card04.png", "bg_camera_small_04.png", "镜头套件 04"),
    ("bg_camera_card04_iqoo.png", "bg_camera_small_04_iqoo.png", "镜头套件 04 (iQOO)"),
    ("bg_camera_card05.png", "bg_camera_small_05.png", "镜头套件 05"),
    ("bg_camera_card06_iqoo.png", "bg_camera_small_06_iqoo.png", "镜头套件 06 (iQOO)"),
    ("bg_camera_card07.png", "bg_camera_small_07.png", "镜头套件 07"),
    ("bg_camera_card08.png", "bg_camera_small_08.png", "镜头套件 08 (OS7默认)"),
    ("bg_camera_card09.png", "bg_camera_small_09.png", "镜头套件 09"),
]


GLOBAL_MODULE_PRESETS: dict[str, dict[str, Any]] = {
    "vivo": {
        "title": "系统全局框架 (弹窗 / 卡片 / 列表 / 背景)",
        "assets": {
            "vigour_window_bg_light.png": "全局窗口背景（浅色）",
            "vigour_window_bg_dark.png": "全局窗口背景（深色）",
            "vigour_window_settting_background_light.png": "设置页立绘背景（浅色）",
            "vigour_window_settting_background_dark.png": "设置页立绘背景（深色）",
            "vigour_dialog_bottom_light.9.png": "底部弹窗背景（浅色）",
            "vigour_dialog_bottom_dark.9.png": "底部弹窗背景（深色）",
            "vigour_dialog_close_btn_light.png": "弹窗关闭按钮（浅色）",
            "vigour_dialog_close_btn_dark.png": "弹窗关闭按钮（深色）",
            "vigour_preference_round_bg_light.9.png": "圆角卡片背景（浅色）",
            "vigour_preference_round_bg_dark.9.png": "圆角卡片背景（深色）",
            "vigour_list_search_bar_bg_light.9.png": "搜索栏背景（浅色）",
        },
    },
    "com.android.mms": {
        "title": "短信与智能通知卡片 (Mms)",
        "assets": {
            "sms_left_bg.9.png": "接收消息气泡（左侧）",
            "sms_left_pressed_bg.9.png": "接收消息气泡按压态",
            "sms_right_bg.9.png": "发送消息气泡（右侧浅色）",
            "sms_right_bg_night.9.png": "发送消息气泡（右侧深色）",
            "sms_right_pressed_bg.9.png": "发送消息气泡按压态",
            "sms_card_view_bg.9.png": "智能通知/验证码卡片背景",
            "sms_card_view_bg_pressed.9.png": "智能卡片按压背景",
            "ic_verify_core_default_mms.png": "验证码卡片默认图标",
            "ic_verify_core_icon.png": "验证码小图标",
        },
    },
    "com.vivo.originui.aar": {
        "title": "OriginUI 全局共享弹窗与底栏 (vdialog / sheet)",
        "assets": {
            "originui_dialog_background_rom13_5.png": "OriginUI 全局弹窗背景图 (ROM13.5+)",
            "originui_sheet_bg_rom14_0.png": "OriginUI 底部弹出面板背景图 (ROM14+)",
            "mtrl_dialog_background.png": "Material 弹窗背景图",
        },
    },
    "com.vivo.originui": {
        "title": "OriginUI 基础组件模块",
        "assets": {
            "originui_dialog_background_rom13_5.png": "OriginUI 全局弹窗背景图",
            "originui_sheet_bg_rom14_0.png": "OriginUI 底部面板背景图",
        },
    },
    "com.bbk.launcher2": {
        "title": "桌面与卸载底部弹窗 (BBKLauncher2)",
        "assets": {
            "originui_dialog_background_rom13_5.9.png": "底部卸载/确认弹窗背景 (ROM13.5+)",
            "originui_sheet_bg_rom14_0.9.png": "底部弹出面板背景 (ROM14+)",
            "vigour_dialog_full_light.9.png": "浅色弹窗全背景",
            "launcher_vigour_popup_background.9.png": "桌面长按菜单气泡背景（浅色）",
            "launcher_vigour_popup_background_night.9.png": "桌面长按菜单气泡背景（深色）",
        },
    },
    "com.vivo.systemuiplugin": {
        "title": "控制中心插件 (OriginOS 5/6/7 SuperQS & 音量条)",
        "assets": {
            "vivo_super_qs_wifi_on.png": "控制中心 Wi-Fi 大头 (开启)",
            "vivo_super_qs_wifi_on4.png": "控制中心 Wi-Fi 大头 (满格)",
            "vivo_super_qs_wifi_off.png": "控制中心 Wi-Fi 大头 (关闭)",
            "vivo_super_qs_data_switch_on.png": "控制中心移动数据 (开启)",
            "vivo_super_qs_data_switch_off.png": "控制中心移动数据 (关闭)",
            "vivo_super_qs_bluetooth_on.png": "控制中心蓝牙 (开启)",
            "vivo_super_qs_bluetooth_off.png": "控制中心蓝牙 (关闭)",
            "vivo_super_qs_airplane_on.png": "控制中心飞行模式 (开启)",
            "vivo_super_qs_location_on.png": "控制中心定位 (开启)",
            "vivo_super_qs_flashlight_on.png": "控制中心手电筒 (开启)",
            "vivo_super_qs_hotspot_on.png": "控制中心个人热点 (开启)",
            "vivo_volume_ic_audio_vol_new.png": "音量条 - 媒体图标",
            "vivo_volume_ic_audio_ring_notif_new.png": "音量条 - 铃声图标",
            "vivo_volume_ic_audio_noti_new.png": "音量条 - 通知图标",
            "vivo_volume_ic_audio_clock_new.png": "音量条 - 闹钟图标",
            "vivo_footer_volume_bg.png": "音量面板背景",
            "control_center_music_qs_tile_bg.png": "控制中心音乐卡片背景",
        },
    },
    "com.android.BBKClock": {
        "title": "世界时钟与闹钟 (BBKClock)",
        "assets": {
            "clock_plate_bg_circle.png": "世界时钟表盘圆形底图",
            "clock_plate_normal_bg_circle.png": "时钟常态表盘底图",
            "clock_plate_day_6_0.png": "时钟刻度表盘 (OS6/7)",
            "clock_plate_day_2_0.png": "时钟刻度表盘 (兼容版)",
            "clock_hand_hour_day_6_0.png": "时针 (OS6/7)",
            "clock_hand_minute_day_6_0.png": "分针 (OS6/7)",
        },
    },
    "com.vivo.timerwidget": {
        "title": "桌面时钟小组件 (TimerWidget)",
        "assets": {},
    },
    "com.vivo.card": {
        "title": "超级卡包 · 付款卡与镜头套件 (SuperCard)",
        "assets": {
            **{big: f"{lbl} 大图" for big, _, lbl in SUPERCARD_PAY_SLOTS},
            **{sml: f"{lbl} 缩略图" for _, sml, lbl in SUPERCARD_PAY_SLOTS},
            **{big: f"{lbl} 大图" for big, _, lbl in SUPERCARD_CAMERA_SLOTS},
            **{sml: f"{lbl} 缩略图" for _, sml, lbl in SUPERCARD_CAMERA_SLOTS},
            "bg_memory_card_holder_cn.png": "记忆卡包底图",
            "bg_staging_card_holder.png": "中转卡包底图",
        },
    },
    "com.vivo.wallet": {
        "title": "钱包与卡包 (多张可选卡面背景)",
        "assets": {
            "card_bag_open_card_bg.png": "卡包开启卡背景 (卡位1)",
            "bank_card_add_card_bg.png": "添加银行卡背景 (卡位2)",
            "bank_card_bg_blue.png": "银行卡背景 - 蓝 (卡位3)",
            "bank_card_bg_green.png": "银行卡背景 - 绿 (卡位4)",
            "bank_card_bg_red.png": "银行卡背景 - 红 (卡位5)",
            "bank_card_bg_yellow.png": "银行卡背景 - 黄 (卡位6)",
            "bank_card_bg_gray.png": "银行卡背景 - 灰 (卡位7)",
            "buscard_select_card_bg.png": "公交卡选卡背景",
            "buscard_custom_select_card_bg.png": "公交卡自定义背景",
            "ic_nfccard_bg.png": "NFC 门禁卡背景",
            "id_card_bg.png": "电子证件卡背景",
            "home_personal_card_bg.png": "个人卡片背景",
        },
    },
    "com.android.contacts": {
        "title": "拨号盘与联系人 (Contacts)",
        "assets": {
            "dialpad_bg.png": "拨号盘背景图",
            "contact_bg.png": "联系人列表背景",
        },
    },
    "com.android.incallui": {
        "title": "通话与来电界面 (InCallUI)",
        "assets": {
            "incall_bg.png": "通话界面背景",
        },
    },
    "com.android.bbkcalculator": {
        "title": "计算器 (Calculator)",
        "assets": {
            "calculator_bg.png": "计算器背景图",
        },
    },
    "com.vivo.weather": {
        "title": "天气 (Weather)",
        "assets": {
            "weather_bg.png": "天气背景图",
        },
    },
    "com.android.packageinstaller": {
        "title": "安装与卸载弹窗 (PackageInstaller)",
        "assets": {},
    },
}


class ThemeProject:
    """In-memory representation of an opened .itz theme package."""

    def __init__(self) -> None:
        self.source_name: str = ""
        self.entries: dict[str, bytes] = {}
        self.modules: dict[str, dict[str, bytes]] = {}
        self.metadata: dict[str, str] = {
            "id": "1000000000000",
            "title": "My OriginOS Theme",
            "author": "Designer",
            "designer": "Designer",
            "version": "1.0.0",
            "sysromver": "17.0",
            "description": "",
        }
        self._raw_description_xml: str = ""

    def new_blank(
        self,
        title: str = "我的 OriginOS 主题",
        author: str = "Designer",
        sysromver: str = "17.0",
        base_color: str = "#98D7E1",
    ) -> None:
        """Initialize a clean .itz theme project with solid-color fills for empty slots."""
        ts = str(int(time.time() * 1000))
        self.source_name = f"{title}.itz"
        self.entries.clear()
        self.modules.clear()
        self.metadata = {
            "id": ts,
            "title": title,
            "author": author,
            "designer": author,
            "version": "1.0.0",
            "sysromver": sysromver,
            "description": "Created with OriginOS .itz Theme Studio",
        }
        self._raw_description_xml = ""

        def solid_jpg(w: int, h: int, rgb: tuple[int, int, int]) -> bytes:
            b = io.BytesIO()
            Image.new("RGB", (w, h), rgb).save(b, format="JPEG", quality=92)
            return b.getvalue()

        def solid_png(w: int, h: int, rgba: tuple[int, int, int, int]) -> bytes:
            b = io.BytesIO()
            Image.new("RGBA", (w, h), rgba).save(b, format="PNG")
            return b.getvalue()

        r, g, b = _hex_to_rgb(base_color)
        wp_bytes = solid_jpg(1080, 2400, (r, g, b))
        self.entries["wallpaper/default_wallpaper.jpg"] = wp_bytes
        self.entries["wallpaper/default_lock_wallpaper.jpg"] = wp_bytes

        prev_bytes = solid_jpg(540, 1200, (r, g, b))
        for i in range(3):
            self.entries[f"preview/preview_lockscreen_{i}.jpg"] = prev_bytes

        # Launcher uniform kit (#98D7E1 + feather)
        for k, v in generate_launcher_kit(hex_color=base_color, ornament="feather").items():
            self.entries[k] = v

        self.entries["launcher/iconsize.xml"] = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<ICONSIZE>\n"
            "\t<width>52</width>\n"
            "\t<height>52</height>\n"
            "\t<leftoffset>0</leftoffset>\n"
            "\t<topoffset>0</topoffset>\n"
            "\t<foldericonwidth>46</foldericonwidth>\n"
            "\t<foldericonheight>46</foldericonheight>\n"
            "\t<folderpreviewcolumn>3</folderpreviewcolumn>\n"
            "\t<folderpreviewrow>3</folderpreviewrow>\n"
            "\t<folderpreviewpadding>0</folderpreviewpadding>\n"
            "\t<version>1</version>\n"
            "</ICONSIZE>\n"
        ).encode("utf-8")
        self.entries["launcher/app_group_info.xml"] = (
            "<AppGroupIcon>\n"
            '  <dimen name="app_group_display_size">136px</dimen>\n'
            '  <dimen name="icon_display_size">128px</dimen>\n'
            '  <dimen name="app_group_icon_display_size">50px</dimen>\n'
            '  <dimen name="app_group_icon_back_plane_size">78px</dimen>\n'
            "</AppGroupIcon>\n"
        ).encode("utf-8")

        # vivo global module: solid light/dark backgrounds & bottom dialogs
        light_bg = solid_png(1080, 2400, (242, 247, 249, 255))
        dark_bg = solid_png(1080, 2400, (20, 25, 32, 255))
        dlg_light = compile_nine_patch(
            make_card_crop(solid_png(960, 720, (255, 255, 255, 245)), w=960, h=720, radius=48),
            x_divs=(420, 540),
            y_divs=(320, 400),
        )
        dlg_dark = compile_nine_patch(
            make_card_crop(solid_png(960, 720, (30, 36, 46, 245)), w=960, h=720, radius=48),
            x_divs=(420, 540),
            y_divs=(320, 400),
        )
        self.modules["vivo"] = {
            "theme_values.xml": (
                '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
                "<vivo_theme_values>\n"
                '    <color name="originui_vclickdrawable_card_click_background_global_theme">#00ffffff</color>\n'
                "</vivo_theme_values>\n"
            ).encode("utf-8"),
            "vigour_window_bg_light.png": light_bg,
            "vigour_window_settting_background_light.png": light_bg,
            "vigour_window_bg_dark.png": dark_bg,
            "vigour_window_settting_background_dark.png": dark_bg,
            "vigour_dialog_bottom_light.9.png": dlg_light,
            "vigour_dialog_bottom_dark.9.png": dlg_dark,
        }

        self.modules["com.android.settings"] = {
            "theme_values.xml": (
                '<?xml version="1.0" encoding="utf-8" standalone="yes" ?>\n'
                "<VIVO_Theme_Values>\n"
                '  <color name="origin_settings_bg_rom13">#00000000</color>\n'
                "</VIVO_Theme_Values>\n"
            ).encode("utf-8"),
        }

        # MMS solid bubbles
        left_b = make_nine_patch_bubble(base_color, right=False)
        right_b = make_nine_patch_bubble(base_color, right=True)
        self.modules["com.android.mms"] = {
            "sms_left_bg.9.png": left_b,
            "sms_left_pressed_bg.9.png": left_b,
            "sms_right_bg.9.png": right_b,
            "sms_right_bg_night.9.png": right_b,
            "sms_right_pressed_bg.9.png": right_b,
        }

        # Control Center colors & solid circle tile avatars
        self.set_systemui_colors(
            {
                "qs_main_color": base_color,
                "switcher_text_light": base_color,
                "statusbar_text_color": "#000000",
                "battery_text_black": "#ffffff",
                "battery_text_white": "#000000",
            }
        )
        circle_tile = make_circle_avatar(solid_png(128, 128, (r, g, b, 255)), size=128)
        plugin_mod = self.modules.setdefault("com.vivo.systemuiplugin", {})
        for i in range(0, 5):
            plugin_mod[f"ic_wifi_{i}.png"] = circle_tile
            plugin_mod[f"ic_mobile_{i}_4_bar.png"] = circle_tile
        for i in range(0, 6):
            plugin_mod[f"ic_mobile_{i}_5_bar.png"] = circle_tile
        plugin_mod["vivo_ic_qs_wifi_detail_connected.png"] = circle_tile
        plugin_mod["vivo_ic_qs_cellular_detail.png"] = circle_tile
        plugin_mod["ic_bluetooth_connected.png"] = circle_tile
        plugin_mod["vivo_ic_qs_bluetooth_detail.png"] = circle_tile

        # SuperCard (com.vivo.card) Payment Card & Camera Kit solid backgrounds
        card_mod = self.modules.setdefault("com.vivo.card", {})
        pay_big = make_card_crop(solid_png(864, 1398, (r, g, b, 255)), w=864, h=1398, radius=0)
        pay_sml = make_card_crop(solid_png(216, 328, (r, g, b, 255)), w=216, h=328, radius=0)
        for big, sml, _ in SUPERCARD_PAY_SLOTS:
            card_mod[big] = pay_big
            card_mod[sml] = pay_sml
        cam_big = make_card_crop(solid_png(864, 1398, (max(0, r - 24), max(0, g - 16), b, 255)), w=864, h=1398, radius=0)
        cam_sml = make_card_crop(solid_png(216, 328, (max(0, r - 24), max(0, g - 16), b, 255)), w=216, h=328, radius=0)
        for big, sml, _ in SUPERCARD_CAMERA_SLOTS:
            card_mod[big] = cam_big
            card_mod[sml] = cam_sml

        # Wallet solid card slots
        wallet_colors = {
            "card_bag_open_card_bg.png": (r, g, b, 255),
            "bank_card_add_card_bg.png": (167, 216, 222, 255),
            "bank_card_bg_blue.png": (127, 190, 208, 255),
            "bank_card_bg_green.png": (140, 211, 197, 255),
            "bank_card_bg_red.png": (232, 165, 165, 255),
            "bank_card_bg_yellow.png": (234, 208, 140, 255),
            "bank_card_bg_gray.png": (184, 196, 204, 255),
            "buscard_select_card_bg.png": (145, 202, 216, 255),
            "ic_nfccard_bg.png": (160, 210, 220, 255),
        }
        self.modules["com.vivo.wallet"] = {
            fn: make_card_crop(solid_png(960, 600, col), w=960, h=600, radius=36)
            for fn, col in wallet_colors.items()
        }

        # Clock solid dial & background
        self.modules["com.android.BBKClock"] = {
            "clock_dial.png": make_circle_avatar(solid_png(600, 600, (238, 247, 249, 255)), size=600),
            "world_clock_bg.png": solid_png(1080, 1920, (242, 247, 249, 255)),
        }

    def load_bytes(self, raw_bytes: bytes, name: str = "theme.itz") -> None:
        self.source_name = name
        self.entries.clear()
        self.modules.clear()

        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zin:
            for item in zin.infolist():
                if item.is_dir():
                    continue
                data = zin.read(item.filename)
                # Detect any root-level nested ZIP module (e.g. vivo, com.android.mms, com.vivo.wallet, etc.)
                if "/" not in item.filename and not item.filename.lower().endswith((".zip", ".itz", ".apk", ".jar")) and data[:2] == b"PK":
                    try:
                        mod_entries: dict[str, bytes] = {}
                        with zipfile.ZipFile(io.BytesIO(data), "r") as mzin:
                            for mitem in mzin.infolist():
                                if not mitem.is_dir():
                                    mod_entries[mitem.filename] = mzin.read(mitem.filename)
                        self.modules[item.filename] = mod_entries
                        continue
                    except zipfile.BadZipFile:
                        pass
                self.entries[item.filename] = data

        if "description.xml" in self.entries:
            self._parse_description(self.entries["description.xml"].decode("utf-8", errors="replace"))

    def _parse_description(self, xml_text: str) -> None:
        self._raw_description_xml = xml_text
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return

        def txt(xpath: str, default: str = "") -> str:
            el = root.find(xpath)
            return (el.text or "").strip() if el is not None else default

        self.metadata["id"] = txt("id", self.metadata["id"])
        self.metadata["version"] = txt("version", "1.0.0")
        self.metadata["title"] = txt("titles/title", "Untitled")
        self.metadata["author"] = txt("authors/author", "Designer")
        self.metadata["designer"] = txt("designers/designer", self.metadata["author"])
        self.metadata["description"] = txt("descriptions/description", "")
        self.metadata["sysromver"] = txt("sysromver", "16.0")

    def build_description_xml(self) -> bytes:
        def esc(s: str) -> str:
            return s.replace("]]>", "]]]]><![CDATA[>")

        xml = (
            '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
            "<theme>\n"
            f'  <id>{self.metadata.get("id", "1000000000000")}</id>\n'
            f'  <version><![CDATA[{esc(self.metadata.get("version", "1.0.0"))}]]></version>\n'
            "  <titles>\n"
            f'    <title locale="zh_CN"><![CDATA[{esc(self.metadata.get("title", ""))}]]></title>\n'
            "  </titles>\n"
            "  <authors>\n"
            f'    <author locale="zh_CN"><![CDATA[{esc(self.metadata.get("author", ""))}]]></author>\n'
            "  </authors>\n"
            "  <designers>\n"
            f'    <designer locale="zh_CN"><![CDATA[{esc(self.metadata.get("designer", ""))}]]></designer>\n'
            "  </designers>\n"
            "  <descriptions>\n"
            f'    <description locale="zh_CN"><![CDATA[{esc(self.metadata.get("description", ""))}]]></description>\n'
            "  </descriptions>\n"
            '  <tool locale="zh_CN"><![CDATA[03]]></tool>\n'
            '  <toolversion><![CDATA[03v4.0.0]]></toolversion>\n'
            f'  <time>{self.metadata.get("id", "1000000000000")}</time>\n'
            f'  <sysromver><![CDATA[{esc(self.metadata.get("sysromver", "16.0"))}]]></sysromver>\n'
            "</theme>\n"
        )
        return xml.encode("utf-8")

    def list_icons(self) -> list[str]:
        return sorted(
            k[6:] for k in self.entries if k.startswith("icons/") and k.lower().endswith(".png")
        )

    def list_launcher_icons(self) -> list[str]:
        return sorted(
            k for k in self.entries if k.startswith("launcher/") and k.lower().endswith(".png")
        )

    def get_launcher_config(self) -> dict[str, int]:
        cfg = {
            "width": 52,
            "height": 52,
            "leftoffset": 0,
            "topoffset": 0,
            "foldericonwidth": 46,
            "foldericonheight": 46,
        }
        raw = self.entries.get("launcher/iconsize.xml")
        if not raw:
            return cfg
        try:
            root = ET.fromstring(raw.decode("utf-8-sig", errors="replace"))
            for key in cfg:
                el = root.find(key)
                if el is not None and el.text and el.text.strip().lstrip("-").isdigit():
                    cfg[key] = int(el.text.strip())
        except Exception:
            pass
        return cfg

    def set_launcher_config(self, cfg: dict[str, int]) -> None:
        cur = self.get_launcher_config()
        for key in cur:
            if key in cfg:
                cur[key] = int(cfg[key])
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<ICONSIZE>\n"
            f"\t<width>{cur['width']}</width>\n"
            f"\t<height>{cur['height']}</height>\n"
            f"\t<leftoffset>{cur['leftoffset']}</leftoffset>\n"
            f"\t<topoffset>{cur['topoffset']}</topoffset>\n"
            f"\t<foldericonwidth>{cur['foldericonwidth']}</foldericonwidth>\n"
            f"\t<foldericonheight>{cur['foldericonheight']}</foldericonheight>\n"
            "\t<folderpreviewcolumn>3</folderpreviewcolumn>\n"
            "\t<folderpreviewrow>3</folderpreviewrow>\n"
            "\t<folderpreviewpadding>0</folderpreviewpadding>\n"
            "\t<version>1</version>\n"
            "</ICONSIZE>\n"
        )
        self.entries["launcher/iconsize.xml"] = xml.encode("utf-8")

    def list_settings_icons(self) -> list[str]:
        mod = self.modules.get("com.android.settings", {})
        return sorted(k for k in mod if k.lower().endswith(".png"))

    def list_systemui_icons(self) -> list[str]:
        s1 = set(self.modules.get("com.android.systemui", {}).keys())
        s2 = set(self.modules.get("com.vivo.systemuiplugin", {}).keys())
        return sorted(k for k in (s1 | s2) if k.lower().endswith(".png"))

    def get_systemui_colors(self) -> dict[str, str]:
        """Read key SystemUI, QuickSettings & Volume colors from theme_values.xml."""
        colors = {
            "qs_main_color": "#98d7e1",
            "switcher_text_light": "#98d7e1",
            "statusbar_text_color": "#000000",
            "battery_text_black": "#ffffff",
            "battery_text_white": "#000000",
            "volume_progress_color": "#98d7e1",
            "volume_bg_color": "#e4f4f7",
            "volume_icon_color": DEFAULT_VOLUME_ICON_LIGHT,
            "volume_icon_color_dark": DEFAULT_VOLUME_ICON_DARK,
        }
        for mod_name, mapping in (
            (
                "com.vivo.systemuiplugin",
                {
                    "vivo_qs_tile_whole_theme_main_color": "qs_main_color",
                    "vivo_volume_whole_theme_progress_color_light": "volume_progress_color",
                    "vivo_volume_whole_theme_background_color_light": "volume_bg_color",
                    "vivo_volume_whole_theme_icon_color_light": "volume_icon_color",
                    "vivo_volume_whole_theme_icon_color_dark": "volume_icon_color_dark",
                },
            ),
            (
                "com.android.systemui",
                {
                    "vivo_switcher_text_light": "switcher_text_light",
                    "vivo_statusbar_expended_text_color": "statusbar_text_color",
                    "vivo_battery_text_color_black": "battery_text_black",
                    "vivo_battery_text_color_white": "battery_text_white",
                },
            ),
        ):
            xml_bytes = self.modules.get(mod_name, {}).get("theme_values.xml")
            if not xml_bytes:
                continue
            text = xml_bytes.decode("utf-8", errors="replace")
            for xml_key, dict_key in mapping.items():
                m = re.search(
                    rf'<color\s+name="{re.escape(xml_key)}"[^>]*>#(?:[0-9a-fA-F]{{2}})?([0-9a-fA-F]{{6}})</color>',
                    text,
                )
                if m:
                    colors[dict_key] = "#" + m.group(1).lower()
        return colors

    def write_volume_glyphs(self) -> None:
        """Generate the volume icons in both modules using the project's tint colors."""
        colors = self.get_systemui_colors()
        glyphs = {}
        for suffix, key in (("", "volume_icon_color"), ("_dark", "volume_icon_color_dark")):
            rgba = (*_hex_to_rgb(colors[key]), 255)
            for resource, kind in (
                ("vol", "media"),
                ("vol_mute", "media_mute"),
                ("ring_notif", "ring"),
                ("noti", "noti"),
                ("clock", "clock"),
            ):
                glyphs[f"vivo_volume_ic_audio_{resource}_new{suffix}.png"] = make_volume_glyph_icon(kind, rgba)

        for module in ("com.vivo.systemuiplugin", "com.android.systemui"):
            self.modules.setdefault(module, {}).update(glyphs)

    def get_settings_strings(self) -> list[dict[str, str]]:
        """Read overridden string resources from com.android.settings/theme_values.xml."""
        overrides: dict[str, str] = {}
        xml_bytes = self.modules.get("com.android.settings", {}).get("theme_values.xml")
        if xml_bytes:
            text = xml_bytes.decode("utf-8", errors="replace")
            for m in re.finditer(r'<string\s+name="([^"]+)"[^>]*>(.*?)</string>', text, re.S):
                overrides[m.group(1)] = m.group(2)

        result = []
        for item in SETTINGS_EDITABLE_STRINGS:
            key = item["key"]
            result.append(
                {
                    "key": key,
                    "label": item["label"],
                    "default": item["default"],
                    "value": overrides.get(key, item["default"]),
                    "overridden": key in overrides,
                }
            )
        return result

    def set_settings_strings(self, values: dict[str, str]) -> None:
        """Write custom string overrides into com.android.settings/theme_values.xml."""
        mod = self.modules.setdefault("com.android.settings", {})
        defaults = {item["key"]: item["default"] for item in SETTINGS_EDITABLE_STRINGS}

        def xml_esc(s: str) -> str:
            return (
                s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

        lines = [
            '<?xml version="1.0" encoding="utf-8" standalone="yes" ?>',
            "<VIVO_Theme_Values>",
        ]
        for key, val in values.items():
            val_clean = val.strip()
            if val_clean and val_clean != defaults.get(key):
                lines.append(f'  <string name="{xml_esc(key)}">{xml_esc(val_clean)}</string>')
        lines.append('  <color name="origin_settings_bg_rom13">#00000000</color>')
        lines.append("</VIVO_Theme_Values>\n")
        mod["theme_values.xml"] = "\n".join(lines).encode("utf-8")

    def set_systemui_colors(self, colors: dict[str, str]) -> None:
        """Update or write SystemUI, QuickSettings & OriginOS 7 Volume whole_theme colors."""
        def norm_hex(val: str, alpha: str = "ff") -> str:
            v = val.strip().lstrip("#")
            if len(v) == 6:
                return f"#{alpha}{v.lower()}"
            if len(v) == 8:
                return "#" + v.lower()
            return f"#{alpha}98d7e1"

        cur = self.get_systemui_colors()
        qs_hex = norm_hex(colors.get("qs_main_color", cur["qs_main_color"]))
        sw_hex = norm_hex(colors.get("switcher_text_light", cur["switcher_text_light"]))
        sb_hex = norm_hex(colors.get("statusbar_text_color", cur["statusbar_text_color"]))
        bat_b = norm_hex(colors.get("battery_text_black", cur["battery_text_black"]))
        bat_w = norm_hex(colors.get("battery_text_white", cur["battery_text_white"]))
        vol_prog = norm_hex(colors.get("volume_progress_color", colors.get("qs_main_color", cur["volume_progress_color"])))
        vol_bg_light = norm_hex(colors.get("volume_bg_color", cur["volume_bg_color"]), alpha="eb")
        vol_ic_light = norm_hex(colors.get("volume_icon_color", cur["volume_icon_color"]))
        vol_ic_dark = norm_hex(colors.get("volume_icon_color_dark", cur["volume_icon_color_dark"]))

        plugin_mod = self.modules.setdefault("com.vivo.systemuiplugin", {})
        plugin_mod["theme_values.xml"] = (
            '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
            "<vivo_theme_values>\n"
            '    <bool name="new_style">true</bool>\n'
            '    <bool name="is_color_style">true</bool>\n'
            f'    <color name="vivo_qs_tile_whole_theme_main_color">{qs_hex}</color>\n'
            f'    <color name="vivo_qs_tile_whole_theme_main_color_local">{qs_hex}</color>\n'
            f'    <color name="vivo_qs_tile_whole_theme_icon_color_active">{qs_hex}</color>\n'
            f'    <color name="vivo_qs_tile_whole_theme_icon_color_active_local">{qs_hex}</color>\n'
            f'    <color name="vivo_qs_tile_whole_theme_22_bg_color_active">{qs_hex}</color>\n'
            f'    <color name="vivo_qs_tile_color_blue">{qs_hex}</color>\n'
            f'    <color name="vivo_qs_tile_color_blue_normal">{qs_hex}</color>\n'
            f'    <color name="vivo_qs_tile_icon_color_them_default_on8">{qs_hex}</color>\n'
            f'    <color name="vivo_qs_tile_tint_active">{qs_hex}</color>\n'
            '    <color name="vivo_qs_tile_whole_theme_11_bg_color_active">#e6f2fafc</color>\n'
            '    <color name="vivo_qs_tile_whole_theme_12_bg_color_active">#e6f2fafc</color>\n'
            '    <color name="vivo_qs_tile_whole_theme_11_bg_color_inactive">#4098d7e1</color>\n'
            '    <color name="vivo_qs_tile_whole_theme_special_bg_color_inactive">#4098d7e1</color>\n'
            f'    <color name="vivo_volume_whole_theme_progress_color_light">{vol_prog}</color>\n'
            f'    <color name="vivo_volume_whole_theme_progress_color_dark">{vol_prog}</color>\n'
            f'    <color name="vivo_volume_whole_theme_background_color_light">{vol_bg_light}</color>\n'
            '    <color name="vivo_volume_whole_theme_background_color_dark">#e6243238</color>\n'
            f'    <color name="vivo_volume_whole_theme_icon_color_light">{vol_ic_light}</color>\n'
            f'    <color name="vivo_volume_whole_theme_icon_color_dark">{vol_ic_dark}</color>\n'
            '    <color name="vivo_volume_whole_theme_sheet_bg_color_light">#f2eef8fa</color>\n'
            '    <color name="vivo_volume_whole_theme_sheet_bg_color_dark">#f21b262c</color>\n'
            '    <color name="vivo_volume_whole_theme_sheet_font_color_light">#cc163840</color>\n'
            '    <color name="vivo_volume_whole_theme_sheet_font_color_dark">#e6eaf9fc</color>\n'
            '    <color name="vivo_volume_whole_theme_tip_bg_color_light">#f5f2fafc</color>\n'
            '    <color name="vivo_volume_whole_theme_tip_bg_color_dark">#f5243238</color>\n'
            '    <color name="vivo_volume_whole_theme_tip_font_color_light">#ff163840</color>\n'
            '    <color name="vivo_volume_whole_theme_tip_font_color_dark">#ffeaf9fc</color>\n'
            f'    <color name="vivo_volume_whole_theme_tip_icon_color_light">{vol_ic_light}</color>\n'
            f'    <color name="vivo_volume_whole_theme_tip_icon_color_dark">{vol_prog}</color>\n'
            f'    <color name="vivo_volume_seekbar_color_for_blur_new">{vol_prog}</color>\n'
            f'    <color name="vivo_volume_seekbar_color_for_no_blur_new">{vol_prog}</color>\n'
            f'    <color name="vivo_volume_seekbar_color_for_gray">{vol_prog}</color>\n'
            f'    <color name="vigour_color_track_gradient_startcolor">{vol_prog}</color>\n'
            f'    <color name="vigour_color_track_gradient_startcolor_for_gray">{vol_prog}</color>\n'
            f'    <color name="vivo_volume_seekbar_bg_color_for_brief_dialog_row_no_blur_new">{vol_bg_light}</color>\n'
            f'    <color name="vivo_volume_seekbar_bg_color_for_expand_dialog_row_blur_new">{vol_bg_light}</color>\n'
            f'    <color name="vivo_volume_seekbar_bg_color_for_expand_dialog_row_no_blur_new">{vol_bg_light}</color>\n'
            '    <color name="vivo_volume_dialog_color_normal_new">#f2eef8fa</color>\n'
            '    <color name="vivo_volume_dialog_color_night_mode_new">#f21b262c</color>\n'
            f'    <color name="vivo_volume_icon_color_for_light_mode_new">{vol_ic_light}</color>\n'
            f'    <color name="vivo_volume_icon_color_for_night_mode_new">{vol_ic_dark}</color>\n'
            f'    <color name="vivo_volume_icon_color_for_theme">{vol_ic_light}</color>\n'
            f'    <color name="vivo_footer_volume_background_color">{vol_bg_light}</color>\n'
            f'    <color name="vivo_footer_volume_progress_color">{vol_prog}</color>\n'
            f'    <color name="vivo_qs_volume_detail_item_select_color">{vol_prog}</color>\n'
            "</vivo_theme_values>\n"
        ).encode("utf-8")

        sysui_mod = self.modules.setdefault("com.android.systemui", {})
        sysui_mod["theme_values.xml"] = (
            '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n'
            "<vivo_theme_values>\n"
            f'    <color name="vivo_switcher_text_light">{sw_hex}</color>\n'
            f'    <color name="vivo_statusbar_expended_text_color">{sb_hex}</color>\n'
            '    <color name="btn_statusbar_shield_press_text_color">#80000000</color>\n'
            '    <color name="btn_statusbar_clean_press_text_color">#80000000</color>\n'
            '    <color name="btn_statusbar_shield_normal_text_color">#ff000000</color>\n'
            '    <color name="btn_statusbar_clean_normal_text_color">#ff000000</color>\n'
            '    <color name="vivo_upslide_background">#ffd7d7d7</color>\n'
            '    <color name="vivo_upslide_divider_background">#00000000</color>\n'
            '    <color name="vivo_upslide_switcher_order_background">#ffd6d6d6</color>\n'
            '    <color name="vivo_upslide_switcher_order_area_background">#ffe1e1e1</color>\n'
            f'    <color name="vivo_battery_text_color_black">{bat_b}</color>\n'
            f'    <color name="vivo_battery_text_color_white">{bat_w}</color>\n'
            "</vivo_theme_values>\n"
        ).encode("utf-8")

    def get_summary(self) -> dict[str, Any]:
        vivo_mod = self.modules.get("vivo", {})
        settings_mod = self.modules.get("com.android.settings", {})
        previews = sorted(
            k for k in self.entries if k.startswith("preview/") and k.lower().endswith((".jpg", ".png"))
        )
        wallpapers = sorted(
            k for k in self.entries if k.startswith("wallpaper/") and k.lower().endswith((".jpg", ".png"))
        )
        return {
            "loaded": bool(self.entries or self.modules),
            "source_name": self.source_name,
            "metadata": self.metadata,
            "icon_count": len(self.list_icons()),
            "launcher_count": len(self.list_launcher_icons()),
            "launcher_config": self.get_launcher_config(),
            "settings_icon_count": len(self.list_settings_icons()),
            "settings_strings": self.get_settings_strings(),
            "systemui_icon_count": len(self.list_systemui_icons()),
            "systemui_colors": self.get_systemui_colors(),
            "extras": {
                "font_name": next((k for k in self.entries if k.startswith("fonts/")), ""),
                "font_size": sum(len(v) for k, v in self.entries.items() if k.startswith("fonts/")),
                "ringtones": sorted(k for k in self.entries if k.startswith("ringtones/")),
                "lockscreen_files": sorted(k for k in self.entries if k.startswith("lockscreen/")),
                "lockscreen_cfg": self.get_lockscreen_config(),
            },
            "modules": sorted(set(self.modules.keys()) | set(GLOBAL_MODULE_PRESETS.keys())),
            "previews": previews,
            "wallpapers": wallpapers,
            "vivo_backgrounds": {
                "light": "vigour_window_settting_background_light.png" in vivo_mod,
                "dark": "vigour_window_settting_background_dark.png" in vivo_mod,
                "window_light": "vigour_window_bg_light.png" in vivo_mod,
                "window_dark": "vigour_window_bg_dark.png" in vivo_mod,
            },
            "origin6_settings_patched": (
                "ic_system_update.png" in settings_mod
                and "set_fan_light_layer0.png" in settings_mod
            ),
        }

    def map_vivo_system_icons(self) -> int:
        added = 0
        for src_name, dst_name in VIVO_ICON_MAPPING.items():
            src_key = f"icons/{src_name}"
            dst_key = f"icons/{dst_name}"
            if src_key in self.entries and dst_key not in self.entries:
                self.entries[dst_key] = self.entries[src_key]
                added += 1
        return added

    def patch_origin6_settings_icons(self) -> dict[str, Any]:
        mod = self.modules.setdefault("com.android.settings", {})
        added: list[str] = []

        # Sample color from existing settings icons if present
        color = (182, 209, 159, 255)
        for sample_name in ("ic_settings_game.png", "ic_system_management_settings.png"):
            if sample_name in mod:
                try:
                    im = Image.open(io.BytesIO(mod[sample_name])).convert("RGBA")
                    pixels = [c for c in im.getdata() if c[3] > 200]
                    if pixels:
                        color = (
                            sum(c[0] for c in pixels) // len(pixels),
                            sum(c[1] for c in pixels) // len(pixels),
                            sum(c[2] for c in pixels) // len(pixels),
                            255,
                        )
                    break
                except Exception:
                    pass

        transparent = make_transparent_png((84, 84))
        if "ic_system_management_settings.png" in mod:
            sys_mgr = mod["ic_system_management_settings.png"]
            for t in ("ic_system_update.png", "ic_system_update_1.png"):
                if t not in mod:
                    mod[t] = sys_mgr
                    added.append(t)
            if "ic_system_update_2.png" not in mod:
                mod["ic_system_update_2.png"] = transparent
                added.append("ic_system_update_2.png")

        fan = make_fan_icon(color=color, size=84)
        for t, data in (
            ("ic_cooling_fan_image.png", mod.get("set_fan_light_layer0.png", fan)),
            ("set_fan_light_layer0.png", fan),
            ("set_fan_light_layer1.png", transparent),
            ("set_fan_light_layer2.png", transparent),
            ("set_fan_layer1.png", fan),
        ):
            if t not in mod:
                mod[t] = data
                added.append(t)

        for src_name, dst_name in (
            ("about_phone_origin_os_rom15.png", "about_phone_origin_os_rom16.png"),
            ("about_phone_origin_os_rom16.png", "about_phone_origin_os_rom16_bg.png"),
            ("about_phone_origin_os_rom15.png", "about_phone_origin_os_rom16_bg.png"),
            ("about_phone_origin_os_rom15_land.png", "about_phone_origin_os_rom16_land.png"),
            ("about_phone_origin_os_rom15.png", "about_phone_origin_os_rom17.png"),
            ("about_phone_origin_os_rom15_land.png", "about_phone_origin_os_rom17_land.png"),
        ):
            if src_name in mod and dst_name not in mod:
                mod[dst_name] = mod[src_name]
                added.append(dst_name)

        return {"added": added, "color": color[:3]}

    def apply_dark_backgrounds(self, brightness: float = 0.26, contrast: float = 1.12) -> list[str]:
        vivo_mod = self.modules.setdefault("vivo", {})
        updated: list[str] = []
        for light_name, dark_name in (
            ("vigour_window_bg_light.png", "vigour_window_bg_dark.png"),
            ("vigour_window_settting_background_light.png", "vigour_window_settting_background_dark.png"),
        ):
            if light_name in vivo_mod:
                vivo_mod[dark_name] = generate_dark_background(
                    vivo_mod[light_name], brightness=brightness, contrast=contrast
                )
                updated.append(dark_name)
        return updated

    def get_module_detail(self, mod_name: str) -> dict[str, Any]:
        mod = self.modules.get(mod_name, {})
        preset = GLOBAL_MODULE_PRESETS.get(mod_name, {})
        preset_assets: dict[str, str] = preset.get("assets", {})
        all_names = sorted(
            {k for k in mod if k.lower().endswith((".png", ".jpg", ".webp"))}
            | set(preset_assets.keys())
        )
        items = [
            {
                "name": n,
                "label": preset_assets.get(n, ""),
                "customized": n in mod,
            }
            for n in all_names
        ]
        items.sort(key=lambda x: (not x["customized"], x["name"]))
        xml_bytes = mod.get("theme_values.xml", b"")
        xml_text = xml_bytes.decode("utf-8", errors="replace") if xml_bytes else (
            '<?xml version="1.0" encoding="utf-8" standalone="no"?>\n<vivo_theme_values>\n</vivo_theme_values>\n'
        )
        return {
            "module": mod_name,
            "title": preset.get("title", mod_name),
            "items": items,
            "xml": xml_text,
            "custom_total": sum(1 for it in items if it["customized"]),
        }

    def set_module_xml(self, mod_name: str, xml_text: str) -> None:
        self.modules.setdefault(mod_name, {})["theme_values.xml"] = xml_text.encode("utf-8")

    def get_lockscreen_config(self) -> dict[str, Any]:
        """Return visual lockscreen editor settings + raw manifest.xml if present."""
        raw_xml = ""
        if "lockscreen/manifest.xml" in self.entries:
            raw_xml = self.entries["lockscreen/manifest.xml"].decode("utf-8", errors="replace")

        cfg: dict[str, Any] = {
            "enabled": bool(raw_xml),
            "clock_x": 540,
            "clock_y": 280,
            "clock_size": 150,
            "clock_color": "#ffffff",
            "date_y": 440,
            "date_size": 36,
            "date_color": "#e2f1f5",
            "tagline": "向右滑动解锁",
            "tagline_y": 1760,
            "tagline_color": "#ffffff",
            "fg_enabled": "lockscreen/fg.png" in self.entries,
            "fg_x": 0,
            "fg_y": 360,
            "fg_scale": 100,
            "slider_enabled": True,
            "xml": raw_xml,
        }
        if raw_xml:
            # Parse saved editor metadata comment if present
            m = re.search(r"<!--\s*STUDIO_CFG:(\{.*?\})\s*-->", raw_xml)
            if m:
                try:
                    import json

                    saved = json.loads(m.group(1))
                    cfg.update(saved)
                    cfg["fg_enabled"] = "lockscreen/fg.png" in self.entries
                    cfg["xml"] = raw_xml
                except Exception:
                    pass
        return cfg

    def save_lockscreen_config(self, cfg: dict[str, Any]) -> str:
        """Generate standard lockscreen/manifest.xml from visual config and store in entries."""
        import json

        clean_cfg = {
            "clock_x": int(cfg.get("clock_x", 540)),
            "clock_y": int(cfg.get("clock_y", 280)),
            "clock_size": int(cfg.get("clock_size", 150)),
            "clock_color": str(cfg.get("clock_color", "#ffffff")),
            "date_y": int(cfg.get("date_y", 440)),
            "date_size": int(cfg.get("date_size", 36)),
            "date_color": str(cfg.get("date_color", "#e2f1f5")),
            "tagline": str(cfg.get("tagline", "向右滑动解锁")),
            "tagline_y": int(cfg.get("tagline_y", 1760)),
            "tagline_color": str(cfg.get("tagline_color", "#ffffff")),
            "fg_x": int(cfg.get("fg_x", 0)),
            "fg_y": int(cfg.get("fg_y", 360)),
            "fg_scale": int(cfg.get("fg_scale", 100)),
            "slider_enabled": bool(cfg.get("slider_enabled", True)),
        }

        # Ensure background image exists in lockscreen/
        if "lockscreen/bg.jpg" not in self.entries and "wallpaper/default_lock_wallpaper.jpg" in self.entries:
            self.entries["lockscreen/bg.jpg"] = self.entries["wallpaper/default_lock_wallpaper.jpg"]

        fg_line = ""
        if "lockscreen/fg.png" in self.entries:
            fw = int(1080 * clean_cfg["fg_scale"] / 100)
            fh = int(1600 * clean_cfg["fg_scale"] / 100)
            fg_line = f'  <Image src="fg.png" x="{clean_cfg["fg_x"]}" y="{clean_cfg["fg_y"]}" w="{fw}" h="{fh}" />\n'

        slider_block = ""
        if clean_cfg["slider_enabled"]:
            ty = clean_cfg["tagline_y"]
            t_esc = (
                clean_cfg["tagline"]
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            slider_block = (
                f'  <Slider x="140" y="{ty - 60}" width="800" height="140" haptic="true">\n'
                "    <Normal>\n"
                f'      <Text text="{t_esc}" x="400" y="70" color="{clean_cfg["tagline_color"]}" size="34" align="center" />\n'
                "    </Normal>\n"
                "    <Triggers>\n"
                '      <Trigger action="up" target="end">\n'
                '        <Intent action="android.intent.action.VIEW" />\n'
                "      </Trigger>\n"
                "    </Triggers>\n"
                "  </Slider>\n"
            )

        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<!-- STUDIO_CFG:{json.dumps(clean_cfg, ensure_ascii=False)} -->\n'
            '<Lockscreen version="2" frameRate="60" screenWidth="1080">\n'
            '  <Image src="bg.jpg" x="0" y="0" w="1080" h="2400" />\n'
            f"{fg_line}"
            f'  <Text text="@time" x="{clean_cfg["clock_x"]}" y="{clean_cfg["clock_y"]}" size="{clean_cfg["clock_size"]}" color="{clean_cfg["clock_color"]}" align="center" />\n'
            f'  <DateTime x="{clean_cfg["clock_x"]}" y="{clean_cfg["date_y"]}" align="center" color="{clean_cfg["date_color"]}" size="{clean_cfg["date_size"]}">\n'
            '    <NormalFormat pattern="yyyy年M月d日 EEEE" />\n'
            "  </DateTime>\n"
            f"{slider_block}"
            "</Lockscreen>\n"
        )
        self.entries["lockscreen/manifest.xml"] = xml.encode("utf-8")
        return xml

    def export_bytes(self) -> bytes:
        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            # Write updated description.xml
            zout.writestr("description.xml", self.build_description_xml())

            for k, v in self.entries.items():
                if k == "description.xml":
                    continue
                zout.writestr(k, v)

            for mod_name, mod_entries in self.modules.items():
                if not mod_entries:
                    continue
                mbuf = io.BytesIO()
                with zipfile.ZipFile(mbuf, "w", compression=zipfile.ZIP_DEFLATED) as mzout:
                    for mk, mv in mod_entries.items():
                        mzout.writestr(mk, mv)
                zout.writestr(mod_name, mbuf.getvalue())

        return out_buf.getvalue()

    def export_font_itz(self, font_title: str = "自定义字体") -> bytes | None:
        """Build a standalone vivo Font .itz package (for .dwd/.../F/ directory)."""
        font_key = next((k for k in self.entries if k.startswith("fonts/") and k.lower().endswith((".ttf", ".otf"))), None)
        if not font_key:
            return None
        ttf_bytes = self.entries[font_key]
        safe_title = "".join(c for c in font_title if c not in r'\/:*?"<>|').strip() or "自定义字体"
        ts = str(int(time.time()))[-6:]

        desc_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<theme>\n"
            f"  <id>{ts}</id>\n"
            "  <version><![CDATA[3.0]]></version>\n"
            "  <titles>\n"
            f'    <title locale="zh_CN"><![CDATA[{safe_title}]]></title>\n'
            "  </titles>\n"
            "  <authors>\n"
            f'    <author locale="zh_CN"><![CDATA[{self.metadata.get("author", "Designer")}]]></author>\n'
            "  </authors>\n"
            "  <descriptions>\n"
            '    <description locale="zh_CN"><![CDATA[简体]]></description>\n'
            "  </descriptions>\n"
            "  <designers>\n"
            f'    <designer locale="zh_CN"><![CDATA[{self.metadata.get("designer", "Designer")}]]></designer>\n'
            "  </designers>\n"
            "  <edition>2</edition>\n"
            "</theme>\n"
        ).encode("utf-8")

        # Generate clean font preview images
        prev_im = Image.new("RGB", (720, 1280), (244, 248, 250))
        prev_buf = io.BytesIO()
        prev_im.save(prev_buf, format="JPEG", quality=88)

        small_png_buf = io.BytesIO()
        Image.new("RGBA", (300, 120), (152, 215, 225, 255)).save(small_png_buf, format="PNG")

        small_jpg_buf = io.BytesIO()
        Image.new("RGB", (300, 180), (152, 215, 225)).save(small_jpg_buf, format="JPEG", quality=88)

        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            zout.writestr("description.xml", desc_xml)
            zout.writestr(f"fonts/{safe_title}.ttf", ttf_bytes)
            zout.writestr("preview/preview_fonts_0.jpg", prev_buf.getvalue())
            zout.writestr("preview/preview_fonts_small_0.png", small_png_buf.getvalue())
            zout.writestr("thumb/preview_fonts_small_1.jpg", small_jpg_buf.getvalue())
        return out_buf.getvalue()
