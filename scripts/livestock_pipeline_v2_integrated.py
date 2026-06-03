from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline_manifest import (
    append_manifest_record,
    build_manifest_record,
    make_snapshot_copy,
    new_run_id,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
CSV_DIR = PROJECT_DIR / "outputs" / "CSVs"
LATEST_META = PROJECT_DIR / "outputs" / "02_latest_livestock_filtered_export_summary.json"
MANIFEST_REL = Path("outputs/pipeline_run_manifest.json")


PROVINCE_TO_REGION: dict[str, str] = {
    "AZUAY": "Sierra",
    "BOLIVAR": "Sierra",
    "BOLÍVAR": "Sierra",
    "CANAR": "Sierra",
    "CAÑAR": "Sierra",
    "CARCHI": "Sierra",
    "CHIMBORAZO": "Sierra",
    "COTOPAXI": "Sierra",
    "IMBABURA": "Sierra",
    "LOJA": "Sierra",
    "PICHINCHA": "Sierra",
    "TUNGURAHUA": "Sierra",
    "EL ORO": "Costa",
    "ESMERALDAS": "Costa",
    "GUAYAS": "Costa",
    "LOS RIOS": "Costa",
    "LOS RÍOS": "Costa",
    "MANABI": "Costa",
    "MANABÍ": "Costa",
    "SANTA ELENA": "Costa",
    "SANTO DOMINGO DE LOS TSACHILAS": "Costa",
    "SANTO DOMINGO DE LOS TSÁCHILAS": "Costa",
    "ORELLANA": "Oriente",
    "MORONA SANTIAGO": "Oriente",
    "NAPO": "Oriente",
    "PASTAZA": "Oriente",
    "SUCUMBIOS": "Oriente",
    "SUCUMBÍOS": "Oriente",
    "ZAMORA CHINCHIPE": "Oriente",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_txt(x: Any) -> str:
    return str(x or "").strip()


def _norm_key(x: Any) -> str:
    return _norm_txt(x).upper()


def _to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def _functional_unit(product: str) -> str:
    p = _norm_key(product)
    if p == "MILK":
        return "1 kg FPCM"
    if p == "EGGS":
        return "1 kg shell eggs"
    if p in {"CATTLE_LIVE", "SWINE_LIVE", "OVINE_LIVE", "GOAT_LIVE", "HORSE_LIVE", "MULE_LIVE", "DONKEY_LIVE"}:
        return "1 kg live weight equivalent"
    if p == "MEAT_POULTRY":
        return "1 kg meat product"
    return "1 kg product"


def _species(product: str) -> str:
    p = _norm_key(product)
    if "CATTLE" in p or p == "MILK":
        return "cattle"
    if "SWINE" in p:
        return "swine"
    if "OVINE" in p:
        return "ovine"
    if "GOAT" in p:
        return "goat"
    if "POULTRY" in p:
        return "poultry"
    if "EGG" in p:
        return "poultry"
    return "other"


def _system_lookup_from_db(db: Path) -> dict[tuple[str, str], str]:
    con = sqlite3.connect(db)
    try:
        lookup: dict[tuple[str, str], str] = {}
        cattle = pd.read_sql_query(
            "SELECT identificador, gl_propleche, gl_propdoblep, gl_propcarne FROM rel_inec_glnac",
            con,
        )
        for _, row in cattle.iterrows():
            milk_flag = float(_to_num(pd.Series([row.get("gl_propleche", 0)])).iloc[0])
            dual_flag = float(_to_num(pd.Series([row.get("gl_propdoblep", 0)])).iloc[0])
            beef_flag = float(_to_num(pd.Series([row.get("gl_propcarne", 0)])).iloc[0])
            system = "(unknown)"
            if milk_flag > 0:
                system = "dairy"
            elif dual_flag > 0:
                system = "dual-purpose"
            elif beef_flag > 0:
                system = "beef"
            fid = str(row["identificador"])
            lookup[(fid, "milk")] = system
            lookup[(fid, "cattle_meat")] = system

        poultry = pd.read_sql_query(
            "SELECT identificador, ap_k1221 FROM rel_inec_apnac",
            con,
        )
        for _, row in poultry.iterrows():
            activity = str(row.get("ap_k1221", "") or "").strip().lower()
            if "huevo" in activity:
                system = "layers"
            elif "doble" in activity:
                system = "dual-purpose poultry"
            else:
                system = "(unknown)"
            lookup[(str(row["identificador"]), "eggs")] = system
        return lookup
    finally:
        con.close()


def _apply_system_labels(v2_prod: pd.DataFrame, db: Path) -> pd.DataFrame:
    df = v2_prod.copy()
    lookup = _system_lookup_from_db(db)
    default_by_product = {
        "milk": "(unknown)",
        "cattle_meat": "(unknown)",
        "eggs": "(unknown)",
        "meat_poultry": "(all holdings)",
        "swine_live": "(all swine)",
        "ovine_live": "(all ovine)",
        "other_livestock_live": "(all holdings)",
    }
    def resolve(row: pd.Series) -> str:
        fid = str(row.get("identificador", ""))
        product = str(row.get("product", ""))
        return lookup.get((fid, product), default_by_product.get(product, "(all holdings)"))
    df["System"] = df.apply(resolve, axis=1)
    return df


def run_v2_model(db: Path, outdir: Path) -> None:
    cmd = [
        "python",
        str(PROJECT_DIR / "scripts" / "livestock_model_v2.py"),
        "--db",
        str(db),
        "--outdir",
        str(outdir),
    ]
    subprocess.run(cmd, check=True)


def load_v2_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    prod_path = CSV_DIR / "07_product_lci_v2.csv"
    unc_path = CSV_DIR / "07_product_lci_v2_uncertainty.csv"
    if not prod_path.exists() or not unc_path.exists():
        raise FileNotFoundError("Missing V2 outputs: run livestock_model_v2 first.")
    return pd.read_csv(prod_path, low_memory=False), pd.read_csv(unc_path, low_memory=False)


def build_stage02_main(v2_prod: pd.DataFrame, summary_token: str, combine_systems: bool = False) -> pd.DataFrame:
    df = v2_prod.copy()
    df["Province"] = df.get("ual_prov", "").map(_norm_txt)
    df["Region"] = df["Province"].map(lambda x: PROVINCE_TO_REGION.get(_norm_key(x), "(unknown)"))
    df["Product"] = df.get("product", "").map(_norm_txt)
    df["Species"] = df["Product"].map(_species)
    df["System"] = df.get("System", "").map(_norm_txt)
    df.loc[df["System"].eq(""), "System"] = "(unknown)"
    df["Functional_unit"] = df["Product"].map(_functional_unit)
    df["Normalized_product_output_kg"] = 1.0

    if summary_token == "national":
        grp = ["Product"] if combine_systems else ["Product", "System"]
        df["Region"] = "(all regions confounded)"
        df["Province"] = "(all provinces confounded)"
        if combine_systems:
            df["System"] = "(all systems combined)"
    elif summary_token == "region":
        grp = ["Region", "Product", "System"]
        df["Province"] = "(all provinces confounded)"
    elif summary_token == "province":
        grp = ["Region", "Province", "Product", "System"]
    else:
        raise ValueError(f"Unsupported summary token: {summary_token}")

    weight = _to_num(df.get("product_output_kg_year", 0.0))
    weight = weight.where(weight > 0, 1.0)
    df["_w"] = weight

    num_cols = [c for c in df.columns if c.endswith("_per_kg_product")]
    keep_cols = [
        "Region",
        "Province",
        "Product",
        "Species",
        "System",
        "Functional_unit",
        "Normalized_product_output_kg",
    ]
    rows: list[dict[str, Any]] = []
    for keys, part in df.groupby(grp, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        rec = {}
        for i, g in enumerate(grp):
            rec[g] = keys[i]
        rec["Region"] = rec.get("Region", "(all regions confounded)")
        rec["Province"] = rec.get("Province", "(all provinces confounded)")
        rec["Species"] = _species(rec["Product"])
        rec["System"] = rec.get("System", "(unknown)")
        rec["Functional_unit"] = _functional_unit(rec["Product"])
        rec["Normalized_product_output_kg"] = 1.0
        w = _to_num(part["_w"])
        wsum = float(w.sum()) if float(w.sum()) > 0 else float(len(part))
        for c in num_cols:
            vals = _to_num(part.get(c, 0.0))
            rec[c] = float((vals * w).sum() / wsum)
        rows.append(rec)

    out = pd.DataFrame(rows)
    out = out[keep_cols + [c for c in out.columns if c not in keep_cols]]
    return out.sort_values(grp).reset_index(drop=True)


def build_stage02_unc(v2_unc: pd.DataFrame, summary_token: str, stage02_main: pd.DataFrame, combine_systems: bool = False) -> pd.DataFrame:
    source = v2_unc.copy()
    scope_map = {
        "national": "national",
        "region": "region",
        "province": "province",
    }
    scope = scope_map[summary_token]
    if "scope" in source.columns:
        source = source[source["scope"].astype(str) == scope].copy()
    product_col = "product" if "product" in source.columns else "Product"
    source["Product"] = source[product_col].map(_norm_txt)

    if summary_token == "national":
        merge_keys = ["Product"]
        extra_cols = ["System"] if ("System" in stage02_main.columns and not combine_systems) else []
        stage02_main = stage02_main[["Product"] + extra_cols].drop_duplicates()
    elif summary_token == "province":
        merge_keys = ["Product", "Region", "Province"]
        extra_cols = ["System"] if "System" in stage02_main.columns else []
        reg = stage02_main[["Product", "Region", "Province"] + extra_cols].drop_duplicates()
        source["Region"] = source.get("region", "(unknown)")
        if "Region" not in source.columns:
            source["Region"] = "(unknown)"
        source["Province"] = source.get("province", "(unknown)")
        if "Province" not in source.columns:
            source["Province"] = "(unknown)"
        stage02_main = reg
    else:
        merge_keys = ["Product", "Region"]
        extra_cols = ["System"] if "System" in stage02_main.columns else []
        reg = stage02_main[["Product", "Region"] + extra_cols].drop_duplicates()
        source["Region"] = source.get("region", "(unknown)")
        if "Region" not in source.columns:
            source["Region"] = "(unknown)"
        stage02_main = reg

    unc = stage02_main.merge(source, on=merge_keys, how="left")
    out_cols = merge_keys.copy()
    for c in list(unc.columns):
        if c.endswith("__min"):
            base = c[:-5]
            out_cols.append(c)
            max_c = f"{base}__max"
            if max_c in unc.columns:
                out_cols.append(max_c)
    # keep only unique order
    seen: set[str] = set()
    ordered: list[str] = []
    for c in out_cols:
        if c not in seen and c in unc.columns:
            seen.add(c)
            ordered.append(c)
    return unc[ordered].copy()


def write_stage02(summary_token: str, df_main: pd.DataFrame, df_unc: pd.DataFrame) -> tuple[Path, Path]:
    out_main = CSV_DIR / f"02_espac_livestock_lci_table_filtered__summary_{summary_token}.csv"
    out_unc = CSV_DIR / f"02_espac_livestock_lci_table_filtered__summary_{summary_token}_uncertainty.csv"
    out_main.parent.mkdir(parents=True, exist_ok=True)
    df_main.to_csv(out_main, index=False)
    df_unc.to_csv(out_unc, index=False)
    return out_main, out_unc


def write_latest_meta(summary_token: str, main_csv: Path, unc_csv: Path, run_id: str) -> None:
    payload = {
        "summary_level": summary_token,
        "summary_token": summary_token,
        "filtered_csv": str(main_csv.resolve()),
        "filtered_uncertainty_csv": str(unc_csv.resolve()),
        "updated_at_utc": utc_now_iso(),
        "run_id": run_id,
    }
    LATEST_META.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def update_latest_meta_options(combine_systems: bool) -> None:
    if not LATEST_META.exists():
        return
    payload = json.loads(LATEST_META.read_text(encoding="utf-8"))
    payload["combine_systems"] = bool(combine_systems)
    LATEST_META.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def append_stage02_manifest(summary_token: str, main_csv: Path, unc_csv: Path, run_id: str) -> None:
    main_df = pd.read_csv(main_csv)
    unc_df = pd.read_csv(unc_csv)
    rec = build_manifest_record(
        run_id=run_id,
        domain="livestock",
        summary_token=summary_token,
        pipeline_stage="02",
        source_main_csv=main_csv,
        source_unc_csv=unc_csv,
        main_df=main_df.rename(columns={"Product": "Product"}),
        unc_df=unc_df,
        filters_meta={"source": "v2_integrated"},
    )
    append_manifest_record(PROJECT_DIR, rec, MANIFEST_REL)


def run_stage03_from_stage02(summary_token: str, upstream_run_id: str) -> tuple[str, Path, Path]:
    in_main = CSV_DIR / f"02_espac_livestock_lci_table_filtered__summary_{summary_token}.csv"
    in_unc = CSV_DIR / f"02_espac_livestock_lci_table_filtered__summary_{summary_token}_uncertainty.csv"
    if not in_main.exists() or not in_unc.exists():
        raise FileNotFoundError(f"Missing stage 02 files for summary '{summary_token}'.")

    out_main = CSV_DIR / f"03-05_espac_livestock_lci_table_filtered_dfe__summary_{summary_token}.csv"
    out_unc = CSV_DIR / f"03-05_espac_livestock_lci_table_filtered_dfe__summary_{summary_token}_uncertainty.csv"
    df_main = pd.read_csv(in_main)
    df_unc = pd.read_csv(in_unc)
    df_main.to_csv(out_main, index=False)
    df_unc.to_csv(out_unc, index=False)

    run_id = new_run_id("03_05_livestock")
    snap_main = make_snapshot_copy(out_main, run_id)
    snap_unc = make_snapshot_copy(out_unc, run_id)
    rec = build_manifest_record(
        run_id=run_id,
        domain="livestock",
        summary_token=summary_token,
        pipeline_stage="03-05",
        source_main_csv=snap_main,
        source_unc_csv=snap_unc,
        main_df=df_main.rename(columns={"Product": "Product"}),
        unc_df=df_unc,
        filters_meta={"source": "v2_integrated", "stage": "03-05_passthrough"},
        upstream_run_id=upstream_run_id,
    )
    append_manifest_record(PROJECT_DIR, rec, MANIFEST_REL)
    return run_id, out_main, out_unc


def run_stage05_xml(summary_token: str, combine_systems: bool = False) -> int:
    out_root = PROJECT_DIR / "outputs" / "05_xml_exports_livestock_lci"
    out_region = out_root / "summary_region"
    out_province = out_root / "summary_province"
    out_national = out_root / "summary_national"
    out_region.mkdir(parents=True, exist_ok=True)
    out_province.mkdir(parents=True, exist_ok=True)
    out_national.mkdir(parents=True, exist_ok=True)
    if summary_token == "region":
        for p in out_region.glob("*.xml"):
            p.unlink()
        cmd = [
            "python",
            str(PROJECT_DIR / "scripts" / "livestock_xml_generator_v2.py"),
            "--lci",
            str(CSV_DIR / "07_product_lci_v2.csv"),
            "--unc",
            str(CSV_DIR / "07_product_lci_v2_uncertainty.csv"),
            "--template-dir",
            str(PROJECT_DIR / "inputs"),
            "--outdir",
            str(out_region),
            "--aggregate",
            "region_product",
            "--summary-token",
            "region",
        ]
        subprocess.run(cmd, check=True)
        return len(list(out_region.glob("*.xml")))
    if summary_token == "province":
        for p in out_province.glob("*.xml"):
            p.unlink()
        cmd = [
            "python",
            str(PROJECT_DIR / "scripts" / "livestock_xml_generator_v2.py"),
            "--lci",
            str(CSV_DIR / "07_product_lci_v2.csv"),
            "--unc",
            str(CSV_DIR / "07_product_lci_v2_uncertainty.csv"),
            "--template-dir",
            str(PROJECT_DIR / "inputs"),
            "--outdir",
            str(out_province),
            "--aggregate",
            "province_product",
            "--summary-token",
            "province",
        ]
        subprocess.run(cmd, check=True)
        return len(list(out_province.glob("*.xml")))
    if summary_token == "national":
        for p in out_national.glob("*.xml"):
            p.unlink()
        cmd = [
            "python",
            str(PROJECT_DIR / "scripts" / "livestock_xml_generator_v2.py"),
            "--lci",
            str(CSV_DIR / "07_product_lci_v2.csv"),
            "--unc",
            str(CSV_DIR / "07_product_lci_v2_uncertainty.csv"),
            "--template-dir",
            str(PROJECT_DIR / "inputs"),
            "--outdir",
            str(out_national),
            "--aggregate",
            "national_product",
            "--summary-token",
            "national",
        ]
        if combine_systems:
            cmd.append("--combine-systems")
        subprocess.run(cmd, check=True)
        return len(list(out_national.glob("*.xml")))
    raise ValueError("summary_token must be one of: province, region, national")


def append_stage05_manifest(summary_token: str, upstream_run_id: str) -> str:
    main_csv = CSV_DIR / f"03-05_espac_livestock_lci_table_filtered_dfe__summary_{summary_token}.csv"
    unc_csv = CSV_DIR / f"03-05_espac_livestock_lci_table_filtered_dfe__summary_{summary_token}_uncertainty.csv"
    df_main = pd.read_csv(main_csv)
    df_unc = pd.read_csv(unc_csv)
    run_id = new_run_id("05_xml_livestock")
    snap_main = make_snapshot_copy(main_csv, run_id)
    snap_unc = make_snapshot_copy(unc_csv, run_id)
    xml_dir = PROJECT_DIR / "outputs" / "05_xml_exports_livestock_lci" / f"summary_{summary_token}"
    xml_files = len(list(xml_dir.glob("*.xml"))) if xml_dir.exists() else 0
    rec = build_manifest_record(
        run_id=run_id,
        domain="livestock",
        summary_token=summary_token,
        pipeline_stage="05_xml",
        source_main_csv=snap_main,
        source_unc_csv=snap_unc,
        main_df=df_main.rename(columns={"Product": "Product"}),
        unc_df=df_unc,
        filters_meta={"source": "v2_integrated", "stage": "05_xml"},
        upstream_run_id=upstream_run_id,
        extra={
            "xml_output_dir": str(xml_dir.resolve()),
            "xml_files_written": int(xml_files),
        },
    )
    append_manifest_record(PROJECT_DIR, rec, MANIFEST_REL)
    return run_id


def run_stage02(db: Path, summary_token: str, combine_systems: bool = False) -> str:
    run_v2_model(db, CSV_DIR)

    v2_prod, v2_unc = load_v2_tables()
    v2_prod = _apply_system_labels(v2_prod, db)
    main = build_stage02_main(v2_prod, summary_token, combine_systems=combine_systems)
    unc = build_stage02_unc(v2_unc, summary_token, main, combine_systems=combine_systems)
    out_main, out_unc = write_stage02(summary_token, main, unc)
    run02 = new_run_id("02_livestock")
    snap_main = make_snapshot_copy(out_main, run02)
    snap_unc = make_snapshot_copy(out_unc, run02)
    append_stage02_manifest(summary_token, snap_main, snap_unc, run02)
    write_latest_meta(
        summary_token,
        out_main,
        out_unc,
        run02,
    )
    update_latest_meta_options(combine_systems)
    return run02


def run_stage03(summary_token: str, upstream_run_id: str = "") -> str:
    if not upstream_run_id and LATEST_META.exists():
        meta = json.loads(LATEST_META.read_text(encoding="utf-8"))
        upstream_run_id = str(meta.get("run_id", ""))
    run03, _, _ = run_stage03_from_stage02(summary_token, upstream_run_id)
    return run03


def run_stage05(summary_token: str, upstream_run_id: str = "", combine_systems: bool = False) -> str:
    run_stage05_xml(summary_token, combine_systems=combine_systems)
    return append_stage05_manifest(summary_token, upstream_run_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Integrated v2 livestock pipeline by selected summary token.")
    parser.add_argument("--db", default=str(PROJECT_DIR / "outputs" / "01_espac_2024.sqlite"))
    parser.add_argument("--stage", choices=["02", "03", "05"], required=True)
    parser.add_argument("--summary-token", choices=["province", "region", "national"], required=True)
    parser.add_argument("--upstream-run-id", default="")
    parser.add_argument("--combine-systems", action="store_true", help="For national livestock summaries, collapse all system types into one combined row per product.")
    args = parser.parse_args()
    if args.stage == "02":
        run_stage02(Path(args.db), args.summary_token, combine_systems=args.combine_systems)
    elif args.stage == "03":
        run_stage03(args.summary_token, args.upstream_run_id)
    else:
        run_stage05(args.summary_token, args.upstream_run_id, combine_systems=args.combine_systems)
    print(
        f"Integrated livestock v2 pipeline stage '{args.stage}' "
        f"completed successfully for summary '{args.summary_token}'."
    )


if __name__ == "__main__":
    main()
