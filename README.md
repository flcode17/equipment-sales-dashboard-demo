# Equipment Sales Dashboard — Demo

A demo of a business-metrics dashboard for a fictional compact-equipment
dealer, **Demo Equipment Co.** Use it for screenshots and presentations.

Everything here is invented: the company, customers, models, prices, leads,
and ad spend. The data is generated to look like a real business (seasonal
but uneven months, a product launch and a discontinuation, price increases,
fleet orders, returns, paused ad campaigns) rather than a clean curve.

This folder is fully standalone: no shared code, no credentials, no
connection to any accounting system.

## Run it

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

streamlit run dashboard.py --server.address 127.0.0.1 --server.port 8502
# opens at http://127.0.0.1:8502
```

The dashboard builds `demo.db` itself (about two years of data ending today)
and rebuilds it once a day so the dates stay current. Same random seed every
time, so the history stays consistent.

## Hosting (Streamlit Community Cloud)

1. Sign in at share.streamlit.io with GitHub.
2. Create app → this repo, branch `main`, main file `dashboard.py`.
3. Under Advanced settings, pick Python 3.13.

No secrets or settings needed; the app generates its own data.

## What's on it

- Stat cards: units sold, revenue (net of returns, excluding sales tax), best
  acquisition channel, top model, average deal size, lead → sale rate, best
  cost-per-acquisition channel
- Sales by city (map, bubble size = units, color = serving warehouse)
- Units sold by model, share of new customers by channel, cost per acquired
  customer by paid channel, sales trend
- A timeframe filter (past week / month / 6 months / year / all time / custom
  dates) that applies to every card

## Files

- `generate_demo_data.py` — builds `demo.db`
- `metrics.py` — the calculations behind each card
- `dashboard.py` — the Streamlit app (refuses to open any database not made by the generator)
