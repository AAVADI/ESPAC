from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import pandas as pd


TOOL_COLUMNS = [
    "__row_id",
    "__action",
    "__parent_path",
    "__order",
    "__tag",
    "__ns_uri",
    "__text",
    "__children_xml",
]


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _ns_uri(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def _qname(local: str, ns_uri: str) -> str:
    return f"{{{ns_uri}}}{local}" if ns_uri else local


def _serialize_children(elem: ET.Element) -> str:
    parts = [ET.tostring(child, encoding="unicode") for child in list(elem)]
    return "".join(parts).strip()


def _replace_children(elem: ET.Element, children_xml: str, ns_map: dict[str, str]) -> None:
    for child in list(elem):
        elem.remove(child)
    txt = "" if children_xml is None else str(children_xml).strip()
    if not txt:
        return
    wrapped = f"<root>{txt}</root>"
    wrapper = ET.fromstring(wrapped)
    for child in list(wrapper):
        elem.append(child)


def _element_path(parts: list[tuple[str, int]]) -> str:
    return "/" + "/".join(f"{name}[{idx}]" for name, idx in parts)


def _iter_with_parents(root: ET.Element):
    def walk(node: ET.Element, parent: ET.Element | None, path_parts: list[tuple[str, int]]):
        yield node, parent, path_parts
        counts: dict[str, int] = {}
        for child in list(node):
            lname = _local_name(child.tag)
            counts[lname] = counts.get(lname, 0) + 1
            child_path = path_parts + [(lname, counts[lname])]
            yield from walk(child, node, child_path)

    root_name = _local_name(root.tag)
    yield from walk(root, None, [(root_name, 1)])


def _collect_namespaces(xml_path: Path) -> dict[str, str]:
    ns_map: dict[str, str] = {}
    for event, item in ET.iterparse(xml_path, events=("start-ns",)):
        prefix, uri = item
        if prefix in ns_map and ns_map[prefix] == uri:
            continue
        ns_map[prefix] = uri
    return ns_map


def _register_namespaces(ns_map: dict[str, str]) -> None:
    for prefix, uri in ns_map.items():
        ET.register_namespace(prefix if prefix is not None else "", uri)


def _load_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path, dtype=str).fillna("")
    raise ValueError(f"Unsupported table format: {path.suffix}")


def _save_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        df.to_excel(path, index=False)
        return
    raise ValueError(f"Unsupported table format: {path.suffix}")


def export_exchanges(xml_path: Path, out_table: Path) -> pd.DataFrame:
    ns_map = _collect_namespaces(xml_path)
    _register_namespaces(ns_map)
    tree = ET.parse(xml_path)
    root = tree.getroot()

    rows = []
    attr_keys: set[str] = set()
    seq = 0
    for elem, parent, path_parts in _iter_with_parents(root):
        if _local_name(elem.tag) != "exchange":
            continue
        seq += 1
        parent_path = _element_path(path_parts[:-1]) if len(path_parts) > 1 else "/"
        row = {
            "__row_id": f"ex_{seq:05d}",
            "__action": "keep",
            "__parent_path": parent_path,
            "__order": seq,
            "__tag": _local_name(elem.tag),
            "__ns_uri": _ns_uri(elem.tag),
            "__text": (elem.text or "").strip(),
            "__children_xml": _serialize_children(elem),
        }
        for k, v in elem.attrib.items():
            col = f"attr__{k}"
            row[col] = v
            attr_keys.add(col)
        rows.append(row)

    ordered_cols = TOOL_COLUMNS + sorted(attr_keys)
    df = pd.DataFrame(rows)
    if not df.empty:
        for c in ordered_cols:
            if c not in df.columns:
                df[c] = ""
        df = df[ordered_cols]

    _save_table(df, out_table)
    return df


def _find_flowdata_parent(root: ET.Element) -> ET.Element:
    for elem in root.iter():
        if _local_name(elem.tag) == "flowData":
            return elem
    raise ValueError("No <flowData> element found in XML")


def _find_exchange_elements(root: ET.Element):
    out = []
    seq = 0
    for elem, parent, _ in _iter_with_parents(root):
        if _local_name(elem.tag) == "exchange":
            seq += 1
            out.append((f"ex_{seq:05d}", elem, parent))
    return out


def _is_blank(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except Exception:
        pass
    return str(v).strip() == ""


def import_exchanges(xml_in: Path, table_in: Path, xml_out: Path, renumber: bool = True) -> tuple[int, int, int]:
    ns_map = _collect_namespaces(xml_in)
    _register_namespaces(ns_map)
    tree = ET.parse(xml_in)
    root = tree.getroot()
    df = _load_table(table_in)

    existing = _find_exchange_elements(root)
    id_to_elem = {rid: (elem, parent) for rid, elem, parent in existing}

    attr_cols = [c for c in df.columns if str(c).startswith("attr__")]
    updated = removed = added = 0

    for _, row in df.iterrows():
        action = str(row.get("__action", "keep")).strip().lower() or "keep"
        row_id = str(row.get("__row_id", "")).strip()

        if action in {"", "keep", "update"} and row_id in id_to_elem:
            elem, _parent = id_to_elem[row_id]
            # Replace attributes from attr__ columns (blank -> remove)
            for col in attr_cols:
                attr = col.replace("attr__", "", 1)
                val = row.get(col)
                if _is_blank(val):
                    elem.attrib.pop(attr, None)
                else:
                    elem.attrib[attr] = str(val)
            text_val = row.get("__text")
            elem.text = None if _is_blank(text_val) else str(text_val)
            _replace_children(elem, row.get("__children_xml", ""), ns_map)
            updated += 1
            continue

        if action in {"delete", "remove"} and row_id in id_to_elem:
            elem, parent = id_to_elem[row_id]
            if parent is not None:
                parent.remove(elem)
                removed += 1
            continue

        if action == "add":
            parent = _find_flowdata_parent(root)
            ns_uri = str(row.get("__ns_uri", "") or "").strip() or _ns_uri(parent.tag)
            tag_local = str(row.get("__tag", "exchange") or "exchange").strip() or "exchange"
            new_elem = ET.Element(_qname(tag_local, ns_uri))
            for col in attr_cols:
                attr = col.replace("attr__", "", 1)
                val = row.get(col)
                if not _is_blank(val):
                    new_elem.attrib[attr] = str(val)
            txt = row.get("__text")
            new_elem.text = None if _is_blank(txt) else str(txt)
            _replace_children(new_elem, row.get("__children_xml", ""), ns_map)
            parent.append(new_elem)
            added += 1
            continue

    if renumber:
        n = 1
        for elem in root.iter():
            if _local_name(elem.tag) == "exchange":
                elem.attrib["number"] = str(n)
                n += 1

    try:
        ET.indent(tree, space="  ")
    except Exception:
        pass
    xml_out.parent.mkdir(parents=True, exist_ok=True)
    tree.write(xml_out, encoding="UTF-8", xml_declaration=True)
    return updated, removed, added


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Export/import ecospold <exchange> rows to/from a spreadsheet-ready table (CSV/XLSX)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_export = sub.add_parser("export", help="Export <exchange> rows from XML to CSV/XLSX")
    p_export.add_argument("--xml", required=True, type=Path, help="Input XML file")
    p_export.add_argument("--out", required=True, type=Path, help="Output table (.csv or .xlsx)")

    p_import = sub.add_parser("import", help="Import edited rows from CSV/XLSX into XML")
    p_import.add_argument("--xml-in", required=True, type=Path, help="Source XML file")
    p_import.add_argument("--table", required=True, type=Path, help="Edited table (.csv or .xlsx)")
    p_import.add_argument("--xml-out", required=True, type=Path, help="Output XML file")
    p_import.add_argument("--no-renumber", action="store_true", help="Do not renumber <exchange number=...> after import")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "export":
        df = export_exchanges(args.xml, args.out)
        print(f"Exported {len(df):,} exchange rows to {args.out}")
        print("Spreadsheet columns include:")
        print("- __action: keep/update/delete/remove/add")
        print("- attr__*: exchange attributes")
        print("- __children_xml: editable XML fragment for child tags (e.g., <inputGroup>)")
        return 0

    if args.cmd == "import":
        updated, removed, added = import_exchanges(
            xml_in=args.xml_in,
            table_in=args.table,
            xml_out=args.xml_out,
            renumber=not args.no_renumber,
        )
        print(f"Wrote XML: {args.xml_out}")
        print(f"Updated: {updated}, Removed: {removed}, Added: {added}")
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
