"""Fast batch extractor for original app icons from an ADB-connected Android device."""

from __future__ import annotations

import concurrent.futures
import csv
import io
import struct
import subprocess
import zipfile
from typing import Callable
from PIL import Image


def _read_string_pool(data: bytes, offset: int) -> tuple[list[str], int]:
    _, _, chunk_size = struct.unpack_from("<HHI", data, offset)
    str_count, _, flags, strings_start, _ = struct.unpack_from("<IIIII", data, offset + 8)
    utf8 = bool(flags & (1 << 8))
    offsets = struct.unpack_from(f"<{str_count}I", data, offset + 28)
    base = offset + strings_start
    strings: list[str] = []
    for off in offsets:
        p = base + off
        if utf8:
            b1 = data[p]
            p += 1
            if b1 & 0x80:
                p += 1
            b2 = data[p]
            p += 1
            if b2 & 0x80:
                b2 = ((b2 & 0x7F) << 8) | data[p]
                p += 1
            strings.append(data[p : p + b2].decode("utf-8", errors="replace"))
        else:
            slen = struct.unpack_from("<H", data, p)[0]
            p += 2
            if slen & 0x8000:
                slen = ((slen & 0x7FFF) << 16) | struct.unpack_from("<H", data, p)[0]
                p += 2
            strings.append(data[p : p + slen * 2].decode("utf-16le", errors="replace"))
    return strings, offset + chunk_size


def _find_axml_ref(axml: bytes, target_tags: tuple[str, ...], target_attrs: tuple[str, ...]) -> int | None:
    pos = 8
    strings: list[str] = []
    while pos + 8 <= len(axml):
        ctype, _, csz = struct.unpack_from("<HHI", axml, pos)
        if csz < 8 or pos + csz > len(axml):
            break
        if ctype == 0x0001:
            strings, _ = _read_string_pool(axml, pos)
        elif ctype == 0x0102:
            name_idx = struct.unpack_from("<I", axml, pos + 20)[0]
            attr_start, attr_size, attr_count = struct.unpack_from("<HHH", axml, pos + 24)
            tag = strings[name_idx] if name_idx < len(strings) else ""
            if tag in target_tags:
                for i in range(attr_count):
                    apos = pos + 16 + attr_start + i * attr_size
                    if apos + 20 > len(axml):
                        break
                    aname_idx = struct.unpack_from("<I", axml, apos + 4)[0]
                    vtype = axml[apos + 15]
                    vdata = struct.unpack_from("<I", axml, apos + 16)[0]
                    aname = strings[aname_idx] if aname_idx < len(strings) else ""
                    if aname in target_attrs and vtype == 1:
                        return vdata
        pos += csz
    return None


def _find_res_paths(arsc: bytes, res_id: int) -> list[str]:
    pos = 12
    global_strings: list[str] = []
    paths: list[str] = []
    target_pkg = res_id >> 24
    target_type = (res_id >> 16) & 0xFF
    entry_idx = res_id & 0xFFFF

    while pos + 8 <= len(arsc):
        ctype, hsz, csz = struct.unpack_from("<HHI", arsc, pos)
        if csz < 8 or pos + csz > len(arsc):
            break
        if ctype == 0x0001:
            global_strings, _ = _read_string_pool(arsc, pos)
        elif ctype == 0x0200:
            pkg_id = struct.unpack_from("<I", arsc, pos + 8)[0]
            if pkg_id == target_pkg:
                p = pos + hsz
                end = pos + csz
                while p + 8 <= end:
                    t, th, ts = struct.unpack_from("<HHI", arsc, p)
                    if ts < 8 or p + ts > end:
                        break
                    if t == 0x0201:
                        type_id = arsc[p + 8]
                        if type_id == target_type:
                            ecount = struct.unpack_from("<I", arsc, p + 12)[0]
                            estart = struct.unpack_from("<I", arsc, p + 16)[0]
                            if entry_idx < ecount:
                                eoff = struct.unpack_from("<I", arsc, p + th + entry_idx * 4)[0]
                                if eoff != 0xFFFFFFFF:
                                    ep = p + estart + eoff
                                    if ep + 8 <= p + ts:
                                        esize, eflags, _ = struct.unpack_from("<HHI", arsc, ep)
                                        if not (eflags & 1) and ep + esize + 8 <= p + ts:
                                            vtype = arsc[ep + esize + 3]
                                            vdata = struct.unpack_from("<I", arsc, ep + esize + 4)[0]
                                            if vtype == 3 and vdata < len(global_strings):
                                                paths.append(global_strings[vdata])
                    p += ts
        pos += csz
    return paths


def _adb_unzip_member(adb_path: str, apk_path: str, member: str) -> bytes | None:
    try:
        res = subprocess.run(
            [adb_path, "exec-out", f"unzip -p '{apk_path}' '{member}'"],
            capture_output=True,
            timeout=12,
        )
        if res.returncode == 0 and res.stdout:
            return res.stdout
    except Exception:
        pass
    return None


def _extract_single_app(adb_path: str, pkg: str, apk_path: str) -> tuple[str, bytes | None, tuple[int, int] | None]:
    axml = _adb_unzip_member(adb_path, apk_path, "AndroidManifest.xml")
    arsc = _adb_unzip_member(adb_path, apk_path, "resources.arsc")
    if not axml or not arsc:
        return pkg, None, None

    icon_id = _find_axml_ref(axml, ("application",), ("icon", "roundIcon"))
    if not icon_id:
        return pkg, None, None

    paths = _find_res_paths(arsc, icon_id)
    img_paths = [p for p in paths if p.lower().endswith((".png", ".webp", ".jpg"))]

    # If adaptive-icon XML, follow foreground drawable reference
    if not img_paths:
        for xp in paths:
            if xp.lower().endswith(".xml"):
                xml_bytes = _adb_unzip_member(adb_path, apk_path, xp)
                if xml_bytes:
                    fg_id = _find_axml_ref(xml_bytes, ("foreground",), ("drawable",))
                    if fg_id:
                        fg_paths = _find_res_paths(arsc, fg_id)
                        img_paths.extend(
                            p for p in fg_paths if p.lower().endswith((".png", ".webp", ".jpg"))
                        )
                if img_paths:
                    break

    best_png: bytes | None = None
    best_area = -1
    best_size: tuple[int, int] | None = None

    for ip in img_paths:
        raw = _adb_unzip_member(adb_path, apk_path, ip)
        if not raw:
            continue
        try:
            im = Image.open(io.BytesIO(raw)).convert("RGBA")
            area = im.size[0] * im.size[1]
            if area > best_area:
                out = io.BytesIO()
                im.save(out, format="PNG")
                best_png = out.getvalue()
                best_area = area
                best_size = im.size
        except Exception:
            continue

    return pkg, best_png, best_size


def extract_phone_icons_zip(
    adb_path: str, app_name_map: dict[str, str], max_workers: int = 6
) -> tuple[bytes, int, int]:
    """Batch-extract original launcher icons from phone into a ZIP archive."""
    act_res = subprocess.run(
        [
            adb_path,
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
        timeout=15,
    )
    launcher_pkgs = sorted(
        {
            line.split("/")[0].strip()
            for line in act_res.stdout.splitlines()
            if "/" in line and line.split("/")[0].strip()
        }
    )

    pkg_res = subprocess.run(
        [adb_path, "shell", "pm", "list", "packages", "-f"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    pkg_to_apk: dict[str, str] = {}
    for line in pkg_res.stdout.splitlines():
        line = line.strip()
        if line.startswith("package:") and "=" in line:
            rest = line[8:]
            apk_p, pkg_name = rest.rsplit("=", 1)
            pkg_to_apk[pkg_name.strip()] = apk_p.strip()

    targets = [(pkg, pkg_to_apk[pkg]) for pkg in launcher_pkgs if pkg in pkg_to_apk]

    zip_buf = io.BytesIO()
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["程序名称", "包名", "压缩包路径", "尺寸"])

    extracted_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = [pool.submit(_extract_single_app, adb_path, pkg, apk) for pkg, apk in targets]
        with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for fut in concurrent.futures.as_completed(futs):
                pkg, png_bytes, size = fut.result()
                if png_bytes and size:
                    extracted_count += 1
                    zout.writestr(f"icons/{pkg}.png", png_bytes)
                    writer.writerow(
                        [app_name_map.get(pkg, ""), pkg, f"icons/{pkg}.png", f"{size[0]}x{size[1]}"]
                    )
            zout.writestr("图标索引清单.csv", csv_buf.getvalue().encode("utf-8-sig"))

    return zip_buf.getvalue(), extracted_count, len(targets)
