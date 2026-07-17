import os
import pandas as pd

def load_dataframe(file_path: str) -> pd.DataFrame:
    if file_path.endswith(('.xlsx', '.xls')):
        return pd.read_excel(file_path)
    return pd.read_csv(file_path)

def format_dataframe(df: pd.DataFrame) -> str:
    if len(df) == 0:
        return "Empty DataFrame (0 rows)"
    headers = list(df.columns)
    lines = [f"| {' | '.join(str(h) for h in headers)} |"]
    lines.append(f"| {' | '.join('---' for _ in headers)} |")
    # limit to max 15 rows for preview
    for idx, row in df.head(15).iterrows():
        row_str = " | ".join(str(row[h]).replace('|', '\\|') for h in headers)
        lines.append(f"| {row_str} |")
    if len(df) > 15:
        lines.append(f"\n*... truncated {len(df) - 15} rows ...*")
    return "\n".join(lines)

def execute_pandas_query(file_path: str, plan: dict) -> str:
    try:
        df = load_dataframe(file_path)
    except Exception as e:
        return f"Failed to load spreadsheet: {str(e)}"

    op = plan.get("operation")
    if not op:
        return f"Invalid plan: no operation specified. Columns: {', '.join(df.columns)}"

    # Match columns case-insensitively for robustness
    col_map = {c.lower(): c for c in df.columns}
    
    def get_real_column(col_name: str) -> str:
        if not col_name:
            return None
        return col_map.get(str(col_name).lower(), col_name)

    try:
        if op == "list_columns":
            return f"Columns in dataset:\n" + "\n".join(f"- {c}" for c in df.columns)

        elif op == "row_count":
            return f"Total row count: {len(df)}"

        elif op == "column_count":
            return f"Total column count: {len(df.columns)}"

        elif op == "describe_column":
            raw_col = plan.get("column")
            target_col = get_real_column(raw_col)
            if not target_col or target_col not in df.columns:
                return f"Column '{raw_col}' not found in dataset. Available columns: {', '.join(df.columns)}"
            desc = df[target_col].describe().reset_index()
            return format_dataframe(desc)

        elif op == "null_count":
            nulls = df.isnull().sum().reset_index()
            nulls.columns = ["Column", "Null Count"]
            return format_dataframe(nulls)

        elif op == "unique_values":
            raw_col = plan.get("column")
            target_col = get_real_column(raw_col)
            if not target_col or target_col not in df.columns:
                return f"Column '{raw_col}' not found in dataset. Available columns: {', '.join(df.columns)}"
            uniques = pd.DataFrame({f"Unique values in {target_col}": df[target_col].unique()})
            return format_dataframe(uniques)

        elif op == "duplicate_count":
            dups = df.duplicated().sum()
            return f"Number of duplicate rows: {dups}"

        elif op == "value_counts":
            raw_col = plan.get("column")
            target_col = get_real_column(raw_col)
            if not target_col or target_col not in df.columns:
                return f"Column '{raw_col}' not found in dataset. Available columns: {', '.join(df.columns)}"
            counts = df[target_col].value_counts().reset_index()
            counts.columns = [target_col, "count"]
            return format_dataframe(counts)

        elif op == "correlation":
            numeric_df = df.select_dtypes(include=['number'])
            if len(numeric_df.columns) < 2:
                return "Not enough numeric columns in dataset to compute correlation matrix."
            corr = numeric_df.corr().reset_index()
            return format_dataframe(corr)

        elif op == "filter":
            filters = plan.get("filters", [])
            filtered_df = df.copy()
            for f in filters:
                raw_col = f.get("column")
                col = get_real_column(raw_col)
                opt = f.get("operator", "equals")
                val = f.get("value")
                
                if not col or col not in df.columns:
                    return f"Filter column '{raw_col}' not found in dataset. Available columns: {', '.join(df.columns)}"
                    
                if opt == "equals":
                    filtered_df = filtered_df[filtered_df[col].astype(str) == str(val)]
                elif opt == "contains":
                    filtered_df = filtered_df[filtered_df[col].astype(str).str.contains(str(val), case=False, na=False)]
                elif opt == "greater_than":
                    try:
                        filtered_df = filtered_df[pd.to_numeric(filtered_df[col], errors='coerce') > float(val)]
                    except Exception:
                        return f"Cannot perform greater_than check on non-numeric filter column '{raw_col}'"
                elif opt == "less_than":
                    try:
                        filtered_df = filtered_df[pd.to_numeric(filtered_df[col], errors='coerce') < float(val)]
                    except Exception:
                        return f"Cannot perform less_than check on non-numeric filter column '{raw_col}'"
                else:
                    return f"Unsupported filter operator '{opt}'. Choose from: equals, contains, greater_than, less_than."
            return format_dataframe(filtered_df)

        elif op == "groupby":
            raw_gb = plan.get("group_by")
            gb_col = get_real_column(raw_gb)
            agg_type = plan.get("aggregate", "sum")
            raw_target = plan.get("column")
            target_col = get_real_column(raw_target)
            
            if not gb_col or not target_col:
                return f"Groupby requires both 'group_by' and 'column' parameters. Provided group_by='{raw_gb}', column='{raw_target}'."
            if gb_col not in df.columns or target_col not in df.columns:
                return f"Columns '{raw_gb}' or '{raw_target}' not found in dataset. Available columns: {', '.join(df.columns)}"
            if agg_type not in ("sum", "mean", "count", "min", "max", "median"):
                return f"Unsupported aggregation '{agg_type}'. Supported: sum, mean, count, min, max, median."
                
            # Validate target is numeric for math aggregations
            if agg_type in ("sum", "mean", "median"):
                numeric_check = pd.to_numeric(df[target_col], errors='coerce')
                if numeric_check.isna().all():
                    return f"Cannot perform '{agg_type}' aggregation on non-numeric column '{raw_target}'."
                df[target_col] = numeric_check
                
            grouped = df.groupby(gb_col)[target_col].agg(agg_type).reset_index()
            return format_dataframe(grouped)

        elif op in ("summary", "describe"):
            desc = df.describe(include='all').transpose().reset_index()
            return format_dataframe(desc)

        elif op in ("aggregate", "aggregation"):
            agg_type = plan.get("aggregate", "sum")
            raw_target = plan.get("column")
            target_col = get_real_column(raw_target)
            
            if not target_col or target_col not in df.columns:
                return f"Column '{raw_target}' not found in dataset. Available columns: {', '.join(df.columns)}"
            if agg_type not in ("sum", "mean", "count", "min", "max", "median"):
                return f"Unsupported aggregation '{agg_type}'."
                
            if agg_type in ("sum", "mean", "median"):
                numeric_check = pd.to_numeric(df[target_col], errors='coerce')
                if numeric_check.isna().all():
                    return f"Cannot perform '{agg_type}' aggregation on non-numeric column '{raw_target}'."
                df[target_col] = numeric_check
                
            val = df[target_col].agg(agg_type)
            return f"{agg_type.upper()} of {target_col}: {val}"

        elif op in ("select", "top_n", "sort"):
            raw_cols = plan.get("columns", list(df.columns))
            limit = plan.get("limit", 15)
            raw_sort = plan.get("sort_by")
            sort_by = get_real_column(raw_sort)
            ascending = plan.get("ascending", False)
            
            cols = [get_real_column(c) for c in raw_cols]
            valid_cols = [c for c in cols if c and c in df.columns]
            res_df = df[valid_cols] if valid_cols else df
            
            if sort_by:
                if sort_by not in df.columns:
                    return f"Sort column '{raw_sort}' not found in dataset."
                res_df = res_df.sort_values(by=sort_by, ascending=ascending)
                
            return format_dataframe(res_df.head(limit))

        else:
            return f"Unrecognized operation: {op}. Dataset columns: {', '.join(df.columns)}"

    except Exception as e:
        return f"Error executing structured operation '{op}': {str(e)}"
