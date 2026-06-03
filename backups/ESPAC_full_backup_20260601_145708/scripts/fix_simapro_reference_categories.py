#!/usr/bin/env python3
"""
Normalize ecoSpold referenceFunction category fields for SimaPro import.

Usage:
  python scripts/fix_simapro_reference_categories.py --glob "outputs/05_xml_exports_crop_lci/*.xml"
  python scripts/fix_simapro_reference_categories.py --file outputs/05_xml_exports_crop_lci/00001_....xml
"""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


ECO_NS = "http://www.EcoInvent.org/EcoSpold01"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
NS = {"spold": ECO_NS}


def update_reference_function(xml_path: Path, category: str, subcategory: str) -> bool:
    # Preserve default EcoSpold namespace style (no ns0 prefixes) on write.
    ET.register_namespace("", ECO_NS)
    ET.register_namespace("xsi", XSI_NS)

    tree = ET.parse(xml_path)
    root = tree.getroot()

    ref = root.find(".//spold:referenceFunction", NS)
    if ref is None:
        return False

    ref.set("category", category)
    ref.set("localCategory", category)
    ref.set("subCategory", subcategory)
    ref.set("localSubCategory", subcategory)

    tree.write(xml_path, encoding="UTF-8", xml_declaration=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", action="append", default=[], help="Single XML file to patch")
    parser.add_argument("--glob", action="append", default=[], help="Glob expression for XML files to patch")
    parser.add_argument("--category", default="Agricultural", help="New referenceFunction category")
    parser.add_argument("--subcategory", default="ECUADOR", help="New referenceFunction subCategory")
    args = parser.parse_args()

    paths: list[Path] = [Path(p) for p in args.file]
    for pattern in args.glob:
        paths.extend(Path(".").glob(pattern))

    seen: set[Path] = set()
    files: list[Path] = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            files.append(p)

    ok = 0
    skipped = 0
    for p in files:
        if not p.exists() or p.suffix.lower() != ".xml":
            skipped += 1
            continue
        changed = update_reference_function(p, args.category, args.subcategory)
        if changed:
            ok += 1
        else:
            skipped += 1

    print(f"Patched: {ok}")
    print(f"Skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
