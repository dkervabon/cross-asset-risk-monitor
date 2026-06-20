"""Cross-Asset Risk Monitor — Dash app.

Run:
    python dashboard/app.py
then open http://127.0.0.1:8050
"""
import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
import plotly.express as px

import data

REGIME_COLORS = {"STRESS": "#d62728", "CALM": "#2ca02c", "NORMAL": "#7f7f7f", "WARMUP": "#cccccc"}

app = dash.Dash(__name__, title="Cross-Asset Risk Monitor")
server = app.server

TICKERS = list(data.get_tickers())


# ----------------------------- figure builders ------------------------------
def fig_heatmap(window_days: int) -> go.Figure:
    mat = data.get_correlation_matrix(window_days)
    fig = go.Figure(
        go.Heatmap(
            z=mat.values,
            x=mat.columns,
            y=mat.index,
            zmin=-1, zmax=1,
            colorscale="RdBu_r",
            colorbar=dict(title="corr"),
            hovertemplate="%{y} vs %{x}<br>corr=%{z:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"Latest {window_days}-day cross-asset correlation matrix ({data.get_latest_date(window_days)})",
        yaxis=dict(autorange="reversed"), height=620, margin=dict(l=90, r=20, t=60, b=90),
    )
    return fig


def fig_pair(ticker_a: str, ticker_b: str) -> go.Figure:
    df = data.get_pair_history(ticker_a, ticker_b)
    fig = go.Figure()
    for w, color in [(30, "#1f77b4"), (90, "#ff7f0e")]:
        sub = df[df["window_days"] == w]
        fig.add_trace(go.Scatter(x=sub["price_date"], y=sub["correlation"],
                                 mode="lines", name=f"{w}-day", line=dict(color=color, width=1.4)))
    fig.add_hline(y=0, line_dash="dot", line_color="#999")
    fig.update_layout(
        title=f"Rolling correlation: {ticker_a} vs {ticker_b}",
        yaxis=dict(title="correlation", range=[-1, 1]), height=420,
        margin=dict(l=60, r=20, t=60, b=40), legend=dict(orientation="h", y=1.08),
    )
    return fig


def fig_regime(window_days: int) -> go.Figure:
    df = data.get_stress_regimes(window_days)
    fig = go.Figure()
    # color the average-correlation line by regime via per-regime scatter overlays
    fig.add_trace(go.Scatter(x=df["price_date"], y=df["avg_corr"], mode="lines",
                             name="avg pairwise corr", line=dict(color="#333", width=1.2)))
    for regime in ["STRESS", "CALM"]:
        sub = df[df["regime"] == regime]
        fig.add_trace(go.Scatter(x=sub["price_date"], y=sub["avg_corr"], mode="markers",
                                 name=regime, marker=dict(color=REGIME_COLORS[regime], size=4)))
    fig.update_layout(
        title=f"Systemic stress regime — avg {window_days}-day correlation (red=STRESS, green=CALM)",
        yaxis=dict(title="avg correlation"), height=420,
        margin=dict(l=60, r=20, t=60, b=40), legend=dict(orientation="h", y=1.08),
    )
    return fig


def fig_decoupling(window_days: int) -> go.Figure:
    df = data.get_decoupling_latest(window_days).sort_values("decoupling_zscore")
    colors = ["#d62728" if z is not None and z <= -1.5 else
              "#ff7f0e" if z is not None and z >= 1.5 else "#1f77b4"
              for z in df["decoupling_zscore"]]
    fig = go.Figure(go.Bar(x=df["decoupling_zscore"], y=df["ticker"], orientation="h",
                           marker_color=colors,
                           hovertemplate="%{y}<br>z=%{x:.2f}<extra></extra>"))
    fig.add_vline(x=-1.5, line_dash="dot", line_color="#d62728")
    fig.add_vline(x=1.5, line_dash="dot", line_color="#ff7f0e")
    fig.update_layout(
        title=f"Decoupling leaderboard — latest {window_days}-day (left=decoupling, right=contagion)",
        xaxis=dict(title="decoupling z-score vs 60d baseline"), height=520,
        margin=dict(l=90, r=20, t=60, b=40),
    )
    return fig


# --------------------------------- layout -----------------------------------
app.layout = html.Div(style={"maxWidth": "1180px", "margin": "0 auto",
                             "fontFamily": "system-ui, sans-serif", "padding": "16px"}, children=[
    html.H1("Cross-Asset Risk Monitor"),
    html.P("When cross-asset correlations break down, which assets decouple first — and "
           "can we spot systemic stress regimes in real time?",
           style={"color": "#555", "marginTop": "-8px"}),

    html.Div(style={"display": "flex", "gap": "24px", "alignItems": "center", "margin": "12px 0"}, children=[
        html.Label("Rolling window:"),
        dcc.RadioItems(id="window", options=[{"label": " 30-day", "value": 30},
                                             {"label": " 90-day", "value": 90}],
                       value=90, inline=True),
    ]),

    dcc.Graph(id="heatmap"),

    html.Div(style={"display": "flex", "gap": "16px", "alignItems": "center", "margin": "8px 0"}, children=[
        html.Label("Pair:"),
        dcc.Dropdown(id="ta", options=[{"label": t, "value": t} for t in TICKERS],
                     value="SPY", clearable=False, style={"width": "180px"}),
        dcc.Dropdown(id="tb", options=[{"label": t, "value": t} for t in TICKERS],
                     value="TLT", clearable=False, style={"width": "180px"}),
    ]),
    dcc.Graph(id="pair"),
    dcc.Graph(id="regime"),
    dcc.Graph(id="decoupling"),
    html.P("Data: yfinance → Snowflake → dbt. Correlations on SPY-aligned daily log returns.",
           style={"color": "#888", "fontSize": "12px", "marginTop": "24px"}),
])


# -------------------------------- callbacks ---------------------------------
@app.callback(Output("heatmap", "figure"), Input("window", "value"))
def _heatmap(window):
    return fig_heatmap(window)


@app.callback(Output("pair", "figure"), Input("ta", "value"), Input("tb", "value"))
def _pair(ta, tb):
    return fig_pair(ta, tb)


@app.callback(Output("regime", "figure"), Input("window", "value"))
def _regime(window):
    return fig_regime(window)


@app.callback(Output("decoupling", "figure"), Input("window", "value"))
def _decoupling(window):
    return fig_decoupling(window)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)
