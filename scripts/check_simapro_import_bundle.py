#!/usr/bin/env python3
"""
Pre-import validation for EcoSpold bundles intended for SimaPro.

This checker verifies that XML files reference mapping files and that those
files are present in the bundle (or in an explicit mapping directory).

Important:
SimaPro project and pathway specific mapping files are required.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


ECO_NS = "http://www.EcoInvent.org/EcoSpold01"
NS = {"spold": ECO_NS}


def find_xml_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".xml" else []
    if target.is_dir():
        return sorted(target.glob("*.xml"))
    return []


def check_one(xml_path: Path, mapping_dir: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        root = ET.parse(xml_path).getroot()
    except Exception as exc:
        return [f"{xml_path.name}: XML parse error: {exc}"], warnings

    dataset = root.find("spold:dataset", NS)
    if dataset is None:
        return [f"{xml_path.name}: missing /ecoSpold/dataset"], warnings

    required = {
        "validCategories": "Categories.xml",
        "validUnits": "Units.xml",
        "validRegionalCodes": "RegionalCodes.xml",
        "validCompanyCodes": "CompanyCodes.xml",
    }

    for attr, expected_default in required.items():
        value = dataset.attrib.get(attr, "").strip()
        if not value:
            errors.append(f"{xml_path.name}: missing dataset/@{attr}")
            continue

        mapping_file = mapping_dir / value
        if not mapping_file.exists():
            errors.append(
                f"{xml_path.name}: referenced mapping file not found: {value} "
                f"(looked in {mapping_dir})"
            )
        elif value != expected_default:
            warnings.append(
                f"{xml_path.name}: dataset/@{attr} uses non-default name '{value}' "
                f"(expected '{expected_default}')"
            )

    ref = root.find(".//spold:referenceFunction", NS)
    if ref is None:
        errors.append(f"{xml_path.name}: missing referenceFunction")
    else:
        if not ref.attrib.get("category", "").strip():
            errors.append(f"{xml_path.name}: missing referenceFunction/@category")
        if not ref.attrib.get("subCategory", "").strip():
            warnings.append(f"{xml_path.name}: missing referenceFunction/@subCategory")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate EcoSpold XML + mapping file bundle for SimaPro import."
    )
    parser.add_argument(
        "target",
        type=Path,
        help="XML file or directory containing XML files",
    )
    parser.add_argument(
        "--mapping-dir",
        type=Path,
        default=None,
        help="Directory containing mapping files; defaults to target directory",
    )
    args = parser.parse_args()

    xml_files = find_xml_files(args.target)
    if not xml_files:
        print(f"No XML files found in: {args.target}")
        return 2

    mapping_dir = args.mapping_dir if args.mapping_dir else (
        args.target.parent if args.target.is_file() else args.target
    )

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for xml_file in xml_files:
        errors, warnings = check_one(xml_file, mapping_dir)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    print("SimaPro import pre-check summary")
    print(f"XML files checked: {len(xml_files)}")
    print(f"Mapping directory: {mapping_dir}")
    print(
        "Note: SimaPro project and pathway specific mapping files are required "
        "(e.g., Categories.xml, Units.xml, RegionalCodes.xml, CompanyCodes.xml)."
    )

    if all_warnings:
        print("\nWarnings:")
        for line in all_warnings:
            print(f"- {line}")

    if all_errors:
        print("\nErrors:")
        for line in all_errors:
            print(f"- {line}")
        return 1

    print("\nOK: no blocking issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

