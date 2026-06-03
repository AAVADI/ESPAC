import pandas as pd
try:
    df = pd.read_excel("outputs/ESPAC LCIA.xlsx", sheet_name="diets")
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print("\nFirst 10 non-empty rows:")
    print(df.dropna(how='all').head(10).to_string())
    keywords = ["2022", "import", "national production", "domestic production", "consumption"]
    target_cols = [c for c in df.columns if any(k in str(c).lower() for k in keywords)]
    if target_cols: print(f"\nTarget Cols: {target_cols}")
    mask = df.apply(lambda r: any(any(k in str(v).lower() for k in keywords) for v in r if pd.notnull(v)), axis=1)
    target_rows = df[mask]
    if not target_rows.empty:
        print("\nTarget Rows:")
        print(target_rows.to_string())
except Exception as e:
    print(f"Error: {e}")
