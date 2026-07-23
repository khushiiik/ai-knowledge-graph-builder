import pandas as pd
import plotly.express as px


class ChartGenerator:

    def generate(self, dataframe: pd.DataFrame, chart_type: str, x: str, y: str):
        ctype = str(chart_type).lower() if chart_type else "bar"

        if ctype == "pie":
            fig = px.pie(dataframe, names=x, values=y if y else None)
        elif ctype == "line":
            fig = px.line(dataframe, x=x, y=y)
        else:
            fig = px.bar(dataframe, x=x, y=y)

        return fig
