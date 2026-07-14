# Argentina vs England — World Cup 2026 Semifinal Prediction

A hybrid **Poisson + Elo** statistical model projecting the outcome of the FIFA World Cup 2026
semifinal between Argentina and England (kickoff 2026-07-16 02:00 GMT+7, Atlanta, neutral venue),
built entirely from real historical international match data — no fabricated or hand-typed stats.

> **Educational / illustrative use only.** This is a probabilistic projection generated ahead of
> kickoff, not a report of an actual result.

## Headline result

| Outcome | Probability |
|---|---|
| **Argentina win** | **47.0%** |
| Draw | 28.3% |
| England win | 24.7% |

Most likely scoreline: **1-0 Argentina** (17.1%).

## How the prediction is made

Two independent submodels are computed from the same historical dataset, then blended:

- **Poisson submodel (60% weight)** — estimates each team's expected goals (λ) from attack/defense
  strength over a rolling 5-year window, then derives win/draw/loss probabilities by summing a
  Poisson scoreline grid (0–10 × 0–10).
- **Elo submodel (40% weight)** — builds each team's Elo rating chronologically across ~49,500
  historical matches (K=32, +65 home advantage on non-neutral matches, goal-difference multiplier),
  then converts the rating gap into a 3-outcome win/draw/loss split using a **Davidson tie-adjusted
  Bradley-Terry model**, whose draw parameter (ν) is calibrated by maximum likelihood against the
  full historical record rather than hand-tuned.

Final probabilities = `0.6 × Poisson + 0.4 × Elo`, renormalized to sum to 100%.

The full step-by-step derivation (every formula, every intermediate number) is in the
[methodology report](#report-files) below.

## Data source

[`martj42/international_results`](https://github.com/martj42/international_results) — a
continuously updated public dataset of international football results since 1872. As of this
project's data snapshot (2026-07-11), it already includes this tournament's real results for both
teams through the quarterfinal round; the semifinal fixture itself is present as an unplayed
placeholder and is excluded from all calculations.

## Project structure

```
data_prep.py               Downloads/caches match data, builds Elo history, calibrates the
                            Davidson draw parameter, computes Poisson attack/defense strengths,
                            head-to-head record, and recent form -> data/model_inputs.json
predict.py                 Computes both submodels, blends 60/40, prints a console breakdown,
                            writes prediction_results.json, and triggers the HTML report
generate_report.py         Renders prediction_results.json into report.html
generate_docx_report.py    Renders prediction_results.json into a detailed Word methodology report

data/results_raw.csv       Cached raw download of the historical match dataset
data/model_inputs.json     Intermediate computed inputs (Elo, Poisson strengths, form, h2h)
prediction_results.json    Final structured prediction output
```

## Report files

| File | Description |
|---|---|
| `report.html` | Interactive-style visual summary (prediction cards, submodel breakdown, team comparison, scorelines, head-to-head) |
| `Argentina vs England - Prediction Methodology Report.docx` | Detailed written methodology report — every formula and calculation step, from raw Elo/goal data to the final blended result |
| `Argentina vs England - Prediction Methodology Report.pdf` | PDF export of the same methodology report |

## Running it

```bash
python data_prep.py   # downloads data, builds Elo/Poisson/form inputs
python predict.py      # computes the blended prediction, writes JSON + HTML report
python generate_docx_report.py   # writes the detailed Word methodology report
```

Requires `pandas`, `numpy`, and (for the Word report) `python-docx`.

## Key limitations

- Poisson attack/defense strength is not opponent-adjusted (strength-of-schedule bias).
- The two teams' goals are modeled as statistically independent (no Dixon-Coles correlation
  correction).
- Head-to-head record and recent form are shown for context only — they do not feed the model.
- The source dataset has no penalty-shootout field, so historical ties decided on penalties are
  recorded as draws.
- No player-level, injury, or lineup information is modeled.

See the methodology report's "Limitations and Caveats" section for the full list.

---
*Sachi Singh - FIFA World Cup Semifinal Analysis - EDUCATIONAL PURPOSES ONLY*
