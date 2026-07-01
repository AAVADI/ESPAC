import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import json
    import os
    import subprocess
    import sys
    import traceback
    from pathlib import Path
    from typing import Any

    import marimo as mo
    import numpy as np
    import pandas as pd
    import plotly.express as px
    import sqlite3
    import time
    import unicodedata

    PROJECT_DIR = Path(__file__).resolve().parents[1]
    if str(PROJECT_DIR) not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR))
    if str(PROJECT_DIR / "scripts") not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR / "scripts"))
    from scripts.crop_groups import infer_crop_group_row
    from scripts.livestock_pipeline_v2_integrated import (
        _apply_system_labels as apply_livestock_system_labels,
        build_stage02_main as build_livestock_stage02_main,
        build_stage02_unc as build_livestock_stage02_unc,
        load_v2_tables as load_livestock_v2_tables,
    )
    CSV_DIR = PROJECT_DIR / "outputs" / "CSVs"
    CROP_META = PROJECT_DIR / "outputs" / "02_latest_filtered_export_summary.json"
    CROP_REFERENCE_CACHE = CSV_DIR / "reference_cache_crops_all_combinations.csv"
    LIVESTOCK_REFERENCE_CACHE = CSV_DIR / "reference_cache_livestock_all_combinations.csv"

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
            "national": (
                "One inventory per livestock product at national level. "
                "This is the only livestock national path and it always uses the integrated V2 model."
            ),
        },
    }

    def run_cmd(cmd: list[str]) -> tuple[int, str]:
        try:
            env = dict(os.environ)
            existing = env.get("PYTHONPATH", "")
            project_paths = [str(PROJECT_DIR), str(PROJECT_DIR / "scripts")]
            env["PYTHONPATH"] = ";".join(project_paths + ([existing] if existing else []))
            p = subprocess.run(
                cmd,
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                env=env,
            )
            out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
            return p.returncode, out.strip()
        except Exception:
            return 1, traceback.format_exc()

    def run_cmd_stream(
        cmd: list[str],
        progress: Any | None = None,
        title: str = "Running command",
        subtitle: str = "Working...",
    ) -> tuple[int, str]:
        try:
            env = dict(os.environ)
            existing = env.get("PYTHONPATH", "")
            project_paths = [str(PROJECT_DIR), str(PROJECT_DIR / "scripts")]
            env["PYTHONPATH"] = ";".join(project_paths + ([existing] if existing else []))
            p = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            started = time.time()
            tick = 0
            while True:
                rc = p.poll()
                if rc is not None:
                    break
                tick += 1
                if progress is not None:
                    progress(
                        increment=0,
                        title=title,
                        subtitle=f"{subtitle} Elapsed: {int(time.time() - started)}s",
                    )
                time.sleep(0.4)
            stdout, stderr = p.communicate()
            out = (stdout or "") + ("\n" + stderr if stderr else "")
            return p.returncode, out.strip()
        except Exception:
            return 1, traceback.format_exc()

    def crop_02_paths(summary_token: str):
        return (
            CSV_DIR / f"02_espac_crop_lci_table_filtered__summary_{summary_token}.csv",
            CSV_DIR / f"02_espac_crop_lci_table_filtered__summary_{summary_token}_uncertainty.csv",
        )

    def crop_02_unfiltered_path(summary_token: str):
        return CSV_DIR / f"02_espac_crop_lci_table__summary_{summary_token}.csv"
    def crop_02_unfiltered_unc_path(summary_token: str):
        return CSV_DIR / f"02_espac_crop_lci_table__summary_{summary_token}_uncertainty.csv"

    def crop_source_paths(summary_token: str) -> tuple[Path | None, Path | None]:
        filtered_main, filtered_unc = crop_02_paths(summary_token)
        unfiltered_main = crop_02_unfiltered_path(summary_token)
        unfiltered_unc = crop_02_unfiltered_unc_path(summary_token)
        if str(summary_token).strip().lower() == "province":
            main_candidates = [unfiltered_main, filtered_main]
            unc_candidates = [unfiltered_unc, filtered_unc]
        else:
            main_candidates = [filtered_main, unfiltered_main]
            unc_candidates = [filtered_unc, unfiltered_unc]
        main = next((p for p in main_candidates if p.exists()), None)
        unc = next((p for p in unc_candidates if p.exists()), None)
        return main, unc

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
            a = pd.to_numeric(out.get("Area_ha", pd.Series([None] * len(out), index=out.index)), errors="coerce")
            import numpy as _np
            out["Farm_size_class"] = _np.select(
                [a <= 1, a <= 10, a <= 100, a > 100],
                ["<= 1 ha", "<= 10 ha", "<= 100 ha", "> 100 ha"],
                default="(unknown)",
            )
        if "Crop_group" not in out.columns and "Crop" in out.columns:
            cat_series = out["Category"] if "Category" in out.columns else pd.Series([""] * len(out), index=out.index)
            p2_series = out["Packaging_type2"] if "Packaging_type2" in out.columns else pd.Series([""] * len(out), index=out.index)
            out["Crop_group"] = [
                infer_crop_group_row(str(crop), category=str(cat), packaging_type2=str(p2))
                for crop, cat, p2 in zip(out["Crop"].astype(str), cat_series.astype(str), p2_series.astype(str))
            ]
        if "Cropping_system" not in out.columns:
            cond_col = None
            for c in ("nuevacondicion", "ct_nuevacondicion", "In_association", "condition"):
                if c in out.columns:
                    cond_col = c
                    break
            if cond_col is None:
                out["Cropping_system"] = "(unknown)"
            else:
                txt = out[cond_col].astype(str).str.upper()
                out["Cropping_system"] = txt.map(
                    lambda v: "monocrop" if "SOLO" in v else ("in association" if "ASOCIADO" in v else "(unknown)")
                )
        return out

    def crop_group_cols(summary_token: str) -> list[str] | None:
        summary = str(summary_token).strip().lower()
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
        return mapping.get(summary)

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

    def aggregate_crop_main_from_base(df: pd.DataFrame, summary_token: str, crop_focus: str = "All", otros_subcrop: str = "All") -> pd.DataFrame:
        grp = crop_group_cols(summary_token)
        if not grp:
            return df.copy()
        work = ensure_crop_strategy_dimensions(df)
        work = apply_crop_selection_semantics(work, summary_token, crop_focus, otros_subcrop)
        group_cols = [c for c in grp if c in work.columns]
        if not group_cols:
            return pd.DataFrame()
        weight = pd.to_numeric(work.get("count", pd.Series([1.0] * len(work), index=work.index)), errors="coerce").fillna(0.0)
        work = work.copy()
        work["_agg_weight"] = weight.where(weight > 0, 1.0)
        numeric_cols = [
            c for c in work.select_dtypes(include="number").columns
            if c not in group_cols and c != "_agg_weight"
        ]
        rows: list[dict[str, Any]] = []
        for keys, part in work.groupby(group_cols, dropna=False):
            key_tuple = keys if isinstance(keys, tuple) else (keys,)
            row = {col: val for col, val in zip(group_cols, key_tuple)}
            if "Region" in work.columns and "Region" not in group_cols:
                row["Region"] = "(all regions confounded)"
            if "Province" in work.columns and "Province" not in group_cols:
                row["Province"] = "(all provinces confounded)"
            if "Crop" in work.columns and "Crop" not in group_cols:
                row["Crop"] = "(all crops in group)" if "Crop_group" in group_cols else crop_focus_label(crop_focus, otros_subcrop)
            if "Category" in work.columns and "Category" not in group_cols:
                row["Category"] = row.get("Crop_group", crop_category_label(crop_focus, otros_subcrop))
            for col in work.columns:
                if col in group_cols or col in numeric_cols or col == "_agg_weight":
                    continue
                if col not in row:
                    row[col] = _series_mode_or_first(part[col])
            weights = part["_agg_weight"]
            total_w = float(weights.sum())
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
        base_cols = [c for c in work.columns if c != "_agg_weight"]
        derived_cols = [c for c in out.columns if c not in base_cols]
        ordered_cols = [c for c in base_cols if c in out.columns] + derived_cols
        return out[ordered_cols]

    def aggregate_crop_unc_from_base(main_df: pd.DataFrame, unc_df: pd.DataFrame, summary_token: str, crop_focus: str = "All", otros_subcrop: str = "All") -> pd.DataFrame:
        if unc_df.empty:
            return unc_df.copy()
        group_cols = crop_group_cols(summary_token) or []
        enriched_main = ensure_crop_strategy_dimensions(main_df)
        enriched_main = apply_crop_selection_semantics(enriched_main, summary_token, crop_focus, otros_subcrop)
        join_cols = [c for c in ("Region", "Province", "Crop", "Category") if c in enriched_main.columns and c in unc_df.columns]
        enriched_unc = unc_df.merge(
            enriched_main[[c for c in set(join_cols + ["Irrig_m3_class", "Farm_size_class", "Crop_group", "Cropping_system"]) if c in enriched_main.columns]].drop_duplicates(),
            on=join_cols,
            how="left",
        )
        active_group_cols = [c for c in group_cols if c in enriched_unc.columns]
        if not active_group_cols:
            return enriched_unc.copy()
        metric_roots = sorted({
            c[:-10] for c in enriched_unc.columns if c.endswith("__minValue")
        } | {
            c[:-10] for c in enriched_unc.columns if c.endswith("__maxValue")
        })
        rows: list[dict[str, Any]] = []
        for keys, part in enriched_unc.groupby(active_group_cols, dropna=False):
            key_tuple = keys if isinstance(keys, tuple) else (keys,)
            row = {col: val for col, val in zip(active_group_cols, key_tuple)}
            if "Region" in enriched_unc.columns and "Region" not in active_group_cols:
                row["Region"] = "(all regions confounded)"
            if "Province" in enriched_unc.columns and "Province" not in active_group_cols:
                row["Province"] = "(all provinces confounded)"
            if "Crop" in enriched_unc.columns and "Crop" not in active_group_cols:
                row["Crop"] = "(all crops in group)" if "Crop_group" in active_group_cols else crop_focus_label(crop_focus, otros_subcrop)
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
        for c in ("Region", "Province", "Crop", "Category", "Irrig_m3_class", "Farm_size_class", "Crop_group", "Cropping_system"):
            if c in out.columns and c not in preferred:
                preferred.append(c)
        metric_cols = [c for c in out.columns if c not in preferred]
        return out[preferred + metric_cols]

    def load_crop_stage02_source_frames(summary_token: str, crop_focus: str = "All", otros_subcrop: str = "All") -> tuple[pd.DataFrame, pd.DataFrame, str]:
        province_main = crop_02_unfiltered_path("province")
        province_unc = crop_02_unfiltered_unc_path("province")
        if not province_main.exists():
            expected_filtered, _ = crop_02_paths(summary_token)
            expected_unfiltered = crop_02_unfiltered_path(summary_token)
            raise FileNotFoundError(
                f"Missing stage-02 crop source for '{summary_token}'. "
                f"Checked: {expected_filtered}, {expected_unfiltered}, and province base {province_main}"
            )
        base_main = pd.read_csv(province_main, low_memory=False)
        base_unc = pd.read_csv(province_unc, low_memory=False) if province_unc.exists() else pd.DataFrame()
        return (
            aggregate_crop_main_from_base(base_main, summary_token, crop_focus, otros_subcrop),
            aggregate_crop_unc_from_base(base_main, base_unc, summary_token, crop_focus, otros_subcrop),
            "derived_from_province",
        )

    def crop_base_for_count() -> pd.DataFrame | None:
        # Always prefer the broadest available base table, independent of selected strategy.
        candidates = [
            CSV_DIR / "02_espac_crop_lci_table__summary_province.csv",
            CSV_DIR / "02_espac_crop_lci_table_filtered__summary_province.csv",
            CSV_DIR / "03-05_espac_crop_lci_table_filtered_dfe__summary_province.csv",
        ]
        for p in candidates:
            if p.exists():
                try:
                    return pd.read_csv(p, low_memory=False)
                except Exception:
                    return None
        return None

    def livestock_02_paths(summary_token: str):
        return (
            CSV_DIR / f"02_espac_livestock_lci_table_filtered__summary_{summary_token}.csv",
            CSV_DIR / f"02_espac_livestock_lci_table_filtered__summary_{summary_token}_uncertainty.csv",
        )

    def cache_status(path: Path) -> dict:
        if not path.exists():
            return {"exists": False, "path": str(path), "rows": 0, "updated_at": ""}
        rows = 0
        try:
            rows = max(sum(1 for _ in path.open("r", encoding="utf-8")) - 1, 0)
        except Exception:
            rows = 0
        return {
            "exists": True,
            "path": str(path),
            "rows": rows,
            "updated_at": pd.Timestamp(path.stat().st_mtime, unit="s").isoformat(),
        }

    def crop_cache_combinations() -> list[tuple[str, str, str]]:
        otros_opts = otros_category_options()
        combos: list[tuple[str, str, str]] = []
        for summary in CROP_STRATEGIES:
            combos.append((summary, "All", "All"))
            combos.append((summary, "PERMANENT", "All"))
            combos.append((summary, "TRANSITORY", "All"))
            for sub in otros_opts:
                combos.append((summary, "OTROS", str(sub)))
        return combos

    def livestock_cache_combinations() -> list[tuple[str, bool]]:
        return [
            ("province", False),
            ("region", False),
            ("national", False),
            ("national", True),
        ]

    def build_crop_reference_cache(progress: Any | None = None) -> tuple[Path, int, list[str]]:
        path = CROP_REFERENCE_CACHE
        generated_at = pd.Timestamp.utcnow().isoformat()
        combos = crop_cache_combinations()
        source_by_summary: dict[str, pd.DataFrame] = {}
        warnings: list[str] = []
        for summary in CROP_STRATEGIES:
            if summary == "province":
                try:
                    main_df, _unc_df, _source_kind = load_crop_stage02_source_frames(summary, "All", "All")
                    source_by_summary[summary] = main_df
                except FileNotFoundError as exc:
                    warnings.append(str(exc))
                    continue

        wrote_header = False
        total_rows = 0
        if path.exists():
            path.unlink()
        for idx, (summary, crop_focus, otros_subcrop) in enumerate(combos, start=1):
            if progress:
                progress(
                    title="Building crops reference cache",
                    subtitle=f"{summary} | focus={crop_focus} | otros={otros_subcrop}",
                )
            if summary == "province":
                base = source_by_summary.get(summary)
                if base is None:
                    continue
                out = apply_crop_selection_semantics(base, summary, crop_focus, otros_subcrop)
            else:
                out, _out_unc, _source_kind = load_crop_stage02_source_frames(summary, crop_focus, otros_subcrop)
            if out.empty:
                continue
            out = out.copy()
            out.insert(0, "cache_generated_at_utc", generated_at)
            out.insert(1, "cache_domain", "crops")
            out.insert(2, "cache_summary_token", summary)
            out.insert(3, "cache_crop_focus", crop_focus)
            out.insert(4, "cache_otros_subcrop", otros_subcrop)
            out.insert(5, "cache_combination_key", f"{summary}__{crop_focus}__{otros_subcrop}")
            out.to_csv(path, mode="w" if not wrote_header else "a", header=not wrote_header, index=False)
            wrote_header = True
            total_rows += len(out)
        return path, total_rows, warnings

    def build_livestock_reference_cache(progress: Any | None = None) -> tuple[Path, int, list[str]]:
        path = LIVESTOCK_REFERENCE_CACHE
        generated_at = pd.Timestamp.utcnow().isoformat()
        combos = livestock_cache_combinations()
        warnings: list[str] = []
        v2_prod, _ = load_livestock_v2_tables()
        v2_prod = apply_livestock_system_labels(v2_prod, PROJECT_DIR / "outputs" / "01_espac_2024.sqlite")

        wrote_header = False
        total_rows = 0
        if path.exists():
            path.unlink()
        for summary, combine_systems in combos:
            if progress:
                progress(
                    title="Building livestock reference cache",
                    subtitle=f"{summary} | combine_systems={combine_systems}",
                )
            out = build_livestock_stage02_main(v2_prod, summary, combine_systems=combine_systems)
            if out.empty:
                continue
            out = out.copy()
            out.insert(0, "cache_generated_at_utc", generated_at)
            out.insert(1, "cache_domain", "livestock")
            out.insert(2, "cache_summary_token", summary)
            out.insert(3, "cache_combine_systems", bool(combine_systems))
            out.insert(4, "cache_combination_key", f"{summary}__combine_{str(bool(combine_systems)).lower()}")
            out.to_csv(path, mode="w" if not wrote_header else "a", header=not wrote_header, index=False)
            wrote_header = True
            total_rows += len(out)
        return path, total_rows, warnings

    def load_crop_cache_selection(summary_token: str, crop_focus: str, otros_subcrop: str) -> pd.DataFrame | None:
        if not CROP_REFERENCE_CACHE.exists():
            return None
        try:
            df = pd.read_csv(CROP_REFERENCE_CACHE, low_memory=False)
        except Exception:
            return None
        mask = (
            df["cache_summary_token"].astype(str).eq(str(summary_token))
            & df["cache_crop_focus"].astype(str).eq(str(crop_focus))
            & df["cache_otros_subcrop"].astype(str).eq(str(otros_subcrop))
        )
        out = df.loc[mask].copy()
        if out.empty:
            return None
        drop_cols = [c for c in out.columns if c.startswith("cache_")]
        return out.drop(columns=drop_cols, errors="ignore")

    def load_livestock_cache_selection(summary_token: str, combine_systems: bool) -> pd.DataFrame | None:
        if not LIVESTOCK_REFERENCE_CACHE.exists():
            return None
        try:
            df = pd.read_csv(LIVESTOCK_REFERENCE_CACHE, low_memory=False)
        except Exception:
            return None
        mask = df["cache_summary_token"].astype(str).eq(str(summary_token))
        if "cache_combine_systems" in df.columns:
            mask = mask & (df["cache_combine_systems"].astype(str).str.lower() == str(bool(combine_systems)).lower())
        out = df.loc[mask].copy()
        if out.empty:
            return None
        drop_cols = [c for c in out.columns if c.startswith("cache_")]
        return out.drop(columns=drop_cols, errors="ignore")

    def get_livestock_meta() -> dict:
        path = PROJECT_DIR / "outputs" / "02_latest_livestock_filtered_export_summary.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def dfe_paths(domain: str, summary_token: str):
        if domain == "crops":
            return (
                CSV_DIR / f"03-05_espac_crop_lci_table_filtered_dfe__summary_{summary_token}.csv",
                CSV_DIR / f"03-05_espac_crop_lci_table_filtered_dfe__summary_{summary_token}_uncertainty.csv",
            )
        return (
            CSV_DIR / f"03-05_espac_livestock_lci_table_filtered_dfe__summary_{summary_token}.csv",
            CSV_DIR / f"03-05_espac_livestock_lci_table_filtered_dfe__summary_{summary_token}_uncertainty.csv",
        )

    def xml_target(domain: str, summary_token: str, combine_systems: bool = False):
        if domain == "crops":
            return PROJECT_DIR / "outputs" / "05_xml_exports_crop_lci" / f"summary_{summary_token}"
        if summary_token == "national":
            suffix = "combined" if combine_systems else "not_combined"
            return PROJECT_DIR / "outputs" / "05_xml_exports_livestock_lci" / f"summary_national_{suffix}"
        return PROJECT_DIR / "outputs" / "05_xml_exports_livestock_lci" / f"summary_{summary_token}"

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
                    q = (
                        "SELECT DISTINCT TRIM(COALESCE(NULLIF(rc_clacul,''), NULLIF(cp_nclavr,''))) AS crop_name "
                        "FROM rel_inec_cpnac WHERE UPPER(TRIM(COALESCE(cp_nclavr,'')))='OTROS PERMANENTES'"
                    )
                else:
                    q = (
                        "SELECT DISTINCT TRIM(COALESCE(NULLIF(ct_codcultiv1_int,''), NULLIF(ct_nclavr,''))) AS crop_name "
                        "FROM rel_inec_ctnac WHERE UPPER(TRIM(COALESCE(ct_nclavr,'')))='OTROS TRANSITORIOS'"
                    )
                d = pd.read_sql_query(q, con)
        except Exception:
            return []
        vals = sorted({str(x).strip().upper() for x in d["crop_name"].dropna().tolist() if str(x).strip()})
        return vals

    def main_category_crop_list(category: str) -> list[str]:
        base = crop_base_for_count()
        if base is None or "Crop" not in base.columns or "Category" not in base.columns:
            return []
        cat = str(category or "").strip().lower()
        m = base["Category"].astype(str).str.strip().str.lower().eq(cat)
        vals = sorted({str(x).strip().upper() for x in base.loc[m, "Crop"].dropna().tolist() if str(x).strip()})
        return vals

    def crop_list_for_focus(crop_focus: str) -> list[str]:
        base = crop_base_for_count()
        if base is None or "Crop" not in base.columns:
            return []
        f = str(crop_focus or "All").strip().upper()
        c = base["Crop"].astype(str).str.strip().str.upper()
        if f == "PERMANENT" and "Category" in base.columns:
            return main_category_crop_list("permanent")
        if f == "TRANSITORY" and "Category" in base.columns:
            return main_category_crop_list("transitory")
        if f == "OTROS":
            vals = set(family_crop_list("OTROS PERMANENTES")) | set(family_crop_list("OTROS TRANSITORIOS"))
            return sorted(v for v in vals if v)
        return sorted(set(c.tolist()))

    def otros_category_options() -> list[str]:
        base = crop_base_for_count()
        if base is None or "Category" not in base.columns:
            return ["All"]
        cats = sorted({str(x).strip().upper() for x in base["Category"].dropna().tolist() if str(x).strip()})
        return ["All"] + cats

    def selected_crop_list(crop_focus: str, otros_subcrop: str = "All") -> list[str]:
        focus = str(crop_focus or "All").strip().upper()
        sub = str(otros_subcrop or "All").strip().upper()
        if focus == "PERMANENT":
            vals = main_category_crop_list("permanent")
            if vals:
                return vals
        if focus == "TRANSITORY":
            vals = main_category_crop_list("transitory")
            if vals:
                return vals
        if focus == "OTROS":
            if sub in {"PERMANENT", "TRANSITORY", "CULTIVATED_PASTURE"}:
                if sub == "PERMANENT":
                    vals = family_crop_list("OTROS PERMANENTES")
                elif sub == "TRANSITORY":
                    vals = family_crop_list("OTROS TRANSITORIOS")
                else:
                    vals = main_category_crop_list("cultivated_pasture")
                return sorted(v for v in vals if v)
            vals = set(family_crop_list("OTROS PERMANENTES")) | set(family_crop_list("OTROS TRANSITORIOS"))
            pasture = main_category_crop_list("cultivated_pasture")
            vals.update(pasture)
            return sorted(v for v in vals if v)
        base = crop_base_for_count()
        if base is None or "Crop" not in base.columns:
            return []
        out = filter_crop_rows(base, crop_focus, otros_subcrop)
        if out.empty:
            return []
        return sorted({str(x).strip().upper() for x in out["Crop"].dropna().tolist() if str(x).strip()})

    def filter_crop_rows(
        df: pd.DataFrame,
        crop_focus: str = "All",
        otros_subcrop: str = "All",
    ) -> pd.DataFrame:
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
                # Keep permanent/transitory as-is; collapse cultivated pasture into OTROS aggregate only.
                keep_main = cat_l.isin({"permanent", "transitory"})
                keep_otros_pasture = crop_u.eq("OTROS PASTOS CULTIVADOS")
                out = out[keep_main | keep_otros_pasture].copy()
        return out

    def write_crop_stage02_selection(summary_token: str, crop_focus: str, otros_subcrop: str) -> tuple[Path, Path]:
        main_df, unc_df, _source_kind = load_crop_stage02_source_frames(summary_token, crop_focus, otros_subcrop)
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
        parts = []
        for col in preferred:
            if col in row.index:
                val = str(row.get(col, "")).strip()
                if val and val.lower() not in {"nan", "(all provinces confounded)", "(all regions confounded)"}:
                    parts.append(val)
        if not parts:
            return "Inventory"
        seen = []
        for p in parts:
            if p not in seen:
                seen.append(p)
        return " | ".join(seen[:4])

    def inventory_heatmap(
        df: pd.DataFrame,
        title: str,
        mode: str = "absolute",
        max_items: int = 28,
        max_inventories: int = 40,
    ):
        if df is None or df.empty:
            return mo.md("_No data to plot._")
        num = df.select_dtypes(include="number").copy()
        if num.empty:
            return mo.md("_No numeric inventory items to plot._")
        non_empty_rows = num.abs().sum(axis=0) > 0
        num = num.loc[:, non_empty_rows]
        if num.empty:
            return mo.md("_All numeric inventory items are zero in this selection._")
        row_strength = num.abs().sum(axis=0).sort_values(ascending=False)
        item_cols = row_strength.head(max_items).index.tolist()
        num = num[item_cols]

        inventory_labels = df.apply(_inventory_label, axis=1)
        labeled = num.copy()
        labeled.index = inventory_labels
        if len(labeled) > max_inventories:
            labeled = labeled.iloc[:max_inventories].copy()
        matrix = labeled.T
        if matrix.empty:
            return mo.md("_No values available for heatmap rendering._")

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
        if len(df) > max_inventories:
            fig.add_annotation(
                text=f"Showing first {max_inventories} LCIs out of {len(df)}",
                xref="paper",
                yref="paper",
                x=1,
                y=1.12,
                showarrow=False,
                xanchor="right",
            )
        if len(item_cols) < len(non_empty_rows[non_empty_rows].index):
            fig.add_annotation(
                text=f"Showing top {len(item_cols)} inventory items by absolute magnitude",
                xref="paper",
                yref="paper",
                x=0,
                y=1.12,
                showarrow=False,
                xanchor="left",
            )
        if subtitle_note:
            fig.add_annotation(
                text=subtitle_note,
                xref="paper",
                yref="paper",
                x=0,
                y=1.18,
                showarrow=False,
                xanchor="left",
            )
        return mo.ui.plotly(fig)

    def crop_xml_target(summary_token: str, crop_focus: str, otros_subcrop: str) -> Path:
        return PROJECT_DIR / "outputs" / "05_xml_exports_crop_lci" / f"summary_{summary_token}"

    def postprocess_crop_xml_outputs(summary_token: str, crop_focus: str, otros_subcrop: str) -> tuple[Path, int]:
        dst = crop_xml_target(summary_token, crop_focus, otros_subcrop)
        if not dst.exists():
            return dst, 0
        xmls = sorted(dst.glob("*.xml"))
        ns = "{http://www.EcoInvent.org/EcoSpold01}"
        count = 0
        for outp in xmls:
            try:
                tree = __import__("xml.etree.ElementTree", fromlist=["ElementTree"]).ElementTree(file=str(outp))
                root = tree.getroot()
                exch = root.findall(f".//{ns}exchange")
                seen = {}
                for ex in exch:
                    nm = str(ex.attrib.get("name", "")).strip()
                    if not nm:
                        nm = "exchange"
                    k = nm.lower()
                    seen[k] = seen.get(k, 0) + 1
                    if seen[k] > 1:
                        gc = str(ex.attrib.get("generalComment", "")).strip()
                        cat = str(ex.attrib.get("category", "")).strip()
                        sub = str(ex.attrib.get("subCategory", "")).strip()
                        hint = gc or "/".join([x for x in (cat, sub) if x]) or "dup"
                        ex.attrib["name"] = f"{nm} [{hint}] #{seen[k]}"
                tree.write(outp, encoding="utf-8", xml_declaration=True)
            except Exception:
                pass
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
            # Compute from aggregated stage-02 crop table by grouping keys per strategy.
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
            # User-defined rule: for crop_national with "All", avoid mixing OTROS
            # disaggregated pasture crops into the main crop total. Use:
            # permanent main + transitory main + 3 OTROS aggregate categories.
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
            # OTROS selections are displayed/selected as expanded subcrops from source logic.
            # Count must reflect expanded subcrop inventories, not the single aggregate OTROS row label.
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
                    for t in targets:
                        r2 = row.copy()
                        r2["Crop"] = t
                        expanded_rows.append(r2)
                if not expanded_rows:
                    return 0
                expanded = pd.DataFrame(expanded_rows)
                return int(len(expanded[keys].drop_duplicates()))
            return int(len(df[keys].drop_duplicates()))

        # Livestock estimates by strategy semantics in current integrated v2 implementation.
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
            # Source products in v2 table before XML expansion.
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
                df["region"] = (
                    df["ual_prov"].astype(str).str.strip().str.upper().map(prov_to_region).fillna("unknown")
                )
                regions = set(df["region"].astype(str).unique().tolist())
                return len(prod) * len(regions)
            # province
            prov = set(df["ual_prov"].astype(str).str.strip())
            return len(prod) * len([p for p in prov if p])
        return None

    def otros_subcrops(crop_label: str) -> list[str]:
        c = str(crop_label or "").strip().upper()
        if c not in {"OTROS PERMANENTES", "OTROS TRANSITORIOS"}:
            return ["All"]
        vals = [v for v in family_crop_list(c) if v]
        return ["All"] + vals

    return (
        CROP_STRATEGIES,
        CROP_REFERENCE_CACHE,
        LIVESTOCK_STRATEGIES,
        LIVESTOCK_REFERENCE_CACHE,
        STRATEGY_HELP,
        PROJECT_DIR,
        Path,
        apply_livestock_system_labels,
        build_livestock_stage02_main,
        build_livestock_stage02_unc,
        build_crop_reference_cache,
        build_livestock_reference_cache,
        cache_status,
        load_crop_cache_selection,
        load_livestock_cache_selection,
        mo,
        pd,
        crop_02_paths,
        crop_cache_combinations,
        crop_list_for_focus,
        selected_crop_list,
        main_category_crop_list,
        dfe_paths,
        estimate_xml_count,
        family_crop_list,
        otros_category_options,
        filter_crop_rows,
        apply_crop_selection_semantics,
        otros_subcrops,
        livestock_02_paths,
        load_livestock_v2_tables,
        get_livestock_meta,
        livestock_cache_combinations,
        numeric_plot,
        run_cmd,
        set_crop_meta,
        get_crop_meta,
        crop_xml_target,
        postprocess_crop_xml_outputs,
        write_crop_stage02_selection,
        xml_target,
    )


@app.cell
def _(mo):
    def render_error(context: str, exc: Exception):
        return mo.callout(
            mo.vstack(
                [
                    mo.md(f"**Error in {context}**"),
                    mo.md("```text\n" + str(exc) + "\n```"),
                ]
            ),
            kind="danger",
        )
    return (render_error,)


@app.cell
def _(mo):
    mo.md(
        """
        # ESPAC LCI Pipeline App (Crops + Livestock)
        1. Choose pipeline (`crops` or `livestock`)
        2. Choose aggregation strategy
        3. Create LCIs
        4. Compute DFE
        5. Review tables and plots, then generate XML
        """
    )
    return


@app.cell
def _(CROP_REFERENCE_CACHE, LIVESTOCK_REFERENCE_CACHE, cache_status, mo):
    crop_cache_status = cache_status(CROP_REFERENCE_CACHE)
    livestock_cache_status = cache_status(LIVESTOCK_REFERENCE_CACHE)
    overwrite_cache = mo.ui.checkbox(
        value=False,
        label="Allow overwrite if a reference cache file already exists",
    )
    build_crop_cache = mo.ui.run_button(label="Build crops reference cache", kind="warn")
    build_livestock_cache = mo.ui.run_button(label="Build livestock reference cache", kind="warn")
    mo.vstack(
        [
            mo.md("## Reference Caches"),
            mo.md(
                f"**Crops cache:** `{crop_cache_status['path']}`  \n"
                f"exists=`{crop_cache_status['exists']}` | rows=`{crop_cache_status['rows']}` | updated_at=`{crop_cache_status['updated_at'] or 'n/a'}`"
            ),
            mo.md(
                f"**Livestock cache:** `{livestock_cache_status['path']}`  \n"
                f"exists=`{livestock_cache_status['exists']}` | rows=`{livestock_cache_status['rows']}` | updated_at=`{livestock_cache_status['updated_at'] or 'n/a'}`"
            ),
            mo.hstack([overwrite_cache, build_crop_cache, build_livestock_cache], justify="start"),
        ]
    )
    return build_crop_cache, build_livestock_cache, overwrite_cache


@app.cell
def _(CROP_REFERENCE_CACHE, LIVESTOCK_REFERENCE_CACHE, build_crop_cache, build_crop_reference_cache, build_livestock_cache, build_livestock_reference_cache, cache_status, crop_cache_combinations, livestock_cache_combinations, mo, overwrite_cache):
    cache_feedback = mo.md("")
    if build_crop_cache.value:
        current = cache_status(CROP_REFERENCE_CACHE)
        if current["exists"] and not overwrite_cache.value:
            cache_feedback = mo.callout(
                mo.md(
                    "Crops reference cache already exists. "
                    "Tick `Allow overwrite if a reference cache file already exists` and click again to rebuild it."
                ),
                kind="warn",
            )
        else:
            with mo.status.progress_bar(
                total=len(crop_cache_combinations()),
                title="Building crops reference cache",
                subtitle="Preparing combinations...",
                completion_title="Crops reference cache completed",
            ) as bar:
                def _progress(**kwargs):
                    bar.update(increment=1, **kwargs)
                path, rows, warnings = build_crop_reference_cache(progress=_progress)
            warn_text = ("\n".join(f"- {w}" for w in warnings)) if warnings else "_No warnings._"
            cache_feedback = mo.callout(
                mo.vstack(
                    [
                        mo.md(f"**Crops cache built:** `{path}`"),
                        mo.md(f"Rows written: `{rows}`"),
                        mo.md(warn_text),
                    ]
                ),
                kind="success",
            )
    elif build_livestock_cache.value:
        current = cache_status(LIVESTOCK_REFERENCE_CACHE)
        if current["exists"] and not overwrite_cache.value:
            cache_feedback = mo.callout(
                mo.md(
                    "Livestock reference cache already exists. "
                    "Tick `Allow overwrite if a reference cache file already exists` and click again to rebuild it."
                ),
                kind="warn",
            )
        else:
            with mo.status.progress_bar(
                total=len(livestock_cache_combinations()),
                title="Building livestock reference cache",
                subtitle="Preparing combinations...",
                completion_title="Livestock reference cache completed",
            ) as bar:
                def _progress(**kwargs):
                    bar.update(increment=1, **kwargs)
                path, rows, warnings = build_livestock_reference_cache(progress=_progress)
            warn_text = ("\n".join(f"- {w}" for w in warnings)) if warnings else "_No warnings._"
            cache_feedback = mo.callout(
                mo.vstack(
                    [
                        mo.md(f"**Livestock cache built:** `{path}`"),
                        mo.md(f"Rows written: `{rows}`"),
                        mo.md(warn_text),
                    ]
                ),
                kind="success",
            )
    cache_feedback
    return


@app.cell
def _(mo):
    domain = mo.ui.dropdown(options=["crops", "livestock"], value="crops", label="Pipeline")
    mo.hstack([domain], justify="start")
    return (domain,)


@app.cell
def _(CROP_STRATEGIES, LIVESTOCK_STRATEGIES, domain, mo):
    if domain.value == "crops":
        strategy = mo.ui.dropdown(options=CROP_STRATEGIES, value="crop_national", label="Aggregation strategy")
    else:
        strategy = mo.ui.dropdown(options=LIVESTOCK_STRATEGIES, value="national", label="Aggregation strategy")
    mo.hstack([strategy], justify="start")
    return (strategy,)


@app.cell
def _(domain, mo, strategy):
    if domain.value == "livestock" and strategy.value == "national":
        livestock_combine_systems = mo.ui.checkbox(
            value=False,
            label="Combine livestock system types into one national result",
        )
        _ui = mo.hstack([livestock_combine_systems], justify="start")
    else:
        livestock_combine_systems = mo.ui.checkbox(
            value=False,
            label="Combine livestock system types into one national result",
        )
        _ui = mo.md("_System-combination control applies only to livestock national aggregation._")
    _ui
    return (livestock_combine_systems,)


@app.cell
def _(domain, mo):
    # Crop-specific selector, mirroring notebook intent.
    if domain.value == "crops":
        crop_focus = mo.ui.dropdown(
            options=[
                "All",
                "PERMANENT",
                "TRANSITORY",
                "OTROS",
            ],
            value="All",
            label="Crop focus (notebook-like selector)",
        )
        _ui_crop_focus = mo.hstack([crop_focus], justify="start")
    else:
        crop_focus = mo.ui.dropdown(options=["All"], value="All", label="Crop focus")
        _ui_crop_focus = mo.md("_Crop focus controls apply only to crops pipeline._")
    _ui_crop_focus
    return (crop_focus,)


@app.cell
def _(crop_focus, domain, mo, otros_category_options, render_error):
    try:
        if domain.value == "crops" and str(crop_focus.value) == "OTROS":
            _sub_opts = otros_category_options()
        else:
            _sub_opts = ["All"]
        otros_subcrop = mo.ui.dropdown(options=_sub_opts, value="All", label="OTROS category")
        _ui_otros = mo.hstack([otros_subcrop], justify="start")
    except Exception as exc:
        _ui_otros = render_error("OTROS subcrop selector", exc)
        otros_subcrop = mo.ui.dropdown(options=["All"], value="All", label="OTROS category")
    _ui_otros
    return (otros_subcrop,)


@app.cell
def _(STRATEGY_HELP, crop_focus, estimate_xml_count, domain, livestock_combine_systems, mo, otros_subcrop, render_error, selected_crop_list, strategy):
    _info_panel = None
    try:
        explanation = STRATEGY_HELP[domain.value][strategy.value]
        est = estimate_xml_count(
            domain.value,
            strategy.value,
            crop_focus.value,
            otros_subcrop.value,
            combine_systems=bool(livestock_combine_systems.value),
        )
        est_txt = str(est) if est is not None else "not available from current source tables"
    except Exception as exc:
        _info_panel = render_error("strategy information panel", exc)
    if _info_panel is None:
        diff_note = ""
        if domain.value == "livestock" and strategy.value == "national":
            diff_note = (
                "System handling: "
                + ("all livestock system types will be combined into one national result." if livestock_combine_systems.value else "livestock system types will remain separated in the national result.")
            )
        selector_line = ""
        if domain.value == "crops":
            selector_line = f"**Applied crop selector:** `{crop_focus.value}`" + (f" / subcrop `{otros_subcrop.value}`" if crop_focus.value == "OTROS" else "")
            fam_list = selected_crop_list(crop_focus.value, otros_subcrop.value)
            if fam_list and crop_focus.value in {"PERMANENT", "TRANSITORY", "OTROS"}:
                preview = ", ".join(fam_list[:25])
                if len(fam_list) > 25:
                    preview += f", ... (+{len(fam_list)-25} more)"
                selector_line += f"\n\n**Crops in selected group ({len(fam_list)}):** {preview}"
        _info_panel = mo.callout(
            mo.vstack(
                [
                    mo.md(f"**Selected strategy:** `{strategy.value}`"),
                    mo.md(explanation),
                    mo.md(diff_note) if diff_note else mo.md(""),
                    mo.md(selector_line) if selector_line else mo.md(""),
                    mo.md(f"**XMLs that will be generated with current selection:** `{est_txt}`"),
                ]
            ),
            kind="info",
        )
    _info_panel




@app.cell
def _(domain, livestock_combine_systems, mo, strategy):
    confirm = mo.ui.checkbox(
        value=False,
        label=(
            f"Confirm selection: pipeline=`{domain.value}`, strategy=`{strategy.value}`"
            + (f", combine_systems=`{livestock_combine_systems.value}`" if domain.value == "livestock" and strategy.value == "national" else "")
        ),
    )
    mo.hstack([confirm], justify="start")
    return (confirm,)


@app.cell
def _(crop_focus, crop_xml_target, domain, livestock_combine_systems, mo, otros_subcrop, strategy, xml_target):
    run_02 = mo.ui.run_button(label="Create LCIs", kind="neutral")
    run_03 = mo.ui.run_button(label="Compute DFE", kind="warn")
    refresh = mo.ui.run_button(label="Refresh Preview", kind="neutral")
    update_heatmap = mo.ui.run_button(label="Update heatmap", kind="neutral")
    gen_xml = mo.ui.run_button(label="Generate XML", kind="success")
    heatmap_mode = mo.ui.dropdown(
        options={
            "absolute": "Absolute values",
            "row_normalized": "Row-normalized",
            "log_positive": "Log-scaled positive",
        },
        value="absolute",
        label="Heatmap mode",
    )
    mo.vstack(
        [
            mo.hstack([run_02, run_03, refresh, update_heatmap, gen_xml, heatmap_mode], justify="start"),
            mo.md(
                f"**XML target folder:** `{crop_xml_target(strategy.value, crop_focus.value, otros_subcrop.value)}`"
                if domain.value == "crops"
                else f"**XML target folder:** `{xml_target(domain.value, strategy.value, livestock_combine_systems.value)}`"
            ),
        ]
    )
    return gen_xml, heatmap_mode, refresh, run_02, run_03, update_heatmap


@app.cell
def _(PROJECT_DIR, render_error, run_cmd_stream, set_crop_meta, write_crop_stage02_selection, confirm, crop_focus, domain, livestock_combine_systems, mo, otros_subcrop, run_02, strategy):
    _log = ""
    _feedback = mo.md("")
    if run_02.value and not confirm.value:
        _feedback = mo.callout(
            mo.md("Selection not confirmed. Tick the confirmation checkbox first."),
            kind="warn",
        )
    elif run_02.value:
        try:
            total_steps = 3 if domain.value == "crops" else 4
            with mo.status.progress_bar(
                total=total_steps,
                title="Create LCIs",
                subtitle="Starting...",
                completion_title="Create LCIs completed",
            ) as _create_bar:
                if domain.value == "crops":
                    selected_crop = crop_focus.value
                    _create_bar.update(
                        increment=1,
                        title="Create LCIs",
                        subtitle="Preparing crop selection metadata...",
                    )
                    set_crop_meta(strategy.value, selected_crop, otros_subcrop.value)
                    _create_bar.update(
                        increment=1,
                        title="Create LCIs",
                        subtitle="Building crop LCI selection...",
                    )
                    out_main, out_unc = write_crop_stage02_selection(strategy.value, selected_crop, otros_subcrop.value)
                    _create_bar.update(
                        increment=1,
                        title="Create LCIs",
                        subtitle="Writing crop stage-02 outputs...",
                    )
                    _log = (
                        f"Crop LCI selection materialized.\n"
                        f"main: {out_main}\n"
                        f"uncertainty: {out_unc}"
                    )
                else:
                    _cmd = [
                        str(PROJECT_DIR / ".venv" / "Scripts" / "python.exe"),
                        str(PROJECT_DIR / "scripts" / "livestock_pipeline_v2_integrated.py"),
                        "--stage",
                        "02",
                        "--summary-token",
                        strategy.value,
                        "--db",
                        str(PROJECT_DIR / "outputs" / "01_espac_2024.sqlite"),
                    ]
                    if strategy.value == "national" and livestock_combine_systems.value:
                        _cmd.append("--combine-systems")
                    _create_bar.update(
                        increment=1,
                        title="Create LCIs",
                        subtitle="Preparing livestock command...",
                    )
                    _create_bar.update(
                        increment=1,
                        title="Create LCIs",
                        subtitle="Running livestock stage 02...",
                    )
                    def _stream_progress(**kwargs):
                        _create_bar.update(**kwargs)
                    _rc, _out = run_cmd_stream(
                        _cmd,
                        progress=_stream_progress,
                        title="Create LCIs",
                        subtitle="Running livestock stage 02...",
                    )
                    _create_bar.update(
                        increment=1,
                        title="Create LCIs",
                        subtitle="Collecting livestock outputs...",
                    )
                    _log = _out if _out else f"livestock LCI creation finished with code {_rc}"
                    _create_bar.update(
                        increment=1,
                        title="Create LCIs",
                        subtitle="Finalizing...",
                    )
            if _log:
                _feedback = mo.callout(
                    mo.vstack(
                        [
                            mo.md("**Create LCIs finished.** Existing files were overwritten if present."),
                            mo.accordion({"Create LCIs log": mo.md(f"```text\n{_log[-8000:]}\n```")}),
                        ]
                    ),
                    kind="success",
                )
        except Exception as exc:
            _feedback = render_error("Create LCIs", exc)
    _feedback
    return


@app.cell
def _(PROJECT_DIR, get_crop_meta, get_livestock_meta, run_cmd, confirm, crop_focus, domain, livestock_combine_systems, mo, otros_subcrop, run_03, strategy):
    _log = ""
    if run_03.value and not confirm.value:
        _log = "Selection not confirmed. Tick the confirmation checkbox first."
    elif run_03.value:
        if domain.value == "crops":
            _meta = get_crop_meta()
            if (
                str(_meta.get("summary_token", "")) != str(strategy.value)
                or str(_meta.get("selected_crop", "")) != str(crop_focus.value)
                or str(_meta.get("selected_subcrop", "")) != str(otros_subcrop.value)
            ):
                _log = (
                    "Current selection is not materialized for DFE computation. "
                    "Run Create LCIs first with the current selectors."
                )
            else:
                _cmd = [
                    str(PROJECT_DIR / ".venv" / "Scripts" / "python.exe"),
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
                _rc, _out = run_cmd(_cmd)
                _log = _out if _out else f"DFE computation finished with code {_rc}"
        else:
            _meta = get_livestock_meta()
            if strategy.value == "national" and bool(_meta.get("combine_systems", False)) != bool(livestock_combine_systems.value):
                _log = (
                    "Current national livestock selection was materialized with a different system-combination setting. "
                    "Run Create LCIs again with the current checkbox state."
                )
            else:
                _cmd = [
                    str(PROJECT_DIR / ".venv" / "Scripts" / "python.exe"),
                    str(PROJECT_DIR / "scripts" / "livestock_pipeline_v2_integrated.py"),
                    "--stage",
                    "03",
                    "--summary-token",
                    strategy.value,
                ]
                _rc, _out = run_cmd(_cmd)
                _log = _out if _out else f"DFE computation finished with code {_rc}"
    if _log:
        _ = mo.accordion({"Compute DFE log": mo.md(f"```text\n{_log[-8000:]}\n```")})
    return


@app.cell
def _(PROJECT_DIR, get_crop_meta, get_livestock_meta, postprocess_crop_xml_outputs, run_cmd, confirm, crop_focus, domain, gen_xml, livestock_combine_systems, mo, otros_subcrop, strategy):
    _log = ""
    if gen_xml.value and not confirm.value:
        _log = "Selection not confirmed. Tick the confirmation checkbox first."
    elif gen_xml.value:
        if domain.value == "crops":
            _meta = get_crop_meta()
            if (
                str(_meta.get("summary_token", "")) != str(strategy.value)
                or str(_meta.get("selected_crop", "")) != str(crop_focus.value)
                or str(_meta.get("selected_subcrop", "")) != str(otros_subcrop.value)
            ):
                _log = (
                    "Current selection is not materialized for XML generation. "
                    "Run Create LCIs first with the current selectors."
                )
            else:
                _cmd = [
                    str(PROJECT_DIR / ".venv" / "Scripts" / "python.exe"),
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
                _rc, _out = run_cmd(_cmd)
                _dest, _n = postprocess_crop_xml_outputs(strategy.value, crop_focus.value, otros_subcrop.value)
                _log = (_out if _out else f"XML generation finished with code {_rc}") + f"\nxml output folder: {_dest}\nxml_count: {_n}"
        else:
            _meta = get_livestock_meta()
            if strategy.value == "national" and bool(_meta.get("combine_systems", False)) != bool(livestock_combine_systems.value):
                _log = (
                    "Current national livestock selection was materialized with a different system-combination setting. "
                    "Run Create LCIs again with the current checkbox state."
                )
            else:
                _cmd = [
                    str(PROJECT_DIR / ".venv" / "Scripts" / "python.exe"),
                    str(PROJECT_DIR / "scripts" / "livestock_pipeline_v2_integrated.py"),
                    "--stage",
                    "05",
                    "--summary-token",
                    strategy.value,
                ]
                if strategy.value == "national" and livestock_combine_systems.value:
                    _cmd.append("--combine-systems")
                _rc, _out = run_cmd(_cmd)
                _log = _out if _out else f"XML generation finished with code {_rc}"
    if _log:
        _ = mo.accordion({"Generate XML log": mo.md(f"```text\n{_log[-8000:]}\n```")})
    return


@app.cell
def _(Path, PROJECT_DIR, apply_livestock_system_labels, build_livestock_stage02_main, build_livestock_stage02_unc, crop_02_paths, crop_focus, dfe_paths, filter_crop_rows, get_livestock_meta, heatmap_mode, inventory_heatmap, livestock_02_paths, livestock_combine_systems, load_crop_cache_selection, load_livestock_cache_selection, load_livestock_v2_tables, domain, mo, otros_subcrop, pd, render_error, run_02, run_03, strategy, update_heatmap):
    _preview_panel = None
    try:
        _ = update_heatmap.value
        _heatmap_mode_value = heatmap_mode.value
        prefer_fresh = bool(run_02.value or run_03.value)
        if domain.value == "crops":
            main_02, unc_02 = crop_02_paths(strategy.value)
        else:
            main_02, unc_02 = livestock_02_paths(strategy.value)
        main_03, unc_03 = dfe_paths(domain.value, strategy.value)

        def _load(path: Path):
            return pd.read_csv(path) if path.exists() else None

        df02 = _load(main_02)
        df03 = _load(main_03)
        unc02_df = None
        unc03_df = None
        if domain.value == "crops":
            if not prefer_fresh:
                cached = load_crop_cache_selection(strategy.value, crop_focus.value, otros_subcrop.value)
                if cached is not None:
                    df02 = cached
        livestock_note = ""
        if domain.value == "livestock":
            _selected = bool(livestock_combine_systems.value) if strategy.value == "national" else False
            if not prefer_fresh:
                cached = load_livestock_cache_selection(strategy.value, _selected)
                if cached is not None:
                    df02 = cached
                    if df03 is None:
                        df03 = cached.copy()
            else:
                livestock_note = "**Preview source:** current in-session stage outputs take precedence over cache."
        if domain.value == "livestock" and strategy.value == "national":
            _meta = get_livestock_meta()
            _materialized = bool(_meta.get("combine_systems", False))
            livestock_note = f"**National livestock preview configuration:** `combine_systems={_selected}`"
            if prefer_fresh:
                livestock_note += "\n\n**Preview source:** current in-session stage outputs take precedence over cache."
            elif (not _meta) or (_selected != _materialized) or df02 is None or df03 is None:
                v2_prod, v2_unc = load_livestock_v2_tables()
                v2_prod = apply_livestock_system_labels(v2_prod, PROJECT_DIR / "outputs" / "01_espac_2024.sqlite")
                df02 = build_livestock_stage02_main(v2_prod, "national", combine_systems=_selected)
                unc02_df = build_livestock_stage02_unc(v2_unc, "national", df02, combine_systems=_selected)
                df03 = df02.copy()
                unc03_df = unc02_df.copy()
                livestock_note += (
                    "\n\n**Preview source:** computed in memory from V2 livestock tables for the currently selected configuration."
                )
            else:
                livestock_note += "\n\n**Preview source:** current materialized livestock files or reference cache."
        elif domain.value == "livestock" and not livestock_note:
            livestock_note = (
                "**Preview source:** current in-session stage outputs take precedence over cache."
                if prefer_fresh
                else "**Preview source:** current materialized livestock files or reference cache."
            )
        if unc02_df is None:
            unc02_df = _load(unc_02)
        if unc03_df is None:
            unc03_df = _load(unc_03)
        _preview_panel = mo.vstack(
            [
                mo.md(f"## Preview for `{domain.value}` / `{strategy.value}`"),
                mo.md(livestock_note) if livestock_note else mo.md(""),
                mo.md(f"`02 main:` `{main_02}`"),
                mo.md(f"`03-05 main:` `{main_03}`"),
                mo.md(f"**Heatmap mode:** `{_heatmap_mode_value}`"),
                mo.md("### Aggregated LCIs + DFE"),
                mo.ui.table(df03.head(200)) if df03 is not None else mo.md("_LCI + DFE table not found._"),
                inventory_heatmap(df03, "LCI + DFE inventory heatmap", mode=_heatmap_mode_value) if df03 is not None else mo.md(""),
                mo.md("### Uncertainty files"),
                mo.md(f"`{unc_02}`") if unc02_df is None else mo.ui.table(unc02_df.head(100)),
                mo.md(f"`{unc_03}`") if unc03_df is None else mo.ui.table(unc03_df.head(100)),
            ]
        )
    except Exception as exc:
        _preview_panel = render_error("preview panel", exc)
    _preview_panel


if __name__ == "__main__":
    app.run()
