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
        dataframe = load_csv(document)
        column_types = []
        for column_name in dataframe.columns:
            dtype = str(dataframe[column_name].dtype)
            if "int" in dtype:
                type_name = "integer"
            elif "float" in dtype:
                type_name = "float"
            elif "object" in dtype or "str" in dtype:
                type_name = "string"
            else:
                type_name = dtype
            column_types.append(f"- {column_name} ({type_name})")

        sample_rows = []
        for _, row in dataframe.head(2).iterrows():
            row_string = " | ".join(str(value) for value in row.values)
            sample_rows.append(row_string)

        columns_text = "\n".join(column_types)
        samples_text = "\n".join(sample_rows)

        return f"Columns:\n{columns_text}\n\n" f"Sample Rows:\n{samples_text}"
    except Exception:
        return "Could not load CSV schema info."
