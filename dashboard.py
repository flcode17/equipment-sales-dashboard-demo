"""
Demo version of the equipment-sales metrics dashboard, for screenshots and
presentations. Reads only demo.db -- invented data for a fictional company --
and refuses to run against anything else.

    python3 generate_demo_data.py   # once (or again to refresh dates)
    streamlit run dashboard.py      # http://127.0.0.1:8502
"""
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import metrics as m

COMPANY = "Demo Equipment Co."
DB_PATH = Path(__file__).with_name("demo.db")

# ── Palette: validated categorical slots + chrome roles (light mode) ───────
BLUE = "#2a78d6"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"
PAGE = "#f9f9f7"
BORDER = "rgba(11,11,11,0.10)"
# Fixed slot per entity (color follows the entity, never its rank).
WAREHOUSE_COLORS = {"North Hub": "#2a78d6", "South Hub": "#eb6834", "East Hub": "#1baf7a"}
CHANNEL_COLORS = {
    "Marketplace": "#2a78d6", "Website": "#eb6834", "Social ads": "#1baf7a",
    "Google ads": "#eda100", "Referral": "#e87ba4", "Walk-in": "#008300",
}

st.set_page_config(page_title="Equipment Sales Dashboard (Demo)", layout="wide")

st.markdown(
    f"""
    <style>
    .stApp {{ background: {PAGE}; }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 10px !important;
        border: 1px solid {BORDER} !important;
        background: {SURFACE} !important;
    }}
    .stat-label {{ font-size: 11px; color: {INK_MUTED}; text-transform: uppercase; letter-spacing: 0.5px; }}
    .stat-value {{ font-size: 28px; font-weight: 500; color: {INK_PRIMARY}; margin-top: 6px;
                   letter-spacing: -0.5px; line-height: 1.1; }}
    .stat-sub {{ font-size: 12px; color: {INK_MUTED}; margin-top: 4px; }}
    .card-title {{ font-size: 15px; font-weight: 500; color: {INK_PRIMARY}; }}
    .card-subtitle {{ font-size: 12px; color: {INK_MUTED}; margin-top: 2px; margin-bottom: 10px; }}
    .empty-box {{ display: flex; align-items: center; justify-content: center; height: 200px;
                  color: {INK_MUTED}; font-size: 13px; border: 1px dashed {GRIDLINE}; border-radius: 8px; }}
    .demo-tag {{ display: inline-block; font-size: 11px; font-weight: 500; color: {INK_SECONDARY};
                 border: 1px solid {BASELINE}; border-radius: 999px; padding: 1px 9px; margin-left: 10px;
                 vertical-align: middle; letter-spacing: 0.3px; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def open_demo_db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        st.error("demo.db not found. Run `python3 generate_demo_data.py` first.")
        st.stop()
    conn = sqlite3.connect(DB_PATH)
    try:
        source = conn.execute("SELECT value FROM meta WHERE key = 'source'").fetchone()
    except sqlite3.DatabaseError:
        source = None
    if not source or source[0] != "demo":
        st.error("This isn't the demo database. The demo only runs on data made by generate_demo_data.py.")
        st.stop()
    return conn


def money(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def stat_card(col, label: str, value: str, sub: str) -> None:
    with col.container(border=True):
        st.markdown(f'<div class="stat-label">{label}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="stat-value">{value}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="stat-sub">{sub}</div>', unsafe_allow_html=True)


def card_header(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="card-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="card-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def empty(note: str = "No data in this timeframe.") -> None:
    st.markdown(f'<div class="empty-box">{note}</div>', unsafe_allow_html=True)


def style(fig, height: int = 240, x_grid: bool = True, y_grid: bool = False, legend: bool = False):
    fig.update_layout(
        height=height, margin=dict(l=0, r=8, t=4, b=0),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font_color=INK_SECONDARY,
        showlegend=legend,
        xaxis=dict(title=None, tickfont=dict(color=INK_MUTED), gridcolor=GRIDLINE, showgrid=x_grid, zeroline=False),
        yaxis=dict(title=None, tickfont=dict(color=INK_SECONDARY), gridcolor=GRIDLINE, showgrid=y_grid, zeroline=False),
        hoverlabel=dict(bgcolor=SURFACE, font_color=INK_PRIMARY, bordercolor=BASELINE),
    )
    return fig


def show(fig) -> None:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


TIMEFRAMES = ["Past week", "Past month", "Past 6 months", "Past year", "All time", "Custom range"]
_MONTHS_BACK = {"Past month": 1, "Past 6 months": 6, "Past year": 12}


def preset_range(choice: str, today: date, bounds: tuple[date, date]) -> tuple[date, date]:
    if choice == "Past week":
        return today - timedelta(days=6), today
    if choice in _MONTHS_BACK:
        months_ago = (pd.Timestamp(today) - pd.DateOffset(months=_MONTHS_BACK[choice])).date()
        return months_ago + timedelta(days=1), today
    return bounds


def format_range(start: date, end: date) -> str:
    return f"{start:%b} {start.day}, {start.year} – {end:%b} {end.day}, {end.year}"


conn = open_demo_db()
today = date.today()
bounds = m.date_bounds(conn)

st.markdown(
    '<h1 style="font-size:22px;font-weight:500;">Business metrics<span class="demo-tag">Demo data</span></h1>',
    unsafe_allow_html=True,
)

# ── Timeframe filter (applies to every card) ─────────────────
f1, f2, _ = st.columns([1, 1.4, 2.6])
choice = f1.selectbox("Timeframe", TIMEFRAMES, index=TIMEFRAMES.index("Past year"))
if choice == "Custom range":
    default_start = max(bounds[0], today - timedelta(days=89))
    picked = f2.date_input("Dates", value=(default_start, today), min_value=bounds[0],
                           max_value=max(bounds[1], today), format="MM/DD/YYYY")
    start, end = (picked[0], picked[-1]) if picked else (default_start, today)
    if len(picked) == 1:
        f2.caption("Now pick an end date.")
else:
    start, end = preset_range(choice, today, bounds)

st.markdown(
    f'<p style="font-size:13px;color:{INK_MUTED};margin-top:0;margin-bottom:16px;">'
    f"{COMPANY} &middot; {format_range(start, end)}</p>",
    unsafe_allow_html=True,
)

units = m.total_units(conn, start, end)
revenue = m.total_revenue(conn, start, end)
models = m.units_by_model(conn, start, end)
channels = m.new_customers_by_channel(conn, start, end)
cpa = m.cost_per_customer(conn, start, end)
leads, converted = m.lead_conversion(conn, start, end)

# ── Top stat cards ──────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
stat_card(c1, "Total units sold", f"{units:,.0f}", "All models, net of returns")
stat_card(c2, "Revenue", money(revenue), "Net of returns, excl. sales tax")
if channels.empty:
    stat_card(c3, "Best channel", "—", "No new customers in this timeframe")
else:
    best = channels.sort_values("customers", ascending=False).iloc[0]
    stat_card(c3, "Best channel", best["channel"], f"{best['customers'] / channels['customers'].sum():.0%} of new customers")
if models.empty:
    stat_card(c4, "Top model", "—", "No sales in this timeframe")
else:
    stat_card(c4, "Top model", models.iloc[0]["item_name"], f"{models.iloc[0]['units']:,.0f} units sold")

# ── Hero: sales by city ──────────────────────────────────────
with st.container(border=True):
    card_header("Sales by city", "Bubble size = units sold &middot; color = serving warehouse")
    cities = m.units_by_city(conn, start, end)
    if cities.empty:
        empty()
    else:
        cities["label"] = ""
        top = cities.nlargest(5, "units").index
        cities.loc[top, "label"] = cities.loc[top, "city"]
        fig = px.scatter_geo(
            cities, lat="lat", lon="lon", size="units", color="warehouse", text="label",
            hover_name="city", hover_data={"units": True, "warehouse": True, "lat": False, "lon": False, "label": False},
            color_discrete_map=WAREHOUSE_COLORS, category_orders={"warehouse": list(WAREHOUSE_COLORS)},
            size_max=42,
        )
        fig.update_traces(marker=dict(opacity=0.7, line=dict(width=2, color=SURFACE)),
                          textposition="top center", textfont=dict(color=INK_SECONDARY, size=11))
        fig.update_geos(
            scope="usa", fitbounds="locations", showland=True, landcolor="#f0efec",
            subunitcolor=BASELINE, countrycolor=BASELINE, showlakes=False, bgcolor=SURFACE,
        )
        style(fig, height=360, legend=True)
        fig.update_layout(legend=dict(title=None, orientation="h", y=1.02, x=0, yanchor="bottom"))
        show(fig)

# ── Chart grid ───────────────────────────────────────────────
row1_left, row1_right = st.columns(2)

with row1_left.container(border=True):
    card_header("Units sold by model", "Best and slowest movers")
    if models.empty:
        empty()
    else:
        fig = px.bar(models, x="units", y="item_name", orientation="h")
        fig.update_traces(marker_color=BLUE, marker_line_width=0, hovertemplate="%{y}: %{x:,.0f} units<extra></extra>")
        fig.update_yaxes(categoryorder="total ascending")
        show(style(fig, x_grid=True))

with row1_right.container(border=True):
    card_header("Where customers come from", "Share of new customers by channel")
    if channels.empty:
        empty("No new customers in this timeframe.")
    else:
        order = [c for c in CHANNEL_COLORS if c in set(channels["channel"])]
        share = channels.set_index("channel").loc[order, "customers"]
        labels = [f"{ch}  {n / share.sum():.0%}" for ch, n in share.items()]
        fig = px.pie(names=labels, values=share.values, hole=0.62,
                     color=labels, color_discrete_sequence=[CHANNEL_COLORS[c] for c in order])
        fig.update_traces(sort=False, direction="clockwise", textinfo="none",
                          marker=dict(line=dict(color=SURFACE, width=2)),
                          hovertemplate="%{label}<br>%{value} new customers<extra></extra>")
        style(fig, legend=True)
        fig.update_layout(legend=dict(title=None, font=dict(color=INK_SECONDARY)))
        show(fig)

row2_left, row2_right = st.columns(2)

with row2_left.container(border=True):
    card_header("Ad spend vs. return", "Cost per acquired customer, by paid channel")
    if cpa.empty:
        empty("No customers from paid channels in this timeframe.")
    else:
        fig = px.bar(cpa, x="cpa", y="channel", orientation="h", text=cpa["cpa"].map(money),
                     custom_data=["spend", "customers"])
        fig.update_traces(
            marker_color=BLUE, marker_line_width=0, textposition="outside", cliponaxis=False,
            textfont=dict(color=INK_SECONDARY),
            hovertemplate="%{y}<br>%{customdata[0]:$,.0f} spent · %{customdata[1]} new customers"
                          "<br>%{x:$,.0f} per customer<extra></extra>",
        )
        fig.update_yaxes(categoryorder="total descending")
        fig.update_xaxes(tickprefix="$", range=[0, cpa["cpa"].max() * 1.25])
        show(style(fig, x_grid=True))

with row2_right.container(border=True):
    freq, grain = m.trend_grain(start, end)
    card_header("Sales trend", f"Units per {grain}")
    trend = m.units_trend(conn, start, end, freq)
    if trend["units"].sum() == 0:
        empty()
    else:
        fig = px.line(trend, x="period", y="units", markers=True)
        fig.update_traces(line_color=BLUE, marker_color=BLUE, line_width=2, marker_size=7,
                          hovertemplate="%{x|%b %d, %Y}: %{y:,.0f} units<extra></extra>")
        fig.update_yaxes(rangemode="tozero")
        fig.update_layout(hovermode="x unified")
        show(style(fig, x_grid=False, y_grid=True))

# ── Bottom stat cards ────────────────────────────────────────
b1, b2, b3 = st.columns(3)
avg_deal = m.avg_deal_size(conn, start, end)
stat_card(b1, "Avg. deal size", money(avg_deal) if avg_deal else "—", "Per sale")
stat_card(b2, "Lead → sale rate", f"{converted / leads:.0%}" if leads else "—",
          f"{converted:,} of {leads:,} leads became customers" if leads else "No leads in this timeframe")
reliable = cpa[cpa["customers"] >= 3]
if reliable.empty:
    stat_card(b3, "Best CPA channel", "—", "Too few paid customers to compare")
else:
    best_cpa = reliable.iloc[0]
    stat_card(b3, "Best CPA channel", best_cpa["channel"], f"{money(best_cpa['cpa'])} per new customer")

conn.close()
