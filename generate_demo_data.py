"""
Builds demo.db: two years of made-up sales for a fictional compact-equipment
dealer ("Demo Equipment Co."), shaped to look like real business data rather
than a clean textbook curve:

  - seasonality (busy summers) with month-to-month noise on top, plus a few
    one-off events: a supplier delay that hurts a peak month, year-end tax
    buying that spikes a winter month
  - ~12%/year growth, two price increases
  - a new model launched partway through (eating into its older sibling's
    sales) and a model discontinued
  - occasional fleet orders (4-8 units), returns, WA sales tax (Oregon has none)
  - leads by channel with conversion rates that drift month to month, and ad
    spend with a paused channel and a campaign spike

Every name, number, and customer is invented. Deterministic: the same seed
always produces the same data (dates run up to the day it's generated).

    python3 generate_demo_data.py
"""
import math
import random
import sqlite3
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

DB_PATH = "demo.db"
SEED = 7
START = date(2024, 11, 1)
END = date.today()

# ── Business shape ─────────────────────────────────────────────────────────
FIRST_YEAR_UNITS = 430
YEARLY_GROWTH = 0.12
MONTH_WEIGHTS = [18, 21, 34, 48, 67, 72, 69, 58, 44, 31, 24, 19]  # Jan..Dec
MONTH_NOISE = 0.17          # lognormal sigma applied to each calendar month
EVENTS = {                  # one-off multipliers on specific months
    (2025, 6): 0.68,        # supplier delay during peak season
    (2025, 12): 1.45,       # year-end tax-deduction buying
    (2026, 4): 1.18,        # spring promotion
}
PRICE_INCREASES = [(date(2025, 4, 1), 1.06), (date(2026, 3, 1), 1.03)]
NEW_CUSTOMER_SHARE = 0.62   # vs. repeat buyers
RETURN_RATE = 0.025

# (name, list price, popularity, launched, discontinued)
MODELS = [
    ("Compact Excavator X1", 7900, 70, None, None),
    ("Compact Excavator X3", 13500, 95, None, None),
    ("Compact Excavator X3 Plus", 15900, 60, date(2025, 9, 15), None),
    ("Excavator X5", 21500, 30, None, None),
    ("Skid Steer S2", 14200, 62, None, None),
    ("Track Loader T4", 18900, 26, None, None),
    ("Mini Dumper D1", 4900, 45, None, None),
    ("Utility Loader U1", 9800, 22, None, date(2025, 10, 31)),
    ("Forklift F20", 17500, 12, None, None),
]

# (city, state, lat, lon, serving warehouse, relative demand)
CITIES = [
    ("Seattle", "WA", 47.6062, -122.3321, "North Hub", 30),
    ("Bellevue", "WA", 47.6101, -122.2015, "North Hub", 8),
    ("Everett", "WA", 47.9790, -122.2021, "North Hub", 9),
    ("Lynnwood", "WA", 47.8209, -122.3151, "North Hub", 5),
    ("Bellingham", "WA", 48.7519, -122.4787, "North Hub", 7),
    ("Tacoma", "WA", 47.2529, -122.4443, "South Hub", 12),
    ("Olympia", "WA", 47.0379, -122.9007, "South Hub", 6),
    ("Vancouver", "WA", 45.6387, -122.6615, "South Hub", 7),
    ("Portland", "OR", 45.5152, -122.6784, "South Hub", 18),
    ("Salem", "OR", 44.9429, -123.0351, "South Hub", 6),
    ("Eugene", "OR", 44.0521, -123.0868, "South Hub", 5),
    ("Spokane", "WA", 47.6588, -117.4260, "East Hub", 14),
    ("Yakima", "WA", 46.6021, -120.5059, "East Hub", 6),
    ("Kennewick", "WA", 46.2112, -119.1372, "East Hub", 6),
    ("Wenatchee", "WA", 47.4235, -120.3103, "East Hub", 4),
    ("Bend", "OR", 44.0582, -121.3153, "East Hub", 5),
]

# (channel, base share of new customers, base lead->sale conversion, monthly ad budget or None)
CHANNELS = [
    ("Marketplace", 30, 0.17, 3800),
    ("Website", 22, 0.21, None),
    ("Social ads", 16, 0.07, 6500),
    ("Google ads", 14, 0.11, 4500),
    ("Referral", 12, 0.38, None),
    ("Walk-in", 6, 0.45, None),
]
SPEND_NOISE = {"Marketplace": 0.10, "Social ads": 0.20, "Google ads": 0.15}
SPEND_EVENTS = {
    ("Social ads", 2025, 8): 0.0, ("Social ads", 2025, 9): 0.0,   # campaign paused
    ("Google ads", 2026, 3): 1.8, ("Google ads", 2026, 4): 1.6,   # spring campaign
}

NAME_PREFIXES = [
    "Alder", "Basalt", "Cedar Ridge", "Coastline", "Copper Creek", "Douglas", "Evergreen Valley",
    "Fir Point", "Glacier", "Granite", "Harbor", "Highline", "Ironwood", "Juniper", "Lakeside",
    "Maple Grove", "Mossy Rock", "North Fork", "Orchard", "Pinecrest", "Redtail", "River Bend",
    "Sagebrush", "Silver Lake", "Spruce", "Stonegate", "Summit View", "Tidewater", "Timber Creek",
    "Twin Peaks", "Valley View", "Westside", "Whitewater", "Willow", "Windward", "Yellow Pine",
]
NAME_SUFFIXES = [
    "Excavation", "Landscaping", "Construction", "Farms", "Site Works", "Builders", "Earthworks",
    "Tree Care", "Hardscapes", "Contracting", "Ranch", "Nursery", "Paving", "Utilities", "Homes",
]
WA_TAX_RANGE = (0.089, 0.104)

SCHEMA = """
CREATE TABLE cities (name TEXT PRIMARY KEY, state TEXT, lat REAL, lon REAL, warehouse TEXT, tax_rate REAL);
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT REFERENCES cities(name),
                        channel TEXT, acquired_on TEXT);
CREATE TABLE sales (id TEXT PRIMARY KEY, txn_type TEXT, customer_id INTEGER REFERENCES customers(id),
                    txn_date TEXT, total_amt REAL, tax_amt REAL);
CREATE TABLE sale_line_items (sale_id TEXT REFERENCES sales(id), item_name TEXT, quantity REAL, amount REAL);
CREATE TABLE leads (id INTEGER PRIMARY KEY, created_on TEXT, channel TEXT, converted INTEGER);
CREATE TABLE ad_spend (month TEXT, channel TEXT, spend REAL, PRIMARY KEY (month, channel));
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def poisson(rng: random.Random, lam: float) -> int:
    threshold, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def main(db_path: str = DB_PATH) -> None:
    rng = random.Random(SEED)
    for suffix in ("", "-wal", "-shm"):
        Path(db_path + suffix).unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    # Cities, each WA city with its own sales-tax rate.
    tax = {}
    for name, state, lat, lon, hub, _ in CITIES:
        tax[name] = round(rng.uniform(*WA_TAX_RANGE), 3) if state == "WA" else 0.0
        conn.execute("INSERT INTO cities VALUES (?,?,?,?,?,?)", (name, state, lat, lon, hub, tax[name]))

    # Per-month randomness, drawn once so every day in a month shares it.
    month_mult = {
        ym: rng.lognormvariate(0, MONTH_NOISE) * EVENTS.get(ym, 1.0) for ym in months(START, END)
    }
    spend = {}
    for y, mth in months(START, END):
        for channel, _, _, budget in CHANNELS:
            if budget is None:
                continue
            amount = budget * rng.lognormvariate(0, SPEND_NOISE[channel]) * SPEND_EVENTS.get((channel, y, mth), 1.0)
            spend[(channel, y, mth)] = round(amount, -1)
            conn.execute("INSERT INTO ad_spend VALUES (?,?,?)", (date(y, mth, 1).isoformat(), channel, spend[(channel, y, mth)]))
    conversion_noise = {
        (channel, ym): rng.lognormvariate(0, 0.2) for channel, *_ in CHANNELS for ym in months(START, END)
    }

    def channel_weights(day: date) -> list[float]:
        """Paid channels bring in customers roughly in proportion to that month's budget."""
        weights = []
        for channel, share, _, budget in CHANNELS:
            factor = spend[(channel, day.year, day.month)] / budget if budget else 1.0
            weights.append(share * factor)
        return weights

    def model_choices(day: date) -> tuple[list[tuple], list[float]]:
        available, weights = [], []
        x3_plus_out = day >= MODELS[2][3]
        for model in MODELS:
            name, _, popularity, launched, discontinued = model
            if (launched and day < launched) or (discontinued and day > discontinued):
                continue
            weight = popularity
            if name == "Compact Excavator X3" and x3_plus_out:
                weight *= 0.55  # buyers move to the Plus
            if launched:  # new models ramp up over ~3 months
                weight *= min(1.0, 0.25 + (day - launched).days / 120)
            available.append(model)
            weights.append(weight)
        return available, weights

    def price_on(day: date, list_price: float) -> float:
        for effective, factor in PRICE_INCREASES:
            if day >= effective:
                list_price *= factor
        return list_price

    used_names: set[str] = set()
    customers: list[dict] = []
    lead_id = 0
    counters = {"Invoice": 0, "SalesReceipt": 0, "CreditMemo": 0}

    def new_customer(day: date) -> dict:
        nonlocal lead_id
        while True:
            name = f"{rng.choice(NAME_PREFIXES)} {rng.choice(NAME_SUFFIXES)}"
            if name not in used_names:
                used_names.add(name)
                break
        city = rng.choices(CITIES, weights=[c[5] for c in CITIES])[0][0]
        channel = rng.choices([c[0] for c in CHANNELS], weights=channel_weights(day))[0]
        customer = {"id": len(customers) + 1, "name": name, "city": city, "channel": channel,
                    "loyalty": rng.choice([1, 1, 1, 2, 3, 8])}
        customers.append(customer)
        conn.execute("INSERT INTO customers VALUES (?,?,?,?,?)",
                     (customer["id"], name, city, channel, day.isoformat()))

        # The lead that became this customer, plus the leads from the same
        # channel and period that didn't convert.
        base_rate = next(c[2] for c in CHANNELS if c[0] == channel)
        rate = min(0.9, base_rate * conversion_noise[(channel, (day.year, day.month))])
        lead_day = max(START, day - timedelta(days=rng.randint(0, 21)))
        lead_id += 1
        conn.execute("INSERT INTO leads VALUES (?,?,?,1)", (lead_id, lead_day.isoformat(), channel))
        for _ in range(poisson(rng, (1 - rate) / rate)):
            other_day = min(END, max(START, lead_day + timedelta(days=rng.randint(-25, 25))))
            lead_id += 1
            conn.execute("INSERT INTO leads VALUES (?,?,?,0)", (lead_id, other_day.isoformat(), channel))
        return customer

    def write_sale(txn_type: str, customer: dict, day: date, lines: list[tuple]) -> None:
        counters[txn_type] += 1
        sale_id = f"{txn_type}-{counters[txn_type]}"
        subtotal = sum(amount for _, _, amount in lines)
        tax_amt = round(subtotal * tax[customer["city"]], 2)
        conn.execute("INSERT INTO sales VALUES (?,?,?,?,?,?)",
                     (sale_id, txn_type, customer["id"], day.isoformat(), subtotal + tax_amt, tax_amt))
        conn.executemany("INSERT INTO sale_line_items VALUES (?,?,?,?)", [(sale_id, *line) for line in lines])

    day = START
    while day <= END:
        years_in = (day - START).days / 365.25
        units_today = (
            FIRST_YEAR_UNITS * (1 + YEARLY_GROWTH) ** years_in
            * MONTH_WEIGHTS[day.month - 1] / sum(MONTH_WEIGHTS)
            / monthrange(day.year, day.month)[1]
            * month_mult[(day.year, day.month)]
            * (rng.uniform(1.0, 1.4) if day.weekday() < 5 else rng.uniform(0.2, 0.6))
        )
        for _ in range(poisson(rng, units_today / 1.35)):
            if not customers or rng.random() < NEW_CUSTOMER_SHARE:
                customer = new_customer(day)
            else:
                customer = rng.choices(customers, weights=[c["loyalty"] for c in customers])[0]

            available, weights = model_choices(day)
            line_count = 2 if rng.random() < 0.09 else 1
            picked = []
            while len(picked) < line_count:
                model = rng.choices(available, weights=weights)[0]
                if model not in picked:
                    picked.append(model)
            lines = []
            for name, list_price, *_ in picked:
                r = rng.random()
                qty = rng.randint(4, 8) if r < 0.02 else 3 if r < 0.05 else 2 if r < 0.15 else 1
                unit = round(price_on(day, list_price) * rng.uniform(0.92, 1.0) / 50) * 50
                lines.append((name, qty, qty * unit))

            txn_type = "SalesReceipt" if rng.random() < 0.14 else "Invoice"
            write_sale(txn_type, customer, day, lines)

            return_day = day + timedelta(days=rng.randint(4, 35))
            if rng.random() < RETURN_RATE and return_day <= END:
                name, qty, amount = rng.choice(lines)
                write_sale("CreditMemo", customer, return_day, [(name, 1, amount / qty)])
        day += timedelta(days=1)

    conn.execute("INSERT INTO meta VALUES ('source', 'demo')")
    conn.execute("INSERT INTO meta VALUES ('generated_on', ?)", (END.isoformat(),))
    conn.commit()
    conn.close()
    print(f"Wrote {db_path} ({START} to {END}): {len(customers)} customers, {lead_id} leads, "
          + ", ".join(f"{n} {t}" for t, n in counters.items()))


if __name__ == "__main__":
    main()
