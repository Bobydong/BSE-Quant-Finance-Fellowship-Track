"""BSE Quant Backtester - web UI.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bsequant as bq
from bsequant.strategy import Strategy

st.set_page_config(page_title="BSE Quant Backtester", page_icon="📈",
                   layout="wide", initial_sidebar_state="expanded")

GREEN, RED, GREY, BLUE = "#1D9E75", "#D8503A", "#8B98A5", "#4A7FB5"

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; max-width: 1400px;}
  [data-testid="stMetricValue"] {font-size: 1.6rem;}
  .warn {background:#4a1f16; border-left:3px solid #D8503A; padding:.7rem 1rem;
         border-radius:4px; margin:.3rem 0; font-size:.9rem;}
  .good {background:#12352a; border-left:3px solid #1D9E75; padding:.7rem 1rem;
         border-radius:4px; margin:.3rem 0; font-size:.9rem;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------- discovery
def discover_strategies() -> dict[str, type]:
    """Find every Strategy subclass in the strategies/ folder."""
    found: dict[str, type] = {}
    folder = Path(__file__).resolve().parent / "strategies"

    for path in sorted(folder.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        mod_name = f"strategies.{path.stem}"
        try:
            mod = importlib.import_module(mod_name)
            importlib.reload(mod)
        except Exception as exc:                      # noqa: BLE001
            st.sidebar.error(f"Could not import {path.name}: {exc}")
            continue

        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if (issubclass(obj, Strategy) and obj is not Strategy
                    and obj.__module__ == mod.__name__):
                found[f"{obj.name}  ·  {path.stem}"] = obj
    return found


@st.cache_data
def load_data(name: str) -> pd.DataFrame:
    return bq.load(name)


def instantiate(cls):
    """Build a strategy, exposing any __init__ parameters as sidebar widgets."""
    sig = inspect.signature(cls.__init__)
    params = [p for n, p in sig.parameters.items()
              if n != "self" and p.default is not inspect.Parameter.empty]
    if not params:
        return cls(), {}

    st.sidebar.markdown("**Strategy parameters**")
    kwargs = {}
    for p in params:
        if isinstance(p.default, bool):
            kwargs[p.name] = st.sidebar.checkbox(p.name, value=p.default)
        elif isinstance(p.default, int):
            kwargs[p.name] = st.sidebar.slider(
                p.name, 1, max(200, p.default * 4), p.default)
        elif isinstance(p.default, float):
            kwargs[p.name] = st.sidebar.slider(
                p.name, 0.0, max(0.20, p.default * 5), p.default, step=0.005,
                format="%.3f")
        else:
            kwargs[p.name] = p.default
    st.sidebar.caption(
        "Careful: every knob you turn is a chance to overfit. "
        "Tune on train, judge on test.")
    return cls(**kwargs), kwargs


# ------------------------------------------------------------------ sidebar
st.sidebar.title("📈 BSE Quant")
st.sidebar.caption("Backtester · Fall 2026")

datasets = bq.available_datasets()
dataset = st.sidebar.selectbox("Dataset", datasets,
                               index=datasets.index("BCH-1d") if "BCH-1d" in datasets else 0)
data_full = load_data(dataset)

strategies = discover_strategies()
if not strategies:
    st.error("No strategies found. Add a file to strategies/ that subclasses Strategy.")
    st.stop()

choice = st.sidebar.selectbox("Strategy", list(strategies))
strategy, params = instantiate(strategies[choice])

st.sidebar.markdown("---")
fee_bps = st.sidebar.slider("Fee (bps per side)", 0.0, 25.0, 1.5, 0.5,
                            help="Charged on the amount of position that changes. "
                                 "Retail crypto is ~10bps; institutional ~1-2bps.")

# Annualization factor. Inferred from the data's spacing, but overridable -
# fellows should understand it rather than treat 252 or 365 as magic.
inferred_ppy = bq.infer_periods_per_year(data_full)
FREQ_PRESETS = {
    f"Auto-detect ({inferred_ppy})": inferred_ppy,
    "365 · daily crypto": 365,
    "252 · daily equities": 252,
    "52 · weekly": 52,
    "12 · monthly": 12,
    "Custom…": None,
}
freq_label = st.sidebar.selectbox(
    "Periods per year", list(FREQ_PRESETS), index=0,
    help="Sharpe is annualized by multiplying by √(periods per year). "
         "This is a property of the DATA's frequency: 365 for crypto, which "
         "never closes; 252 for daily equities, after weekends and holidays.")
periods_per_year = FREQ_PRESETS[freq_label]
if periods_per_year is None:
    periods_per_year = st.sidebar.number_input(
        "Custom periods per year", min_value=1, max_value=100_000,
        value=inferred_ppy, step=1)
st.sidebar.caption(
    f"Annualizing by √{periods_per_year} ≈ {np.sqrt(periods_per_year):.1f}×. "
    f"This scales Sharpe, annualized return and volatility — never total return.")

period = st.sidebar.radio("Evaluate on",
                          ["Full history", "Train (first 75%)", "Test (last 25%)"],
                          help="Develop on train. Judge on test. That gap is the "
                               "only honest estimate of future performance.")

train, test = bq.split(data_full)
data = {"Full history": data_full, "Train (first 75%)": train,
        "Test (last 25%)": test}[period]

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Reload strategy files", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption(f"{len(data):,} days · {data.index[0].date()} → {data.index[-1].date()}")


# --------------------------------------------------------------------- run
result = bq.run(strategy, data, fee_bps=fee_bps,
                periods_per_year=periods_per_year)
m = result.metrics

st.title(strategy.name)
if strategy.description:
    st.caption(strategy.description)

for w in result.warnings:
    st.markdown(f'<div class="warn"><b>⚠️ {w}</b></div>', unsafe_allow_html=True)

# headline metrics
c = st.columns(6)
c[0].metric("Total return", f"{m['total_return']:.1%}",
            f"{m['total_return'] - m['benchmark_return']:.1%} vs hold")
c[1].metric("Sharpe", f"{m['sharpe']:.2f}",
            f"{m['sharpe'] - m['benchmark_sharpe']:+.2f} vs hold")
c[2].metric("Annualized", f"{m['annual_return']:.1%}")
c[3].metric("Max drawdown", f"{m['max_drawdown']:.1%}")
c[4].metric("Win rate", f"{m['win_rate']:.1%}")
c[5].metric("Trades", f"{m['trades']:,}")

tab_perf, tab_risk, tab_costs, tab_years, tab_data = st.tabs(
    ["Performance", "Risk", "Costs", "Year by year", "Data"])


# ------------------------------------------------------------- performance
with tab_perf:
    d = result.data
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.72, 0.28], vertical_spacing=0.06,
                        subplot_titles=("Equity curve (log scale)", "Position"))

    fig.add_trace(go.Scatter(x=d.index, y=d["equity"], name=strategy.name,
                             line=dict(color=GREEN, width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["benchmark_equity"], name="Buy and hold",
                             line=dict(color=GREY, width=1.4, dash="dot")), row=1, col=1)
    fig.add_hline(y=1.0, line=dict(color=GREY, width=0.8), row=1, col=1)

    fig.add_trace(go.Scatter(x=d.index, y=d["position"], name="Position",
                             line=dict(color=BLUE, width=1), fill="tozeroy",
                             showlegend=False), row=2, col=1)

    fig.update_yaxes(type="log", row=1, col=1, title_text="Growth of $1")
    fig.update_yaxes(row=2, col=1, title_text="Exposure")
    fig.update_layout(height=560, template="plotly_dark", hovermode="x unified",
                      legend=dict(orientation="h", y=1.08, x=0),
                      margin=dict(t=60, b=20, l=10, r=10))
    st.plotly_chart(fig, use_container_width=True)

    st.caption("Log scale: a straight line means steady compounding. "
               "Flat stretches on the position chart are days out of the market.")

    a, b = st.columns(2)
    with a:
        st.markdown("**Return distribution**")
        r = d["net_return"] * 100
        h = go.Figure(go.Histogram(x=r, nbinsx=70, marker_color=GREEN, opacity=0.75))
        h.add_vline(x=0, line=dict(color=GREY, dash="dash"))
        h.add_vline(x=float(r.mean()), line=dict(color=RED),
                    annotation_text=f"mean {r.mean():.2f}%")
        h.update_layout(height=280, template="plotly_dark",
                        margin=dict(t=10, b=10, l=10, r=10),
                        xaxis_title="Daily return (%)", yaxis_title="Days")
        st.plotly_chart(h, use_container_width=True)
    with b:
        st.markdown("**vs. buy and hold**")
        st.dataframe(pd.DataFrame({
            "Strategy": [f"{m['total_return']:.1%}", f"{m['sharpe']:.2f}",
                         f"{m['max_drawdown']:.1%}"],
            "Buy & hold": [f"{m['benchmark_return']:.1%}",
                           f"{m['benchmark_sharpe']:.2f}",
                           f"{(d['benchmark_equity'] / d['benchmark_equity'].cummax() - 1).min():.1%}"],
        }, index=["Total return", "Sharpe", "Max drawdown"]),
            use_container_width=True)

        st.markdown("**Extremes**")
        st.dataframe(pd.DataFrame({
            "Value": [f"{m['best_day']:.1%}", f"{m['worst_day']:.1%}",
                      f"{m['volatility']:.1%}", f"{m['days_in_market']:,} / {m['total_days']:,}"],
        }, index=["Best day", "Worst day", "Annualized volatility", "Days in market"]),
            use_container_width=True)


# --------------------------------------------------------------------- risk
with tab_risk:
    d = result.data
    fig = go.Figure(go.Scatter(x=d.index, y=d["drawdown"] * 100, fill="tozeroy",
                               line=dict(color=RED, width=1.2), name="Drawdown"))
    fig.update_layout(height=340, template="plotly_dark",
                      yaxis_title="Drawdown (%)", hovermode="x unified",
                      margin=dict(t=30, b=20, l=10, r=10))
    st.plotly_chart(fig, use_container_width=True)

    peak = d["equity"].cummax()
    trough_i = (d["equity"] / peak - 1).idxmin()
    peak_i = d["equity"].loc[:trough_i].idxmax()
    recovered = d["equity"].loc[trough_i:]
    rec_i = recovered[recovered >= d["equity"].loc[peak_i]].index
    rec_txt = str(rec_i[0].date()) if len(rec_i) else "never recovered"

    a, b, c2 = st.columns(3)
    a.metric("Worst drawdown", f"{m['max_drawdown']:.1%}")
    b.metric("Peak → trough", f"{(trough_i - peak_i).days} days",
             f"{peak_i.date()} → {trough_i.date()}")
    c2.metric("Recovered", rec_txt)

    st.markdown(
        f'<div class="warn">A {abs(m["max_drawdown"]):.0%} drawdown means that at '
        f'some point you were down {abs(m["max_drawdown"]):.0%} from your peak. '
        f'Would you have kept trading? Most people would not - which is why '
        f'drawdown matters more than volatility.</div>',
        unsafe_allow_html=True)

    st.markdown("**Rolling 90-day Sharpe**")
    roll = d["net_return"].rolling(90)
    rs = (roll.mean() / roll.std() * np.sqrt(periods_per_year)).dropna()
    f2 = go.Figure(go.Scatter(x=rs.index, y=rs, line=dict(color=BLUE, width=1.4)))
    f2.add_hline(y=0, line=dict(color=GREY, dash="dash"))
    f2.add_hline(y=1, line=dict(color=GREEN, dash="dot"),
                 annotation_text="Sharpe = 1")
    f2.update_layout(height=280, template="plotly_dark",
                     margin=dict(t=20, b=20, l=10, r=10), hovermode="x unified")
    st.plotly_chart(f2, use_container_width=True)
    st.caption("An edge that only exists in one stretch of the chart is not an edge.")


# -------------------------------------------------------------------- costs
with tab_costs:
    st.markdown("**At what cost does the edge disappear?**")
    sweep = bq.cost_sweep(strategy, data, periods_per_year=periods_per_year)

    f = make_subplots(specs=[[{"secondary_y": True}]])
    f.add_trace(go.Scatter(x=sweep.index, y=sweep["sharpe"], name="Sharpe",
                           line=dict(color=GREEN, width=2.4),
                           mode="lines+markers"), secondary_y=False)
    f.add_trace(go.Scatter(x=sweep.index, y=sweep["annual_return"] * 100,
                           name="Annual return (%)",
                           line=dict(color=BLUE, width=1.6, dash="dot"),
                           mode="lines+markers"), secondary_y=True)
    f.add_hline(y=0, line=dict(color=RED, dash="dash"))
    f.update_xaxes(title_text="Fee (bps per side)")
    f.update_yaxes(title_text="Sharpe", secondary_y=False)
    f.update_yaxes(title_text="Annual return (%)", secondary_y=True)
    f.update_layout(height=380, template="plotly_dark",
                    margin=dict(t=30, b=20, l=10, r=10),
                    legend=dict(orientation="h", y=1.1, x=0))
    st.plotly_chart(f, use_container_width=True)

    dead = sweep[sweep["sharpe"] <= 0]
    if len(dead):
        st.markdown(
            f'<div class="warn">This strategy stops working at about '
            f'<b>{dead.index[0]} bps</b> per side. Retail crypto fees are '
            f'roughly 10bps, so judge accordingly.</div>',
            unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="good">The edge survives every cost level tested here.</div>',
            unsafe_allow_html=True)

    st.dataframe(sweep.style.format({
        "sharpe": "{:.2f}", "annual_return": "{:.1%}",
        "total_return": "{:.1%}", "max_drawdown": "{:.1%}"}),
        use_container_width=True)

    a, b, c3 = st.columns(3)
    a.metric("Trades", f"{m['trades']:,}")
    b.metric("Avg daily turnover", f"{m['avg_turnover']:.2f}x")
    c3.metric("Total paid in fees", f"{m['total_fees_paid']:.1%} of equity")
    st.caption("Turnover is what costs you money. A strategy that flips every "
               "day needs a much bigger edge than one that rebalances monthly.")


# ---------------------------------------------------------------- by year
with tab_years:
    y = result.yearly
    colors = [GREEN if v > 0 else RED for v in y["return"]]
    f = go.Figure(go.Bar(x=y.index.astype(str), y=y["return"] * 100,
                         marker_color=colors,
                         text=[f"{v:.0%}" for v in y["return"]],
                         textposition="outside"))
    f.add_hline(y=0, line=dict(color=GREY))
    f.update_layout(height=340, template="plotly_dark",
                    yaxis_title="Return (%)",
                    margin=dict(t=30, b=20, l=10, r=10))
    st.plotly_chart(f, use_container_width=True)

    st.dataframe(y.style.format({
        "return": "{:.1%}", "sharpe": "{:.2f}",
        "max_drawdown": "{:.1%}", "days": "{:,}"}),
        use_container_width=True)

    bad = y[y["return"] < 0]
    if len(bad):
        worst = bad["return"].idxmin()
        st.markdown(
            f'<div class="warn">{len(bad)} losing year(s). The worst was '
            f'<b>{worst}</b> at <b>{bad["return"].min():.1%}</b>. A real edge can '
            f'vanish for a year or more - if you had started trading in {worst}, '
            f'you would have spent twelve months wondering if you had fooled '
            f'yourself.</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------- data
with tab_data:
    st.dataframe(result.data.tail(300).style.format({
        "close": "{:.2f}", "position": "{:+.2f}", "market_return": "{:+.3%}",
        "gross_return": "{:+.3%}", "net_return": "{:+.3%}",
        "cost": "{:.4%}", "equity": "{:.3f}", "drawdown": "{:.1%}",
        "turnover": "{:.2f}", "benchmark_equity": "{:.3f}"}),
        use_container_width=True, height=460)
    st.download_button("Download full results (CSV)",
                       result.data.to_csv().encode(),
                       f"{strategy.name.replace(' ', '_')}_{dataset}.csv",
                       "text/csv")
