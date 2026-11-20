"""
Aggregations behind every stat card and chart, over demo.db.

Sales come in two signs: Invoice/SalesReceipt are sales, CreditMemo is a
return and gets netted out. Revenue excludes sales tax. Every query takes an
inclusive [start, end] date range.
"""
import sqlite3
from calendar import monthrange
from datetime import date

import pandas as pd

PAID_CHANNELS = ("Marketplace", "Social ads", "Google ads")

_SIGNED_REVENUE = """CASE WHEN s.txn_type = 'CreditMemo' THEN -(s.total_amt - s.tax_amt)
                          ELSE (s.total_amt - s.tax_amt) END"""
_SIGNED_QTY = "CASE WHEN s.txn_type = 'CreditMemo' THEN -li.quantity ELSE li.quantity END"
_IN_RANGE = "s.txn_date BETWEEN ? AND ?"


def _df(conn: sqlite3.Connection, sql: str, params: tuple) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def _span(start: date, end: date) -> tuple[str, str]:
    return start.isoformat(), end.isoformat()


def date_bounds(conn: sqlite3.Connection) -> tuple[date, date]:
    lo, hi = conn.execute("SELECT MIN(txn_date), MAX(txn_date) FROM sales").fetchone()
    return date.fromisoformat(lo), date.fromisoformat(hi)


# ── Sales ──────────────────────────────────────────────────────────────────

def total_units(conn, start: date, end: date) -> float:
    return conn.execute(
        f"SELECT COALESCE(SUM({_SIGNED_QTY}), 0) FROM sale_line_items li JOIN sales s ON s.id = li.sale_id "
        f"WHERE {_IN_RANGE}", _span(start, end)).fetchone()[0]


def total_revenue(conn, start: date, end: date) -> float:
    return conn.execute(f"SELECT COALESCE(SUM({_SIGNED_REVENUE}), 0) FROM sales s WHERE {_IN_RANGE}",
                        _span(start, end)).fetchone()[0]


def avg_deal_size(conn, start: date, end: date) -> float:
    deals = conn.execute(f"SELECT COUNT(*) FROM sales s WHERE s.txn_type != 'CreditMemo' AND {_IN_RANGE}",
                         _span(start, end)).fetchone()[0]
    return total_revenue(conn, start, end) / deals if deals else 0


def units_by_model(conn, start: date, end: date) -> pd.DataFrame:
    return _df(conn, f"""
        SELECT li.item_name AS item_name, SUM({_SIGNED_QTY}) AS units
        FROM sale_line_items li JOIN sales s ON s.id = li.sale_id
        WHERE {_IN_RANGE}
        GROUP BY li.item_name HAVING units > 0 ORDER BY units DESC""", _span(start, end))


def trend_grain(start: date, end: date) -> tuple[str, str]:
    days = (end - start).days + 1
    if days <= 31:
        return "D", "day"
    if days <= 186:
        return "W-MON", "week"
    return "MS", "month"


def _bucket_start(d: date, freq: str) -> pd.Timestamp:
    ts = pd.Timestamp(d)
    if freq == "W-MON":
        return ts - pd.Timedelta(days=ts.weekday())
    if freq == "MS":
        return ts.replace(day=1)
    return ts


def units_trend(conn, start: date, end: date, freq: str) -> pd.DataFrame:
    df = _df(conn, f"""
        SELECT s.txn_date AS txn_date, {_SIGNED_QTY} AS qty
        FROM sale_line_items li JOIN sales s ON s.id = li.sale_id WHERE {_IN_RANGE}""", _span(start, end))
    df["txn_date"] = pd.to_datetime(df["txn_date"])
    periods = pd.date_range(_bucket_start(start, freq), _bucket_start(end, freq), freq=freq)
    totals = (df.set_index("txn_date")["qty"].resample(freq, label="left", closed="left").sum()
              if not df.empty else pd.Series(dtype=float))
    return totals.reindex(periods, fill_value=0).rename_axis("period").reset_index(name="units")


def units_by_city(conn, start: date, end: date) -> pd.DataFrame:
    return _df(conn, f"""
        SELECT c.name AS city, c.lat, c.lon, c.warehouse, SUM({_SIGNED_QTY}) AS units
        FROM sale_line_items li
        JOIN sales s ON s.id = li.sale_id
        JOIN customers cu ON cu.id = s.customer_id
        JOIN cities c ON c.name = cu.city
        WHERE {_IN_RANGE}
        GROUP BY c.name HAVING units > 0 ORDER BY units DESC""", _span(start, end))


# ── Acquisition (leads, channels, ad spend) ───────────────────────────────

def new_customers_by_channel(conn, start: date, end: date) -> pd.DataFrame:
    return _df(conn, """
        SELECT channel, COUNT(*) AS customers FROM customers
        WHERE acquired_on BETWEEN ? AND ? GROUP BY channel""", _span(start, end))


def lead_conversion(conn, start: date, end: date) -> tuple[int, int]:
    """(leads created in range, how many of those became customers)."""
    total, converted = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(converted), 0) FROM leads WHERE created_on BETWEEN ? AND ?",
        _span(start, end)).fetchone()
    return total, converted


def ad_spend_in_range(conn, start: date, end: date) -> pd.Series:
    """Spend per paid channel, prorating monthly budgets by how many of each
    month's days fall inside the range."""
    df = _df(conn, "SELECT month, channel, spend FROM ad_spend", ())
    totals = dict.fromkeys(PAID_CHANNELS, 0.0)
    for month, channel, spend in df.itertuples(index=False):
        first = date.fromisoformat(month)
        last = first.replace(day=monthrange(first.year, first.month)[1])
        overlap = (min(end, last) - max(start, first)).days + 1
        if overlap > 0:
            totals[channel] += spend * overlap / ((last - first).days + 1)
    return pd.Series(totals)


def cost_per_customer(conn, start: date, end: date) -> pd.DataFrame:
    """Ad spend / new customers, per paid channel. Channels with no new
    customers in the range are dropped (cost per customer is undefined)."""
    spend = ad_spend_in_range(conn, start, end)
    acquired = new_customers_by_channel(conn, start, end).set_index("channel")["customers"]
    rows = [{"channel": ch, "spend": spend[ch], "customers": int(acquired.get(ch, 0))} for ch in PAID_CHANNELS]
    df = pd.DataFrame(rows)
    df = df[df["customers"] > 0].copy()
    df["cpa"] = df["spend"] / df["customers"]
    return df.sort_values("cpa")
