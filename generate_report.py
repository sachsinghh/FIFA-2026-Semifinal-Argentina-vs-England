"""
Renders prediction_results.json into a styled, self-contained report.html.
Palette validated with the dataviz skill's validate_palette.js (3-slot categorical,
light+dark, all checks pass; the draw/yellow slot needs visible direct labels on
light surfaces per the relief rule, which this template always provides).
"""

import json
import os

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  color-scheme: light;
  --surface: #fcfcfb;
  --page: #f9f9f7;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --gridline: #e1e0d9;
  --border: rgba(11,11,11,0.10);
  --series-a: #2a78d6;   /* Argentina */
  --series-draw: #eda100; /* Draw */
  --series-b: #e34948;   /* England */
}

@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --surface: #1a1a19;
    --page: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --gridline: #2c2c2a;
    --border: rgba(255,255,255,0.10);
    --series-a: #3987e5;
    --series-draw: #c98500;
    --series-b: #e66767;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface: #1a1a19;
  --page: #0d0d0d;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted: #898781;
  --gridline: #2c2c2a;
  --border: rgba(255,255,255,0.10);
  --series-a: #3987e5;
  --series-draw: #c98500;
  --series-b: #e66767;
}

body {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background-color: var(--page);
  color: var(--text-primary);
  line-height: 1.5;
  padding: 24px 16px 64px;
}

.container { max-width: 920px; margin: 0 auto; }

.disclaimer {
  background-color: var(--surface);
  border: 1px solid var(--series-draw);
  border-left: 4px solid var(--series-draw);
  border-radius: 4px;
  padding: 12px 16px;
  margin-bottom: 24px;
  font-size: 14px;
  color: var(--text-secondary);
}
.disclaimer strong { color: var(--text-primary); }

header {
  border-bottom: 2px solid var(--gridline);
  padding-bottom: 20px;
  margin-bottom: 32px;
}
h1 { font-size: 26px; font-weight: 600; margin-bottom: 8px; }
.match-meta { color: var(--text-secondary); font-size: 14px; }
.match-meta div { margin-top: 2px; }

.section {
  background-color: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 20px 24px;
  margin-bottom: 20px;
}
h2 { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
h3 { font-size: 13px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.03em; margin: 16px 0 8px; }

.prediction-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.card {
  border: 1px solid var(--gridline);
  border-radius: 4px;
  padding: 16px;
  text-align: center;
}
.card-outcome { font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.card-value { font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; }
.card.team-a .card-value { color: var(--series-a); }
.card.draw .card-value { color: var(--series-draw); }
.card.team-b .card-value { color: var(--series-b); }
.card.highlight { border-color: currentColor; border-width: 2px; }

.bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; font-size: 13px; }
.bar-label { width: 130px; flex-shrink: 0; color: var(--text-secondary); }
.bar-track { flex: 1; background-color: var(--gridline); border-radius: 3px; overflow: hidden; height: 18px; position: relative; }
.bar-fill { height: 100%; display: flex; align-items: center; }
.bar-fill.team-a { background-color: var(--series-a); }
.bar-fill.draw { background-color: var(--series-draw); }
.bar-fill.team-b { background-color: var(--series-b); }
.bar-value { width: 52px; flex-shrink: 0; text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--gridline); }
th { color: var(--text-secondary); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.02em; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }

.comparison { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.team-stats dt { color: var(--text-secondary); font-size: 12px; margin-top: 10px; }
.team-stats dd { font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }

.scoreline-callout {
  display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px;
}
.scoreline-callout .score { font-size: 32px; font-weight: 700; font-variant-numeric: tabular-nums; }
.scoreline-callout .prob { color: var(--text-secondary); font-size: 14px; }

ul.caveats { padding-left: 20px; font-size: 13px; color: var(--text-secondary); }
ul.caveats li { margin-bottom: 6px; }

footer { color: var(--text-muted); font-size: 12px; text-align: center; margin-top: 32px; }
footer a { color: var(--text-muted); }
"""


def _bar_row(label, value, css_class):
    pct = value * 100
    label_inside = f'{pct:.1f}%' if pct >= 12 else ""
    return f"""
    <div class="bar-row">
      <div class="bar-label">{label}</div>
      <div class="bar-track">
        <div class="bar-fill {css_class}" style="width:{pct:.1f}%;"></div>
      </div>
      <div class="bar-value">{pct:.1f}%</div>
    </div>"""


def render(results, out_path):
    team_a = results["predictions"]["team_a"]
    team_b = results["predictions"]["team_b"]
    preds = results["predictions"]
    poisson = results["submodels"]["poisson"]
    elo = results["submodels"]["elo_davidson"]
    stats_a = results["team_stats"]["team_a"]
    stats_b = results["team_stats"]["team_b"]
    h2h = results["h2h_record"]
    meth = results["methodology"]
    venue = results.get("venue")

    outcomes = {
        f"{team_a} Win": preds["team_a_win"],
        "Draw": preds["draw"],
        f"{team_b} Win": preds["team_b_win"],
    }
    most_likely_outcome = max(outcomes, key=outcomes.get)

    venue_line = ""
    if venue:
        venue_line = f"<div>Venue: {venue['city']}, {venue['country']} ({'neutral' if venue['neutral'] else 'home advantage'})</div>"

    prediction_cards = f"""
    <div class="prediction-cards">
      <div class="card team-a {'highlight' if most_likely_outcome == f'{team_a} Win' else ''}" style="color:var(--series-a)">
        <div class="card-outcome">{team_a} Win</div>
        <div class="card-value">{preds['team_a_win']*100:.1f}%</div>
      </div>
      <div class="card draw {'highlight' if most_likely_outcome == 'Draw' else ''}" style="color:var(--series-draw)">
        <div class="card-outcome">Draw</div>
        <div class="card-value">{preds['draw']*100:.1f}%</div>
      </div>
      <div class="card team-b {'highlight' if most_likely_outcome == f'{team_b} Win' else ''}" style="color:var(--series-b)">
        <div class="card-outcome">{team_b} Win</div>
        <div class="card-value">{preds['team_b_win']*100:.1f}%</div>
      </div>
    </div>"""

    blended_bars = (
        _bar_row(f"{team_a} win", preds["team_a_win"], "team-a")
        + _bar_row("Draw", preds["draw"], "draw")
        + _bar_row(f"{team_b} win", preds["team_b_win"], "team-b")
    )

    submodel_table = f"""
    <table>
      <thead><tr><th>Model</th><th class="num">{team_a} Win</th><th class="num">Draw</th><th class="num">{team_b} Win</th></tr></thead>
      <tbody>
        <tr><td>Poisson (expected goals)</td><td class="num">{poisson['team_a_win']*100:.1f}%</td><td class="num">{poisson['draw']*100:.1f}%</td><td class="num">{poisson['team_b_win']*100:.1f}%</td></tr>
        <tr><td>Elo (Davidson tie-adjusted)</td><td class="num">{elo['team_a_win']*100:.1f}%</td><td class="num">{elo['draw']*100:.1f}%</td><td class="num">{elo['team_b_win']*100:.1f}%</td></tr>
        <tr><td><strong>Blended ({int(meth['blend_weights']['poisson']*100)}% Poisson / {int(meth['blend_weights']['elo']*100)}% Elo)</strong></td>
            <td class="num"><strong>{preds['team_a_win']*100:.1f}%</strong></td>
            <td class="num"><strong>{preds['draw']*100:.1f}%</strong></td>
            <td class="num"><strong>{preds['team_b_win']*100:.1f}%</strong></td></tr>
      </tbody>
    </table>"""

    comparison = f"""
    <div class="comparison">
      <dl class="team-stats">
        <h3>{team_a}</h3>
        <dt>Elo rating</dt><dd>{stats_a['elo']:.1f}</dd>
        <dt>Expected goals (&lambda;)</dt><dd>{poisson['lambda_team_a']:.2f}</dd>
        <dt>Attack / Defense index</dt><dd>{stats_a['attack_strength']:.2f} / {stats_a['defense_strength']:.2f}</dd>
        <dt>Last 10 matches: PPG / GF / GA</dt><dd>{stats_a['form']['ppg']:.2f} / {stats_a['form']['gf_avg']:.2f} / {stats_a['form']['ga_avg']:.2f}</dd>
      </dl>
      <dl class="team-stats">
        <h3>{team_b}</h3>
        <dt>Elo rating</dt><dd>{stats_b['elo']:.1f}</dd>
        <dt>Expected goals (&lambda;)</dt><dd>{poisson['lambda_team_b']:.2f}</dd>
        <dt>Attack / Defense index</dt><dd>{stats_b['attack_strength']:.2f} / {stats_b['defense_strength']:.2f}</dd>
        <dt>Last 10 matches: PPG / GF / GA</dt><dd>{stats_b['form']['ppg']:.2f} / {stats_b['form']['gf_avg']:.2f} / {stats_b['form']['ga_avg']:.2f}</dd>
      </dl>
    </div>"""

    top_scorelines_rows = "".join(
        f"<tr><td>{s['score']}</td><td class='num'>{s['probability']*100:.1f}%</td></tr>"
        for s in poisson["top_scorelines"]
    )
    scoreline_section = f"""
    <div class="scoreline-callout">
      <div class="score">{poisson['most_likely_score']}</div>
      <div class="prob">most likely scoreline ({poisson['top_scorelines'][0]['probability']*100:.1f}% of simulated outcomes)</div>
    </div>
    <table>
      <thead><tr><th>Scoreline</th><th class="num">Probability</th></tr></thead>
      <tbody>{top_scorelines_rows}</tbody>
    </table>"""

    last_match = h2h.get("last_match")
    last_match_line = ""
    if last_match:
        last_match_line = (
            f"<div>Last meeting: {last_match['date']} &mdash; "
            f"{last_match['home_team']} {last_match['home_score']}-{last_match['away_score']} {last_match['away_team']} "
            f"({last_match['tournament']})</div>"
        )
    a_wins_key = f"{team_a.lower()}_wins"
    b_wins_key = f"{team_b.lower()}_wins"
    h2h_section = f"""
    <p style="margin-bottom:12px; font-size:14px; color:var(--text-secondary);">
      {h2h['total_meetings']} all-time meetings: {h2h[a_wins_key]} {team_a} wins, {h2h['draws']} draws, {h2h[b_wins_key]} {team_b} wins.
    </p>
    {_bar_row(f'{team_a} wins', h2h[a_wins_key] / max(h2h['total_meetings'],1), 'team-a')}
    {_bar_row('Draws', h2h['draws'] / max(h2h['total_meetings'],1), 'draw')}
    {_bar_row(f'{team_b} wins', h2h[b_wins_key] / max(h2h['total_meetings'],1), 'team-b')}
    {last_match_line}
    <p style="margin-top:10px; font-size:12px; color:var(--text-muted);">
      Note: the underlying dataset has no penalty-shootout field, so any past meeting decided on penalties is recorded as a draw.
    </p>"""

    caveats_html = "".join(f"<li>{c}</li>" for c in results["caveats"])

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{team_a} vs {team_b} — World Cup 2026 Semifinal Prediction</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">

  <div class="disclaimer">
    <strong>Statistical projection, not a result.</strong> This report was generated ahead of kickoff
    ({results['match_date_local']}) using a hybrid Poisson + Elo model built on real historical match
    data (as of {results['data_as_of']}). It is a probabilistic forecast, not a report of what actually happened.
  </div>

  <header>
    <h1>{results['match']}</h1>
    <div class="match-meta">
      <div>Kickoff: {results['match_date_local']}</div>
      {venue_line}
      <div>Data as of: {results['data_as_of']}</div>
    </div>
  </header>

  <div class="section">
    <h2>Blended Prediction</h2>
    {prediction_cards}
    {blended_bars}
  </div>

  <div class="section">
    <h2>Submodel Breakdown</h2>
    {submodel_table}
  </div>

  <div class="section">
    <h2>Team Comparison</h2>
    {comparison}
  </div>

  <div class="section">
    <h2>Most Likely Scoreline (Poisson grid)</h2>
    {scoreline_section}
  </div>

  <div class="section">
    <h2>Head-to-Head</h2>
    {h2h_section}
  </div>

  <div class="section">
    <h2>Methodology</h2>
    <p style="font-size:14px; color:var(--text-secondary); margin-bottom:10px;">
      <strong>Poisson submodel:</strong> each team's expected goals (&lambda;) are derived from attack strength
      (goals scored vs. league average) and defense strength (goals conceded vs. league average) over a
      rolling {meth['poisson_window_years']}-year window, with no home-advantage adjustment since this is a neutral venue.
      Win/draw/loss probabilities and the most likely scoreline come from summing the Poisson probability mass
      over a 0&ndash;10 &times; 0&ndash;10 scoreline grid.
    </p>
    <p style="font-size:14px; color:var(--text-secondary); margin-bottom:10px;">
      <strong>Elo submodel:</strong> ratings are built chronologically from {meth['elo_n_matches_used']:,} historical matches
      since {meth['elo_history_start']} (K-factor {meth['elo_k_factor']:.0f}, goal-difference multiplier capped at 1.75,
      +{meth['elo_home_advantage']:.0f} home-advantage adjustment on non-neutral historical matches only). The two-team Elo gap is
      converted into a 3-outcome win/draw/loss split using a Davidson tie-adjusted Bradley-Terry model, whose draw
      parameter (&nu; = {meth['davidson_nu']:.2f}) was calibrated by maximum likelihood against the full historical
      match log rather than hand-tuned.
    </p>
    <p style="font-size:14px; color:var(--text-secondary);">
      <strong>Blend:</strong> final probabilities = {meth['blend_weights']['poisson']*100:.0f}% &times; Poisson +
      {meth['blend_weights']['elo']*100:.0f}% &times; Elo, renormalized to sum to 100%.
    </p>
  </div>

  <div class="section">
    <h2>Caveats</h2>
    <ul class="caveats">{caveats_html}</ul>
  </div>

  <footer>
    Data source: martj42/international_results (GitHub) &middot; Generated {results['generated_at']}
  </footer>

</div>
</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base_dir, "prediction_results.json")) as f:
        results = json.load(f)
    render(results, os.path.join(base_dir, "report.html"))
    print("[OK] report.html regenerated")
