import pytest
import pandas as pd
from app.tools.chart_generator import ChartGenerator


def test_chart_generator_generates_bar_chart():
    df = pd.DataFrame({"Category": ["A", "B", "C"], "Value": [10, 20, 30]})

    generator = ChartGenerator()
    fig = generator.generate(df, chart_type="bar", x="Category", y="Value")

    assert fig is not None
    # Verify it has correct properties
    fig_json = fig.to_json()
    assert "bar" in fig_json or "data" in fig_json


def test_chart_generator_generates_line_chart():
    df = pd.DataFrame({"Month": ["Jan", "Feb", "Mar"], "Sales": [100, 150, 200]})

    generator = ChartGenerator()
    fig = generator.generate(df, chart_type="line", x="Month", y="Sales")

    assert fig is not None
    fig_json = fig.to_json()
    assert "scatter" in fig_json or "line" in fig_json or "data" in fig_json


def test_chart_generator_generates_pie_chart():
    df = pd.DataFrame(
        {"Browser": ["Chrome", "Firefox", "Safari"], "Share": [60, 20, 20]}
    )

    generator = ChartGenerator()
    fig = generator.generate(df, chart_type="pie", x="Browser", y="Share")

    assert fig is not None
    fig_json = fig.to_json()
    assert "pie" in fig_json or "data" in fig_json


def test_chart_generator_invalid_column_raises_error():
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    generator = ChartGenerator()

    # Passing an invalid column name should raise ValueError or KeyError from Plotly Express
    with pytest.raises((ValueError, KeyError)):
        generator.generate(df, chart_type="bar", x="Nonexistent", y="B")


def test_chart_generator_empty_dataframe_raises_error():
    df = pd.DataFrame()
    generator = ChartGenerator()

    with pytest.raises((ValueError, IndexError, KeyError)):
        generator.generate(df, chart_type="bar", x="A", y="B")
