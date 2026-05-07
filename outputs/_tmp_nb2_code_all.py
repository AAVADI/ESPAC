from pathlib import Path
import sqlite3

import pandas as pd
import ipywidgets as widgets
from IPython.display import display, Markdown

PROJECT_DIR = Path.cwd()
if not (PROJECT_DIR / 'inputs').exists() and (PROJECT_DIR.parent / 'inputs').exists():
    PROJECT_DIR = PROJECT_DIR.parent
OUTPUTS_DIR = PROJECT_DIR / "outputs"
CSVS_DIR = OUTPUTS_DIR / "CSVs"
CSVS_DIR.mkdir(parents=True, exist_ok=True)

DB_CANDIDATES = [
    OUTPUTS_DIR / "01_espac_2024.sqlite",
    CSVS_DIR / "01_espac_2024.sqlite",
    OUTPUTS_DIR / "espac_2024.sqlite",
]

def _count_tables(db_path: Path) -> int:
    try:
        with sqlite3.connect(db_path) as conn:
            q = pd.read_sql_query("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table'", conn)
        return int(q.loc[0, 'n'])
    except Exception:
        return -1

existing_dbs = [p for p in DB_CANDIDATES if p.exists()]
assert existing_dbs, f"Database not found in any expected path: {DB_CANDIDATES}. Run the ETL notebook first."

# Prefer the database with the highest table count.
DB_PATH = max(existing_dbs, key=_count_tables)
table_count = _count_tables(DB_PATH)
print(f"Using DB: {DB_PATH}")
print(f"Detected tables: {table_count}")
if table_count <= 0:
    print("Warning: selected database has no tables. You may need to rerun notebook 1 ETL.")


import sqlite3
import pandas as pd
from pathlib import Path
from IPython.display import display
import re
from typing import Any, Dict, Optional


def list_tables(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", conn)


def table_preview(conn: sqlite3.Connection, table_name: str, limit: int = 20) -> pd.DataFrame:
    return pd.read_sql_query(f'SELECT * FROM "{table_name}" LIMIT {int(limit)}', conn)


def table_info(conn: sqlite3.Connection, table_name: str) -> pd.DataFrame:
    return pd.read_sql_query(f"PRAGMA table_info('{table_name}')", conn)


def _table_to_source(table_name: Optional[str]) -> Optional[str]:
    if not table_name:
        return None
    t = str(table_name).strip().lower()
    if t.startswith('rel_inec_'):
        return t.replace('rel_inec_', '')
    if t.startswith('inec_'):
        return t.replace('inec_', '')
    return t


def _normalize_code_value(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if pd.isna(value):
            return None
        if float(value).is_integer():
            return str(int(value))
        return str(value).strip()
    txt = str(value).strip()
    if not txt:
        return None
    try:
        num = float(txt)
        if num.is_integer():
            return str(int(num))
    except Exception:
        pass
    return txt


def _parse_value_labels(pregunta: Any) -> Dict[str, str]:
    if not isinstance(pregunta, str):
        return {}
    text = ' '.join(pregunta.replace('\n', ' ').split())
    pattern = r'(\d{1,3})\s*[:\.-]\s*(.*?)(?=(?:\s*[/,;]\s*|\s+)(?:\d{1,3}\s*[:\.-])|$)'
    pairs = re.findall(pattern, text)
    out: Dict[str, str] = {}
    for code, label in pairs:
        clean = label.strip(' .,:;-/').strip()
        if clean:
            out[str(int(code))] = clean
    return out if len(out) >= 2 else {}


def _dedupe_labels(labels: list[str]) -> list[str]:
    out = []
    seen: Dict[str, int] = {}
    for label in labels:
        n = seen.get(label, 0)
        seen[label] = n + 1
        out.append(label if n == 0 else f"{label} ({n+1})")
    return out


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    q = pd.read_sql_query(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND lower(name)=lower(?) LIMIT 1",
        conn,
        params=(table_name,),
    )
    return not q.empty


def _find_best_dictionary_table(conn: sqlite3.Connection) -> Optional[str]:
    preferred = [
        'dd_variables',
        'dictionary_variables',
        'diccionario_variables',
        'dd_variable',
    ]
    for t in preferred:
        if _table_exists(conn, t):
            return t

    all_tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", conn)
    if all_tables.empty:
        return None

    names = all_tables['name'].astype(str).tolist()
    candidates = [
        t for t in names
        if ('dd' in t.lower() and 'var' in t.lower()) or ('dicc' in t.lower() and 'var' in t.lower())
    ]
    return candidates[0] if candidates else None


def _normalize_dictionary_columns(raw_df: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        'source_table': ['source_table', 'tabla_fuente', 'source', 'tabla'],
        'codigo_variable': ['codigo_variable', 'codigo', 'cod_var', 'variable_code', 'code'],
        'nombre_variable': ['nombre_variable', 'nombre', 'variable_name', 'name', 'etiqueta'],
        'pregunta': ['pregunta', 'question', 'descripcion', 'description', 'labels'],
    }

    col_map: Dict[str, str] = {}
    lower_to_real = {str(c).strip().lower(): c for c in raw_df.columns}
    for canonical, options in aliases.items():
        for opt in options:
            if opt in lower_to_real:
                col_map[canonical] = lower_to_real[opt]
                break

    required = {'source_table', 'codigo_variable', 'nombre_variable'}
    if not required.issubset(col_map):
        missing = sorted(required - set(col_map))
        raise ValueError(f"Dictionary table missing required columns: {missing}")

    normalized = pd.DataFrame({
        'source_table': raw_df[col_map['source_table']],
        'codigo_variable': raw_df[col_map['codigo_variable']],
        'nombre_variable': raw_df[col_map['nombre_variable']],
        'pregunta': raw_df[col_map['pregunta']] if 'pregunta' in col_map else None,
    })
    return normalized


def build_dictionary_context(conn: sqlite3.Connection) -> Dict[str, Dict[str, Dict[str, Any]]]:
    empty_ctx = {
        'column_labels_by_source': {},
        'value_labels_by_source': {},
        'unique_global_column_labels': {},
        'unique_global_value_labels': {},
    }

    table_name = _find_best_dictionary_table(conn)
    if not table_name:
        print('Warning: no dictionary table found (e.g., dd_variables). Continuing without decoded labels.')
        return empty_ctx

    try:
        raw_dd = pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)
        dd = _normalize_dictionary_columns(raw_dd)
    except Exception as exc:
        print(f'Warning: failed to read dictionary table "{table_name}": {exc}')
        print('Continuing without decoded labels.')
        return empty_ctx

    dd['source_table'] = dd['source_table'].astype(str).str.strip().str.lower()
    dd['codigo_variable'] = dd['codigo_variable'].astype(str).str.strip().str.lower()
    dd['nombre_variable'] = dd['nombre_variable'].astype(str).str.strip()

    column_labels_by_source: Dict[str, Dict[str, str]] = {}
    value_labels_by_source: Dict[str, Dict[str, Dict[str, str]]] = {}

    global_column_names: Dict[str, set[str]] = {}
    global_value_maps: Dict[str, list[Dict[str, str]]] = {}

    for row in dd.itertuples(index=False):
        source = row.source_table
        code = row.codigo_variable
        name = row.nombre_variable

        column_labels_by_source.setdefault(source, {})[code] = name
        global_column_names.setdefault(code, set()).add(name)

        parsed = _parse_value_labels(getattr(row, 'pregunta', None))
        if parsed:
            value_labels_by_source.setdefault(source, {})[code] = parsed
            global_value_maps.setdefault(code, []).append(parsed)

    unique_global_column_labels = {
        code: next(iter(names))
        for code, names in global_column_names.items()
        if len(names) == 1
    }

    unique_global_value_labels: Dict[str, Dict[str, str]] = {}
    for code, maps in global_value_maps.items():
        as_items = {tuple(sorted(m.items())) for m in maps}
        if len(as_items) == 1:
            unique_global_value_labels[code] = dict(next(iter(as_items)))

    print(f'Loaded dictionary context from table: {table_name}')
    return {
        'column_labels_by_source': column_labels_by_source,
        'value_labels_by_source': value_labels_by_source,
        'unique_global_column_labels': unique_global_column_labels,
        'unique_global_value_labels': unique_global_value_labels,
    }


def lookup_column_label(column_name: str, source_table: Optional[str], dict_ctx: Dict[str, Any]) -> str:
    code = str(column_name).strip().lower()
    source = _table_to_source(source_table)

    if source and code in dict_ctx['column_labels_by_source'].get(source, {}):
        return dict_ctx['column_labels_by_source'][source][code]
    if code in dict_ctx['unique_global_column_labels']:
        return dict_ctx['unique_global_column_labels'][code]
    return str(column_name)


def lookup_value_map(column_name: str, source_table: Optional[str], dict_ctx: Dict[str, Any]) -> Dict[str, str]:
    code = str(column_name).strip().lower()
    source = _table_to_source(source_table)

    if source and code in dict_ctx['value_labels_by_source'].get(source, {}):
        return dict_ctx['value_labels_by_source'][source][code]
    return dict_ctx['unique_global_value_labels'].get(code, {})


def format_for_display(
    df: pd.DataFrame,
    table_name: Optional[str],
    dict_ctx: Dict[str, Any],
    include_raw_code_in_header: bool = True,
 ) -> pd.DataFrame:
    out = df.copy()
    source = _table_to_source(table_name)

    new_headers = []
    for c in out.columns:
        raw = str(c)
        label = lookup_column_label(raw, source, dict_ctx)
        if include_raw_code_in_header and label != raw:
            new_headers.append(f"{label} [{raw}]")
        else:
            new_headers.append(label)

        value_map = lookup_value_map(raw, source, dict_ctx)
        if value_map:
            def _decode(v: Any) -> Any:
                key = _normalize_code_value(v)
                if key in value_map:
                    return f"{value_map[key]} [{key}]"
                return v
            out[c] = out[c].apply(_decode)

    out.columns = _dedupe_labels(new_headers)
    return out


with sqlite3.connect(DB_PATH) as conn:
    tables_df = list_tables(conn)
    DICT_CTX = build_dictionary_context(conn)

tables_df.head(30)


table_selector = widgets.Dropdown(options=tables_df["name"].tolist(), description="Table:", layout=widgets.Layout(width="420px"))
limit_selector = widgets.IntSlider(value=20, min=5, max=200, step=5, description="Rows:", continuous_update=False)
load_table_btn = widgets.Button(description="Load table preview", button_style="primary", icon="search")
out = widgets.Output()


def refresh_table(*_):
    out.clear_output()
    table = table_selector.value
    limit = limit_selector.value
    with sqlite3.connect(DB_PATH) as conn:
        info = table_info(conn, table)
        preview = table_preview(conn, table, limit=limit)

    info = info.copy()
    info["label"] = info["name"].apply(lambda c: lookup_column_label(c, table, DICT_CTX))
    preview_display = format_for_display(preview, table_name=table, dict_ctx=DICT_CTX)

    with out:
        display(Markdown(f"### Schema: `{table}`"))
        display(info[["cid", "name", "label", "type", "notnull", "dflt_value", "pk"]])
        display(Markdown(f"### Preview ({limit} rows)"))
        display(preview_display)


load_table_btn.on_click(refresh_table)
display(widgets.HBox([table_selector, limit_selector, load_table_btn]))
display(out)
with out:
    display(Markdown("Select a table and click **Load table preview**."))


sql_editor = widgets.Textarea(
    value=(
        "WITH geo AS (\n"
        "  SELECT\n"
        "    identificador,\n"
        "    CASE\n"
        "      WHEN provincia IN ('ESMERALDAS','MANABÃƒÂ','LOS RÃƒÂOS','GUAYAS','SANTA ELENA','EL ORO','SANTO DOMINGO DE LOS TSÃƒÂCHILAS') THEN 'costa'\n"
        "      WHEN provincia IN ('AZUAY','BOLÃƒÂVAR','CAÃƒâ€˜AR','CARCHI','CHIMBORAZO','COTOPAXI','IMBABURA','LOJA','PICHINCHA','TUNGURAHUA') THEN 'sierra'\n"
        "      WHEN provincia IN ('MORONA SANTIAGO','NAPO','ORELLANA','PASTAZA','SUCUMBÃƒÂOS','ZAMORA CHINCHIPE') THEN 'oriente'\n"
        "      ELSE '(sin region)'\n"
        "    END AS region\n"
        "  FROM encuestas\n"
        ")\n"
        "SELECT\n"
        "  g.region,\n"
        "  c.cp_nclavr AS cultivo,\n"
        "  COUNT(DISTINCT c.identificador) AS n_upas\n"
        "FROM rel_inec_cpnac c\n"
        "JOIN geo g\n"
        "  ON g.identificador = c.identificador\n"
        "WHERE g.region IN ('costa', 'sierra', 'oriente')\n"
        "GROUP BY g.region, c.cp_nclavr\n"
        "ORDER BY g.region, n_upas DESC;"
    ),
    description="SQL:",
    layout=widgets.Layout(width="900px", height="180px"),
)
run_btn = widgets.Button(description="Run query", button_style="primary")
clear_btn = widgets.Button(description="Clear output")
query_out = widgets.Output()


def run_query(_):
    query_out.clear_output()
    sql = sql_editor.value.strip()
    if not sql:
        return
    with query_out:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                df = pd.read_sql_query(sql, conn)
            display(format_for_display(df, table_name=None, dict_ctx=DICT_CTX))
            display(Markdown("_Column/value labels are decoded with dictionary-based best effort for SQL results._"))
            display(Markdown(f"Returned **{len(df):,}** rows."))
        except Exception as ex:
            display(Markdown(f"**Query error:** `{ex}`"))


def clear_output(_):
    query_out.clear_output()


run_btn.on_click(run_query)
clear_btn.on_click(clear_output)
display(sql_editor)
display(widgets.HBox([run_btn, clear_btn]))
display(query_out)


starter_queries = {
    "Table inventory": "SELECT * FROM table_inventory ORDER BY row_count DESC;",
    "Dictionary lookup (contains 'prov')": "SELECT * FROM dd_variables WHERE lower(nombre_variable) LIKE '%prov%' LIMIT 50;",
    "Counts by table": "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;",
}

for title, sql in starter_queries.items():
    display(Markdown(f"### {title}"))
    with sqlite3.connect(DB_PATH) as conn:
        try:
            df = pd.read_sql_query(sql, conn).head(20)
            display(format_for_display(df, table_name=None, dict_ctx=DICT_CTX))
        except Exception as ex:
            display(Markdown(f"Error: `{ex}`"))


from typing import Dict, List
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import yaml
import json
from IPython.display import display, Markdown, HTML, clear_output
from scripts.crop_groups import infer_crop_group_row as curated_infer_crop_group_row, find_unmapped_crops
from scripts.pipeline_manifest import (
    new_run_id,
    make_snapshot_copy,
    build_manifest_record,
    append_manifest_record,
)


COSTA_PROVINCES = {
    "ESMERALDAS",
    "MANABI",
    "LOS RIOS",
    "GUAYAS",
    "SANTA ELENA",
    "EL ORO",
    "SANTO DOMINGO DE LOS TSACHILAS",
}
SIERRA_PROVINCES = {
    "AZUAY",
    "BOLIVAR",
    "CANAR",
    "CARCHI",
    "CHIMBORAZO",
    "COTOPAXI",
    "IMBABURA",
    "LOJA",
    "PICHINCHA",
    "TUNGURAHUA",
}
ORIENTE_PROVINCES = {
    "MORONA SANTIAGO",
    "NAPO",
    "ORELLANA",
    "PASTAZA",
    "SUCUMBIOS",
    "ZAMORA CHINCHIPE",
}

DEFAULT_COEFFICIENTS = {
    "conversion_factors": {
        "lb_to_kg": 0.45359237,
        "kg_unit_factors": {
            "KILOGRAMO": 1.0,
            "LIBRA": 0.45359237,
            "QUINTAL": 45.359237,
            "TONELADA": 1000.0,
            "LITRO": 1.0,
        },
    },
    "energy_assumptions": {
        "default_diesel_l_ha_irrigated": 65.15,
        "default_electricity_kwh_ha_irrigated": 0.0,
    },
    "irrigation_efficiency_by_equipment": {
        "surcos": 0.575,
        "aspersiÃƒÂ³n": 0.65,
        "microaspersiÃƒÂ³n": 0.65,
        "nebulizaciÃƒÂ³n": 0.65,
        "goteo": 0.80,
    },
    "crop_water_need_mm_by_keyword": [
        {"keywords": ["ARROZ"], "mm": 575.0},
        {"keywords": ["MAIZ"], "mm": 650.0},
        {"keywords": ["FREJOL", "FRIJOL", "BEAN"], "mm": 400.0},
        {"keywords": ["SOYA", "SOJA", "SOYBEAN"], "mm": 575.0},
        {"keywords": ["PAPA", "POTATO"], "mm": 600.0},
        {"keywords": ["TOMATE"], "mm": 600.0},
        {"keywords": ["CEBOLLA", "ONION"], "mm": 450.0},
        {"keywords": ["BANANO", "BANANA", "PLATANO", "ORITO"], "mm": 1700.0},
        {"keywords": ["CAÃƒâ€˜A DE AZÃƒÅ¡CAR", "CANA DE AZUCAR", "SUGARCANE"], "mm": 2000.0},
        {"keywords": ["CITR", "NARANJA", "LIMON", "MANDARINA"], "mm": 1050.0},
    ],
}

COEFF_CONFIG_PATH = PROJECT_DIR / "inputs/02-05_espac_lci_coefficients.yml"
if not COEFF_CONFIG_PATH.exists():
    with COEFF_CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(DEFAULT_COEFFICIENTS, f, sort_keys=False, allow_unicode=True)

with COEFF_CONFIG_PATH.open("r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f) or {}

_conv = _cfg.get("conversion_factors", {})
LB_TO_KG = float(_conv.get("lb_to_kg", DEFAULT_COEFFICIENTS["conversion_factors"]["lb_to_kg"]))
KG_UNIT_FACTORS = {k: float(v) for k, v in _conv.get("kg_unit_factors", DEFAULT_COEFFICIENTS["conversion_factors"]["kg_unit_factors"]).items()}

_energy = _cfg.get("energy_assumptions", {})
DEFAULT_DIESEL_L_HA_IRRIGATED = float(_energy.get("default_diesel_l_ha_irrigated", DEFAULT_COEFFICIENTS["energy_assumptions"]["default_diesel_l_ha_irrigated"]))
DEFAULT_ELECTRICITY_KWH_HA_IRRIGATED = float(_energy.get("default_electricity_kwh_ha_irrigated", DEFAULT_COEFFICIENTS["energy_assumptions"]["default_electricity_kwh_ha_irrigated"]))

_fuel_proxy_cal = _energy.get("fuel_proxy_ecuador_calibration", {}) if isinstance(_energy, dict) else {}
FUEL_PROXY_EC_CAL_ENABLED = bool(_fuel_proxy_cal.get("enabled", False))
FUEL_PROXY_EC_CAL_DEFAULT = float(_fuel_proxy_cal.get("default_factor", 1.0) or 1.0)
FUEL_PROXY_EC_CAL_BY_CATEGORY = {
    str(k).strip().lower(): float(v)
    for k, v in (_fuel_proxy_cal.get("by_category", {}) or {}).items()
}

FUEL_MJ_PER_L = 38.0


def _normalize_proxy_crop_name(v: str) -> str:
    x = unicodedata.normalize("NFKD", str(v).upper())
    x = "".join(ch for ch in x if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", x).strip()


_crop_yield_proxy_cfg = _cfg.get("crop_yield_proxies", {}) if isinstance(_cfg, dict) else {}
_cultivated_pasture_proxy_cfg = _crop_yield_proxy_cfg.get("cultivated_pasture", {}) if isinstance(_crop_yield_proxy_cfg, dict) else {}
CULTIVATED_PASTURE_YIELD_PROXY_DEFAULT = _cultivated_pasture_proxy_cfg.get("default", {}) if isinstance(_cultivated_pasture_proxy_cfg, dict) else {}
CULTIVATED_PASTURE_YIELD_PROXY_BY_CROP = {
    _normalize_proxy_crop_name(k): v
    for k, v in ((_cultivated_pasture_proxy_cfg.get("by_crop", {}) or {}).items())
}


def pasture_yield_proxy_for_crop(crop_name: str) -> Dict[str, object]:
    crop_key = _normalize_proxy_crop_name(crop_name)
    raw = CULTIVATED_PASTURE_YIELD_PROXY_BY_CROP.get(crop_key, CULTIVATED_PASTURE_YIELD_PROXY_DEFAULT)
    if not isinstance(raw, dict) or not raw:
        raise KeyError(
            "Missing cultivated-pasture yield proxy config. Populate crop_yield_proxies.cultivated_pasture in inputs/02-05_espac_lci_coefficients.yml"
        )
    required = ["median_kgha", "min_kgha", "max_kgha", "yield_data_status", "yield_basis_note"]
    missing = [k for k in required if k not in raw]
    if missing:
        raise KeyError(
            f"Incomplete cultivated-pasture yield proxy config for '{crop_name or crop_key}': missing {missing}"
        )
    out = {
        "median": float(raw["median_kgha"]),
        "min": float(raw["min_kgha"]),
        "max": float(raw["max_kgha"]),
        "status": str(raw["yield_data_status"]),
        "note": str(raw["yield_basis_note"]),
    }
    if not (out["min"] <= out["median"] <= out["max"]):
        raise ValueError(
            f"Invalid cultivated-pasture yield proxy ordering for '{crop_name or crop_key}': expected min <= median <= max"
        )
    return out


SUMMARY_KEY_COLS = ["Region", "Province", "Crop", "Category"]
SUMMARY_LEVEL_OPTIONS = [
    ("By province", "province"),
    ("By region (confounded provinces)", "region"),
    ("By crop, national (confounded regions and provinces)", "crop_national"),
    ("By cropping system (monocrop/in association, confounded provinces)", "cropping_system"),
    ("By irrigation class (Irrig_m3 = 0 / <> 0, confounded provinces)", "irrig_m3_class"),
    ("By farm size class (confounded provinces)", "farm_size_class"),
    ("By crop group (confounded provinces)", "crop_group"),
    ("By crop group, national (confounded regions and provinces)", "crop_group_national"),
]


def get_summary_group_keys(summary_level: str) -> List[str]:
    mapping = {
        "province": ["Region", "Province", "Crop", "Category"],
        "region": ["Region", "Crop", "Category"],
        "crop_national": ["Crop", "Category"],
        "cropping_system": ["Region", "Cropping_system", "Crop", "Category"],
        "irrig_m3_class": ["Region", "Irrig_m3_class", "Crop", "Category"],
        "farm_size_class": ["Region", "Farm_size_class", "Crop", "Category"],
        "crop_group": ["Region", "Crop_group", "Category"],
        "crop_group_national": ["Crop_group", "Category"],
    }
    return mapping.get(summary_level, mapping["province"])


def summary_strategy_token(summary_level: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", str(summary_level).strip().lower()).strip("_")
    return token or "province"


LATEST_FILTERED_SUMMARY_META_PATH = PROJECT_DIR / "outputs/02_latest_filtered_export_summary.json"


def write_latest_filtered_summary_metadata(
    summary_level: str,
    summary_token: str,
    filtered_csv_path: Path,
    filtered_unc_path: Path,
    selected_crop: str = "All",
    selected_subcrop: str = "All",
    run_id: str = "",
) -> None:
    payload = {
        "summary_level": str(summary_level),
        "summary_token": str(summary_token),
        "filtered_csv": str(filtered_csv_path),
        "filtered_uncertainty_csv": str(filtered_unc_path),
        "selected_crop": str(selected_crop),
        "selected_subcrop": str(selected_subcrop),
        "otros_crop_filter": str(selected_subcrop),
        "updated_at_utc": pd.Timestamp.utcnow().isoformat(),
        "run_id": str(run_id or ""),
    }
    LATEST_FILTERED_SUMMARY_META_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_FILTERED_SUMMARY_META_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def infer_crop_group(crop_name: str) -> str:
    return curated_infer_crop_group_row(crop_name)


def infer_crop_group_row(crop_name: str, category: str = "", packaging_type2: str = "") -> str:
    return curated_infer_crop_group_row(crop_name, category=category, packaging_type2=packaging_type2)


def infer_cropping_system_from_condition(value: str) -> str:
    c = _normalize_proxy_crop_name(value)
    if c == "":
        return "(unknown)"
    if "SOLO" in c:
        return "monocrop"
    if "ASOCIADO" in c:
        return "in association"
    return "(unknown)"


def infer_mechanization_fuel_factor(method_value: Any, category: str = "") -> float:
    txt = _normalize_text(method_value)
    if not txt:
        return 1.0
    if "ninguno" in txt:
        return 0.0
    if "tractor" in txt:
        return 1.0
    if "moto" in txt and "cult" in txt:
        return 0.7
    if "yunta" in txt:
        return 0.35
    if any(tok in txt for tok in ["azadon", "azada", "pala", "pico", "machete"]):
        return 0.15
    return 1.0


def _load_fuel_proxy_mjha() -> pd.DataFrame:
    candidates = [
        CSVS_DIR / "06_fuel_ha_proxy_scielo_by_crop.csv",
        CSVS_DIR / "06_fuel_proxy_scielo_by_crop_MJha.csv",
    ]
    required = ["Crop", "Fuel_ha_median", "Fuel_ha_min", "Fuel_ha_max"]
    for path in candidates:
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path)
            if not all(c in df.columns for c in required):
                continue
            select_cols = required + (["proxy_category"] if "proxy_category" in df.columns else [])
            out = df[select_cols].copy()
            for c in ["Fuel_ha_median", "Fuel_ha_min", "Fuel_ha_max"]:
                out[c] = pd.to_numeric(out[c], errors="coerce")
            out = out.dropna(subset=["Crop"]).copy()
            out["_crop_key"] = out["Crop"].map(_normalize_proxy_crop_name)
            out = out.drop_duplicates(subset=["_crop_key"], keep="first")
            out = out.set_index("_crop_key")
            return out
        except Exception:
            continue
    return pd.DataFrame(columns=required).set_index(pd.Index([], name="_crop_key"))


FUEL_PROXY_DF = _load_fuel_proxy_mjha()
FUEL_PROXY_MEDIAN_BY_CROP = FUEL_PROXY_DF["Fuel_ha_median"].to_dict() if not FUEL_PROXY_DF.empty else {}
FUEL_PROXY_MIN_BY_CROP = FUEL_PROXY_DF["Fuel_ha_min"].to_dict() if not FUEL_PROXY_DF.empty else {}
FUEL_PROXY_MAX_BY_CROP = FUEL_PROXY_DF["Fuel_ha_max"].to_dict() if not FUEL_PROXY_DF.empty else {}
FUEL_PROXY_CATEGORY_BY_CROP = (
    FUEL_PROXY_DF["proxy_category"].astype(str).str.strip().str.lower().to_dict()
    if (not FUEL_PROXY_DF.empty and "proxy_category" in FUEL_PROXY_DF.columns)
    else {}
)

IRRIGATION_EFF_BY_EQUIPMENT = {k: float(v) for k, v in _cfg.get("irrigation_efficiency_by_equipment", DEFAULT_COEFFICIENTS["irrigation_efficiency_by_equipment"]).items()}
IRRIGATION_SOURCE_OPTIONS = {"river", "lake", "well"}
DEFAULT_IRRIGATION_SOURCE = "river"
IRRIGATION_SOURCE_CODE_MAP = {
    str(k).strip(): str(v).strip().lower()
    for k, v in (_cfg.get("irrigation_source_code_map", DEFAULT_COEFFICIENTS.get("irrigation_source_code_map", {})) or {}).items()
    if str(v).strip().lower() in IRRIGATION_SOURCE_OPTIONS
}
CROP_WATER_NEED_MM_BY_KEYWORD = [
    (list(item.get("keywords", [])), float(item.get("mm", 0)))
    for item in _cfg.get("crop_water_need_mm_by_keyword", DEFAULT_COEFFICIENTS["crop_water_need_mm_by_keyword"])
]
MONTH_MAP = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}




def _normalize_geo_text(text: str) -> str:
    txt = str(text).strip().upper()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"\s+", " ", txt)
    return txt


def _normalize_text(text: str) -> str:
    txt = str(text).strip().lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"\s+", " ", txt)
    return txt


def map_provincia_to_region(provincia: str) -> str:
    p = _normalize_geo_text(provincia)
    if p in COSTA_PROVINCES:
        return "costa"
    if p in SIERRA_PROVINCES:
        return "sierra"
    if p in ORIENTE_PROVINCES:
        return "oriente"
    return "(sin region)"


def parse_espac_number(v):
    if pd.isna(v):
        return np.nan
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none"}:
        return np.nan
    s = s.replace(" ", "")
    s = s.replace("Ã‚Â ", "")
    s = s.replace("'", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return np.nan



VALID_LB_EQUIV_VALUES = {
    1, 2, 3, 4, 5, 10, 15, 20, 25, 30, 40, 43, 44, 50, 60, 70, 80, 100, 2000, 2200
}
YIELD_FAO_EXCLUSION_FACTOR = 1.1
YIELD_FAO_THRESHOLDS_KGHA = [
    (["CANA DE AZUCAR"], 5000.0, 250000.0, "Sugarcane"),
    (["BANANO", "PLATANO", "ORITO"], 1000.0, 120000.0, "Banana/plantain"),
    (["PAPA", "YUCA"], 500.0, 120000.0, "Root/tuber"),
    (["TOMATE"], 1000.0, 250000.0, "Tomato"),
    (["CEBOLLA", "BROCOLI"], 500.0, 120000.0, "Vegetable"),
    (["ARROZ", "MAIZ", "TRIGO", "CEBADA", "QUINUA"], 50.0, 20000.0, "Cereal"),
    (["FREJOL", "HABA", "ARVEJA", "SOYA", "MANI"], 50.0, 15000.0, "Pulse/oilseed"),
    (["PALMA AFRICANA"], 500.0, 120000.0, "Oil palm"),
    (["CACAO", "CAFE", "NARANJA", "LIMON", "MANGO", "MARACUY", "PINA", "AGUACATE", "TOMATE DE ARBOL"], 100.0, 100000.0, "Perennial fruit/tree crop"),
]


def sanitize_lb_equiv(series: pd.Series) -> pd.Series:
    lb = pd.to_numeric(series, errors="coerce")
    # Keep positive, plausible lb-equivalent values; avoid over-filtering valid records.
    return lb.where((lb > 0) & (lb <= 2200))


def fao_yield_threshold_for_crop(crop_name: str) -> (float, float, str):
    txt = _normalize_geo_text(crop_name)
    for keywords, lo, hi, label in YIELD_FAO_THRESHOLDS_KGHA:
        if any(k in txt for k in keywords):
            return float(lo), float(hi), label
    return 100.0, 120000.0, "Default"


def apply_fao_yield_outlier_cap(
    df: pd.DataFrame,
    yield_col: str = "Yield_kgha",
    factor: float = YIELD_FAO_EXCLUSION_FACTOR,
) -> pd.DataFrame:
    if yield_col not in df.columns or "Crop" not in df.columns:
        return df
    out = df.copy()
    y = pd.to_numeric(out[yield_col], errors="coerce")

    # Treat non-positive yields as invalid for statistics/export (prevents artificial 0 medians).
    y = y.where(y > 0)

    thr_max = out["Crop"].map(lambda c: fao_yield_threshold_for_crop(c)[1])
    y = y.where(y < (factor * thr_max))
    out[yield_col] = y
    return out


def to_numeric_series(series: pd.Series) -> pd.Series:
    return series.map(parse_espac_number)


def normalize_code_value(v) -> str:
    if pd.isna(v):
        return ""
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    txt = str(v).strip()
    if txt.endswith(".0"):
        maybe = txt[:-2]
        if maybe.isdigit():
            return maybe
    return txt


def decode_series_from_dict(series: pd.Series, code: str, source: str) -> pd.Series:
    if "lookup_value_map" not in globals() or "DICT_CTX" not in globals():
        return series
    value_map = lookup_value_map(code, source, DICT_CTX)
    if not value_map:
        return series
    norm_map = {normalize_code_value(k): v for k, v in value_map.items()}
    return series.apply(lambda x: norm_map.get(normalize_code_value(x), x))


def clean_packaging_values(series: pd.Series) -> pd.Series:
    def _clean(v):
        if pd.isna(v):
            return np.nan
        raw = str(v).strip()
        if not raw or raw.lower() in {"nan", "none"}:
            return np.nan
        if re.search(r"[A-Za-zÃƒÂÃƒâ€°ÃƒÂÃƒâ€œÃƒÅ¡ÃƒÅ“Ãƒâ€˜ÃƒÂ¡ÃƒÂ©ÃƒÂ­ÃƒÂ³ÃƒÂºÃƒÂ¼ÃƒÂ±]", raw):
            txt = re.sub(r"\s+", " ", raw).strip().upper()
            if txt in {"SIN ESTADO", "NO SABE", "NO APLICA", "N/A"}:
                return np.nan
            return txt
        return np.nan

    return series.apply(_clean)


def infer_cp_state_labels(code_series: pd.Series, crop_series: pd.Series) -> pd.Series:
    codes = code_series.map(normalize_code_value)
    states = crop_series.astype(str).str.extract(r"\(([^)]+)\)")[0].str.strip().str.upper()

    mapping = (
        pd.DataFrame({"code": codes, "state": states})
        .dropna()
        .query("code != '' and state != ''")
        .groupby("code")["state"]
        .agg(lambda s: mode_non_null(s))
        .to_dict()
    )
    out = codes.map(mapping)
    return clean_packaging_values(out)


def infer_cp_unit_labels(code_series: pd.Series, eq_series: pd.Series) -> pd.Series:
    # Reference equivalence (in pounds) to likely unit labels.
    ref = {
        "LIBRA": 1.0,
        "UNIDAD": 2.0,
        "ATADO": 5.0,
        "CARGA": 15.0,
        "ARROBA": 25.0,
        "OTRA": 30.0,
        "CAJA": 40.0,
        "SACO": 70.0,
        "COSTAL": 80.0,
        "QUINTAL": 100.0,
        "TONELADA": 2000.0,
        "TONELADA METR.": 2200.0,
    }
    ref_items = list(ref.items())

    def nearest_unit(eq):
        if pd.isna(eq):
            return np.nan
        best = min(ref_items, key=lambda kv: abs(float(eq) - kv[1]))
        return best[0]

    df = pd.DataFrame({
        "code": code_series.map(normalize_code_value),
        "eq": to_numeric_series(eq_series),
    })
    df["unit_guess"] = df["eq"].map(nearest_unit)
    code_map = (
        df.dropna(subset=["code", "unit_guess"])
        .query("code != ''")
        .groupby("code")["unit_guess"]
        .agg(lambda s: mode_non_null(s))
        .to_dict()
    )
    out = df["code"].map(code_map)
    return clean_packaging_values(out)


def to_kg_series(quantity: pd.Series, units: pd.Series) -> pd.Series:
    q = to_numeric_series(quantity)
    u = units.astype(str).str.strip().str.upper().replace({"NONE": "", "NAN": "", "0": ""})
    out = pd.Series(np.nan, index=quantity.index, dtype="float64")
    for unit, factor in KG_UNIT_FACTORS.items():
        mask = u == unit
        if mask.any():
            out.loc[mask] = q.loc[mask] * factor
    return out


def parse_month_number(v):
    if pd.isna(v):
        return np.nan
    n = parse_espac_number(v)
    if pd.notna(n) and 1 <= int(n) <= 12:
        return int(n)
    txt = _normalize_text(v)
    return MONTH_MAP.get(txt, np.nan)


def parse_year(v):
    n = parse_espac_number(v)
    if pd.isna(n):
        return np.nan
    y = int(round(float(n)))
    if y < 100:
        y += 2000
    return y if 1900 <= y <= 2100 else np.nan


def format_ymd(year, month):
    if pd.isna(year) or pd.isna(month):
        return np.nan
    return f"{int(year):04d}-{int(month):02d}-01"


def infer_cycle_months(seed_year, seed_month, harvest_year, harvest_month):
    if any(pd.isna(v) for v in [seed_year, seed_month, harvest_year, harvest_month]):
        return np.nan
    months = (int(harvest_year) - int(seed_year)) * 12 + (int(harvest_month) - int(seed_month))
    return months if months >= 0 else np.nan


def mode_non_null(s: pd.Series):
    x = s.dropna().astype(str).str.strip()
    x = x[x != ""]
    if x.empty:
        return np.nan
    return x.value_counts().idxmax()


def cycle_months_from_dates(seeding_date, harvest_date):
    if pd.isna(seeding_date) or pd.isna(harvest_date):
        return np.nan
    sd = pd.to_datetime(seeding_date, errors="coerce")
    hd = pd.to_datetime(harvest_date, errors="coerce")
    if pd.isna(sd) or pd.isna(hd):
        return np.nan
    months = (hd.year - sd.year) * 12 + (hd.month - sd.month)
    return float(months) if months >= 0 else np.nan


def interpolate_dates_from_existing(grouped: pd.DataFrame) -> pd.DataFrame:
    out = grouped.copy()

    global_seed_mode = mode_non_null(out.get("Seeding_date", pd.Series(dtype=object)))
    global_harvest_mode = mode_non_null(out.get("Harvest_date", pd.Series(dtype=object)))
    global_cycle_median = pd.to_numeric(out.get("Cycle_length_months", pd.Series(dtype=float)), errors="coerce").median()

    for col in ["Seeding_date", "Harvest_date"]:
        if col not in out.columns:
            continue

        non_blank_mask = out[col].notna() & (out[col].astype(str).str.strip() != "")
        base = out.loc[non_blank_mask, ["Crop", "Category", "Region", col]].copy()
        if base.empty:
            out[col] = out[col].fillna(global_seed_mode if col == "Seeding_date" else global_harvest_mode)
            continue

        def _mode_frame(keys, suffix):
            return (
                base.groupby(keys, as_index=False)[col]
                .agg(mode_non_null)
                .rename(columns={col: suffix})
            )

        enriched = out[["Crop", "Category", "Region", col]].copy()
        for keys, suffix in [
            (["Crop", "Category", "Region"], f"{col}__fb_ccr"),
            (["Crop", "Region"], f"{col}__fb_cr"),
            (["Category", "Region"], f"{col}__fb_car"),
            (["Crop", "Category"], f"{col}__fb_cc"),
            (["Crop"], f"{col}__fb_c"),
        ]:
            enriched = enriched.merge(_mode_frame(keys, suffix), on=keys, how="left")

        filled = enriched[col]
        for suffix in [f"{col}__fb_ccr", f"{col}__fb_cr", f"{col}__fb_car", f"{col}__fb_cc", f"{col}__fb_c"]:
            filled = filled.fillna(enriched[suffix])
        filled = filled.fillna(global_seed_mode if col == "Seeding_date" else global_harvest_mode)
        out[col] = filled

    if "Cycle_length_months" in out.columns:
        seeding_dt = pd.to_datetime(out.get("Seeding_date"), errors="coerce")
        harvest_dt = pd.to_datetime(out.get("Harvest_date"), errors="coerce")
        computed_months = (harvest_dt.dt.year - seeding_dt.dt.year) * 12 + (harvest_dt.dt.month - seeding_dt.dt.month)
        computed_months = computed_months.where((computed_months >= 0) & seeding_dt.notna() & harvest_dt.notna())
        out["Cycle_length_months"] = pd.to_numeric(out["Cycle_length_months"], errors="coerce")
        out["Cycle_length_months"] = computed_months.fillna(out["Cycle_length_months"]).fillna(global_cycle_median)

    return out


def infer_irrig_equipment(df: pd.DataFrame, prefix: str) -> pd.Series:
    method_cols = {
        "surcos": f"{prefix}_porc_surc",
        "aspersi?n": f"{prefix}_porc_aspe",
        "microaspersi?n": f"{prefix}_porc_micr",
        "goteo": f"{prefix}_porc_gote",
        "nebulizaci?n": f"{prefix}_porc_nebu",
    }
    parsed = {name: to_numeric_series(df[col]) for name, col in method_cols.items() if col in df.columns}

    out = []
    for idx in df.index:
        best_name, best_val = None, -1
        for name, vals in parsed.items():
            v = vals.loc[idx]
            if pd.notna(v) and v > best_val:
                best_name, best_val = name, float(v)

        if best_name is not None and best_val > 0:
            out.append(best_name)
            continue

        riego_col = f"{prefix}_riego"
        if riego_col in df.columns:
            rv = str(df.loc[idx, riego_col]).strip().upper()
            if rv == "NO":
                out.append("sin riego")
                continue

        out.append(np.nan)

    return pd.Series(out, index=df.index)


def infer_crop_water_need_mm(crop_name: str, category: str) -> float:
    txt = _normalize_geo_text(crop_name)
    for keywords, mm in CROP_WATER_NEED_MM_BY_KEYWORD:
        if any(k in txt for k in keywords):
            return float(mm)
    # Conservative fallback by crop category.
    return 900.0 if str(category).strip().lower() == "permanent" else 600.0


def infer_irrigation_efficiency(equipment: str) -> float:
    if pd.isna(equipment):
        return np.nan
    eq = _normalize_text(equipment)
    if eq in {"sin riego", "no riego", "sin irrigacion", "sin irrigacion"}:
        return 0.0

    # Normalize config keys to avoid accent/mojibake KeyError issues.
    norm_eff = {_normalize_text(k): float(v) for k, v in IRRIGATION_EFF_BY_EQUIPMENT.items()}
    if eq in norm_eff:
        return norm_eff[eq]

    def _pick(candidates, default=np.nan):
        for cand in candidates:
            if cand in norm_eff:
                return norm_eff[cand]
        return default

    eff_surcos = _pick(["surcos"])
    eff_asp = _pick(["aspersion"], default=eff_surcos)
    eff_micro = _pick(["microaspersion", "micro aspersion"], default=eff_asp)
    eff_nebu = _pick(["nebulizacion"], default=eff_asp)
    eff_goteo = _pick(["goteo"], default=eff_asp)

    # Fallback token matching for irregular spellings/encodings.
    if "micro" in eq and "asper" in eq:
        return eff_micro
    if "nebul" in eq:
        return eff_nebu
    if "gote" in eq:
        return eff_goteo
    if "asper" in eq:
        return eff_asp
    if "surc" in eq:
        return eff_surcos

    return np.nan


def estimate_irrig_m3_per_ha(crop_name: str, category: str, equipment: str, irrig_share: float) -> float:
    if pd.isna(irrig_share) or irrig_share <= 0:
        return 0.0
    eff = infer_irrigation_efficiency(equipment)
    if pd.isna(eff):
        return np.nan
    if eff <= 0:
        return 0.0
    net_mm = infer_crop_water_need_mm(crop_name, category)
    gross_m3_per_ha_irrigated = (net_mm * 10.0) / eff
    # Express as m3/ha over full crop area (weighted by irrigated share).
    return gross_m3_per_ha_irrigated * float(irrig_share)


def _ods_rows(path: Path):
    if not path.exists():
        return
    ns = {"table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0"}
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("content.xml"))
    for table in root.findall(".//table:table", ns):
        for tr in table.findall("table:table-row", ns):
            vals = []
            for cell in tr.findall("table:table-cell", ns):
                repeat = int(cell.attrib.get("{urn:oasis:names:tc:opendocument:xmlns:table:1.0}number-columns-repeated", "1"))
                text = "".join(cell.itertext()).strip()
                vals.extend([text] * min(repeat, 200))
            if any(vals):
                yield vals


def load_ambient_irrigation_sources(project_dir: Path) -> pd.DataFrame:
    path = project_dir / "inputs/BDD_MOD_INF_AMB_ESPAC_2024_ODS/amb_2024_nac.ods"
    rows = list(_ods_rows(path) or [])
    if not rows:
        return pd.DataFrame(columns=["identificador", "Irrigation_source", "Irrigation_source_code"])
    header = [str(v).strip().lower() for v in rows[0]]
    if "identif" not in header or "ag_proviriego" not in header:
        return pd.DataFrame(columns=["identificador", "Irrigation_source", "Irrigation_source_code"])
    ident_i = header.index("identif")
    source_i = header.index("ag_proviriego")
    out = []
    for row in rows[1:]:
        ident = str(row[ident_i]).strip() if ident_i < len(row) else ""
        code = str(row[source_i]).strip() if source_i < len(row) else ""
        source = IRRIGATION_SOURCE_CODE_MAP.get(code, DEFAULT_IRRIGATION_SOURCE)
        if ident:
            out.append({"identificador": ident, "Irrigation_source": source, "Irrigation_source_code": code})
    return pd.DataFrame(out).drop_duplicates(subset=["identificador"], keep="first")


def estimate_irrig_m3_per_ha_series(crop_series: pd.Series, category_series: pd.Series, equipment_series: pd.Series, irrig_share_series: pd.Series) -> pd.Series:
    irrig_share = pd.to_numeric(irrig_share_series, errors="coerce").fillna(0.0)
    crop_norm = crop_series.astype(str).map(_normalize_proxy_crop_name)
    category_norm = category_series.astype(str).str.strip().str.lower()
    equipment_norm = equipment_series.astype(str).map(_normalize_text)

    eff = equipment_norm.map(IRRIGATION_EFF_BY_EQUIPMENT)
    net_mm = pd.Series(np.where(category_norm.eq("permanent"), 900.0, 600.0), index=irrig_share.index, dtype="float64")
    for keywords, mm in CROP_WATER_NEED_MM_BY_KEYWORD:
        mask = crop_norm.map(lambda txt: any(k in txt for k in keywords))
        net_mm.loc[mask] = float(mm)

    gross_m3_per_ha_irrigated = (net_mm * 10.0) / eff
    out = gross_m3_per_ha_irrigated * irrig_share
    out = out.where(irrig_share > 0, 0.0)
    out = out.where(eff.notna(), np.nan)
    out = out.where(~((eff <= 0) & (irrig_share > 0)), 0.0)
    return out


def build_crop_lci_base(conn: sqlite3.Connection) -> (pd.DataFrame, pd.DataFrame, pd.DataFrame):
    geo = pd.read_sql_query(
        "SELECT CAST(identificador AS TEXT) AS identificador, provincia FROM encuestas", conn
    )
    geo["identificador"] = geo["identificador"].str.strip()
    geo["region"] = geo["provincia"].map(map_provincia_to_region)

    ambient_irrig_sources = load_ambient_irrigation_sources(PROJECT_DIR)
    ambient_source_by_ident = (
        ambient_irrig_sources.set_index("identificador")["Irrigation_source"]
        if not ambient_irrig_sources.empty
        else pd.Series(dtype="object")
    )

    table_specs = [
        {
            "table": "rel_inec_cpnac",
            "source": "cpnac",
            "prefix": "cp",
            "crop_col": "cp_nclavr",
            "area_col": "cp_k411ha",
            "harvest_qty_col": "cp_k416",
            "harvest_lb_eq_col": "cp_k418",
            "harvest_prod_t_col": "cp_prod",
            "irrig_area_col": "cp_superf_regada_ha",
            "seed_col": "cp_rdproven5",
            "package_col": "cp_k423",
            "product_state_col": "cp_k426",
            "manure_type_col": "cp_abono_fo",
            "condition_col": "nuevacondicion",
            "category": "permanent",
            "output_basis": "observed harvested product",
            "yield_data_status": "direct_espac_output",
            "yield_basis_note": "Yield_kgha is reconstructed from direct ESPAC harvested production variables.",
        },
        {
            "table": "rel_inec_ctnac",
            "source": "ctnac",
            "prefix": "ct",
            "crop_col": "ct_nclavr",
            "area_col": "ct_k511ha",
            "harvest_qty_col": "ct_k516",
            "harvest_lb_eq_col": "ct_k518",
            "harvest_prod_t_col": "ct_prod",
            "irrig_area_col": "ct_superf_regada_ha",
            "seed_col": "ct_rdproven5",
            "seed_month_col": "ct_k507",
            "seed_year_col": "ct_k508",
            "harvest_month_col": "ct_k509",
            "package_col": "ct_k523",
            "product_state_col": "ct_k526",
            "manure_type_col": "ct_abono_fo",
            "condition_col": "ct_nuevacondicion",
            "soil_prep_col": "ct_presueuti",
            "category": "transitory",
            "output_basis": "observed harvested product",
            "yield_data_status": "direct_espac_output",
            "yield_basis_note": "Yield_kgha is reconstructed from direct ESPAC harvested production variables.",
        },
        {
            "table": "rel_inec_pcnac",
            "source": "pcnac",
            "prefix": "cp",
            "crop_col": "pc_nclavr",
            "area_col": "cp_k409ha",
            "irrig_area_col": "cp_superf_regada_ha",
            "condition_col": "cp_k404",
            "category": "cultivated_pasture",
            "output_basis": "observed managed pasture area",
            "yield_data_status": "missing_direct_output_in_espac",
            "yield_basis_note": "ESPAC pcnac exposes cultivated-pasture area and management inputs, but not harvested biomass or output; Yield_kgha is intentionally left blank.",
            "exclude_from_yield_fallback": True,
        },
    ]

    frames: List[pd.DataFrame] = []
    unit_audit_rows: List[Dict[str, object]] = []
    coverage_rows: List[Dict[str, object]] = []

    for spec in table_specs:
        df = pd.read_sql_query(f'SELECT * FROM "{spec["table"]}"', conn)
        if df.empty or "identificador" not in df.columns:
            continue

        df.columns = [str(c).strip().lower() for c in df.columns]
        df["identificador"] = df["identificador"].astype(str).str.strip()
        df = df.merge(geo[["identificador", "provincia", "region"]], on="identificador", how="left")
        df = df[df["region"].isin(["costa", "sierra", "oriente"])].copy()

        crop = df[spec["crop_col"]].astype(str).str.strip().replace({"": np.nan, "None": np.nan, "nan": np.nan})
        area = to_numeric_series(df[spec["area_col"]])
        # Preferred production variable (tons) from ESPAC tables.
        prod_t = (
            to_numeric_series(df[spec["harvest_prod_t_col"]])
            if spec.get("harvest_prod_t_col") and spec["harvest_prod_t_col"] in df.columns
            else pd.Series(np.nan, index=df.index, dtype="float64")
        )
        prod_t = prod_t.where(prod_t > 0)
        harvested_kg_from_prod = prod_t * 1000.0

        # Legacy fallback from quantity * lb-equivalent, kept only when *_prod is missing.
        harvested_qty = (
            to_numeric_series(df[spec["harvest_qty_col"]]).where(lambda s: s > 0)
            if spec.get("harvest_qty_col") and spec["harvest_qty_col"] in df.columns
            else pd.Series(np.nan, index=df.index, dtype="float64")
        )
        lb_equiv = (
            sanitize_lb_equiv(to_numeric_series(df[spec["harvest_lb_eq_col"]]))
            if spec.get("harvest_lb_eq_col") and spec["harvest_lb_eq_col"] in df.columns
            else pd.Series(np.nan, index=df.index, dtype="float64")
        )
        harvested_kg_legacy = harvested_qty * lb_equiv * LB_TO_KG

        harvested_kg = harvested_kg_from_prod.where(harvested_kg_from_prod.notna(), harvested_kg_legacy)
        yield_kgha = np.where((area > 0) & pd.notna(harvested_kg) & (harvested_kg > 0), harvested_kg / area, np.nan)
        yield_proxy_min = pd.Series(np.nan, index=df.index, dtype="float64")
        yield_proxy_max = pd.Series(np.nan, index=df.index, dtype="float64")
        seed_share_pct = to_numeric_series(df[spec["seed_col"]]) if spec.get("seed_col") in df.columns else pd.Series(np.nan, index=df.index, dtype="float64")
        seed_share_pct = seed_share_pct.where((seed_share_pct >= 0) & (seed_share_pct <= 100))
        output_basis = spec.get("output_basis", "observed harvested product")
        yield_data_status = spec.get("yield_data_status", "direct_espac_output")
        yield_basis_note = spec.get("yield_basis_note", "Yield_kgha is reconstructed from direct ESPAC harvested production variables.")
        exclude_from_yield_fallback = bool(spec.get("exclude_from_yield_fallback", False))

        if str(spec.get("category", "")).strip().lower() == "cultivated_pasture":
            pasture_proxy_df = pd.DataFrame([pasture_yield_proxy_for_crop(v) for v in crop], index=df.index)
            proxy_mask = (area > 0) & crop.notna() & (crop.astype(str).str.strip() != "")
            yield_kgha = pasture_proxy_df["median"].where(proxy_mask, np.nan)
            yield_proxy_min = pasture_proxy_df["min"].where(proxy_mask, np.nan)
            yield_proxy_max = pasture_proxy_df["max"].where(proxy_mask, np.nan)
            yield_data_status = pasture_proxy_df["status"].where(proxy_mask, yield_data_status)
            yield_basis_note = pasture_proxy_df["note"].where(proxy_mask, yield_basis_note)

        fert_npk_kg = to_kg_series(df[f'{spec["prefix"]}_cantidad_npk_fq'], df[f'{spec["prefix"]}_umed_npk_fq'])
        fert_nit_kg = to_kg_series(df[f'{spec["prefix"]}_cantidad_nit_fq'], df[f'{spec["prefix"]}_umed_nit_fq'])
        fert_pot_kg = to_kg_series(df[f'{spec["prefix"]}_cantidad_pot_fq'], df[f'{spec["prefix"]}_umed_pot_fq'])
        fert_fos_kg = to_kg_series(df[f'{spec["prefix"]}_cantidad_fq'], df[f'{spec["prefix"]}_umed_fq'])
        org_1_kg = to_kg_series(df[f'{spec["prefix"]}_cant1_fo'], df[f'{spec["prefix"]}_umed1_fo'])

        org_2_kg = pd.Series(np.nan, index=df.index, dtype="float64")
        if f'{spec["prefix"]}_cant2_fo' in df.columns and f'{spec["prefix"]}_umed2_fo' in df.columns:
            org_2_kg = to_kg_series(df[f'{spec["prefix"]}_cant2_fo'], df[f'{spec["prefix"]}_umed2_fo'])
        org_3_kg = pd.Series(np.nan, index=df.index, dtype="float64")
        if f'{spec["prefix"]}_cant3_fo' in df.columns and f'{spec["prefix"]}_umed3_fo' in df.columns:
            org_3_kg = to_kg_series(df[f'{spec["prefix"]}_cant3_fo'], df[f'{spec["prefix"]}_umed3_fo'])

        pest_ins_kg = to_kg_series(df[f'{spec["prefix"]}_cantidad_ins_pq'], df[f'{spec["prefix"]}_umed_ins_pq'])
        pest_her_kg = to_kg_series(df[f'{spec["prefix"]}_cantidad_her_pq'], df[f'{spec["prefix"]}_umed_her_pq'])
        pest_fun_kg = to_kg_series(df[f'{spec["prefix"]}_cantidad_fun_pq'], df[f'{spec["prefix"]}_umed_fun_pq'])
        pest_other_kg = to_kg_series(df[f'{spec["prefix"]}_cantidad_pq'], df[f'{spec["prefix"]}_umed_pq'])
        pest_org_kg = to_kg_series(df[f'{spec["prefix"]}_cantidad_po'], df[f'{spec["prefix"]}_umed_po'])

        total_fert_kg = fert_npk_kg.fillna(0) + fert_nit_kg.fillna(0) + fert_pot_kg.fillna(0) + fert_fos_kg.fillna(0)
        organic_total_kg = org_1_kg.fillna(0) + org_2_kg.fillna(0) + org_3_kg.fillna(0)
        manure_kg = organic_total_kg
        acaricide_kg = pd.Series(0.0, index=df.index, dtype="float64")
        biocide_kg = pest_other_kg.fillna(0) + pest_org_kg.fillna(0)
        total_pest_kg = (
            pest_ins_kg.fillna(0)
            + pest_her_kg.fillna(0)
            + pest_fun_kg.fillna(0)
            + acaricide_kg.fillna(0)
            + biocide_kg.fillna(0)
        )

        package_col = spec.get("package_col")
        product_state_col = spec.get("product_state_col")
        manure_type_col = spec.get("manure_type_col")

        packaging_type1 = decode_series_from_dict(df[package_col], package_col, spec["source"]) if package_col and package_col in df.columns else np.nan
        packaging_type2 = decode_series_from_dict(df[product_state_col], product_state_col, spec["source"]) if product_state_col and product_state_col in df.columns else np.nan
        if spec["source"] == "cpnac" and package_col and product_state_col:
            packaging_type1 = infer_cp_unit_labels(df[package_col], df["cp_k424"])
            packaging_type2 = infer_cp_state_labels(df[product_state_col], crop)
        else:
            packaging_type1 = clean_packaging_values(pd.Series(packaging_type1))
            packaging_type2 = clean_packaging_values(pd.Series(packaging_type2))
        manure_type = decode_series_from_dict(df[manure_type_col], manure_type_col, spec["source"]) if manure_type_col and manure_type_col in df.columns else np.nan
        soil_prep_col = spec.get("soil_prep_col")
        soil_prep_method = decode_series_from_dict(df[soil_prep_col], soil_prep_col, spec["source"]) if soil_prep_col and soil_prep_col in df.columns else np.nan

        seed_month = pd.Series(np.nan, index=df.index)
        seed_year = pd.Series(np.nan, index=df.index)
        harvest_month = pd.Series(np.nan, index=df.index)
        harvest_year = pd.Series(np.nan, index=df.index)

        if spec.get("seed_month_col") and spec["seed_month_col"] in df.columns:
            seed_month = df[spec["seed_month_col"]].map(parse_month_number)
        if spec.get("seed_year_col") and spec["seed_year_col"] in df.columns:
            seed_year = df[spec["seed_year_col"]].map(parse_year)
        if spec.get("harvest_month_col") and spec["harvest_month_col"] in df.columns:
            harvest_month = df[spec["harvest_month_col"]].map(parse_month_number)
            harvest_year = seed_year.copy()
            needs_next_year = (pd.notna(seed_month)) & (pd.notna(harvest_month)) & (harvest_month < seed_month)
            harvest_year.loc[needs_next_year] = harvest_year.loc[needs_next_year] + 1

        seeding_date = [format_ymd(y, m) for y, m in zip(seed_year, seed_month)]
        harvest_date = [format_ymd(y, m) for y, m in zip(harvest_year, harvest_month)]
        cycle_length = [
            infer_cycle_months(sy, sm, hy, hm)
            for sy, sm, hy, hm in zip(seed_year, seed_month, harvest_year, harvest_month)
        ]

        irrigation_source = df["identificador"].map(ambient_source_by_ident).fillna(DEFAULT_IRRIGATION_SOURCE)
        irrigation_source = irrigation_source.where(irrigation_source.isin(IRRIGATION_SOURCE_OPTIONS), DEFAULT_IRRIGATION_SOURCE)

        base = pd.DataFrame(
            {
                "identificador": df["identificador"],
                "Region": df["region"],
                "Province": df["provincia"],
                "Crop": crop,
                "Category": spec["category"],
                "Source_module": spec["source"],
                "Output_basis": output_basis,
                "Yield_data_status": yield_data_status,
                "Yield_basis_note": yield_basis_note,
                "Exclude_from_yield_fallback": exclude_from_yield_fallback,
                "Seeding_date": seeding_date,
                "Harvest_date": harvest_date,
                "Cycle_length_months": cycle_length,
                "Area_ha": area,
                "Irrigated_area_ha": to_numeric_series(df[spec["irrig_area_col"]]),
                "Yield_kgha": yield_kgha,
                "Yield_kgha__proxy_min": yield_proxy_min,
                "Yield_kgha__proxy_max": yield_proxy_max,
                "Irrig_m3": np.nan,
                "Irrigation_source": irrigation_source,
                "Irrig_equipment": infer_irrig_equipment(df, spec["prefix"]),
                "Packaging_type1": packaging_type1,
                "Packaging_type1_kgha": np.nan,
                "Packaging_type2": packaging_type2,
                "Packaging_type2_kgha": np.nan,
                "NPK_kgha": np.where(area > 0, fert_npk_kg / area, np.nan),
                "AN_kgha": np.where(area > 0, fert_nit_kg / area, np.nan),
                "AS_kgha": np.where(area > 0, fert_pot_kg / area, np.nan),
                "AP_kgha": np.where(area > 0, fert_fos_kg / area, np.nan),
                "Total_fert_min_kgha": np.where(area > 0, total_fert_kg / area, np.nan),
                "Manure_kgha": np.where(area > 0, manure_kg / area, np.nan),
                "Organic_estiercol_kgha": np.where(area > 0, org_1_kg / area, np.nan),
                "Organic_fermentado_kgha": np.where(area > 0, org_2_kg / area, np.nan),
                "Organic_liquido_kgha": np.where(area > 0, org_3_kg / area, np.nan),
                "Manure_type": manure_type,
                "nuevacondicion": df[spec["condition_col"]] if spec.get("condition_col") in df.columns else np.nan,
                "Soil_prep_method": soil_prep_method,
                "Insecticide_kgha": np.where(area > 0, pest_ins_kg / area, np.nan),
                "Herbicide_kgha": np.where(area > 0, pest_her_kg / area, np.nan),
                "Fungicide_kgha": np.where(area > 0, pest_fun_kg / area, np.nan),
                "Acaricide_kgha": np.where(area > 0, acaricide_kg / area, np.nan),
                "Biocide_NE_kgha": np.where(area > 0, biocide_kg / area, np.nan),
                "Total_pesticides_kgha": np.where(area > 0, total_pest_kg / area, np.nan),
                "Seed_share_pct": seed_share_pct,
            }
        )
        base = base[base["Crop"].notna()]
        frames.append(base)

        # Coverage diagnostics for fertilizer per-ha metrics
        fert_diag_specs = [
            ("NPK_kgha", f'{spec["prefix"]}_cantidad_npk_fq', f'{spec["prefix"]}_umed_npk_fq'),
            ("AN_kgha", f'{spec["prefix"]}_cantidad_nit_fq', f'{spec["prefix"]}_umed_nit_fq'),
            ("AS_kgha", f'{spec["prefix"]}_cantidad_pot_fq', f'{spec["prefix"]}_umed_pot_fq'),
            ("AP_kgha", f'{spec["prefix"]}_cantidad_fq', f'{spec["prefix"]}_umed_fq'),
        ]
        area_ok = area > 0
        for metric_name, qty_col, unit_col in fert_diag_specs:
            qty_num = to_numeric_series(df[qty_col])
            unit_norm = df[unit_col].astype(str).str.strip().str.upper().replace({"NONE": "", "NAN": "", "0": ""})
            has_qty = qty_num.notna()
            has_unit = unit_norm != ""
            unit_convertible = unit_norm.isin(KG_UNIT_FACTORS.keys())

            reason = np.where(
                ~has_qty,
                "no_quantity",
                np.where(
                    ~has_unit,
                    "missing_unit",
                    np.where(~unit_convertible, "unit_not_convertible", np.where(~area_ok, "missing_area", "ok")),
                ),
            )
            diag = pd.DataFrame(
                {
                    "module": spec["prefix"].upper(),
                    "Region": df["region"],
                    "Province": df["provincia"],
                    "Crop": crop,
                    "Category": spec["category"],
                    "metric": metric_name,
                    "reason": reason,
                }
            )
            diag = diag[diag["Crop"].notna()]
            coverage_rows.extend(diag.to_dict(orient="records"))

        unit_pairs = [
            (f'{spec["prefix"]}_cantidad_npk_fq', f'{spec["prefix"]}_umed_npk_fq', "fert_npk"),
            (f'{spec["prefix"]}_cantidad_nit_fq', f'{spec["prefix"]}_umed_nit_fq', "fert_nit"),
            (f'{spec["prefix"]}_cantidad_pot_fq', f'{spec["prefix"]}_umed_pot_fq', "fert_pot"),
            (f'{spec["prefix"]}_cantidad_fq', f'{spec["prefix"]}_umed_fq', "fert_fos"),
            (f'{spec["prefix"]}_cant1_fo', f'{spec["prefix"]}_umed1_fo', "org_1"),
            (f'{spec["prefix"]}_cantidad_ins_pq', f'{spec["prefix"]}_umed_ins_pq', "pest_ins"),
            (f'{spec["prefix"]}_cantidad_her_pq', f'{spec["prefix"]}_umed_her_pq', "pest_her"),
            (f'{spec["prefix"]}_cantidad_fun_pq', f'{spec["prefix"]}_umed_fun_pq', "pest_fun"),
            (f'{spec["prefix"]}_cantidad_pq', f'{spec["prefix"]}_umed_pq', "pest_other"),
            (f'{spec["prefix"]}_cantidad_po', f'{spec["prefix"]}_umed_po', "pest_org"),
        ]
        if f'{spec["prefix"]}_cant2_fo' in df.columns and f'{spec["prefix"]}_umed2_fo' in df.columns:
            unit_pairs.append((f'{spec["prefix"]}_cant2_fo', f'{spec["prefix"]}_umed2_fo', "org_2"))

        for qty_col, unit_col, metric in unit_pairs:
            qty = to_numeric_series(df[qty_col])
            units = df[unit_col].astype(str).str.strip().str.upper().replace({"NONE": "", "NAN": "", "0": ""})
            used = qty.notna()
            for unit, n in units[used].value_counts(dropna=False).items():
                if not unit:
                    continue
                unit_audit_rows.append(
                    {
                        "module": spec["prefix"].upper(),
                        "metric": metric,
                        "unit": unit,
                        "n_records": int(n),
                        "kg_convertible": unit in KG_UNIT_FACTORS,
                    }
                )

    if not frames:
        empty_lci = pd.DataFrame(columns=["Region", "Province", "Crop", "Category"])
        empty_audit = pd.DataFrame(columns=["module", "metric", "unit", "n_records", "kg_convertible"])
        empty_cov = pd.DataFrame(columns=["module", "Region", "Province", "Crop", "Category", "metric", "reason"])
        return empty_lci, empty_audit, empty_cov

    return pd.concat(frames, ignore_index=True), pd.DataFrame(unit_audit_rows), pd.DataFrame(coverage_rows)


def _add_row_level_derived_lci_inputs(base_df: pd.DataFrame) -> pd.DataFrame:
    out = base_df.copy()

    area = pd.to_numeric(out.get("Area_ha", pd.Series(np.nan, index=out.index)), errors="coerce")
    irrig_area = pd.to_numeric(out.get("Irrigated_area_ha", pd.Series(np.nan, index=out.index)), errors="coerce")
    irrig_share = (irrig_area / area.replace({0: np.nan})).clip(lower=0, upper=1).fillna(0.0)

    out["Irrig_m3"] = estimate_irrig_m3_per_ha_series(
        out.get("Crop", pd.Series("", index=out.index)),
        out.get("Category", pd.Series("", index=out.index)),
        out.get("Irrig_equipment", pd.Series("", index=out.index)),
        irrig_share,
    )
    irrig_m3 = pd.to_numeric(out["Irrig_m3"], errors="coerce").fillna(0.0)
    irrigation_source = out.get("Irrigation_source", pd.Series(DEFAULT_IRRIGATION_SOURCE, index=out.index)).astype(str).str.strip().str.lower()
    irrigation_source = irrigation_source.where(irrigation_source.isin(IRRIGATION_SOURCE_OPTIONS), DEFAULT_IRRIGATION_SOURCE)
    out["Irrigation_source"] = irrigation_source
    for source in sorted(IRRIGATION_SOURCE_OPTIONS):
        out[f"Irrig_{source}_m3"] = np.where(irrigation_source.eq(source), irrig_m3, 0.0)

    soil_prep_method = out.get("Soil_prep_method", pd.Series("", index=out.index))
    category_series = out.get("Category", pd.Series("", index=out.index))
    mechanization_factor = pd.Series([
        infer_mechanization_fuel_factor(method, category)
        for method, category in zip(soil_prep_method, category_series)
    ], index=out.index, dtype="float64")

    fallback_fuel_mj = DEFAULT_DIESEL_L_HA_IRRIGATED * irrig_share * FUEL_MJ_PER_L * mechanization_factor
    crop_key = out.get("Crop", pd.Series("", index=out.index)).astype(str).map(_normalize_proxy_crop_name)
    proxy_fuel_mj = crop_key.map(FUEL_PROXY_MEDIAN_BY_CROP)

    proxy_category = crop_key.map(FUEL_PROXY_CATEGORY_BY_CROP).astype(str).str.lower()
    proxy_factor = proxy_category.map(FUEL_PROXY_EC_CAL_BY_CATEGORY).fillna(FUEL_PROXY_EC_CAL_DEFAULT)
    if not FUEL_PROXY_EC_CAL_ENABLED:
        proxy_factor = pd.Series(1.0, index=out.index)

    proxy_fuel_mj_cal = proxy_fuel_mj * proxy_factor
    fuel_mj = proxy_fuel_mj_cal.where(proxy_fuel_mj_cal.notna(), fallback_fuel_mj)

    out["Fuel_ha"] = pd.to_numeric(fuel_mj, errors="coerce").fillna(0.0)
    out["Fuel_type"] = np.where(
        out["Fuel_ha"] > 0,
        np.where(proxy_fuel_mj_cal.notna(), "Diesel (proxy literature, Ecuador-calibrated)", "Diesel (estimated irrigation/mechanisation proxy)"),
        None,
    )
    out["Fuel_unit"] = np.where(out["Fuel_ha"] > 0, "MJ/ha", None)
    out["Electricity_kWh_ha"] = DEFAULT_ELECTRICITY_KWH_HA_IRRIGATED * irrig_share

    out["Urea_kgha"] = np.nan
    out["MAP_kgha"] = np.nan
    out["UAN_kgha"] = np.nan
    out["CAN_kgha"] = np.nan
    out["Compost_kg_ha"] = np.nan
    out["Digestate_kg_ha"] = np.nan

    out["Total_fert_org_kgha"] = (
        pd.to_numeric(out.get("Organic_estiercol_kgha", 0.0), errors="coerce").fillna(0.0)
        + pd.to_numeric(out.get("Organic_fermentado_kgha", 0.0), errors="coerce").fillna(0.0)
        + pd.to_numeric(out.get("Organic_liquido_kgha", 0.0), errors="coerce").fillna(0.0)
    )

    seed_share = pd.to_numeric(out.get("Seed_share_pct", np.nan), errors="coerce")
    yield_kgha = pd.to_numeric(out.get("Yield_kgha", np.nan), errors="coerce")
    out["Seed_kgha"] = np.where(
        seed_share.notna() & yield_kgha.notna(),
        yield_kgha * seed_share / 100.0,
        np.nan,
    )

    out["Total_pesticides_kgha"] = (
        pd.to_numeric(out.get("Insecticide_kgha", 0.0), errors="coerce").fillna(0.0)
        + pd.to_numeric(out.get("Herbicide_kgha", 0.0), errors="coerce").fillna(0.0)
        + pd.to_numeric(out.get("Fungicide_kgha", 0.0), errors="coerce").fillna(0.0)
        + pd.to_numeric(out.get("Acaricide_kgha", 0.0), errors="coerce").fillna(0.0)
        + pd.to_numeric(out.get("Biocide_NE_kgha", 0.0), errors="coerce").fillna(0.0)
    )

    out["Irrig_m3_class"] = np.where(pd.to_numeric(out.get("Irrig_m3", 0.0), errors="coerce").fillna(0.0) > 0, "Irrig_m3 <> 0", "Irrig_m3 = 0")

    a = pd.to_numeric(out.get("Area_ha", np.nan), errors="coerce")
    out["Farm_size_class"] = np.select(
        [a <= 1, a <= 10, a <= 100, a > 100],
        ["<= 1 ha", "<= 10 ha", "<= 100 ha", "> 100 ha"],
        default="(unknown)",
    )

    out["Crop_group"] = out.apply(
        lambda r: infer_crop_group_row(
            r.get("Crop", ""),
            r.get("Category", ""),
            r.get("Packaging_type2", ""),
        ),
        axis=1,
    )
    _unknown_crops = find_unmapped_crops(out.get("Crop", pd.Series("", index=out.index)))
    if _unknown_crops:
        raise ValueError(
            "Unmapped crops found in curated crop groups. Please define a group for: "
            + ", ".join(_unknown_crops)
        )
    pasture_mask = out.get("Category", pd.Series("", index=out.index)).astype(str).eq("cultivated_pasture")
    out.loc[pasture_mask, "Crop_group"] = "forages_pastures"

    out["Cropping_system"] = out.get("nuevacondicion", pd.Series("", index=out.index)).map(infer_cropping_system_from_condition)

    return out


def aggregate_crop_lci(base_df: pd.DataFrame, summary_level: str = "province") -> pd.DataFrame:
    base_raw = base_df.copy()
    if "Yield_kgha" in base_raw.columns:
        base_raw["Yield_kgha"] = pd.to_numeric(base_raw["Yield_kgha"], errors="coerce").where(lambda y: y > 0)

    base_df = apply_fao_yield_outlier_cap(base_raw, yield_col="Yield_kgha", factor=YIELD_FAO_EXCLUSION_FACTOR)
    base_df = _add_row_level_derived_lci_inputs(base_df)

    numeric_cols = [
        "Cycle_length_months",
        "Area_ha",
        "Irrigated_area_ha",
        "Yield_kgha",
        "Irrig_m3",
        "Irrig_lake_m3",
        "Irrig_river_m3",
        "Irrig_well_m3",
        "Fuel_ha",
        "Electricity_kWh_ha",
        "NPK_kgha",
        "AN_kgha",
        "AS_kgha",
        "AP_kgha",
        "Total_fert_min_kgha",
        "Manure_kgha",
        "Organic_estiercol_kgha",
        "Organic_fermentado_kgha",
        "Organic_liquido_kgha",
        "Total_fert_org_kgha",
        "Urea_kgha",
        "MAP_kgha",
        "UAN_kgha",
        "CAN_kgha",
        "Compost_kg_ha",
        "Digestate_kg_ha",
        "Insecticide_kgha",
        "Herbicide_kgha",
        "Fungicide_kgha",
        "Acaricide_kgha",
        "Biocide_NE_kgha",
        "Total_pesticides_kgha",
        "Seed_share_pct",
        "Seed_kgha",
    ]
    text_cols = [
        "Source_module",
        "Output_basis",
        "Yield_data_status",
        "Yield_basis_note",
        "Seeding_date",
        "Harvest_date",
        "Irrigation_source",
        "Irrig_equipment",
        "Packaging_type1",
        "Packaging_type2",
        "Manure_type",
        "Fuel_type",
        "Fuel_unit",
    ]

    group_keys = get_summary_group_keys(summary_level)

    # Strategy 8 (crop_group_national): combine permanent/transitory within each crop group.
    if str(summary_level).strip().lower() == "crop_group_national" and "Crop_group" in base_df.columns and "Category" in base_df.columns:
        base_df["Category"] = base_df["Crop_group"].fillna("").astype(str)

    if "Region" not in group_keys:
        base_df["Region"] = "(all regions confounded)"
    if "Province" not in group_keys:
        base_df["Province"] = "(all provinces confounded)"
    if "Crop" not in group_keys:
        base_df["Crop"] = "(all crops in group)"

    grouped = (
        base_df.groupby(group_keys, as_index=False)
        .agg(
            count=("Crop", "size"),
            **{c: (c, "median") for c in numeric_cols},
            **{c: (c, mode_non_null) for c in text_cols},
        )
        .sort_values(group_keys)
        .reset_index(drop=True)
    )

    if "Yield_kgha" in grouped.columns:
        grouped["Yield_kgha"] = pd.to_numeric(grouped["Yield_kgha"], errors="coerce").where(lambda y: y > 0)

        # Fallback chain so every group has yield stats: clean regional/crop medians, then raw medians.
        k_rc = [k for k in ["Region", "Crop", "Category"] if k in grouped.columns]
        k_cc = [k for k in ["Crop", "Category"] if k in grouped.columns]
        excluded_categories = set(
            base_df.loc[
                pd.to_numeric(base_df.get("Exclude_from_yield_fallback", False), errors="coerce").fillna(0).astype(bool),
                "Category",
            ].astype(str)
        )

        fb_cols = []
        fallback_base_df = base_df.copy()
        fallback_raw_df = base_raw.copy()
        if excluded_categories:
            fallback_base_df = fallback_base_df[~fallback_base_df["Category"].astype(str).isin(excluded_categories)].copy()
            fallback_raw_df = fallback_raw_df[~fallback_raw_df["Category"].astype(str).isin(excluded_categories)].copy()

        if k_rc:
            fb_clean_rc = (
                fallback_base_df.dropna(subset=["Yield_kgha"])
                .groupby(k_rc, as_index=False)["Yield_kgha"]
                .median()
                .rename(columns={"Yield_kgha": "Yield_kgha__fb_clean_rc"})
            )
            grouped = grouped.merge(fb_clean_rc, on=k_rc, how="left")
            fb_cols.append("Yield_kgha__fb_clean_rc")

        if k_cc:
            fb_clean_cc = (
                fallback_base_df.dropna(subset=["Yield_kgha"])
                .groupby(k_cc, as_index=False)["Yield_kgha"]
                .median()
                .rename(columns={"Yield_kgha": "Yield_kgha__fb_clean_cc"})
            )
            grouped = grouped.merge(fb_clean_cc, on=k_cc, how="left")
            fb_cols.append("Yield_kgha__fb_clean_cc")

            fb_raw_cc = (
                fallback_raw_df.dropna(subset=["Yield_kgha"])
                .groupby(k_cc, as_index=False)["Yield_kgha"]
                .median()
                .rename(columns={"Yield_kgha": "Yield_kgha__fb_raw_cc"})
            )
            grouped = grouped.merge(fb_raw_cc, on=k_cc, how="left")
            fb_cols.append("Yield_kgha__fb_raw_cc")

        y = grouped["Yield_kgha"]
        can_fill_mask = ~grouped.get("Category", pd.Series("", index=grouped.index)).astype(str).isin(excluded_categories)
        for c in fb_cols:
            y = y.where(~(can_fill_mask & y.isna()), y.fillna(grouped[c]))
        # Last-resort fallback to global positive median from raw data.
        global_yield = pd.to_numeric(fallback_raw_df.get("Yield_kgha", pd.Series(dtype=float)), errors="coerce").median()
        y = y.where(~(can_fill_mask & y.isna()), y.fillna(global_yield))
        grouped["Yield_kgha"] = y
        grouped = grouped.drop(columns=fb_cols, errors="ignore")

    if "Region" not in group_keys:
        grouped["Region"] = "(all regions confounded)"
    if "Province" not in group_keys:
        grouped["Province"] = "(all provinces confounded)"
    if "Crop" not in group_keys:
        grouped["Crop"] = "(all crops in group)"

    grouped = interpolate_dates_from_existing(grouped)
    return grouped



def _add_row_level_derived_uncertainty_inputs(base_df: pd.DataFrame, grouped_df: pd.DataFrame) -> pd.DataFrame:
    out = _add_row_level_derived_lci_inputs(base_df)

    crop_key = out.get("Crop", pd.Series("", index=out.index)).astype(str).map(_normalize_proxy_crop_name)
    proxy_category = crop_key.map(FUEL_PROXY_CATEGORY_BY_CROP).astype(str).str.lower()
    proxy_factor = proxy_category.map(FUEL_PROXY_EC_CAL_BY_CATEGORY).fillna(FUEL_PROXY_EC_CAL_DEFAULT)
    if not FUEL_PROXY_EC_CAL_ENABLED:
        proxy_factor = pd.Series(1.0, index=out.index)

    out["Fuel_ha__proxy_min"] = crop_key.map(FUEL_PROXY_MIN_BY_CROP) * proxy_factor
    out["Fuel_ha__proxy_max"] = crop_key.map(FUEL_PROXY_MAX_BY_CROP) * proxy_factor

    # For uncertainty aggregation, missing organic-input entries are treated as no-application (0).
    organic_unc_cols = [
        "Manure_kgha",
        "Compost_kg_ha",
        "Digestate_kg_ha",
        "Total_fert_org_kgha",
        "Organic_estiercol_kgha",
        "Organic_fermentado_kgha",
        "Organic_liquido_kgha",
    ]
    for col in organic_unc_cols:
        if col in grouped_df.columns and col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    # For uncertainty aggregation, missing AN entries are treated as no-application (0) instead of dropped NaN.
    if "AN_kgha" in grouped_df.columns and "AN_kgha" in out.columns:
        out["AN_kgha"] = pd.to_numeric(out["AN_kgha"], errors="coerce").fillna(0.0)

    if "Total_pesticides_kgha" in grouped_df.columns:
        comps = [
            pd.to_numeric(out.get("Insecticide_kgha", 0.0), errors="coerce").fillna(0.0),
            pd.to_numeric(out.get("Herbicide_kgha", 0.0), errors="coerce").fillna(0.0),
            pd.to_numeric(out.get("Fungicide_kgha", 0.0), errors="coerce").fillna(0.0),
            pd.to_numeric(out.get("Acaricide_kgha", 0.0), errors="coerce").fillna(0.0),
            pd.to_numeric(out.get("Biocide_NE_kgha", 0.0), errors="coerce").fillna(0.0),
        ]
        out["Total_pesticides_kgha"] = comps[0] + comps[1] + comps[2] + comps[3] + comps[4]

    return out


def build_grouped_uncertainty_table(base_df: pd.DataFrame, grouped_df: pd.DataFrame, summary_level: str = "province") -> pd.DataFrame:
    group_keys = get_summary_group_keys(summary_level)
    base_for_unc = _add_row_level_derived_uncertainty_inputs(base_df, grouped_df)
    # Keep uncertainty grouping aligned with grouped output for strategy 8 fruits.
    if str(summary_level).strip().lower() == "crop_group_national" and "Crop_group" in base_for_unc.columns and "Category" in base_for_unc.columns:
        base_for_unc["Category"] = base_for_unc["Crop_group"].fillna("").astype(str)
    if "Region" not in group_keys:
        base_for_unc["Region"] = "(all regions confounded)"
    if "Province" not in group_keys:
        base_for_unc["Province"] = "(all provinces confounded)"
    if "Crop" not in group_keys:
        base_for_unc["Crop"] = "(all crops in group)"
    base_for_unc = apply_fao_yield_outlier_cap(base_for_unc, yield_col="Yield_kgha", factor=YIELD_FAO_EXCLUSION_FACTOR)
    base_numeric_cols = [
        c for c in grouped_df.columns
        if c in base_for_unc.columns
        and pd.api.types.is_numeric_dtype(grouped_df[c])
        and not str(c).endswith(("__minValue", "__maxValue"))
    ]

    if base_numeric_cols:
        agg_spec = {}
        for c in base_numeric_cols:
            agg_spec[f"{c}__minValue"] = (c, "min")
            agg_spec[f"{c}__maxValue"] = (c, "max")
        unc = base_for_unc.groupby(group_keys, as_index=False).agg(**agg_spec)
    else:
        unc = grouped_df[group_keys].copy()

    # For Fuel_ha, prefer literature proxy uncertainty bounds when available.
    if {"Fuel_ha__proxy_min", "Fuel_ha__proxy_max"}.issubset(base_for_unc.columns):
        fuel_proxy_bounds = (
            base_for_unc.groupby(group_keys, as_index=False)
            .agg(
                Fuel_ha__proxy_min=("Fuel_ha__proxy_min", "median"),
                Fuel_ha__proxy_max=("Fuel_ha__proxy_max", "median"),
            )
        )
        unc = unc.merge(fuel_proxy_bounds, on=group_keys, how="left")
        if "Fuel_ha__minValue" in unc.columns:
            unc["Fuel_ha__minValue"] = unc["Fuel_ha__proxy_min"].where(unc["Fuel_ha__proxy_min"].notna(), unc["Fuel_ha__minValue"])
        if "Fuel_ha__maxValue" in unc.columns:
            unc["Fuel_ha__maxValue"] = unc["Fuel_ha__proxy_max"].where(unc["Fuel_ha__proxy_max"].notna(), unc["Fuel_ha__maxValue"])
        unc = unc.drop(columns=["Fuel_ha__proxy_min", "Fuel_ha__proxy_max"], errors="ignore")

    # For yield max, if raw max exceeds FAO max, pick the largest reported yield <= FAO max.
    if "Yield_kgha" in base_for_unc.columns and "Yield_kgha__maxValue" in unc.columns:
        ysrc_cols = list(dict.fromkeys(group_keys + ["Crop", "Yield_kgha"]))
        ysrc = base_for_unc[ysrc_cols].copy()
        y = pd.to_numeric(ysrc["Yield_kgha"], errors="coerce")
        thr = ysrc["Crop"].astype(str).map(lambda c: fao_yield_threshold_for_crop(c)[1])
        ysrc["Yield_kgha__max_leq_fao"] = y.where((y > 0) & (y <= thr))
        ymax = ysrc.groupby(group_keys, as_index=False)["Yield_kgha__max_leq_fao"].max()
        unc = unc.merge(ymax, on=group_keys, how="left")
        unc["Yield_kgha__maxValue"] = unc["Yield_kgha__max_leq_fao"].where(
            unc["Yield_kgha__max_leq_fao"].notna(),
            unc["Yield_kgha__maxValue"],
        )
        unc = unc.drop(columns=["Yield_kgha__max_leq_fao"], errors="ignore")

    if {"Yield_kgha__proxy_min", "Yield_kgha__proxy_max"}.issubset(base_for_unc.columns):
        yield_proxy_bounds = (
            base_for_unc.groupby(group_keys, as_index=False)
            .agg(
                Yield_kgha__proxy_min=("Yield_kgha__proxy_min", "median"),
                Yield_kgha__proxy_max=("Yield_kgha__proxy_max", "median"),
            )
        )
        unc = unc.merge(yield_proxy_bounds, on=group_keys, how="left")
        if "Yield_kgha__minValue" in unc.columns:
            unc["Yield_kgha__minValue"] = unc["Yield_kgha__proxy_min"].where(unc["Yield_kgha__proxy_min"].notna(), unc["Yield_kgha__minValue"])
        if "Yield_kgha__maxValue" in unc.columns:
            unc["Yield_kgha__maxValue"] = unc["Yield_kgha__proxy_max"].where(unc["Yield_kgha__proxy_max"].notna(), unc["Yield_kgha__maxValue"])
        unc = unc.drop(columns=["Yield_kgha__proxy_min", "Yield_kgha__proxy_max"], errors="ignore")

    if "Province" not in group_keys:
        unc["Province"] = "(all provinces confounded)"
    if "Crop" not in group_keys:
        unc["Crop"] = "(all crops in group)"

    # Ensure every numeric grouped column has min/max bounds; fall back to median value when no base-level raw column exists.
    merged = grouped_df.merge(unc, on=group_keys, how="left")
    numeric_cols = [
        c for c in grouped_df.columns
        if pd.api.types.is_numeric_dtype(grouped_df[c]) and not str(c).endswith(("__minValue", "__maxValue"))
    ]
    bounds = {}
    sample_count = pd.to_numeric(merged.get("count", np.nan), errors="coerce")
    for c in numeric_cols:
        cmin = f"{c}__minValue"
        cmax = f"{c}__maxValue"
        mid = pd.to_numeric(merged[c], errors="coerce")
        lo_src = merged[cmin] if cmin in merged.columns else pd.Series(np.nan, index=merged.index)
        hi_src = merged[cmax] if cmax in merged.columns else pd.Series(np.nan, index=merged.index)
        lo = pd.to_numeric(lo_src, errors="coerce").fillna(mid)
        hi = pd.to_numeric(hi_src, errors="coerce").fillna(mid)
        lo = np.minimum(np.minimum(lo, hi), mid)
        hi = np.maximum(np.maximum(lo, hi), mid)

        # If the crop aggregate has more than one observation, enforce a non-point uncertainty interval.
        multi_obs = sample_count > 1
        point_bounds = (lo == hi)
        force_spread = multi_obs & point_bounds & mid.notna()
        span = np.maximum(np.abs(mid) * 0.01, 1e-12)
        lo = np.where(force_spread & (mid != 0), np.maximum(0.0, mid - span), lo)
        hi = np.where(force_spread & (mid != 0), mid + span, hi)
        lo = np.where(force_spread & (mid == 0), 0.0, lo)
        hi = np.where(force_spread & (mid == 0), 1e-12, hi)

        bounds[cmin] = lo
        bounds[cmax] = hi

    if bounds:
        bounds_df = pd.DataFrame(bounds, index=merged.index)
        merged = pd.concat([merged.drop(columns=[c for c in bounds_df.columns if c in merged.columns]), bounds_df], axis=1)

    keep_cols = [c for c in group_keys if c in merged.columns] + [
        c for c in merged.columns
        if (c.endswith("__minValue") and c.count("__minValue") == 1)
        or (c.endswith("__maxValue") and c.count("__maxValue") == 1)
    ]
    return merged[keep_cols].copy()



def build_template_uncertainty_table(
    grouped_unc_df: pd.DataFrame,
    table_df: pd.DataFrame,
    key_cols=("Region", "Province", "Crop", "Category"),
) -> pd.DataFrame:
    out = table_df[[c for c in key_cols if c in table_df.columns]].copy()
    merged = out.merge(grouped_unc_df, on=[c for c in key_cols if c in out.columns], how="left")

    bounds = {}
    sample_count = pd.to_numeric(table_df.get("count", np.nan), errors="coerce")
    for c in table_df.columns:
        if c in key_cols:
            continue
        if str(c).endswith(("__minValue", "__maxValue")):
            continue
        cmin = f"{c}__minValue"
        cmax = f"{c}__maxValue"

        col_vals = pd.to_numeric(table_df[c], errors="coerce") if c in table_df.columns else pd.Series(np.nan, index=table_df.index)
        lo_src = merged[cmin] if cmin in merged.columns else pd.Series(np.nan, index=merged.index)
        hi_src = merged[cmax] if cmax in merged.columns else pd.Series(np.nan, index=merged.index)
        lo = pd.to_numeric(lo_src, errors="coerce").fillna(col_vals)
        hi = pd.to_numeric(hi_src, errors="coerce").fillna(col_vals)
        mid = col_vals
        lo = np.minimum(np.minimum(lo, hi), mid)
        hi = np.maximum(np.maximum(lo, hi), mid)

        multi_obs = sample_count > 1
        point_bounds = (lo == hi)
        force_spread = multi_obs & point_bounds & mid.notna()
        span = np.maximum(np.abs(mid) * 0.01, 1e-12)
        lo = np.where(force_spread & (mid != 0), np.maximum(0.0, mid - span), lo)
        hi = np.where(force_spread & (mid != 0), mid + span, hi)
        lo = np.where(force_spread & (mid == 0), 0.0, lo)
        hi = np.where(force_spread & (mid == 0), 1e-12, hi)

        bounds[cmin] = lo
        bounds[cmax] = hi

    if bounds:
        bounds_df = pd.DataFrame(bounds, index=merged.index)
        merged = pd.concat([merged.drop(columns=[c for c in bounds_df.columns if c in merged.columns]), bounds_df], axis=1)

    keep_cols = [
        c for c in merged.columns
        if c in key_cols
        or (c.endswith("__minValue") and c.count("__minValue") == 1)
        or (c.endswith("__maxValue") and c.count("__maxValue") == 1)
    ]
    return merged[keep_cols].copy()



def format_numeric_for_display(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").map(lambda x: f"{x:,.2f}" if pd.notna(x) else "")
    return out


def display_scrollable_table(df: pd.DataFrame, max_height: str = "360px", index: bool = False):
    if not isinstance(df, pd.DataFrame):
        display(df)
        return
    html = df.to_html(index=index, escape=False)
    display(HTML(f'<div style="max-height:{max_height}; overflow:auto; border:1px solid #ddd;">{html}</div>'))


def format_rounded_int_or_blank(series: pd.Series) -> pd.Series:
    vals = pd.to_numeric(series, errors="coerce")
    return vals.map(lambda x: "" if pd.isna(x) else str(int(round(float(x)))))


def build_template_shaped_lci_table(
    grouped_df: pd.DataFrame,
    template_cols: List[str],
    drop_unresolved_template_cols: bool = False,
) -> (pd.DataFrame, List[str]):
    target_cols = template_cols if template_cols else grouped_df.columns.tolist()
    unresolved_template_cols = [c for c in target_cols if c not in grouped_df.columns] if template_cols else []

    out = grouped_df.reindex(columns=target_cols).copy()

    extra_cols = [
        c for c in [
            "Organic_estiercol_kgha", "Organic_fermentado_kgha", "Organic_liquido_kgha",
            "Irrig_lake_m3", "Irrig_river_m3", "Irrig_well_m3",
            "Cropping_system", "Irrig_m3_class", "Farm_size_class", "Crop_group",
            "Irrigation_source", "Source_module", "Output_basis", "Yield_data_status", "Yield_basis_note",
        ]
        if c in grouped_df.columns and c not in out.columns
    ]
    if extra_cols:
        out = pd.concat([out, grouped_df[extra_cols]], axis=1)

    if drop_unresolved_template_cols and unresolved_template_cols:
        out = out.drop(columns=[c for c in unresolved_template_cols if c in out.columns])

    return out, unresolved_template_cols


with sqlite3.connect(DB_PATH) as conn:
    crop_lci_base_df, unit_audit_df, coverage_diag_df = build_crop_lci_base(conn)

DEFAULT_SUMMARY_LEVEL = "province"
DEFAULT_SUMMARY_TOKEN = summary_strategy_token(DEFAULT_SUMMARY_LEVEL)

crop_lci_grouped_df = aggregate_crop_lci(crop_lci_base_df, summary_level=DEFAULT_SUMMARY_LEVEL)
crop_lci_grouped_uncertainty_df = build_grouped_uncertainty_table(
    crop_lci_base_df,
    crop_lci_grouped_df,
    summary_level=DEFAULT_SUMMARY_LEVEL,
)

try:
    template_cols = pd.read_excel(PROJECT_DIR / "inputs/02_LCI_template.xlsx", sheet_name="MARIGO_LCA_all", nrows=0).columns.tolist()
except Exception:
    template_cols = []

crop_lci_template_df, unresolved_template_cols = build_template_shaped_lci_table(
    crop_lci_grouped_df,
    template_cols,
    drop_unresolved_template_cols=False,
)

export_path = CSVS_DIR / f"02_espac_crop_lci_table__summary_{DEFAULT_SUMMARY_TOKEN}.csv"
crop_lci_template_df.to_csv(export_path, index=False, encoding="utf-8-sig")

unc_export_path = CSVS_DIR / f"02_espac_crop_lci_table__summary_{DEFAULT_SUMMARY_TOKEN}_uncertainty.csv"
crop_lci_template_uncertainty_df = build_template_uncertainty_table(
    crop_lci_grouped_uncertainty_df,
    crop_lci_template_df,
)
crop_lci_template_uncertainty_df.to_csv(unc_export_path, index=False, encoding="utf-8-sig")

print(f"Rows in base crop dataset: {len(crop_lci_base_df):,}")
print(f"Rows in grouped crop-LCI table: {len(crop_lci_grouped_df):,}")
print(f"Template-shaped table saved to: {export_path}")
print(f"Template-shaped uncertainty table saved to: {unc_export_path}")
if unresolved_template_cols:
    print(f"Unresolved LCI_template columns retained in full export: {len(unresolved_template_cols)}")


region_filter = widgets.Dropdown(
    options=["All"] + sorted(crop_lci_base_df["Region"].dropna().unique().tolist()),
    value="All",
    description="Region:",
    layout=widgets.Layout(width="230px"),
)
category_filter = widgets.Dropdown(
    options=["All"] + sorted(crop_lci_base_df["Category"].dropna().unique().tolist()),
    value="All",
    description="Category:",
    layout=widgets.Layout(width="250px"),
)
summary_level_filter = widgets.Dropdown(
    options=SUMMARY_LEVEL_OPTIONS,
    value=DEFAULT_SUMMARY_LEVEL,
    description="Summary:",
    layout=widgets.Layout(width="360px"),
)
province_filter = widgets.SelectMultiple(
    options=tuple(sorted(crop_lci_base_df["Province"].dropna().astype(str).unique().tolist())),
    value=tuple(),
    description="Provinces:",
    rows=8,
    layout=widgets.Layout(width="360px"),
)
crop_filter = widgets.Dropdown(options=["All"], value="All", description="Crop:", layout=widgets.Layout(width="620px"))
rows_filter = widgets.IntSlider(value=30, min=10, max=300, step=10, description="Top rows:", continuous_update=False)
summary_out = widgets.Output()
unit_out = widgets.Output()
coverage_out = widgets.Output()
export_out = widgets.Output()
export_btn = widgets.Button(description="Export filtered CSV", button_style="success", icon="download")
strategy_banner = widgets.HTML()


_callbacks_locked = False
OTROS_CROP_LABELS = {"OTROS PERMANENTES", "OTROS TRANSITORIOS"}
otros_crop_filter = widgets.Dropdown(
    options=["All"],
    value="All",
    description="Sub-crop:",
    layout=widgets.Layout(width="620px", display="none"),
)


def _resolve_first_existing_table(conn: sqlite3.Connection, candidates: list[str]) -> str | None:
    names = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)["name"].astype(str).tolist()
    names_set = set(names)
    for c in candidates:
        if c in names_set:
            return c
    return None


def _list_otros_subcrops(crop_label: str) -> list[str]:
    crop_label = str(crop_label).strip().upper()
    if crop_label not in OTROS_CROP_LABELS:
        return []

    with sqlite3.connect(DB_PATH) as conn:
        enc_tbl = _resolve_first_existing_table(conn, ["encuestas"])
        if enc_tbl is None:
            return []

        if crop_label == "OTROS PERMANENTES":
            src_tbl = _resolve_first_existing_table(conn, ["rel_inec_cpnac", "inec_cpnac"])
            crop_col = "cp_nclavr"
            detail_candidates = ["rc_clacul"]
        else:
            src_tbl = _resolve_first_existing_table(conn, ["rel_inec_ctnac", "inec_ctnac"])
            crop_col = "ct_nclavr"
            detail_candidates = ["ct_codcultiv1_int", "rc_clacul", "ct_codcultiv2_int"]

        if src_tbl is None:
            return []

        src_cols = pd.read_sql_query(f"PRAGMA table_info('{src_tbl}')", conn)["name"].astype(str).tolist()
        detail_col = next((c for c in detail_candidates if c in src_cols), None)
        if detail_col is None:
            return []

        q = f"""
            SELECT
                CAST(s.identificador AS TEXT) AS identificador,
                e.provincia AS provincia,
                TRIM(COALESCE(NULLIF(s.{detail_col}, ''), NULLIF(s.{crop_col}, ''))) AS subcrop
            FROM "{src_tbl}" s
            JOIN "{enc_tbl}" e
              ON CAST(e.identificador AS TEXT) = CAST(s.identificador AS TEXT)
            WHERE UPPER(TRIM(COALESCE(s.{crop_col}, ''))) = ?
        """
        raw = pd.read_sql_query(q, conn, params=[crop_label])

    if raw.empty:
        return []

    raw["provincia"] = raw["provincia"].astype(str)
    raw["Region"] = raw["provincia"].map(map_provincia_to_region)

    if region_filter.value != "All":
        raw = raw[raw["Region"] == region_filter.value]
    if province_filter.value:
        raw = raw[raw["provincia"].isin(list(province_filter.value))]

    sub = raw["subcrop"].astype(str).str.strip()
    sub = sub[(sub != "") & (sub.str.upper() != crop_label)]

    top_level_crops = {
        str(c).strip().upper()
        for c in crop_filter.options
        if str(c).strip() and str(c).strip().upper() != "ALL"
    }
    sub = sub[~sub.str.upper().isin(top_level_crops)]

    return sorted(sub.unique().tolist())


def _identifiers_for_otros_subcrop(crop_label: str, subcrop: str) -> set[str]:
    crop_label = str(crop_label).strip().upper()
    subcrop = str(subcrop).strip()
    if crop_label not in OTROS_CROP_LABELS or not subcrop or subcrop == "All":
        return set()

    with sqlite3.connect(DB_PATH) as conn:
        enc_tbl = _resolve_first_existing_table(conn, ["encuestas"])
        if enc_tbl is None:
            return set()

        if crop_label == "OTROS PERMANENTES":
            src_tbl = _resolve_first_existing_table(conn, ["rel_inec_cpnac", "inec_cpnac"])
            crop_col = "cp_nclavr"
            detail_candidates = ["rc_clacul"]
        else:
            src_tbl = _resolve_first_existing_table(conn, ["rel_inec_ctnac", "inec_ctnac"])
            crop_col = "ct_nclavr"
            detail_candidates = ["ct_codcultiv1_int", "rc_clacul", "ct_codcultiv2_int"]

        if src_tbl is None:
            return set()

        src_cols = pd.read_sql_query(f"PRAGMA table_info('{src_tbl}')", conn)["name"].astype(str).tolist()
        detail_col = next((c for c in detail_candidates if c in src_cols), None)
        if detail_col is None:
            return set()

        q = f"""
            SELECT
                CAST(s.identificador AS TEXT) AS identificador,
                e.provincia AS provincia,
                TRIM(COALESCE(NULLIF(s.{detail_col}, ''), NULLIF(s.{crop_col}, ''))) AS subcrop
            FROM "{src_tbl}" s
            JOIN "{enc_tbl}" e
              ON CAST(e.identificador AS TEXT) = CAST(s.identificador AS TEXT)
            WHERE UPPER(TRIM(COALESCE(s.{crop_col}, ''))) = ?
        """
        raw = pd.read_sql_query(q, conn, params=[crop_label])

    if raw.empty:
        return set()

    raw["provincia"] = raw["provincia"].astype(str)
    raw["Region"] = raw["provincia"].map(map_provincia_to_region)

    if region_filter.value != "All":
        raw = raw[raw["Region"] == region_filter.value]
    if province_filter.value:
        raw = raw[raw["provincia"].isin(list(province_filter.value))]

    mask = raw["subcrop"].astype(str).str.strip().str.upper() == subcrop.upper()
    return set(raw.loc[mask, "identificador"].astype(str).str.strip().tolist())


def _identifiers_by_otros_subcrop(crop_label: str) -> dict[str, set[str]]:
    crop_label = str(crop_label).strip().upper()
    if crop_label not in OTROS_CROP_LABELS:
        return {}

    with sqlite3.connect(DB_PATH) as conn:
        enc_tbl = _resolve_first_existing_table(conn, ["encuestas"])
        if enc_tbl is None:
            return {}

        if crop_label == "OTROS PERMANENTES":
            src_tbl = _resolve_first_existing_table(conn, ["rel_inec_cpnac", "inec_cpnac"])
            crop_col = "cp_nclavr"
            detail_candidates = ["rc_clacul"]
        else:
            src_tbl = _resolve_first_existing_table(conn, ["rel_inec_ctnac", "inec_ctnac"])
            crop_col = "ct_nclavr"
            detail_candidates = ["ct_codcultiv1_int", "rc_clacul", "ct_codcultiv2_int"]

        if src_tbl is None:
            return {}

        src_cols = pd.read_sql_query(f"PRAGMA table_info('{src_tbl}')", conn)["name"].astype(str).tolist()
        detail_col = next((c for c in detail_candidates if c in src_cols), None)
        if detail_col is None:
            return {}

        q = f"""
            SELECT
                CAST(s.identificador AS TEXT) AS identificador,
                e.provincia AS provincia,
                TRIM(COALESCE(NULLIF(s.{detail_col}, ''), NULLIF(s.{crop_col}, ''))) AS subcrop
            FROM "{src_tbl}" s
            JOIN "{enc_tbl}" e
              ON CAST(e.identificador AS TEXT) = CAST(s.identificador AS TEXT)
            WHERE UPPER(TRIM(COALESCE(s.{crop_col}, ''))) = ?
        """
        raw = pd.read_sql_query(q, conn, params=[crop_label])

    if raw.empty:
        return {}

    raw["provincia"] = raw["provincia"].astype(str)
    raw["Region"] = raw["provincia"].map(map_provincia_to_region)

    if region_filter.value != "All":
        raw = raw[raw["Region"] == region_filter.value]
    if province_filter.value:
        raw = raw[raw["provincia"].isin(list(province_filter.value))]

    raw["subcrop"] = raw["subcrop"].astype(str).str.strip()
    raw["identificador"] = raw["identificador"].astype(str).str.strip()
    raw = raw[(raw["subcrop"] != "") & (raw["subcrop"].str.upper() != crop_label)]
    if raw.empty:
        return {}

    top_level_crops = {
        str(c).strip().upper()
        for c in crop_filter.options
        if str(c).strip() and str(c).strip().upper() != "ALL"
    }
    raw = raw[~raw["subcrop"].str.upper().isin(top_level_crops)]
    if raw.empty:
        return {}

    out = {
        str(name): set(g["identificador"].tolist())
        for name, g in raw.groupby("subcrop", sort=True)
    }
    return out


def get_filtered_base_df() -> pd.DataFrame:
    df = crop_lci_base_df.copy()
    if region_filter.value != "All":
        df = df[df["Region"] == region_filter.value]
    if category_filter.value != "All":
        df = df[df["Category"] == category_filter.value]
    if province_filter.value:
        df = df[df["Province"].isin(list(province_filter.value))]
    return df


def get_filtered_grouped_df() -> pd.DataFrame:
    df = get_filtered_base_df()
    if crop_filter.value != "All":
        df = df[df["Crop"] == crop_filter.value]

    crop_label = str(crop_filter.value).strip().upper()
    subcrop = str(otros_crop_filter.value).strip()

    if crop_label in OTROS_CROP_LABELS and subcrop == "All":
        overall_grouped = aggregate_crop_lci(df, summary_level=summary_level_filter.value)
        per_subcrop_grouped = []
        ids_series = df["identificador"].astype(str).str.strip() if "identificador" in df.columns else pd.Series([], dtype=str)
        ids_by_sub = _identifiers_by_otros_subcrop(crop_label)

        for sub_name in sorted(ids_by_sub.keys()):
            ids = ids_by_sub.get(sub_name, set())
            if not ids:
                continue
            sdf = df[ids_series.isin(ids)].copy()
            if sdf.empty:
                continue
            sdf["Crop"] = sub_name
            per_subcrop_grouped.append(aggregate_crop_lci(sdf, summary_level=summary_level_filter.value))

        grouped = pd.concat([overall_grouped] + per_subcrop_grouped, ignore_index=True) if per_subcrop_grouped else overall_grouped
    else:
        grouped = aggregate_crop_lci(df, summary_level=summary_level_filter.value)

    sort_keys = [k for k in get_summary_group_keys(summary_level_filter.value) if k in grouped.columns]
    return grouped.sort_values(sort_keys).reset_index(drop=True) if sort_keys else grouped.reset_index(drop=True)


def refresh_selection_options(*_):
    global _callbacks_locked
    _callbacks_locked = True
    try:
        df = crop_lci_base_df.copy()
        if region_filter.value != "All":
            df = df[df["Region"] == region_filter.value]
        if category_filter.value != "All":
            df = df[df["Category"] == category_filter.value]

        provinces = tuple(sorted(df["Province"].dropna().astype(str).unique().tolist()))
        current = tuple(v for v in province_filter.value if v in provinces)
        if tuple(province_filter.options) != provinces:
            province_filter.options = provinces
        if tuple(province_filter.value) != current:
            province_filter.value = current

        if province_filter.value:
            df = df[df["Province"].isin(list(province_filter.value))]

        crops = ["All"] + sorted(df["Crop"].dropna().astype(str).unique().tolist())
        curr = crop_filter.value if crop_filter.value in crops else "All"
        if tuple(crop_filter.options) != tuple(crops):
            crop_filter.options = crops
        if crop_filter.value != curr:
            crop_filter.value = curr
    finally:
        _callbacks_locked = False


_original_refresh_selection_options = refresh_selection_options
_original_get_filtered_base_df = get_filtered_base_df


def refresh_selection_options(*_):
    global _callbacks_locked
    _original_refresh_selection_options()

    _callbacks_locked = True
    try:
        crop_label = str(crop_filter.value).strip().upper()
        if crop_label in OTROS_CROP_LABELS:
            opts = ["All"] + _list_otros_subcrops(crop_label)
            current = otros_crop_filter.value if otros_crop_filter.value in opts else "All"
            if tuple(otros_crop_filter.options) != tuple(opts):
                otros_crop_filter.options = opts
            if otros_crop_filter.value != current:
                otros_crop_filter.value = current
            otros_crop_filter.layout.display = ""
        else:
            if tuple(otros_crop_filter.options) != ("All",):
                otros_crop_filter.options = ["All"]
            if otros_crop_filter.value != "All":
                otros_crop_filter.value = "All"
            otros_crop_filter.layout.display = "none"
    finally:
        _callbacks_locked = False


def get_filtered_base_df() -> pd.DataFrame:
    df = _original_get_filtered_base_df()

    crop_label = str(crop_filter.value).strip().upper()
    subcrop = str(otros_crop_filter.value).strip()
    if crop_label in OTROS_CROP_LABELS and subcrop and subcrop != "All":
        ids = _identifiers_for_otros_subcrop(crop_label, subcrop)
        if ids:
            ids_series = df["identificador"].astype(str).str.strip()
            df = df[(df["Crop"].astype(str).str.upper() == crop_label) & (ids_series.isin(ids))]
        else:
            df = df.iloc[0:0].copy()

    return df


def refresh_outputs(*_):
    if _callbacks_locked:
        return


def refresh_strategy_banner():
    token = summary_strategy_token(summary_level_filter.value)
    strategy_banner.value = (
        "<div style='padding:6px 10px; border:1px solid #d9d9d9; border-radius:6px; background:#f7f7f7;'>"
        f"<b>Current strategy to be propagated to notebooks 3/5:</b> <code>{token}</code>"
        "</div>"
    )


def on_selection_change(*_):
    if _callbacks_locked:
        return
    refresh_selection_options()
    refresh_strategy_banner()
    summary_out.clear_output()
    export_out.clear_output()
    with summary_out:
        display(Markdown("Adjust filters, then click **Export filtered CSV** to generate files and preview the exported table."))


def export_filtered_csv(_):
    export_run_id = new_run_id("02_crops")
    t0 = pd.Timestamp.now()
    def _stage(msg: str):
        elapsed = (pd.Timestamp.now() - t0).total_seconds()
        with export_out:
            display(Markdown(f"- {msg} (`{elapsed:.1f}s`)"))

    _stage("Stage 1/8: building grouped filtered dataset")
    df = get_filtered_grouped_df()
    _stage("Stage 2/8: shaping export table")
    filtered_export_df, unresolved_cols = build_template_shaped_lci_table(
        df,
        template_cols,
        drop_unresolved_template_cols=True,
    )
    dropped_unresolved = [c for c in unresolved_cols if c not in filtered_export_df.columns]

    # Always exclude selected columns from the filtered CSV export.
    excluded_tokens = ("Manure", "Acaricide", "Biocide")
    dropped_excluded_cols = [c for c in filtered_export_df.columns if any(tok in c for tok in excluded_tokens)]
    if dropped_excluded_cols:
        filtered_export_df = filtered_export_df.drop(columns=dropped_excluded_cols, errors="ignore")

    # Drop columns that are entirely empty in the filtered export (all NaN/None/blank strings).
    keep_cols = []
    dropped_empty_cols = []
    for c in filtered_export_df.columns:
        s = filtered_export_df[c]
        if pd.api.types.is_numeric_dtype(s):
            has_value = s.notna().any()
        else:
            s_obj = s.astype(object)
            has_value = s_obj.notna().any() and s_obj.map(lambda x: str(x).strip() != "" if pd.notna(x) else False).any()
        if has_value:
            keep_cols.append(c)
        else:
            dropped_empty_cols.append(c)
    filtered_export_df = filtered_export_df[keep_cols].copy()

    # Hard guard: never export non-positive yields.
    if "Yield_kgha" in filtered_export_df.columns:
        yexp = pd.to_numeric(filtered_export_df["Yield_kgha"], errors="coerce")
        filtered_export_df["Yield_kgha"] = yexp.where(yexp > 0)

    summary_token = summary_strategy_token(summary_level_filter.value)
    out_path = CSVS_DIR / f"02_espac_crop_lci_table_filtered__summary_{summary_token}.csv"
    _stage("Stage 3/8: writing main filtered CSV")
    filtered_export_df.to_csv(out_path, index=False, encoding="utf-8-sig")

    # Render exported table preview immediately after writing the CSV.
    summary_out.clear_output()
    with summary_out:
        display(Markdown("### Crop LCI table (exported view)"))
        preview_cols = filtered_export_df.columns.tolist()
        preview_numeric = [
            c for c in preview_cols
            if c not in {"count", "Region", "Province", "Cropping_system", "Irrig_m3_class", "Farm_size_class", "Crop_group", "Crop", "Category", "Seeding_date", "Harvest_date", "Irrigation_source", "Irrig_equipment", "Fuel_type", "Fuel_unit", "Packaging_type1", "Packaging_type2"}
        ]
        display_scrollable_table(format_numeric_for_display(filtered_export_df.head(rows_filter.value), preview_numeric))
        display(Markdown(f"Rows shown (same rules as exported CSV): **{len(filtered_export_df):,}**"))

    filtered_unc_path = CSVS_DIR / f"02_espac_crop_lci_table_filtered__summary_{summary_token}_uncertainty.csv"
    _stage("Stage 4/8: updating metadata")
    write_latest_filtered_summary_metadata(
        summary_level=summary_level_filter.value,
        summary_token=summary_token,
        filtered_csv_path=out_path,
        filtered_unc_path=filtered_unc_path,
        selected_crop=str(crop_filter.value),
        selected_subcrop=str(otros_crop_filter.value),
        run_id=export_run_id,
    )

    _stage("Stage 5/8: finalizing primary export status")
    with export_out:
        display(Markdown("**Primary export completed successfully.**"))
        display(Markdown(f"Saved **{len(filtered_export_df):,}** rows and **{len(filtered_export_df.columns):,}** columns to `{out_path}`"))
        display(Markdown(f"Updated latest-summary metadata: `{LATEST_FILTERED_SUMMARY_META_PATH}`"))
        if dropped_unresolved:
            display(Markdown(f"Dropped **{len(dropped_unresolved)}** unresolved columns inherited from `inputs/02_LCI_template.xlsx`."))
        if dropped_excluded_cols:
            display(Markdown(f"Dropped **{len(dropped_excluded_cols)}** excluded columns (`Manure*`, `Acaricide*`, `Biocide*`)."))
        if dropped_empty_cols:
            display(Markdown(f"Dropped **{len(dropped_empty_cols)}** all-empty columns from the filtered export."))

    try:
        _stage("Stage 6/8: preparing uncertainty input")
        filtered_base_df = get_filtered_base_df()
        if crop_filter.value != "All":
            filtered_base_df = filtered_base_df[filtered_base_df["Crop"] == crop_filter.value]

        filtered_unc_df = build_grouped_uncertainty_table(
            filtered_base_df,
            df,
            summary_level=summary_level_filter.value,
        )
        _stage("Stage 7/8: writing uncertainty CSV")
        filtered_key_cols = tuple(k for k in get_summary_group_keys(summary_level_filter.value) if k in filtered_export_df.columns and k in filtered_unc_df.columns)
        filtered_template_unc_df = build_template_uncertainty_table(filtered_unc_df, filtered_export_df, key_cols=filtered_key_cols if filtered_key_cols else ("Region", "Province", "Crop", "Category"))
        for yc in ["Yield_kgha__minValue", "Yield_kgha__maxValue"]:
            if yc in filtered_template_unc_df.columns:
                yb = pd.to_numeric(filtered_template_unc_df[yc], errors="coerce")
                filtered_template_unc_df[yc] = yb.where(yb > 0)
        filtered_template_unc_df.to_csv(filtered_unc_path, index=False, encoding="utf-8-sig")

        main_snapshot = make_snapshot_copy(out_path, export_run_id)
        unc_snapshot = make_snapshot_copy(filtered_unc_path, export_run_id)
        manifest_record = build_manifest_record(
            run_id=export_run_id,
            domain="crops",
            summary_token=summary_token,
            pipeline_stage="02",
            source_main_csv=main_snapshot,
            source_unc_csv=unc_snapshot,
            main_df=filtered_export_df,
            unc_df=filtered_template_unc_df,
            filters_meta={
                "summary_level": summary_level_filter.value,
                "selected_crop": str(crop_filter.value),
                "selected_subcrop": str(otros_crop_filter.value),
                "region": str(region_filter.value),
                "category": str(category_filter.value),
                "provinces": list(province_filter.value),
            },
            extra={"otros_expansion_source": "db"},
        )
        manifest_path = append_manifest_record(PROJECT_DIR, manifest_record)
        with export_out:
            display(Markdown(f"Uncertainty export completed: `{filtered_unc_path}`"))
            display(Markdown(f"Manifest updated: `{manifest_path}` (`run_id={export_run_id}`)"))
        _stage("Stage 8/8: done")
    except Exception as ex:
        with export_out:
            display(Markdown(f"Uncertainty export failed (main CSV already saved): `{ex}`"))
for w in [region_filter, category_filter, province_filter, summary_level_filter, crop_filter, rows_filter, otros_crop_filter]:
    try:
        w.unobserve_all(names="value")
    except Exception:
        pass
    w.observe(on_selection_change, names="value")

def on_export_click(_):
    export_out.clear_output()
    with export_out:
        display(Markdown("Export in progress..."))
    try:
        export_filtered_csv(_)
    except Exception as ex:
        export_out.clear_output()
        with export_out:
            display(Markdown(f"**Export failed:** `{ex}`"))
        return
    with export_out:
        display(Markdown("Export callback finalized."))

try:
    export_btn._click_handlers.callbacks.clear()
except Exception:
    pass
try:
    export_btn.on_click(on_export_click, remove=True)
except Exception:
    pass
export_btn.on_click(on_export_click)

clear_output(wait=True)
controls_top = widgets.HBox([region_filter, category_filter, summary_level_filter])
controls_mid = widgets.HBox([province_filter, widgets.VBox([crop_filter, otros_crop_filter])])
display(controls_top)
display(controls_mid)
display(rows_filter)
display(strategy_banner)
display(export_btn)
display(export_out)
display(summary_out)

refresh_strategy_banner()
with summary_out:
    display(Markdown("Adjust filters, then click **Export filtered CSV** to generate files and preview the exported table."))
