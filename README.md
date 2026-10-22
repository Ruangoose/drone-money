# drone-money

Who won the US Department of Defense's drone contract money from 2016 to 2026, and how did the listed drone
makers' shares do against the big defense contractors (the primes)? A study on public data (USAspending.gov,
SEC EDGAR and Kenneth French's factors) and Alpaca's share prices, to 20 October 2026.

The write-up: https://ruangoosen.co.za/projects/drones-vs-primes/

## What it does
- **The drone money:** DoD contract obligations under product code 1550 (unmanned aircraft) by fiscal year,
  split between the primes, the listed drone makers, the large private firms and everyone else. Then the same
  with the contracts that name loitering munitions or counter-drone systems added, since those sit under other
  codes.
- **Two baskets, by rules fixed on 21 October 2026, before any share prices were downloaded:**
  - *Drone makers:* 10-Ks found by EDGAR full-text search for phrases such as "our drones" and "counter-UAS";
    at least 5 drone terms per 10,000 words; drones a reportable segment or the main business
    (`config/drone-materiality.csv`, with the 10-K for each decision); listed on NYSE, Nasdaq or NYSE American;
    a median of at least $5 million traded a day over the previous 63 sessions.
  - *Primes:* the six largest US-listed companies by DoD contract obligations each fiscal year, among those
    with at least half their DoD money under defense manufacturing industry codes. A fiscal year's ranking
    sets the next calendar year's basket. Recipients are grouped by their own names, with mergers applied by
    year (`drones/companies.py`), because USAspending's parent links put old contracts under today's parents.
  - Equal weights, rebalanced monthly. Market-value weights are a check.
- **History:** the baskets and the dollar-neutral pair (long drones, short primes) by period; factor loadings
  on Kenneth French's five factors and momentum, with Newey-West standard errors; the pair's moves around 21
  policy, budget and war dates (`config/events.csv`, each with its primary source), against what its factor
  exposures predict.
- **Valuation:** enterprise value to sales from XBRL filings as published at each month end, so there's no
  hindsight.
- **Checks on the screen:** broader EDGAR searches for companies the phrases missed, those that stopped filing
  included, with each candidate's outcome under every rule (`output/screen-candidates.csv`).

The study describes the past. It makes no forecast and no recommendation, and it isn't investment advice.

## Rerun
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q     # checks on made-up data, no downloads
.venv\Scripts\python run.py           # from the screens in data/screen/; downloads the rest
.venv\Scripts\python run.py --refresh # reruns the EDGAR and USAspending screens too (it reads every 10-K)
```
Downloading needs two things:
- a free Alpaca key pair in `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`;
- your name and email in `SEC_USER_AGENT` (for example `Jane Doe jane@example.com`): the SEC asks every
  script to name a contact.

Share prices end on 20 October 2026 (`END` in `drones/study.py`). Kenneth French's daily factors ended on 31
August 2026 when the study ran. DoD's contract data reaches USAspending up to 90 days late, so fiscal 2026 is
incomplete. Downloads are cached in `data/cache/` (git-ignored); set `DVP_REFRESH=1` to fetch them again.
On Windows, keep the clone at a short path: with long paths switched off, pip can install statsmodels
incompletely without an error.

## Output
- `data/screen/`: the EDGAR screens and the USAspending tables (public data).
- `output/membership.csv`: each name's eligibility spells, with the 10-K or the ranking behind it;
  `rebalances.csv`: the names each basket held at each monthly rebalance.
- `output/performance.csv`: return, volatility and worst fall by period; `attribution.json`: factor loadings.
- `output/screen-candidates.csv` and `screen-check-summary.json`: the checks on the screen.
- `output/site/`: the JSON the web page is built from.

## Share prices
Alpaca's market data is for personal, non-commercial use, and none of it may be republished without Alpaca's
written consent. Alpaca agreed on 22 October 2026 to the web page charting the baskets and the pair indexed
to 100, the pair's moves around the catalyst dates and EV/sales over time, each credited, with no raw prices
and no data to download. So this repo holds no price or return series: the series behind those charts go to
`output/site/shares.json`, and the daily series to `output/`, all git-ignored. What is committed are summary
figures computed from the prices (returns and volatility by period, factor loadings, valuation multiples).

See [SOURCES.md](SOURCES.md) for every source, its terms and its limits.

Code: MIT licence. Ruan Goosen.
