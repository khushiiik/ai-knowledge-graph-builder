import pandas as pd
import plotly.express as px


class ChartGenerator:

    def generate(self, dataframe: pd.DataFrame, chart_type: str, x: str, y: str):

        if chart_type == "bar":
            fig = px.bar(dataframe, x=x, y=y)

        elif chart_type == "pie":
            fig = px.pie(dataframe, names=x, values=y)

        elif chart_type == "line":
            fig = px.line(dataframe, x=x, y=y)

        else:
            raise Exception("Unsupported chart")

        return fig
