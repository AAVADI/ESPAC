#!/usr/bin/env python3
"""
Normalize reference-product exchange metadata for SimaPro compatibility.

This script targets the exchange with <outputGroup>0 (typically exchange #1)
and removes uncertainty attributes that can interfere with comment display in
some SimaPro imports.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET


ECO_NS = "http://www.EcoInvent.org/EcoSpold01"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
NS = {"spold": ECO_NS}


def normalize_one(xml_path: Path) -> tuple[bool, int]:
    ET.register_namespace("", ECO_NS)
    ET.register_namespace("xsi", XSI_NS)

    tree = ET.parse(xml_path)
    root = tree.getroot()

    changed = 0
    for ex in root.findall(".//spold:flowData/spold:exchange", NS):
        og = ex.find("spold:outputGroup", NS)
        if og is None:
            continue
        if (og.text or "").strip() != "0":
            continue

        for attr in ("uncertaintyType", "minValue", "maxValue"):
            if attr in ex.attrib:
                del ex.attrib[attr]
                changed += 1

    if changed:
        tree.write(xml_path, encoding="UTF-8", xml_declaration=True)
        return True, changed
    return False, 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glob", action="append", default=[], help="Glob pattern for XML files")
    parser.add_argument("--file", action="append", default=[], help="Single XML file")
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

    updated_files = 0
    removed_attrs = 0
    for p in files:
        if not p.exists() or p.suffix.lower() != ".xml":
            continue
        changed, n = normalize_one(p)
        if changed:
            updated_files += 1
            removed_attrs += n

    print(f"Files updated: {updated_files}")
    print(f"Attributes removed: {removed_attrs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

