# Tehran Market Data

![tests](https://github.com/Amir-Shokat/tehran-market-data/actions/workflows/tests.yml/badge.svg)

Python clients for Iranian capital-market data, and a network analysis of who runs the
country's mutual funds. These are the data-collection tools behind my risk reporting work at
an investment bank in Tehran (2025-2026), rewritten from one-off notebooks into a tested
package.

| Source | What you get | Module |
|---|---|---|
| **TSETMC** (Tehran Stock Exchange) | daily price history, instrument data incl. *base volume*, daily major-shareholder lists, multi-instrument shareholder panels | `tsetmc` |
| **FIPIRAN** (fund registry) | every registered mutual fund with size, NAVs, returns, manager and guarantor | `fipiran` |
| **FIPIRAN + TSETMC** | a **daily panel of all funds** (NAV, returns, asset mix, size, firms), with optional licence and investor details and the market index return, built from scratch or updated incrementally | `fund_panel` |
| **Mabna** (paid data vendor) | full instrument master, paginated (bring your own token) | `mabna` |

All clients share an HTTP layer with retries, exponential back-off on 5xx/429 and polite
rate limiting, and they are tested against fake sessions, so the test suite needs no network.

## Fund network: who manages Iran's mutual funds?

`scripts/fund_network.py` links every fund to its manager and guarantor (the bank or broker
that guarantees liquidity), measures concentration and draws an interactive network.

On a FIPIRAN snapshot from April 2025:

```
505 funds with assets, 172 firms, 528 links
manager  : 505 funds (100% of assets) report one; 155 firms; top 5 hold 37.4% of those assets (37.4% of all); HHI 442
guarantor:  43 funds (22% of assets) report one;  29 firms; top 5 hold 66.9% of those assets (14.9% of all); HHI 1,114
```

Fund *management* is fragmented. Liquidity guarantees are much more concentrated: only 43 funds
(holding 22% of all fund assets) report a guarantor in the registry, and among them five banks and
brokers back two thirds of the money. One guarantor alone backs 17.6% of guaranteed assets through a
single large fund. That concentration of counterparty and liquidity risk is invisible when funds are
looked at one by one.

Firm names are normalised first (Arabic vs Persian letters, legal-form suffixes, role
prefixes, spacing). Without that, 6 managers appear twice under different spellings.

## Quick start

```bash
git clone https://github.com/Amir-Shokat/tehran-market-data.git
cd tehran-market-data
pip install -e ".[dev,viz]"
pytest

python scripts/fund_network.py --out output          # writes concentration tables + fund_network.html
python scripts/fund_panel.py --start 2025-02-17 --out funds.parquet   # daily panel of all funds
python scripts/fund_panel.py --update funds.parquet                    # later: append only the new days
python scripts/shareholder_panel.py instruments.csv --start 20250101 --filter-type 8
export MABNA_TOKEN=...                                # only for the Mabna client
```

```python
from tehran_data import TsetmcClient
tse = TsetmcClient()
prices = tse.closing_prices(inscode)                   # DataFrame indexed by date
tse.base_volume(inscode, "20250621")
tse.shareholders(inscode, "20250831")
```

Note: TSETMC and FIPIRAN are often unreachable from outside Iran.

## History

This repository merges two earlier projects: notebooks I wrote at work, and my public
[Fipiran-Web-Scraping-Iran-mutual-fund-Market](https://github.com/Amir-Shokat/Fipiran-Web-Scraping-Iran-mutual-fund-Market)
repository, whose fund-panel scraper now lives in `fund_panel.py`.

## Changes from the original notebooks

* **Credentials removed.** An API token was hard-coded in a notebook. Tokens now come only from
  environment variables (that token should be considered exposed and revoked).
* The shareholder panel requested **every calendar day**; the exchange trades Saturday to
  Wednesday, so Thursdays and Fridays are now skipped (about 30% fewer requests).
* One failed request no longer silently drops data. Failures are logged per instrument and day,
  and transient errors are retried.
* Manager and guarantor fields come back from FIPIRAN either as nested objects or as temporary
  name fields; both are handled.
* A sample graph containing personal names was removed; the network is built from the
  registry's company data only.
* **Fund panel (from the old Fipiran repository):** details were requested for every fund on
  every date, including fund-date pairs that do not exist; now only funds present on a date are
  requested. Missing numbers no longer become the text "nan", 17-digit instrument codes are kept
  exact, percentages are converted once, and everything runs in memory instead of through
  temporary Excel files. The old README promised a quick update from a file the repository did
  not contain; `update_panel` now appends new days to any existing CSV or Parquet panel.
* An experimental scraper for a currency-rate website was dropped. It never worked reliably
  (the site renders with JavaScript and blocks bots).

## Data and privacy

No data is included in this repository. Shareholder lists published by TSETMC can include
names of individual investors; if you collect them, handle them under your local
data-protection rules.

## License

MIT
