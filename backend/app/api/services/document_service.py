from pathlib import Path
import pandas as pd


def load_csv(document):
    file_path = Path(document.storage_path)

    if not file_path.exists():
        raise FileNotFoundError()

    return pd.read_csv(file_path)


def get_csv_schema_info(document) -> str:
    """
    Extracts the columns, their types, and the first 2 sample rows
    from the CSV document to feed into the LLM context.
    """
    try:
        df = load_csv(document)
        col_types = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            if 'int' in dtype:
                t = "integer"
            elif 'float' in dtype:
                t = "float"
            elif 'object' in dtype or 'str' in dtype:
                t = "string"
            else:
                t = dtype
            col_types.append(f"- {col} ({t})")
        
        sample_rows = []
        for _, row in df.head(2).iterrows():
            row_str = " | ".join(str(val) for val in row.values)
            sample_rows.append(row_str)
        
        columns_text = "\n".join(col_types)
        samples_text = "\n".join(sample_rows)
        
        return (
            f"Columns:\n{columns_text}\n\n"
            f"Sample Rows:\n{samples_text}"
        )
    except Exception:
        return "Could not load CSV schema info."
