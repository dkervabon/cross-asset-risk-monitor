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
    snap_date = str(df["price_date"].iloc[0]) if len(df) else ""
    labels = [f"{t} — {data.TICKER_NAME.get(t, t)}" for t in df["ticker"]]
    colors = ["#d62728" if z is not None and z <= -1.5 else
              "#ff7f0e" if z is not None and z >= 1.5 else "#bdbdbd"
              for z in df["decoupling_zscore"]]
    fig = go.Figure(go.Bar(x=df["decoupling_zscore"], y=labels, orientation="h",
                           marker_color=colors,
                           hovertemplate="%{y}<br>z=%{x:.2f} vs its own 60d norm<extra></extra>"))
    fig.add_vline(x=-1.5, line_dash="dot", line_color="#d62728", annotation_text="decoupling")
    fig.add_vline(x=1.5, line_dash="dot", line_color="#ff7f0e", annotation_text="contagion")
    fig.update_layout(
        title=f"Decoupling snapshot — {snap_date} ({window_days}-day) · ← decoupling | contagion →",
        xaxis=dict(title="change in correlation-to-market vs own 60-day baseline (z-score)"),
        height=560, margin=dict(l=160, r=20, t=60, b=40),
    )
    return fig


# --------------------------------- layout -----------------------------------
def caption(text: str):
    """Explanatory note rendered beneath a chart."""
    return html.P(text, style={
        "color": "#555", "fontSize": "13px", "lineHeight": "1.5",
        "margin": "2px 0 26px 0", "borderLeft": "3px solid #e0e0e0", "paddingLeft": "10px",
    })


def ticker_appendix():
    """Sidebar listing every ticker and its friendly name, grouped by asset class."""
    blocks = []
    current_class = None
    for ticker, name, asset_class in data.TICKER_META:
        if asset_class != current_class:
            blocks.append(html.Div(asset_class, style={
                "fontWeight": "600", "fontSize": "12px", "textTransform": "uppercase",
                "color": "#888", "margin": "12px 0 4px 0", "letterSpacing": "0.04em"}))
            current_class = asset_class
        blocks.append(html.Div([
            html.Span(ticker, style={"fontFamily": "monospace", "fontWeight": "600",
                                     "color": "#1f77b4", "display": "inline-block", "width": "82px"}),
            html.Span(name, style={"color": "#333"}),
        ], style={"fontSize": "13px", "padding": "1px 0"}))
    return html.Div(style={
        "flex": "0 0 230px", "alignSelf": "flex-start", "position": "sticky", "top": "16px",
        "background": "#fafafa", "border": "1px solid #ececec", "borderRadius": "8px",
        "padding": "14px 16px",
    }, children=[
        html.Div("Ticker appendix", style={"fontWeight": "700", "marginBottom": "2px"}),
        html.Div("16 assets across 5 classes", style={"fontSize": "12px", "color": "#999"}),
        *blocks,
    ])


main_column = html.Div(style={"flex": "1 1 auto", "minWidth": "0"}, children=[
    html.Div(style={"display": "flex", "gap": "24px", "alignItems": "center", "margin": "12px 0"}, children=[
        html.Label("Rolling window:"),
        dcc.RadioItems(id="window", options=[{"label": " 30-day", "value": 30},
                                             {"label": " 90-day", "value": 90}],
                       value=90, inline=True),
    ]),

    dcc.Graph(id="heatmap"),
    caption("Pairwise correlation of daily returns for every asset pair on the most recent date. "
            "Deep red = strongly positive (move together), deep blue = strongly negative (move opposite), "
            "white ≈ uncorrelated. As a reading guide: assets within a class (the equity sectors, the two "
            "Treasuries) tend to be the most correlated, while diversifiers like Treasuries and gold often sit "
            "blue against stocks. The warning sign is those normally-offsetting blue cells turning red — when "
            "diversifiers start moving WITH risk assets, that's the everything-moves-together signature of a "
            "risk-off regime."),

    html.Div(style={"display": "flex", "gap": "16px", "alignItems": "center", "margin": "8px 0"}, children=[
        html.Label("Pair:"),
        dcc.Dropdown(id="ta", options=[{"label": f"{t} — {data.TICKER_NAME[t]}", "value": t} for t in TICKERS],
                     value="SPY", clearable=False, style={"width": "260px"}),
        dcc.Dropdown(id="tb", options=[{"label": f"{t} — {data.TICKER_NAME[t]}", "value": t} for t in TICKERS],
                     value="TLT", clearable=False, style={"width": "260px"}),
    ]),
    dcc.Graph(id="pair"),
    caption("How one pair's correlation has evolved over 10 years. The 30-day line reacts fast (catches the onset "
            "of decoupling); the 90-day line shows the structural trend. The default SPY vs TLT is the classic "
            "stock/bond hedge. It was reliably negative from 2017–2020 — most negative around −0.63 at the March "
            "2020 COVID crash, the hedge working exactly when needed. It blipped positive in mid-2021 (the reflation "
            "trade), then shifted regime from H2 2022: as the Fed hiked aggressively, stocks and bonds increasingly "
            "fell together and the correlation has stayed near-zero-to-positive ever since (peaking ~+0.41 in late "
            "2023, and still positive in 2024–2026). A reliable hedge that structurally weakened in the higher-rate era."),

    dcc.Graph(id="regime"),
    caption("The market-wide average of all pairwise correlations, our systemic-stress gauge. Each day's average "
            "is z-scored against its trailing 1-year distribution: red dots (STRESS) mark days when correlations "
            "are abnormally elevated — diversification is failing — and green dots (CALM) mark unusually decoupled "
            "markets. Spikes line up with the COVID crash, the 2022 bear market, and the April 2025 tariff shock."),

    dcc.Graph(id="decoupling"),
    caption("A snapshot of the single most recent trading day. For each asset we take its average correlation to "
            "all 15 others right now, then compare it to that same asset's average over the prior 60 days; the bar "
            "is the change in standard deviations (z-score). A big RED bar on the LEFT = correlation-to-market "
            "dropped sharply, so the asset is decoupling — breaking away from the pack first. A big ORANGE bar on "
            "the RIGHT = correlation jumped, so the asset is being pulled into a contagion / everything-together "
            "move. Small grey bars mean a calm day where everything is about as correlated as usual. This is the "
            "panel that answers 'which assets decouple first, and which follow' — watch it during a stress spike "
            "in the chart above, when the bars get large."),

    html.P("Data: yfinance → Snowflake → dbt. Correlations computed on SPY-aligned daily log returns.",
           style={"color": "#888", "fontSize": "12px", "marginTop": "8px"}),
])


app.layout = html.Div(style={"maxWidth": "1280px", "margin": "0 auto",
                             "fontFamily": "system-ui, sans-serif", "padding": "16px"}, children=[
    html.H1("Cross-Asset Risk Monitor"),
    html.P("When cross-asset correlations break down, which assets decouple first — and "
           "can we spot systemic stress regimes in real time?",
           style={"color": "#555", "marginTop": "-8px"}),

    html.Div(style={"display": "flex", "gap": "28px", "alignItems": "flex-start"}, children=[
        main_column,
        ticker_appendix(),
    ]),
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
