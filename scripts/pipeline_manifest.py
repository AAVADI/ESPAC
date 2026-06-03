from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

MANIFEST_PATH_DEFAULT = Path('outputs/pipeline_run_manifest.json')


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id(prefix: str = 'run') -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _to_abs_str(path: Path | str) -> str:
    return str(Path(path).resolve())


def schema_fingerprint(df: pd.DataFrame) -> str:
    cols = [f"{c}:{str(df[c].dtype)}" for c in df.columns]
    payload = '|'.join(cols).encode('utf-8', errors='ignore')
    return hashlib.sha256(payload).hexdigest()[:16]


def file_sha256(path: Path | str) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def filters_signature(meta: dict[str, Any] | None) -> str:
    payload = json.dumps(meta or {}, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()[:16]


def load_manifest(project_dir: Path, manifest_rel: Path = MANIFEST_PATH_DEFAULT) -> list[dict[str, Any]]:
    p = (project_dir / manifest_rel).resolve()
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding='utf-8'))
    if isinstance(data, dict):
        rows = data.get('records', [])
    else:
        rows = data
    return rows if isinstance(rows, list) else []


def save_manifest(project_dir: Path, records: list[dict[str, Any]], manifest_rel: Path = MANIFEST_PATH_DEFAULT) -> Path:
    p = (project_dir / manifest_rel).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'version': 1,
        'updated_at_utc': utc_now_iso(),
        'records': records,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return p


def append_manifest_record(project_dir: Path, record: dict[str, Any], manifest_rel: Path = MANIFEST_PATH_DEFAULT) -> Path:
    rows = load_manifest(project_dir, manifest_rel)
    rows.append(record)
    return save_manifest(project_dir, rows, manifest_rel)


def make_snapshot_copy(path: Path | str, run_id: str) -> Path:
    src = Path(path)
    snapshot = src.with_name(f"{src.stem}__run_{run_id}{src.suffix}")
    snapshot.write_bytes(src.read_bytes())
    return snapshot


def validate_for_notebook6(domain: str, summary_token: str, main_df: pd.DataFrame, unc_df: pd.DataFrame) -> tuple[bool, list[str]]:
    errs: list[str] = []
    if main_df is None or main_df.empty:
        errs.append('main_df_empty')
    if unc_df is None or unc_df.empty:
        errs.append('unc_df_empty')

    required_by_domain = {
        'crops': ['Crop', 'Category'],
        'livestock': ['Product'],
    }
    for c in required_by_domain.get(domain, []):
        if c not in main_df.columns:
            errs.append(f'missing_required_col:{c}')

    unc_min = [c for c in unc_df.columns if c.endswith('__minValue')]
    unc_max = [c for c in unc_df.columns if c.endswith('__maxValue')]
    if not unc_min or not unc_max:
        errs.append('uncertainty_columns_missing')

    key_map = {
        ('crops', 'province'): ['Region', 'Province', 'Crop', 'Category'],
        ('crops', 'region'): ['Region', 'Crop', 'Category'],
        ('crops', 'crop_national'): ['Crop', 'Category'],
        ('crops', 'crop_group_national'): ['Crop_group', 'Category'],
        ('livestock', 'province'): ['Region', 'Province', 'Product', 'System'],
        ('livestock', 'region'): ['Region', 'Product', 'System'],
        ('livestock', 'national'): ['Product', 'System'],
    }
    keys = [k for k in key_map.get((domain, summary_token), []) if k in main_df.columns]
    if keys and not main_df.empty and main_df.duplicated(subset=keys).any():
        errs.append('duplicate_group_rows')

    return len(errs) == 0, errs


def crop_otros_metadata_from_db(project_dir: Path, crop_label: str) -> int:
    try:
        import sqlite3

        db_candidates = [
            project_dir / 'outputs' / '01_espac_2024.sqlite',
            project_dir / 'outputs' / 'CSVs' / '01_espac_2024.sqlite',
            project_dir / 'outputs' / 'espac_2024.sqlite',
        ]
        db = next((p for p in db_candidates if p.exists()), None)
        if db is None:
            return 0
        crop_u = str(crop_label).strip().upper()
        with sqlite3.connect(db) as conn:
            enc = 'encuestas'
            if crop_u == 'OTROS PERMANENTES':
                src_tbl, crop_col, detail = 'rel_inec_cpnac', 'cp_nclavr', 'rc_clacul'
            else:
                src_tbl, crop_col, detail = 'rel_inec_ctnac', 'ct_nclavr', 'ct_codcultiv1_int'
            q = (
                f"SELECT TRIM(COALESCE(NULLIF(s.{detail}, ''), NULLIF(s.{crop_col}, ''))) AS subcrop "
                f"FROM \"{src_tbl}\" s JOIN \"{enc}\" e "
                f"ON CAST(e.identificador AS TEXT)=CAST(s.identificador AS TEXT) "
                f"WHERE UPPER(TRIM(COALESCE(s.{crop_col}, ''))) = ?"
            )
            raw = pd.read_sql_query(q, conn, params=[crop_u])
        vals = raw['subcrop'].dropna().astype(str).str.strip()
        vals = vals[(vals != '') & (vals.str.upper() != crop_u)]
        return int(vals.nunique())
    except Exception:
        return 0


def build_manifest_record(
    *,
    run_id: str,
    domain: str,
    summary_token: str,
    pipeline_stage: str,
    source_main_csv: Path | str,
    source_unc_csv: Path | str,
    main_df: pd.DataFrame,
    unc_df: pd.DataFrame,
    filters_meta: dict[str, Any] | None,
    upstream_run_id: str | None = None,
    is_complete_for_notebook6: bool | None = None,
    validation_errors: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if is_complete_for_notebook6 is None:
        ok, errs = validate_for_notebook6(domain, summary_token, main_df, unc_df)
    else:
        ok = bool(is_complete_for_notebook6)
        errs = list(validation_errors or [])

    rec: dict[str, Any] = {
        'run_id': run_id,
        'created_at_utc': utc_now_iso(),
        'domain': domain,
        'summary_token': summary_token,
        'pipeline_stage': pipeline_stage,
        'source_main_csv': _to_abs_str(source_main_csv),
        'source_unc_csv': _to_abs_str(source_unc_csv),
        'row_count': int(len(main_df) if main_df is not None else 0),
        'schema_fingerprint': schema_fingerprint(main_df) if main_df is not None else '',
        'main_file_sha256': file_sha256(source_main_csv) if Path(source_main_csv).exists() else '',
        'unc_file_sha256': file_sha256(source_unc_csv) if Path(source_unc_csv).exists() else '',
        'filters_signature': filters_signature(filters_meta),
        'is_complete_for_notebook6': bool(ok),
        'validation_errors': errs,
        'upstream_run_id': upstream_run_id,
    }
    if extra:
        rec.update(extra)
    return rec


def discover_runs(project_dir: Path, domain: str | None = None) -> list[dict[str, Any]]:
    rows = load_manifest(project_dir)
    if domain:
        rows = [r for r in rows if str(r.get('domain', '')) == str(domain)]
    return sorted(rows, key=lambda r: str(r.get('created_at_utc', '')))


def latest_valid_run(project_dir: Path, domain: str, summary_token: str) -> dict[str, Any] | None:
    rows = discover_runs(project_dir, domain)
    cand = [r for r in rows if str(r.get('summary_token')) == str(summary_token) and bool(r.get('is_complete_for_notebook6'))]
    return cand[-1] if cand else None


def discover_available_summary_tokens(project_dir: Path, domain: str) -> list[str]:
    rows = discover_runs(project_dir, domain)
    vals = sorted({str(r.get('summary_token')) for r in rows if bool(r.get('is_complete_for_notebook6')) and str(r.get('summary_token'))})
    return vals
