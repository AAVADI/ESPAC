from __future__ import annotations

import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pandas as pd


GROUP_LABELS = {
    ("output", "0"): "reference product",
    ("output", "4"): "elementary/resource output",
    ("input", "4"): "elementary/resource input",
    ("input", "5"): "technosphere input",
}

# Audit-oriented section order requested by stakeholders.
AUDIT_SECTION_ORDER = {
    "reference function": 1,
    "inputs from nature": 2,
    "inputs from technosphere": 3,
    "outputs to air, water, soil": 4,
    "other exchanges": 9,
}


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _clean_sheet_token(token: str) -> str:
    # Excel sheet names cannot contain: []:*?/\ and are limited to 31 chars.
    token = re.sub(r"[\[\]:*?/\\]", "_", token)
    token = re.sub(r"\s+", "_", token).strip("_ ")
    return token or "sheet"


def _make_sheet_name(source: Path, used: set[str], ordinal: int) -> str:
    stem = source.stem
    # Remove leading numeric prefix already present in many XML file names (e.g. 00001_foo).
    stem = re.sub(r"^\d+[_-]+", "", stem)
    base = _clean_sheet_token(stem)
    prefix = f"{ordinal:04d}_"
    max_base_len = 31 - len(prefix)
    candidate = f"{prefix}{base[:max_base_len]}"

    if candidate not in used:
        used.add(candidate)
        return candidate

    # Resolve rare collisions with compact suffix.
    for i in range(1, 1000):
        suffix = f"_{i}"
        max_base_len = 31 - len(prefix) - len(suffix)
        candidate = f"{prefix}{base[:max_base_len]}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate

    raise RuntimeError(f"Unable to generate unique sheet name for {source}")


def _extract_inventory_name(root: ET.Element) -> str:
    for elem in root.iter():
        if _local_name(elem.tag) == "referenceFunction":
            name = str(elem.attrib.get("name", "")).strip()
            if name:
                return name
            local_name = str(elem.attrib.get("localName", "")).strip()
            if local_name:
                return local_name
    return ""


def _extract_exchange_rows(root: ET.Element) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for idx, elem in enumerate((e for e in root.iter() if _local_name(e.tag) == "exchange"), start=1):
        row: dict[str, str] = {"__exchange_order": str(idx)}
        exchange_group_type = ""
        exchange_group_value = ""
        for attr, value in elem.attrib.items():
            row[attr] = str(value)
        for child in list(elem):
            lname = _local_name(child.tag)
            text = "" if child.text is None else str(child.text).strip()
            row[lname] = text
            if lname == "inputGroup" and text:
                exchange_group_type = "input"
                exchange_group_value = text
            elif lname == "outputGroup" and text and not exchange_group_value:
                exchange_group_type = "output"
                exchange_group_value = text
        row["__exchange_group_type"] = exchange_group_type
        row["__exchange_group"] = exchange_group_value
        row["__exchange_group_label"] = GROUP_LABELS.get(
            (exchange_group_type, exchange_group_value),
            f"{exchange_group_type} group {exchange_group_value}".strip(),
        ) if exchange_group_value else ""
        row["__audit_section"] = _classify_audit_section(
            number_raw=row.get("number", ""),
            exchange_group_type=exchange_group_type,
            exchange_group_value=exchange_group_value,
        )
        rows.append(row)
    return rows


def _classify_audit_section(number_raw: str, exchange_group_type: str, exchange_group_value: str) -> str:
    try:
        number = int(str(number_raw).strip())
    except Exception:
        number = None

    if number == 1 or (exchange_group_type == "output" and exchange_group_value == "0"):
        return "reference function"
    if exchange_group_type == "input" and exchange_group_value == "4":
        return "inputs from nature"
    if exchange_group_type == "input" and exchange_group_value == "5":
        return "inputs from technosphere"
    if exchange_group_type == "output" and exchange_group_value == "4":
        return "outputs to air, water, soil"
    return "other exchanges"


def _xml_to_dataframe(xml_path: Path) -> tuple[pd.DataFrame, str]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    inventory_name = _extract_inventory_name(root)
    rows = _extract_exchange_rows(root)
    df = pd.DataFrame(rows)
    if df.empty:
        # Keep a stable shape for audit if inventory has no exchanges.
        df = pd.DataFrame(
            [{
                "__exchange_order": "",
                "__exchange_group": "",
                "__exchange_group_type": "",
                "__exchange_group_label": "",
                "__audit_section": "",
            }]
        )
    else:
        # Cluster exchanges by requested audit sections.
        order_numeric = pd.to_numeric(df.get("__exchange_order"), errors="coerce")
        group_numeric = pd.to_numeric(df.get("__exchange_group"), errors="coerce")
        group_rank = group_numeric.fillna(9999).astype(int)
        section_rank = df.get("__audit_section", pd.Series(["other exchanges"] * len(df))).map(AUDIT_SECTION_ORDER).fillna(99).astype(int)
        df = df.assign(
            __section_rank=section_rank,
            __group_rank=group_rank,
            __order_rank=order_numeric.fillna(999999).astype(int),
        )
        df = df.sort_values(["__section_rank", "__group_rank", "__exchange_group_type", "__order_rank"], kind="stable")
        df = df.drop(columns=["__section_rank", "__group_rank", "__order_rank"])
    return df, inventory_name


def _collect_xml_files(crop_root: Path, livestock_root: Path) -> list[Path]:
    files: list[Path] = []
    for root in (crop_root, livestock_root):
        if root.exists():
            files.extend(p for p in root.rglob("*.xml") if p.is_file())
    return sorted(files)


def export_xml_inventories(crop_root: Path, livestock_root: Path, output_xlsx: Path) -> tuple[int, int]:
    xml_files = _collect_xml_files(crop_root, livestock_root)
    output_xlsx.parent.mkdir(parents=True, exist_ok=True)

    index_rows: list[dict[str, str]] = []
    used_sheet_names: set[str] = set()
    exported = 0

    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        for i, xml_path in enumerate(xml_files, start=1):
            rel_path = str(xml_path.as_posix())
            sheet_name = _make_sheet_name(xml_path, used_sheet_names, i)

            try:
                df, inventory_name = _xml_to_dataframe(xml_path)
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                index_rows.append(
                    {
                        "sheet_name": sheet_name,
                        "source_xml": rel_path,
                        "inventory_name": inventory_name,
                        "exchange_rows": str(len(df.index)),
                        "status": "ok",
                        "error": "",
                    }
                )
                exported += 1
            except Exception as exc:
                index_rows.append(
                    {
                        "sheet_name": sheet_name,
                        "source_xml": rel_path,
                        "inventory_name": "",
                        "exchange_rows": "0",
                        "status": "parse_error",
                        "error": str(exc),
                    }
                )

        index_df = pd.DataFrame(index_rows)
        if index_df.empty:
            index_df = pd.DataFrame(
                [
                    {
                        "sheet_name": "",
                        "source_xml": "",
                        "inventory_name": "",
                        "exchange_rows": "0",
                        "status": "no_xml_files_found",
                        "error": "",
                    }
                ]
            )
        index_df.to_excel(writer, sheet_name="index", index=False)

    return exported, len(xml_files)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export crop and livestock XML inventories to one Excel workbook (one inventory per sheet)."
    )
    parser.add_argument(
        "--crop-root",
        type=Path,
        default=Path("outputs/05_xml_exports_crop_lci"),
        help="Root folder containing crop XML outputs.",
    )
    parser.add_argument(
        "--livestock-root",
        type=Path,
        default=Path("outputs/05_xml_exports_livestock_lci"),
        help="Root folder containing livestock XML outputs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/reports/xml_inventories_audit.xlsx"),
        help="Destination Excel file path.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    exported, discovered = export_xml_inventories(
        crop_root=args.crop_root,
        livestock_root=args.livestock_root,
        output_xlsx=args.output,
    )

    print(f"Discovered XML files: {discovered}")
    print(f"Exported inventory sheets: {exported}")
    print(f"Workbook: {args.output}")


if __name__ == "__main__":
    main()
