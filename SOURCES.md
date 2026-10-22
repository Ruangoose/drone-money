# Sources and terms

Checked 21 and 22 October 2026.

| Source | What | Route | Terms |
|---|---|---|---|
| USAspending.gov | DoD contract obligations (award types A to D) by recipient, product code and industry code, fiscal years 2015 to 2026; contract actions whose descriptions name loitering munitions or counter-drone systems | `api.usaspending.gov`, no key | US government data, public |
| SEC EDGAR | Full-text search of 10-Ks; 10-K documents (drone intensity, segments, listing); XBRL company facts (revenue, debt, cash, shares) | `efts.sec.gov`, `data.sec.gov` and `sec.gov/Archives`, no key; a User-Agent naming a contact is required | US government work, public domain; fair-access limit of 10 requests a second |
| Kenneth R. French Data Library | Daily five factors (2x3) and momentum | `mba.tuck.dartmouth.edu`, no key | No stated terms; only results derived from them (loadings, alpha, t-statistics) are published, never the factor series |
| Alpaca market data | Daily bars since 2016 for the basket companies (consolidated SIP feed; adjusted for splits and dividends for returns, raw closes for market values) | `data.alpaca.markets`, free key pair | Personal, non-commercial use; nothing may be republished without Alpaca's written consent. Alpaca agreed by email on 22 October 2026 to the web page charting the baskets and the pair indexed to 100, the pair's moves around the catalyst dates and EV/sales over time, credited "Source: Alpaca", with no raw prices, no tables of daily prices, no quotes and no data to download. So prices and the series behind those charts are never committed |
| Primary sources in `config/` | The dates in `events.csv` and the facts in `background.csv` (company releases and filings, the FY2027 budget request, the House budget resolution, the continuing resolution, the Drone Dominance Program's vendor list), each with its link | the links in each file | as each source |

Not used: FINRA short interest, option prices, and Yahoo, S&P, MSCI, ICE and Bloomberg data.

## Limits
- **Thin history.** The drone basket starts in February 2017 and holds only AeroVironment and Kratos for most
  of 2017 to 2024. Its results are mostly those two companies'.
- **Code 1550 understates drones.** Loitering munitions (Switchblade, LASSO) sit mainly under code 1425
  (guided missile systems), and counter-drone work has no code of its own. Adding only the contracts whose
  descriptions name them misses those described generically, so it understates them too. Adding code 1425
  whole would swamp the series with the primes' missiles.
- **Fiscal 2026 is incomplete:** DoD's contract data reaches USAspending up to 90 days late.
- **The factors end on 31 August 2026,** so the last two catalysts have raw returns only.
- **Recipient groups** are matched by name (`drones/companies.py`). "Private" means General Atomics, Anduril,
  Shield AI and Skydio; other private firms fall under "other".
- **The screen** can miss a company whose 10-Ks never use one of its phrases; the broader check (`drones/reach.py`)
  searched for that and found none that would have joined the basket.
