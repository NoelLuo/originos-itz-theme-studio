#!/usr/bin/env python3
"""Standalone validator for OriginOS 6/7 .itz themes and merged replacement packs.

Uses Python standard library only. Checks all verified OriginOS 7 invariants:
- Zero binary npTc chunks in .9.png files
- No accidental fonts/ directory in the main theme package
- SuperCard (com.vivo.card) AAPT2 obfuscated resource coverage
- Volume seekbar bool/new_style & track gradient colors in com.vivo.systemuiplugin
- Control Center QS icon format (Animated WebP vs static PNG)
- Replacement pack integrity (themeicon/icons.zip + nested .dwd/.../T/*.itz preview/wallpaper)
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path


def _open_nested_zip(z: zipfile.ZipFile, name: str) -> zipfile.ZipFile | None:
    if name not in z.namelist():
        return None
    try:
        return zipfile.ZipFile(io.BytesIO(z.read(name)), "r")
    except zipfile.BadZipFile:
        return None


def audit_theme_zip(zf: zipfile.ZipFile, obf_map_path: Path | None = None) -> dict:
    names = zf.namelist()
    report: dict = {
        "entries": len(names),
        "has_description_xml": "description.xml" in names,
        "font_files": [n for n in names if n.startswith("fonts/")],
        "icons_count": sum(1 for n in names if n.startswith("icons/") and n.lower().endswith(".png")),
        "wallpapers": [n for n in names if n.startswith("wallpaper/") and not n.endswith("/")],
        "previews": [n for n in names if n.startswith("preview/") and not n.endswith("/")],
        "nine_patch_total": 0,
        "binary_nptc_files": [],
        "supercard_total": 0,
        "supercard_obf_matched": 0,
        "volume_new_style": False,
        "volume_track_gradient": False,
        "volume_expand_bg": False,
        "qs_icons": {},
        "warnings": [],
        "errors": [],
    }

    if not report["has_description_xml"]:
        report["errors"].append("Missing description.xml at theme root")
    if report["font_files"]:
        report["warnings"].append(f"Theme bundles {len(report['font_files'])} font file(s) under fonts/")

    # Scan root entries for .9.png
    for n in names:
        if n.lower().endswith(".9.png"):
            report["nine_patch_total"] += 1
            if b"npTc" in zf.read(n):
                report["binary_nptc_files"].append(n)

    # Load known SuperCard obfuscated filenames if available
    known_obf: set[str] = set()
    if obf_map_path and obf_map_path.is_file():
        data = json.loads(obf_map_path.read_text(encoding="utf-8"))
        for entry in data.values():
            if isinstance(entry, dict):
                known_obf.update(entry.keys())

    # Inspect nested module zips
    for n in names:
        if "/" in n or "." in n and not n.startswith(("com.", "org.", "vivo")):
            continue
        mz = _open_nested_zip(zf, n)
        if mz is None:
            continue
        with mz:
            mnames = mz.namelist()
            for mn in mnames:
                if mn.lower().endswith(".9.png"):
                    report["nine_patch_total"] += 1
                    if b"npTc" in mz.read(mn):
                        report["binary_nptc_files"].append(f"{n}/{mn}")

            if n == "com.vivo.card":
                report["supercard_total"] = len(mnames)
                if known_obf:
                    report["supercard_obf_matched"] = sum(1 for mn in mnames if mn in known_obf)

            if n == "com.vivo.systemuiplugin":
                if "theme_values.xml" in mnames:
                    xml = mz.read("theme_values.xml").decode("utf-8", errors="ignore")
                    report["volume_new_style"] = 'name="new_style">true<' in xml
                    report["volume_track_gradient"] = "vigour_color_track_gradient_startcolor" in xml
                    report["volume_expand_bg"] = "vivo_volume_seekbar_bg_color_for_expand_dialog_row_blur_new" in xml
                for qfn in (
                    "vivo_super_qs_wifi_on.png",
                    "vivo_super_qs_data_switch_on.png",
                    "vivo_super_qs_bluetooth_on.png",
                ):
                    if qfn in mnames:
                        raw = mz.read(qfn)
                        if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
                            kind = "animated_webp" if b"ANIM" in raw[:64] else "static_webp"
                        elif raw[:8] == b"\x89PNG\r\n\x1a\n":
                            kind = "static_png"
                        else:
                            kind = "unknown"
                        report["qs_icons"][qfn] = {"bytes": len(raw), "format": kind}

    if report["binary_nptc_files"]:
        report["errors"].append(
            f"Found {len(report['binary_nptc_files'])} binary npTc .9.png file(s): "
            + ", ".join(report["binary_nptc_files"][:5])
        )
    if report["supercard_total"] > 0 and known_obf and report["supercard_obf_matched"] == 0:
        report["warnings"].append("com.vivo.card has files but 0 matched OriginOS 7 AAPT2 obfuscated filenames")
    if not report["volume_new_style"]:
        report["warnings"].append("com.vivo.systemuiplugin/theme_values.xml missing <bool name=\"new_style\">true</bool>")

    return report


def audit_replacement_pack(path: Path, obf_map_path: Path | None = None) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        if "themeicon/icons.zip" not in names:
            return {"errors": ["Not a valid replacement pack: missing themeicon/icons.zip"], "warnings": []}
        nested_t = [n for n in names if "/T/" in n and n.lower().endswith(".itz")]
        with zipfile.ZipFile(io.BytesIO(zf.read("themeicon/icons.zip")), "r") as inner:
            rep = audit_theme_zip(inner, obf_map_path)
        rep["replacement_pack"] = True
        rep["nested_base_themes"] = []
        for tn in nested_t:
            with zipfile.ZipFile(io.BytesIO(zf.read(tn)), "r") as tz:
                tnames = tz.namelist()
                rep["nested_base_themes"].append(
                    {
                        "path": tn,
                        "preview_count": sum(1 for x in tnames if x.startswith("preview/") and not x.endswith("/")),
                        "wallpaper_count": sum(1 for x in tnames if x.startswith("wallpaper/") and not x.endswith("/")),
                    }
                )
        if not rep["nested_base_themes"]:
            rep["errors"].append("Missing nested .dwd/.../T/*.itz base theme inside replacement pack")
        return rep


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit an OriginOS 6/7 .itz theme or replacement pack.")
    parser.add_argument("itz_path", type=Path, help="Path to .itz file")
    parser.add_argument("--replacement-pack", action="store_true", help="Inspect as merged replacement pack")
    parser.add_argument("--json", action="store_true", help="Output raw JSON report")
    args = parser.parse_args()

    if not args.itz_path.is_file():
        print(f"ERROR: File not found: {args.itz_path}", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[4]
    obf_map = repo_root / "supercard_obf_map.json"
    if not obf_map.is_file():
        obf_map = None

    if args.replacement_pack:
        rep = audit_replacement_pack(args.itz_path, obf_map)
    else:
        with zipfile.ZipFile(args.itz_path, "r") as zf:
            if "themeicon/icons.zip" in zf.namelist() and "description.xml" not in zf.namelist():
                rep = audit_replacement_pack(args.itz_path, obf_map)
            else:
                rep = audit_theme_zip(zf, obf_map)

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        mode = "Replacement Pack" if rep.get("replacement_pack") else "Source .itz Theme"
        print(f"=== OriginOS .itz Audit ({mode}): {args.itz_path.name} ===")
        print(f"  Icons: {rep.get('icons_count', 0)} | Wallpapers: {len(rep.get('wallpapers', []))} | Previews: {len(rep.get('previews', []))}")
        print(f"  Nine-patch (.9.png): {rep.get('nine_patch_total', 0)} total, {len(rep.get('binary_nptc_files', []))} binary npTc")
        print(f"  Fonts under fonts/: {len(rep.get('font_files', []))}")
        print(f"  SuperCard (com.vivo.card): {rep.get('supercard_total', 0)} files ({rep.get('supercard_obf_matched', 0)} OS7 obfuscated matched)")
        print(
            f"  Volume OS7 flags: new_style={rep.get('volume_new_style')} "
            f"track_gradient={rep.get('volume_track_gradient')} expand_bg={rep.get('volume_expand_bg')}"
        )
        if rep.get("qs_icons"):
            for k, v in rep["qs_icons"].items():
                print(f"  QS {k}: {v['format']} ({v['bytes']} B)")
        for bt in rep.get("nested_base_themes", []):
            print(f"  Nested base theme: {bt['path']} (preview={bt['preview_count']}, wallpaper={bt['wallpaper_count']})")
        for w in rep.get("warnings", []):
            print(f"  [WARN] {w}")
        for e in rep.get("errors", []):
            print(f"  [FAIL] {e}")
        print("RESULT:", "PASS" if not rep.get("errors") else "FAIL")

    return 0 if not rep.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
