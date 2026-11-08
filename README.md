# EU Defence Tender Monitor

**Live dashboard:** [ADD GITHUB PAGES LINK]

A small pipeline that collects European military procurement notices from the EU's
[Tenders Electronic Daily](https://ted.europa.eu) every morning, validates them and publishes
a dashboard. It asks one simple question: **how much do published defence award notices
actually disclose?**

All data is public. The project uses no API keys, logins or private sources.

## How it works

| Step | What happens | Code |
|---|---|---|
| Fetch | Queries the TED Search API for CPV groups 353 to 358, re-reading the last 7 days to catch corrections | `src/monitor/ted.py` |
| Validate | Checks every notice. Failures go to `data/quarantine.csv` with the reason | `src/monitor/clean.py` |
| Store | Updates `data/notices.csv` by publication number and keeps the first and latest retrieval time | `src/monitor/store.py` |
| Publish | Builds a static page with no external dependencies | `src/monitor/dashboard.py` |
| Schedule | Runs tests and the pipeline daily on GitHub Actions | `.github/workflows/daily.yml` |

## Design choices

- **Every record is traceable.** Each row links to its source notice and carries its retrieval time.
- **Nothing is estimated.** Missing values stay empty. A stated value of 0, or several conflicting amounts, counts as not disclosed.
- **A bad run cannot overwrite good data.** The run stops before writing if TED times out, returns fewer notices than it reports, or more than 20% of notices fail validation.
- **API changes are visible.** `data/run_log.json` records how many notices carry each field, so a field that disappears shows up as 0.
- **Search fields are read conservatively.** TED returns repeated fields as separate lists that are not linked by position, so they are not combined into lot-level rows.

## Limitations

- This is **not** total European defence procurement. Many large purchases never appear on TED, for example under Article 346 TFEU or in government-to-government deals.
- Notice counts measure publication activity, not spending, and one procedure can produce several notices.
- Values are not summed. Doing so properly needs currency conversion and treatment of framework agreements and lots.
- The CPV filter misses defence purchases coded elsewhere and includes any notice carrying one of these codes.
- A low disclosure rate is not evidence of wrongdoing. Buyers may lawfully withhold some information.

## Data

| Column | Meaning |
|---|---|
| `publication_number`, `publication_date` | TED notice identifier and publication date |
| `form_type`, `notice_type`, `procedure_type` | TED classifications. `form_type = result` marks award notices |
| `title`, `buyer_name`, `buyer_country` | As published. English where available; country in ISO alpha-3 |
| `cpv_codes`, `cpv_group` | All CPV codes, and the group of the first military code |
| `winner_names` | Distinct winners named on the notice |
| `total_value`, `total_value_currency` | Stated only if the notice gives exactly one amount and currency |
| `value_disclosed`, `winner_disclosed` | Whether a value above 0 and a winner are stated |
| `source_url` | Source notice on TED |
| `first_retrieved_at`, `last_retrieved_at` | When the pipeline first and last saw the notice (UTC) |

Source: TED, © European Union. Reuse of notices is permitted with attribution
([legal notice](https://ted.europa.eu/en/legal-notice)). Records are shown here after processing.

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q
PYTHONPATH=src python -m monitor.pipeline --days 365
PYTHONPATH=src python -m monitor.audit   # draws 20 records to check by hand
```

## How this was built

The code was written by an AI coding assistant (Claude) under my direction.
[ADD IN YOUR OWN WORDS: what you decided, checked and changed yourself.]

## What I would add next

Bidder counts and legal basis, PDF and press-release sources with evaluated LLM extraction,
real-euro values, and a comparison of what appears on TED with what governments announce.

## Licence

Code: MIT. Independent project, not affiliated with TED or any research institute.
