from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parents[1]
CSV_DIR = PROJECT_DIR / "outputs" / "CSVs"
CROP_META = PROJECT_DIR / "outputs" / "02_latest_filtered_export_summary.json"

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(PROJECT_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "scripts"))

from scripts.crop_groups import infer_crop_group_row

CROP_STRATEGIES = [
    "province",
    "region",
    "crop_national",
    "cropping_system",
    "irrig_m3_class",
    "farm_size_class",
    "crop_group",
    "crop_group_national",
]
LIVESTOCK_STRATEGIES = ["province", "region", "national"]
STRATEGY_HELP = {
    "crops": {
        "province": "One inventory per crop x province (most granular geography).",
        "region": "One inventory per crop x region (Costa/Sierra/Oriente).",
        "crop_national": "One inventory per crop at national level.",
        "cropping_system": "One inventory per cropping-system class at national level.",
        "irrig_m3_class": "One inventory per irrigation class (Irrig_m3 = 0 vs > 0), confounded provinces.",
        "farm_size_class": "One inventory per farm-size class, confounded provinces.",
        "crop_group": "One inventory per crop-group by region.",
        "crop_group_national": "One inventory per crop-group at national level.",
    },
    "livestock": {
        "province": "One inventory per livestock product x province.",
        "region": "One inventory per livestock product x region.",
        "national": "One inventory per livestock product at national level (integrated V2 model).",
    },
}


def python_executable() -> str:
    local_venv = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
    return str(local_venv) if local_venv.exists() else sys.executable


def run_cmd(
    cmd: list[str],
    timeout_sec: int = 3600,
    progress_callback: Any | None = None,
    progress_label: str = "Running command",
) -> tuple[int, str]:
    try:
        p = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        started = time.time()
        while True:
            rc = p.poll()
            elapsed = int(time.time() - started)
            if progress_callback is not None:
                progress_callback(f"{progress_label}... {elapsed}s")
            if rc is not None:
                break
            if elapsed >= timeout_sec:
                p.kill()
                stdout, stderr = p.communicate()
                out = (stdout or "") + ("\n" + stderr if stderr else "")
                out = (out + f"\nCommand timed out after {timeout_sec}s.").strip()
                return 124, out
            time.sleep(0.5)

        stdout, stderr = p.communicate()
        out = (stdout or "") + ("\n" + stderr if stderr else "")
        return int(p.returncode or 0), out.strip()
    except Exception as exc:
        return 1, str(exc)


def crop_02_paths(summary_token: str) -> tuple[Path, Path]:
    return (
        CSV_DIR / f"02_espac_crop_lci_table_filtered__summary_{summary_token}.csv",
        CSV_DIR / f"02_espac_crop_lci_table_filtered__summary_{summary_token}_uncertainty.csv",
    )


def crop_02_unfiltered_path(summary_token: str) -> Path:
    return CSV_DIR / f"02_espac_crop_lci_table__summary_{summary_token}.csv"


def crop_02_unfiltered_unc_path(summary_token: str) -> Path:
    return CSV_DIR / f"02_espac_crop_lci_table__summary_{summary_token}_uncertainty.csv"


def crop_group_cols(summary_token: str) -> list[str] | None:
    mapping = {
        "province": ["Region", "Province", "Crop", "Category"],
        "region": ["Region"],
        "crop_national": ["Crop", "Category"],
        "cropping_system": ["Region", "Cropping_system"],
        "irrig_m3_class": ["Region", "Irrig_m3_class"],
        "farm_size_class": ["Region", "Farm_size_class"],
        "crop_group": ["Region", "Crop_group"],
        "crop_group_national": ["Crop_group"],
    }
    return mapping.get(str(summary_token).strip().lower())


def crop_focus_label(crop_focus: str, otros_subcrop: str) -> str:
    focus = str(crop_focus or "All").strip().upper()
    sub = str(otros_subcrop or "All").strip().upper()
    if focus == "ALL":
        return "All crops"
    if focus == "PERMANENT":
        return "Permanent crops"
    if focus == "TRANSITORY":
        return "Transitory crops"
    if focus == "OTROS":
        mapping = {
            "ALL": "OTROS crops",
            "PERMANENT": "OTROS permanent crops",
            "TRANSITORY": "OTROS transitory crops",
            "CULTIVATED_PASTURE": "OTROS cultivated pasture crops",
        }
        return mapping.get(sub, "OTROS crops")
    return str(crop_focus)


def crop_category_label(crop_focus: str, otros_subcrop: str) -> str:
    focus = str(crop_focus or "All").strip().upper()
    sub = str(otros_subcrop or "All").strip().upper()
    if focus == "PERMANENT":
        return "permanent"
    if focus == "TRANSITORY":
        return "transitory"
    if focus == "OTROS":
        mapping = {
            "ALL": "otros",
            "PERMANENT": "otros_permanent",
            "TRANSITORY": "otros_transitory",
            "CULTIVATED_PASTURE": "cultivated_pasture",
        }
        return mapping.get(sub, "otros")
    return "all_categories"


def _series_mode_or_first(values: pd.Series):
    non_null = values.dropna()
    if non_null.empty:
        return None
    try:
        modes = non_null.mode(dropna=True)
        if not modes.empty:
            return modes.iloc[0]
    except Exception:
        pass
    return non_null.iloc[0]


def ensure_crop_strategy_dimensions(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out

    if "Irrig_m3_class" not in out.columns:
        if "Irrig_m3" in out.columns:
            irrig = pd.to_numeric(out.get("Irrig_m3", 0.0), errors="coerce").fillna(0.0)
            out["Irrig_m3_class"] = irrig.map(lambda v: "Irrig_m3 <> 0" if float(v) > 0 else "Irrig_m3 = 0")
        elif "Irrig_equipment" in out.columns:
            eq = out["Irrig_equipment"].astype(str).str.strip().str.lower()
            out["Irrig_m3_class"] = eq.map(lambda v: "Irrig_m3 = 0" if "sin riego" in v else "Irrig_m3 <> 0")
        else:
            out["Irrig_m3_class"] = "(unknown)"

    if "Farm_size_class" not in out.columns:
        area = pd.to_numeric(out.get("Area_ha", pd.Series([None] * len(out), index=out.index)), errors="coerce")
        out["Farm_size_class"] = np.select(
            [area <= 1, area <= 10, area <= 100, area > 100],
            ["<= 1 ha", "<= 10 ha", "<= 100 ha", "> 100 ha"],
            default="(unknown)",
        )

    if "Crop_group" not in out.columns and "Crop" in out.columns:
        cat_series = out["Category"] if "Category" in out.columns else pd.Series([""] * len(out), index=out.index)
        p2_series = (
            out["Packaging_type2"] if "Packaging_type2" in out.columns else pd.Series([""] * len(out), index=out.index)
        )
        out["Crop_group"] = [
            infer_crop_group_row(str(crop), category=str(cat), packaging_type2=str(p2))
            for crop, cat, p2 in zip(out["Crop"].astype(str), cat_series.astype(str), p2_series.astype(str))
        ]

    if "Cropping_system" not in out.columns:
        cond_col = None
        for col in ("nuevacondicion", "ct_nuevacondicion", "In_association", "condition"):
            if col in out.columns:
                cond_col = col
                break
        if cond_col is None:
            out["Cropping_system"] = "(unknown)"
        else:
            txt = out[cond_col].astype(str).str.upper()
            out["Cropping_system"] = txt.map(
                lambda v: "monocrop" if "SOLO" in v else ("in association" if "ASOCIADO" in v else "(unknown)")
            )

    return out


def crop_base_for_count() -> pd.DataFrame | None:
    candidates = [
        CSV_DIR / "02_espac_crop_lci_table__summary_province.csv",
        CSV_DIR / "02_espac_crop_lci_table_filtered__summary_province.csv",
        CSV_DIR / "03-05_espac_crop_lci_table_filtered_dfe__summary_province.csv",
    ]
    for path in candidates:
        if path.exists():
            try:
                return pd.read_csv(path, low_memory=False)
            except Exception:
                return None
    return None


def family_crop_list(otros_family: str) -> list[str]:
    db = PROJECT_DIR / "outputs" / "01_espac_2024.sqlite"
    if not db.exists():
        return []
    fam = str(otros_family or "").strip().upper()
    if fam not in {"OTROS PERMANENTES", "OTROS TRANSITORIOS"}:
        return []
    try:
        with sqlite3.connect(db) as con:
            if fam == "OTROS PERMANENTES":
                query = (
                    "SELECT DISTINCT TRIM(COALESCE(NULLIF(rc_clacul,''), NULLIF(cp_nclavr,''))) AS crop_name "
                    "FROM rel_inec_cpnac WHERE UPPER(TRIM(COALESCE(cp_nclavr,'')))='OTROS PERMANENTES'"
                )
            else:
                query = (
                    "SELECT DISTINCT TRIM(COALESCE(NULLIF(ct_codcultiv1_int,''), NULLIF(ct_nclavr,''))) AS crop_name "
                    "FROM rel_inec_ctnac WHERE UPPER(TRIM(COALESCE(ct_nclavr,'')))='OTROS TRANSITORIOS'"
                )
            data = pd.read_sql_query(query, con)
    except Exception:
        return []
    vals = sorted({str(x).strip().upper() for x in data["crop_name"].dropna().tolist() if str(x).strip()})
    return vals


def main_category_crop_list(category: str) -> list[str]:
    base = crop_base_for_count()
    if base is None or "Crop" not in base.columns or "Category" not in base.columns:
        return []
    cat = str(category or "").strip().lower()
    mask = base["Category"].astype(str).str.strip().str.lower().eq(cat)
    vals = sorted({str(x).strip().upper() for x in base.loc[mask, "Crop"].dropna().tolist() if str(x).strip()})
    return vals


def otros_category_options() -> list[str]:
    base = crop_base_for_count()
    if base is None or "Category" not in base.columns:
        return ["All"]
    cats = sorted({str(x).strip().upper() for x in base["Category"].dropna().tolist() if str(x).strip()})
    return ["All"] + cats


def filter_crop_rows(df: pd.DataFrame, crop_focus: str = "All", otros_subcrop: str = "All") -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out
    crop_col = "Crop" if "Crop" in out.columns else ("crop" if "crop" in out.columns else None)
    cat_col = "Category" if "Category" in out.columns else ("category" if "category" in out.columns else None)
    focus = str(crop_focus or "All").strip().upper()
    sub = str(otros_subcrop or "All").strip().upper()

    if focus == "PERMANENT" and cat_col:
        out = out[out[cat_col].astype(str).str.strip().str.lower() == "permanent"].copy()
    elif focus == "TRANSITORY" and cat_col:
        out = out[out[cat_col].astype(str).str.strip().str.lower() == "transitory"].copy()
    elif focus == "OTROS" and crop_col:
        crop_u = out[crop_col].astype(str).str.strip().str.upper()
        if sub == "PERMANENT":
            out = out[crop_u == "OTROS PERMANENTES"].copy()
        elif sub == "TRANSITORY":
            out = out[crop_u == "OTROS TRANSITORIOS"].copy()
        elif sub == "CULTIVATED_PASTURE":
            out = out[crop_u == "OTROS PASTOS CULTIVADOS"].copy()
        else:
            out = out[crop_u.isin({"OTROS PERMANENTES", "OTROS TRANSITORIOS", "OTROS PASTOS CULTIVADOS"})].copy()
    return out


def apply_crop_selection_semantics(
    df: pd.DataFrame,
    summary_token: str,
    crop_focus: str,
    otros_subcrop: str,
) -> pd.DataFrame:
    out = filter_crop_rows(df, crop_focus, otros_subcrop)
    if out.empty:
        return out
    focus_u = str(crop_focus or "All").strip().upper()
    if str(summary_token).strip().lower() == "crop_national" and focus_u == "ALL":
        if "Crop" in out.columns and "Category" in out.columns:
            crop_u = out["Crop"].astype(str).str.strip().str.upper()
            cat_l = out["Category"].astype(str).str.strip().str.lower()
            keep_main = cat_l.isin({"permanent", "transitory"})
            keep_otros_pasture = crop_u.eq("OTROS PASTOS CULTIVADOS")
            out = out[keep_main | keep_otros_pasture].copy()
    return out


def aggregate_crop_main_from_base(
    df: pd.DataFrame,
    summary_token: str,
    crop_focus: str = "All",
    otros_subcrop: str = "All",
) -> pd.DataFrame:
    group_cols = crop_group_cols(summary_token)
    if not group_cols:
        return df.copy()

    work = ensure_crop_strategy_dimensions(df)
    work = apply_crop_selection_semantics(work, summary_token, crop_focus, otros_subcrop)
    active_group_cols = [col for col in group_cols if col in work.columns]
    if not active_group_cols:
        return pd.DataFrame()

    weight = pd.to_numeric(work.get("count", pd.Series([1.0] * len(work), index=work.index)), errors="coerce").fillna(0.0)
    work = work.copy()
    work["_agg_weight"] = weight.where(weight > 0, 1.0)

    numeric_cols = [
        col
        for col in work.select_dtypes(include="number").columns
        if col not in active_group_cols and col != "_agg_weight"
    ]

    rows: list[dict[str, Any]] = []
    for keys, part in work.groupby(active_group_cols, dropna=False):
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        row = {col: val for col, val in zip(active_group_cols, key_tuple)}
        if "Region" in work.columns and "Region" not in active_group_cols:
            row["Region"] = "(all regions confounded)"
        if "Province" in work.columns and "Province" not in active_group_cols:
            row["Province"] = "(all provinces confounded)"
        if "Crop" in work.columns and "Crop" not in active_group_cols:
            row["Crop"] = (
                "(all crops in group)" if "Crop_group" in active_group_cols else crop_focus_label(crop_focus, otros_subcrop)
            )
        if "Category" in work.columns and "Category" not in active_group_cols:
            row["Category"] = row.get("Crop_group", crop_category_label(crop_focus, otros_subcrop))

        for col in work.columns:
            if col in active_group_cols or col in numeric_cols or col == "_agg_weight":
                continue
            if col not in row:
                row[col] = _series_mode_or_first(part[col])

        weights = part["_agg_weight"]
        for col in numeric_cols:
            series = pd.to_numeric(part[col], errors="coerce")
            valid = series.notna()
            if not valid.any():
                row[col] = None
                continue
            if col == "count":
                row[col] = float(series[valid].sum())
                continue
            w = weights[valid]
            denom = float(w.sum())
            row[col] = float((series[valid] * w).sum() / denom) if denom > 0 else float(series[valid].mean())

        rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    base_cols = [col for col in work.columns if col != "_agg_weight"]
    derived_cols = [col for col in out.columns if col not in base_cols]
    ordered_cols = [col for col in base_cols if col in out.columns] + derived_cols
    return out[ordered_cols]


def aggregate_crop_unc_from_base(
    main_df: pd.DataFrame,
    unc_df: pd.DataFrame,
    summary_token: str,
    crop_focus: str = "All",
    otros_subcrop: str = "All",
) -> pd.DataFrame:
    if unc_df.empty:
        return unc_df.copy()

    group_cols = crop_group_cols(summary_token) or []
    enriched_main = ensure_crop_strategy_dimensions(main_df)
    enriched_main = apply_crop_selection_semantics(enriched_main, summary_token, crop_focus, otros_subcrop)
    join_cols = [c for c in ("Region", "Province", "Crop", "Category") if c in enriched_main.columns and c in unc_df.columns]

    extra_cols = [
        c
        for c in set(join_cols + ["Irrig_m3_class", "Farm_size_class", "Crop_group", "Cropping_system"])
        if c in enriched_main.columns
    ]
    enriched_unc = unc_df.merge(enriched_main[extra_cols].drop_duplicates(), on=join_cols, how="left")

    active_group_cols = [c for c in group_cols if c in enriched_unc.columns]
    if not active_group_cols:
        return enriched_unc.copy()

    metric_roots = sorted({c[:-10] for c in enriched_unc.columns if c.endswith("__minValue")} | {c[:-10] for c in enriched_unc.columns if c.endswith("__maxValue")})

    rows: list[dict[str, Any]] = []
    for keys, part in enriched_unc.groupby(active_group_cols, dropna=False):
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        row = {col: val for col, val in zip(active_group_cols, key_tuple)}

        if "Region" in enriched_unc.columns and "Region" not in active_group_cols:
            row["Region"] = "(all regions confounded)"
        if "Province" in enriched_unc.columns and "Province" not in active_group_cols:
            row["Province"] = "(all provinces confounded)"
        if "Crop" in enriched_unc.columns and "Crop" not in active_group_cols:
            row["Crop"] = (
                "(all crops in group)" if "Crop_group" in active_group_cols else crop_focus_label(crop_focus, otros_subcrop)
            )
        if "Category" in enriched_unc.columns and "Category" not in active_group_cols:
            row["Category"] = row.get("Crop_group", crop_category_label(crop_focus, otros_subcrop))

        for root in metric_roots:
            min_col = f"{root}__minValue"
            max_col = f"{root}__maxValue"
            if min_col in part.columns:
                vals = pd.to_numeric(part[min_col], errors="coerce")
                row[min_col] = float(vals.min()) if vals.notna().any() else _series_mode_or_first(part[min_col])
            if max_col in part.columns:
                vals = pd.to_numeric(part[max_col], errors="coerce")
                row[max_col] = float(vals.max()) if vals.notna().any() else _series_mode_or_first(part[max_col])

        rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    preferred = [c for c in active_group_cols if c in out.columns]
    for col in (
        "Region",
        "Province",
        "Crop",
        "Category",
        "Irrig_m3_class",
        "Farm_size_class",
        "Crop_group",
        "Cropping_system",
    ):
        if col in out.columns and col not in preferred:
            preferred.append(col)
    metric_cols = [col for col in out.columns if col not in preferred]
    return out[preferred + metric_cols]


def load_crop_stage02_source_frames(
    summary_token: str,
    crop_focus: str = "All",
    otros_subcrop: str = "All",
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    province_main = crop_02_unfiltered_path("province")
    province_unc = crop_02_unfiltered_unc_path("province")
    if not province_main.exists():
        expected_filtered, _ = crop_02_paths(summary_token)
        expected_unfiltered = crop_02_unfiltered_path(summary_token)
        raise FileNotFoundError(
            f"Missing stage-02 crop source for '{summary_token}'. Checked: {expected_filtered}, {expected_unfiltered}, and {province_main}."
        )

    base_main = pd.read_csv(province_main, low_memory=False)
    base_unc = pd.read_csv(province_unc, low_memory=False) if province_unc.exists() else pd.DataFrame()

    return (
        aggregate_crop_main_from_base(base_main, summary_token, crop_focus, otros_subcrop),
        aggregate_crop_unc_from_base(base_main, base_unc, summary_token, crop_focus, otros_subcrop),
        "derived_from_province",
    )


def write_crop_stage02_selection(summary_token: str, crop_focus: str, otros_subcrop: str) -> tuple[Path, Path]:
    main_df, unc_df, _ = load_crop_stage02_source_frames(summary_token, crop_focus, otros_subcrop)
    out_main_df = main_df.copy()

    possible_key_cols = (
        "Region",
        "Province",
        "Crop",
        "Category",
        "Crop_group",
        "Cropping_system",
        "Irrig_m3_class",
        "Farm_size_class",
    )
    key_cols = [c for c in possible_key_cols if c in out_main_df.columns and c in unc_df.columns]

    if not unc_df.empty:
        if key_cols:
            out_unc_df = unc_df.merge(out_main_df[key_cols].drop_duplicates(), on=key_cols, how="inner")
        else:
            out_unc_df = unc_df.copy()
    else:
        out_unc_df = pd.DataFrame()

    out_main, out_unc = crop_02_paths(summary_token)
    out_main_df.to_csv(out_main, index=False)
    out_unc_df.to_csv(out_unc, index=False)
    return out_main, out_unc


def set_crop_meta(summary_token: str, selected_crop: str = "All", selected_subcrop: str = "All") -> None:
    main, unc = crop_02_paths(summary_token)
    payload = {
        "summary_level": summary_token,
        "summary_token": summary_token,
        "filtered_csv": str(main.resolve()),
        "filtered_uncertainty_csv": str(unc.resolve()),
        "selected_crop": str(selected_crop),
        "selected_subcrop": str(selected_subcrop),
        "otros_crop_filter": str(selected_subcrop),
    }
    CROP_META.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def get_crop_meta() -> dict:
    if not CROP_META.exists():
        return {}
    try:
        return json.loads(CROP_META.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_livestock_meta() -> dict:
    path = PROJECT_DIR / "outputs" / "02_latest_livestock_filtered_export_summary.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def livestock_02_paths(summary_token: str) -> tuple[Path, Path]:
    return (
        CSV_DIR / f"02_espac_livestock_lci_table_filtered__summary_{summary_token}.csv",
        CSV_DIR / f"02_espac_livestock_lci_table_filtered__summary_{summary_token}_uncertainty.csv",
    )


def dfe_paths(domain: str, summary_token: str) -> tuple[Path, Path]:
    if domain == "crops":
        return (
            CSV_DIR / f"03-05_espac_crop_lci_table_filtered_dfe__summary_{summary_token}.csv",
            CSV_DIR / f"03-05_espac_crop_lci_table_filtered_dfe__summary_{summary_token}_uncertainty.csv",
        )
    return (
        CSV_DIR / f"03-05_espac_livestock_lci_table_filtered_dfe__summary_{summary_token}.csv",
        CSV_DIR / f"03-05_espac_livestock_lci_table_filtered_dfe__summary_{summary_token}_uncertainty.csv",
    )


def xml_target(domain: str, summary_token: str, combine_systems: bool = False) -> Path:
    if domain == "crops":
        return PROJECT_DIR / "outputs" / "05_xml_exports_crop_lci" / f"summary_{summary_token}"
    if summary_token == "national":
        suffix = "combined" if combine_systems else "not_combined"
        return PROJECT_DIR / "outputs" / "05_xml_exports_livestock_lci" / f"summary_national_{suffix}"
    return PROJECT_DIR / "outputs" / "05_xml_exports_livestock_lci" / f"summary_{summary_token}"


def crop_xml_target(summary_token: str, crop_focus: str, otros_subcrop: str) -> Path:
    return PROJECT_DIR / "outputs" / "05_xml_exports_crop_lci" / f"summary_{summary_token}"


def postprocess_crop_xml_outputs(summary_token: str, crop_focus: str, otros_subcrop: str) -> tuple[Path, int]:
    dst = crop_xml_target(summary_token, crop_focus, otros_subcrop)
    if not dst.exists():
        return dst, 0

    xmls = sorted(dst.glob("*.xml"))
    count = 0
    for _path in xmls:
        count += 1
    return dst, count


def estimate_xml_count(
    domain: str,
    summary: str,
    crop_focus: str = "All",
    otros_subcrop: str = "All",
    combine_systems: bool = False,
) -> int | None:
    if domain == "crops":
        df = crop_base_for_count()
        if df is None:
            return None
        df = apply_crop_selection_semantics(df, summary, crop_focus, otros_subcrop)
        if df.empty:
            return 0
        df = ensure_crop_strategy_dimensions(df)
        keys = crop_group_cols(summary) or []
        keys = [k for k in keys if k in df.columns]
        if not keys:
            return None

        focus_u = str(crop_focus or "All").strip().upper()
        if summary == "crop_national" and focus_u == "ALL":
            if "Crop" in df.columns and "Category" in df.columns:
                cat = df["Category"].astype(str).str.strip().str.lower()
                crop = df["Crop"].astype(str).str.strip().str.upper()
                perm_n = int(crop[cat.eq("permanent")].nunique())
                trans_n = int(crop[cat.eq("transitory")].nunique())
                otros_labels = {"OTROS PERMANENTES", "OTROS TRANSITORIOS", "OTROS PASTOS CULTIVADOS"}
                otros_n = int(sum(1 for lbl in otros_labels if bool((crop == lbl).any())))
                return perm_n + trans_n + otros_n

        if focus_u == "OTROS" and "Crop" in keys:
            sub_u = str(otros_subcrop or "All").strip().upper()
            perm = family_crop_list("OTROS PERMANENTES")
            trans = family_crop_list("OTROS TRANSITORIOS")
            past = main_category_crop_list("cultivated_pasture")
            expanded_rows = []
            for _, row in df.iterrows():
                crop_u = str(row.get("Crop", "")).strip().upper()
                if crop_u == "OTROS PERMANENTES":
                    targets = perm if sub_u in {"ALL", "PERMANENT"} else []
                elif crop_u == "OTROS TRANSITORIOS":
                    targets = trans if sub_u in {"ALL", "TRANSITORY"} else []
                elif crop_u == "OTROS PASTOS CULTIVADOS":
                    targets = past if sub_u in {"ALL", "CULTIVATED_PASTURE"} else []
                else:
                    targets = []
                for target in targets:
                    row2 = row.copy()
                    row2["Crop"] = target
                    expanded_rows.append(row2)
            if not expanded_rows:
                return 0
            expanded = pd.DataFrame(expanded_rows)
            return int(len(expanded[keys].drop_duplicates()))

        return int(len(df[keys].drop_duplicates()))

    if summary == "national":
        try:
            from scripts.livestock_xml_generator_v2 import (
                LEGACY_STRATEGY_PRODUCTS,
                aggregate_national_product,
                expand_legacy_products_from_other,
            )

            src = CSV_DIR / "07_product_lci_v2.csv"
            if not src.exists():
                return None
            df = pd.read_csv(src, low_memory=False)
            if "Product" in df.columns and "product" not in df.columns:
                df = df.rename(columns={"Product": "product"})
            df = aggregate_national_product(df, combine_systems=combine_systems)
            df = expand_legacy_products_from_other(
                df,
                aggregate_mode="national_product",
                stock_path=CSV_DIR / "07_animal_class_stock.csv",
            )
            df = df[df["product"].astype(str).isin(LEGACY_STRATEGY_PRODUCTS)].copy()
            return int(len(df))
        except Exception:
            return None
        return None

    if summary in {"region", "province"}:
        src = CSV_DIR / "07_product_lci_v2.csv"
        if not src.exists():
            return None
        df = pd.read_csv(src, usecols=["product", "ual_prov"], low_memory=False)
        legacy_products = {
            "cattle_live",
            "donkey_live",
            "eggs",
            "goat_live",
            "horse_live",
            "meat_poultry",
            "milk",
            "mule_live",
            "ovine_live",
            "swine_live",
        }
        prov_to_region = {
            "AZUAY": "sierra", "BOLIVAR": "sierra", "BOLÍVAR": "sierra", "CANAR": "sierra", "CAÑAR": "sierra",
            "CARCHI": "sierra", "CHIMBORAZO": "sierra", "COTOPAXI": "sierra", "IMBABURA": "sierra", "LOJA": "sierra",
            "PICHINCHA": "sierra", "TUNGURAHUA": "sierra", "EL ORO": "costa", "ESMERALDAS": "costa", "GUAYAS": "costa",
            "LOS RIOS": "costa", "LOS RÍOS": "costa", "MANABI": "costa", "MANABÍ": "costa", "SANTA ELENA": "costa",
            "SANTO DOMINGO DE LOS TSACHILAS": "costa", "SANTO DOMINGO DE LOS TSÁCHILAS": "costa",
            "MORONA SANTIAGO": "oriente", "NAPO": "oriente", "ORELLANA": "oriente", "PASTAZA": "oriente",
            "SUCUMBIOS": "oriente", "SUCUMBÍOS": "oriente", "ZAMORA CHINCHIPE": "oriente",
        }
        src_products = set(df["product"].astype(str).unique().tolist())
        prod = set()
        for p in src_products:
            if p == "cattle_meat":
                prod.add("cattle_live")
            elif p == "other_livestock_live":
                prod.update({"horse_live", "mule_live", "donkey_live", "goat_live"})
            else:
                prod.add(p)
        prod = prod.intersection(legacy_products)
        if summary == "region":
            df["region"] = df["ual_prov"].astype(str).str.strip().str.upper().map(prov_to_region).fillna("unknown")
            regions = set(df["region"].astype(str).unique().tolist())
            return len(prod) * len(regions)
        prov = set(df["ual_prov"].astype(str).str.strip())
        return len(prod) * len([p for p in prov if p])

    return None


def _inventory_label(row: pd.Series) -> str:
    preferred = [
        "Product",
        "product",
        "Crop",
        "Crop_group",
        "Region",
        "Province",
        "System",
        "Cropping_system",
        "Irrig_m3_class",
        "Farm_size_class",
        "Category",
    ]
    parts: list[str] = []
    for col in preferred:
        if col in row.index:
            val = str(row.get(col, "")).strip()
            if val and val.lower() not in {"nan", "(all provinces confounded)", "(all regions confounded)"}:
                parts.append(val)
    if not parts:
        return "Inventory"
    seen: list[str] = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return " | ".join(seen[:4])


def inventory_heatmap(
    df: pd.DataFrame,
    title: str,
    mode: str = "absolute",
    max_items: int = 28,
    max_inventories: int = 40,
):
    if df is None or df.empty:
        st.info("No data to plot.")
        return

    num = df.select_dtypes(include="number").copy()
    if num.empty:
        st.info("No numeric inventory items to plot.")
        return

    non_empty_rows = num.abs().sum(axis=0) > 0
    num = num.loc[:, non_empty_rows]
    if num.empty:
        st.info("All numeric inventory items are zero in this selection.")
        return

    row_strength = num.abs().sum(axis=0).sort_values(ascending=False)
    item_cols = row_strength.head(max_items).index.tolist()
    num = num[item_cols]

    labeled = num.copy()
    labeled.index = df.apply(_inventory_label, axis=1)
    if len(labeled) > max_inventories:
        labeled = labeled.iloc[:max_inventories].copy()

    matrix = labeled.T
    if matrix.empty:
        st.info("No values available for heatmap rendering.")
        return

    matrix_values = matrix.astype(float)
    color_label = "Value"
    subtitle_note = ""
    if mode == "row_normalized":
        denom = matrix_values.abs().max(axis=1).replace(0, np.nan)
        matrix_values = matrix_values.div(denom, axis=0).fillna(0.0)
        color_label = "Normalized value"
        subtitle_note = "Rows normalized to each inventory item's max absolute value."
    elif mode == "log_positive":
        positive = matrix_values.clip(lower=0.0)
        matrix_values = np.log10(positive + 1.0)
        color_label = "log10(value + 1)"
        subtitle_note = "Negative values clipped to zero for log display."

    vmax = float(np.nanmax(np.abs(matrix_values.to_numpy(dtype=float)))) if matrix_values.size else 1.0
    if not np.isfinite(vmax) or vmax == 0:
        vmax = 1.0

    has_negative = bool((matrix_values.to_numpy(dtype=float) < 0).any())
    fig = px.imshow(
        matrix_values,
        labels={"x": "LCIs", "y": "Inventory items", "color": color_label},
        color_continuous_scale="RdBu_r" if has_negative else "YlGnBu",
        zmin=(-vmax if has_negative else 0.0),
        zmax=vmax,
        aspect="auto",
    )
    fig.update_layout(
        title=title,
        height=max(500, 22 * len(matrix.index) + 220),
        xaxis_tickangle=-45,
        margin=dict(l=40, r=20, t=60, b=120),
    )
    fig.update_xaxes(side="bottom")

    if subtitle_note:
        fig.add_annotation(
            text=subtitle_note,
            xref="paper",
            yref="paper",
            x=0,
            y=1.16,
            showarrow=False,
            xanchor="left",
        )

    st.plotly_chart(fig, use_container_width=True)


def load_df(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return None


def ensure_selection_confirmed(confirmed: bool) -> bool:
    if not confirmed:
        st.warning("Selection not confirmed. Tick the confirmation checkbox first.")
        return False
    return True


def create_lcis(
    domain: str,
    strategy: str,
    crop_focus: str,
    otros_subcrop: str,
    combine_systems: bool,
    status_callback: Any | None = None,
    progress_callback: Any | None = None,
) -> tuple[bool, str]:
    def _emit_status(message: str) -> None:
        if status_callback is not None:
            status_callback(message)

    def _emit_progress(value: float) -> None:
        if progress_callback is not None:
            progress_callback(value)

    if domain == "crops":
        _emit_progress(0.1)
        _emit_status("Preparing crop selection metadata")
        set_crop_meta(strategy, crop_focus, otros_subcrop)
        _emit_progress(0.5)
        _emit_status("Building and writing crop stage-02 outputs")
        out_main, out_unc = write_crop_stage02_selection(strategy, crop_focus, otros_subcrop)
        _emit_progress(1.0)
        return True, f"Crop LCI selection materialized.\nmain: {out_main}\nuncertainty: {out_unc}"

    cmd = [
        python_executable(),
        str(PROJECT_DIR / "scripts" / "livestock_pipeline_v2_integrated.py"),
        "--stage",
        "02",
        "--summary-token",
        strategy,
        "--db",
        str(PROJECT_DIR / "outputs" / "01_espac_2024.sqlite"),
    ]
    if strategy == "national" and combine_systems:
        cmd.append("--combine-systems")

    timeout_sec = 5400
    started = time.time()

    def _livestock_progress(message: str) -> None:
        elapsed = max(time.time() - started, 0.0)
        # Keep some headroom so the bar does not look fully done before process exit.
        fraction = min((elapsed / timeout_sec) * 0.95, 0.95)
        _emit_progress(fraction)
        _emit_status(message)

    rc, out = run_cmd(
        cmd,
        timeout_sec=timeout_sec,
        progress_callback=_livestock_progress,
        progress_label="Running livestock stage 02",
    )
    _emit_progress(1.0)
    return rc == 0, (out if out else f"livestock LCI creation finished with code {rc}")


def compute_dfe(
    domain: str,
    strategy: str,
    crop_focus: str,
    otros_subcrop: str,
    combine_systems: bool,
    status_callback: Any | None = None,
    progress_callback: Any | None = None,
) -> tuple[bool, str]:
    def _emit_status(message: str) -> None:
        if status_callback is not None:
            status_callback(message)

    def _emit_progress(value: float) -> None:
        if progress_callback is not None:
            progress_callback(value)

    if domain == "crops":
        meta = get_crop_meta()
        if (
            str(meta.get("summary_token", "")) != str(strategy)
            or str(meta.get("selected_crop", "")) != str(crop_focus)
            or str(meta.get("selected_subcrop", "")) != str(otros_subcrop)
        ):
            return False, "Current selection is not materialized for DFE computation. Run Create LCIs first with the current selectors."

        timeout_sec = 10800
        started = time.time()

        def _crop_progress(message: str) -> None:
            elapsed = max(time.time() - started, 0.0)
            fraction = min((elapsed / timeout_sec) * 0.95, 0.95)
            _emit_progress(fraction)
            _emit_status(message)

        cmd = [
            python_executable(),
            "-m",
            "jupyter",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            str(PROJECT_DIR / "notebooks" / "3_crops_espac_direct_field_emissions.ipynb"),
            "--output",
            str(PROJECT_DIR / "outputs" / "_tmp_nb3_crops_executed.ipynb"),
        ]
        rc, out = run_cmd(
            cmd,
            timeout_sec=timeout_sec,
            progress_callback=_crop_progress,
            progress_label="Executing crops DFE notebook",
        )
        _emit_progress(1.0)
        return rc == 0, (out if out else f"DFE computation finished with code {rc}")

    meta = get_livestock_meta()
    if strategy == "national" and bool(meta.get("combine_systems", False)) != bool(combine_systems):
        return False, "Current national livestock selection was materialized with a different system-combination setting. Run Create LCIs again."

    timeout_sec = 7200
    started = time.time()

    def _livestock_progress(message: str) -> None:
        elapsed = max(time.time() - started, 0.0)
        fraction = min((elapsed / timeout_sec) * 0.95, 0.95)
        _emit_progress(fraction)
        _emit_status(message)

    cmd = [
        python_executable(),
        str(PROJECT_DIR / "scripts" / "livestock_pipeline_v2_integrated.py"),
        "--stage",
        "03",
        "--summary-token",
        strategy,
    ]
    rc, out = run_cmd(
        cmd,
        timeout_sec=timeout_sec,
        progress_callback=_livestock_progress,
        progress_label="Running livestock stage 03",
    )
    _emit_progress(1.0)
    return rc == 0, (out if out else f"DFE computation finished with code {rc}")


def generate_xml(
    domain: str,
    strategy: str,
    crop_focus: str,
    otros_subcrop: str,
    combine_systems: bool,
    status_callback: Any | None = None,
    progress_callback: Any | None = None,
) -> tuple[bool, str]:
    def _emit_status(message: str) -> None:
        if status_callback is not None:
            status_callback(message)

    def _emit_progress(value: float) -> None:
        if progress_callback is not None:
            progress_callback(value)

    if domain == "crops":
        meta = get_crop_meta()
        if (
            str(meta.get("summary_token", "")) != str(strategy)
            or str(meta.get("selected_crop", "")) != str(crop_focus)
            or str(meta.get("selected_subcrop", "")) != str(otros_subcrop)
        ):
            return False, "Current selection is not materialized for XML generation. Run Create LCIs first with the current selectors."

        timeout_sec = 10800
        started = time.time()

        def _crop_progress(message: str) -> None:
            elapsed = max(time.time() - started, 0.0)
            fraction = min((elapsed / timeout_sec) * 0.9, 0.9)
            _emit_progress(fraction)
            _emit_status(message)

        cmd = [
            python_executable(),
            "-m",
            "jupyter",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            str(PROJECT_DIR / "notebooks" / "5_crops_espac_lci_xml_generator.ipynb"),
            "--output",
            str(PROJECT_DIR / "outputs" / "_tmp_nb5_crops_executed.ipynb"),
        ]
        rc, out = run_cmd(
            cmd,
            timeout_sec=timeout_sec,
            progress_callback=_crop_progress,
            progress_label="Executing crops XML notebook",
        )
        dest, n = postprocess_crop_xml_outputs(strategy, crop_focus, otros_subcrop)
        _emit_status("Postprocessing crop XML outputs")
        _emit_progress(1.0)
        base = out if out else f"XML generation finished with code {rc}"
        return rc == 0, f"{base}\nxml output folder: {dest}\nxml_count: {n}"

    meta = get_livestock_meta()
    if strategy == "national" and bool(meta.get("combine_systems", False)) != bool(combine_systems):
        return False, "Current national livestock selection was materialized with a different system-combination setting. Run Create LCIs again."

    timeout_sec = 7200
    started = time.time()

    def _livestock_progress(message: str) -> None:
        elapsed = max(time.time() - started, 0.0)
        fraction = min((elapsed / timeout_sec) * 0.95, 0.95)
        _emit_progress(fraction)
        _emit_status(message)

    cmd = [
        python_executable(),
        str(PROJECT_DIR / "scripts" / "livestock_pipeline_v2_integrated.py"),
        "--stage",
        "05",
        "--summary-token",
        strategy,
    ]
    if strategy == "national" and combine_systems:
        cmd.append("--combine-systems")
    rc, out = run_cmd(
        cmd,
        timeout_sec=timeout_sec,
        progress_callback=_livestock_progress,
        progress_label="Running livestock stage 05",
    )
    _emit_progress(1.0)
    return rc == 0, (out if out else f"XML generation finished with code {rc}")


def render_preview(domain: str, strategy: str, heatmap_mode: str) -> None:
    if domain == "crops":
        main_02, unc_02 = crop_02_paths(strategy)
    else:
        main_02, unc_02 = livestock_02_paths(strategy)
    main_03, unc_03 = dfe_paths(domain, strategy)

    df03 = load_df(main_03)
    unc02_df = load_df(unc_02)
    unc03_df = load_df(unc_03)

    st.subheader(f"Preview for {domain} / {strategy}")
    st.caption(f"02 main: {main_02}")
    st.caption(f"03-05 main: {main_03}")

    st.markdown("### Aggregated LCIs + DFE")
    if df03 is None:
        st.info("LCI + DFE table not found.")
    else:
        st.dataframe(df03.head(200), use_container_width=True)
        inventory_heatmap(df03, "LCI + DFE inventory heatmap", mode=heatmap_mode)

    st.markdown("### Uncertainty files")
    col1, col2 = st.columns(2)
    with col1:
        st.caption(str(unc_02))
        if unc02_df is None:
            st.info("02 uncertainty file not found.")
        else:
            st.dataframe(unc02_df.head(100), use_container_width=True)
    with col2:
        st.caption(str(unc_03))
        if unc03_df is None:
            st.info("03-05 uncertainty file not found.")
        else:
            st.dataframe(unc03_df.head(100), use_container_width=True)


def run_app() -> None:
    st.set_page_config(page_title="ESPAC LCI Pipeline", layout="wide")
    st.title("ESPAC LCI Pipeline App (Streamlit)")
    st.markdown(
        "Choose pipeline and strategy, confirm selection, then run Create LCIs, Compute DFE, and Generate XML."
    )

    with st.sidebar:
        st.header("Controls")
        domain = st.selectbox("Pipeline", options=["crops", "livestock"], index=0)
        strategy_opts = CROP_STRATEGIES if domain == "crops" else LIVESTOCK_STRATEGIES
        default_strategy = "crop_national" if domain == "crops" else "national"
        strategy = st.selectbox(
            "Aggregation strategy",
            options=strategy_opts,
            index=strategy_opts.index(default_strategy) if default_strategy in strategy_opts else 0,
        )
        st.caption(STRATEGY_HELP.get(domain, {}).get(strategy, ""))

        if domain == "livestock":
            combine_systems = st.checkbox(
                "Combine systems into single national inventory",
                value=True if strategy == "national" else False,
                disabled=(strategy != "national"),
            )
        else:
            combine_systems = False

        if domain == "crops":
            crop_focus = st.selectbox("Crop focus", options=["All", "PERMANENT", "TRANSITORY", "OTROS"], index=0)
            if crop_focus == "OTROS":
                otros_subcrop = st.selectbox("OTROS category", options=otros_category_options(), index=0)
            else:
                otros_subcrop = "All"
        else:
            crop_focus = "All"
            otros_subcrop = "All"

        confirm = st.checkbox(
            "Confirm selection",
            value=False,
            help="Required before running Create LCIs, Compute DFE, or Generate XML.",
        )

        heatmap_mode = st.selectbox(
            "Heatmap mode",
            options=["absolute", "row_normalized", "log_positive"],
            index=0,
        )

        estimated_xml_count = estimate_xml_count(
            domain,
            strategy,
            crop_focus,
            otros_subcrop,
            combine_systems=bool(combine_systems),
        )
        if estimated_xml_count is None:
            st.info("XMLs to be generated with current selection: not available")
        else:
            st.info(f"XMLs to be generated with current selection: {estimated_xml_count}")

    xml_dest = (
        crop_xml_target(strategy, crop_focus, otros_subcrop)
        if domain == "crops"
        else xml_target(domain, strategy, combine_systems=bool(combine_systems))
    )
    st.caption(f"XML target folder: {xml_dest}")

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col1:
        do_create = st.button("Create LCIs", use_container_width=True)
    with col2:
        do_dfe = st.button("Compute DFE", use_container_width=True)
    with col3:
        do_xml = st.button("Generate XML", use_container_width=True)
    with col4:
        do_refresh = st.button("Refresh Preview", use_container_width=True)

    def _show_result(action_name: str, ok: bool, log: str) -> None:
        if ok:
            st.success(f"{action_name} finished.")
        else:
            low = str(log).lower()
            if "run create lcis first" in low or "not materialized" in low or "different system-combination" in low:
                st.warning(log)
            else:
                st.error(f"{action_name} failed.")
        st.text_area(f"{action_name} log", value=str(log)[-15000:], height=220)

    if do_create and ensure_selection_confirmed(confirm):
        status_box = st.empty()
        progress_bar = st.progress(0.0, text="Starting Create LCIs...")
        with st.spinner("Creating LCIs..."):
            try:
                ok, log = create_lcis(
                    domain,
                    strategy,
                    crop_focus,
                    otros_subcrop,
                    combine_systems,
                    status_callback=lambda msg: status_box.info(msg),
                    progress_callback=lambda val: progress_bar.progress(
                        float(min(max(val, 0.0), 1.0)),
                        text=f"Create LCIs progress: {int(min(max(val, 0.0), 1.0) * 100)}%",
                    ),
                )
            except Exception as exc:
                ok, log = False, str(exc)
        progress_bar.empty()
        status_box.empty()
        _show_result("Create LCIs", ok, log)

    if do_dfe and ensure_selection_confirmed(confirm):
        status_box = st.empty()
        progress_bar = st.progress(0.0, text="Starting Compute DFE...")
        with st.spinner("Computing DFE..."):
            try:
                ok, log = compute_dfe(
                    domain,
                    strategy,
                    crop_focus,
                    otros_subcrop,
                    combine_systems,
                    status_callback=lambda msg: status_box.info(msg),
                    progress_callback=lambda val: progress_bar.progress(
                        float(min(max(val, 0.0), 1.0)),
                        text=f"Compute DFE progress: {int(min(max(val, 0.0), 1.0) * 100)}%",
                    ),
                )
            except Exception as exc:
                ok, log = False, str(exc)
        progress_bar.empty()
        status_box.empty()
        _show_result("Compute DFE", ok, log)

    if do_xml and ensure_selection_confirmed(confirm):
        status_box = st.empty()
        progress_bar = st.progress(0.0, text="Starting Generate XML...")
        with st.spinner("Generating XML..."):
            try:
                ok, log = generate_xml(
                    domain,
                    strategy,
                    crop_focus,
                    otros_subcrop,
                    combine_systems,
                    status_callback=lambda msg: status_box.info(msg),
                    progress_callback=lambda val: progress_bar.progress(
                        float(min(max(val, 0.0), 1.0)),
                        text=f"Generate XML progress: {int(min(max(val, 0.0), 1.0) * 100)}%",
                    ),
                )
            except Exception as exc:
                ok, log = False, str(exc)
        progress_bar.empty()
        status_box.empty()
        _show_result("Generate XML", ok, log)

    if do_refresh or not any([do_create, do_dfe, do_xml]):
        render_preview(domain, strategy, heatmap_mode)


if __name__ == "__main__":
    run_app()
