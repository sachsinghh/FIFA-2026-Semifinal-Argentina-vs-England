"""
Predict Argentina vs England outcome using a hybrid Poisson + Elo model,
blended 60% Poisson / 40% Elo (Davidson tie-adjusted).
"""

import json
import math
import os
from datetime import datetime, timezone

import numpy as np

import generate_report

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_INPUTS_PATH = os.path.join(BASE_DIR, "data", "model_inputs.json")
RESULTS_PATH = os.path.join(BASE_DIR, "prediction_results.json")
REPORT_PATH = os.path.join(BASE_DIR, "report.html")

POISSON_WEIGHT = 0.6
ELO_WEIGHT = 0.4
MAX_GOALS = 10


def poisson_pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def poisson_submodel(lambda_a, lambda_b):
    grid = {}
    p_a_win = p_draw = p_b_win = 0.0
    for i in range(MAX_GOALS + 1):
        pi = poisson_pmf(i, lambda_a)
        for j in range(MAX_GOALS + 1):
            pj = poisson_pmf(j, lambda_b)
            p = pi * pj
            grid[(i, j)] = p
            if i > j:
                p_a_win += p
            elif i == j:
                p_draw += p
            else:
                p_b_win += p

    total = p_a_win + p_draw + p_b_win
    p_a_win, p_draw, p_b_win = p_a_win / total, p_draw / total, p_b_win / total

    top_scores = sorted(grid.items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_scorelines = [{"score": f"{i}-{j}", "probability": round(p / total, 4)} for (i, j), p in top_scores]

    return {
        "team_a_win": p_a_win,
        "draw": p_draw,
        "team_b_win": p_b_win,
        "lambda_team_a": lambda_a,
        "lambda_team_b": lambda_b,
        "most_likely_score": top_scorelines[0]["score"],
        "top_scorelines": top_scorelines,
    }


def davidson_elo_submodel(elo_a, elo_b, nu):
    pi_a = 10 ** (elo_a / 400.0)
    pi_b = 10 ** (elo_b / 400.0)
    sqrt_term = math.sqrt(pi_a * pi_b)
    denom = pi_a + pi_b + nu * sqrt_term

    p_a_win = pi_a / denom
    p_b_win = pi_b / denom
    p_draw = nu * sqrt_term / denom

    return {
        "team_a_win": p_a_win,
        "draw": p_draw,
        "team_b_win": p_b_win,
        "elo_team_a": elo_a,
        "elo_team_b": elo_b,
        "davidson_nu": nu,
    }


def compute_lambda(poisson_a, poisson_b):
    league_avg = poisson_a["league_avg_goals"]
    attack_a = poisson_a["goals_for_avg"] / league_avg
    defense_a = poisson_a["goals_against_avg"] / league_avg
    attack_b = poisson_b["goals_for_avg"] / league_avg
    defense_b = poisson_b["goals_against_avg"] / league_avg

    lambda_a = attack_a * defense_b * league_avg
    lambda_b = attack_b * defense_a * league_avg

    strengths = {
        "league_avg_goals": league_avg,
        "attack_team_a": attack_a,
        "defense_team_a": defense_a,
        "attack_team_b": attack_b,
        "defense_team_b": defense_b,
    }
    return lambda_a, lambda_b, strengths


def main():
    with open(MODEL_INPUTS_PATH) as f:
        inputs = json.load(f)

    team_a, team_b = inputs["team_a"], inputs["team_b"]

    lambda_a, lambda_b, strengths = compute_lambda(inputs["poisson"]["team_a"], inputs["poisson"]["team_b"])
    poisson_result = poisson_submodel(lambda_a, lambda_b)

    elo_result = davidson_elo_submodel(
        inputs["elo"]["team_a"], inputs["elo"]["team_b"], inputs["elo"]["davidson_nu"]
    )

    poisson_vec = np.array([poisson_result["team_a_win"], poisson_result["draw"], poisson_result["team_b_win"]])
    elo_vec = np.array([elo_result["team_a_win"], elo_result["draw"], elo_result["team_b_win"]])
    blend = POISSON_WEIGHT * poisson_vec + ELO_WEIGHT * elo_vec
    blend = blend / blend.sum()

    print(f"=== {team_a} vs {team_b} - Hybrid Poisson + Elo Prediction ===\n")
    print(f"Data as of: {inputs['data_as_of']}")
    if inputs.get("fixture"):
        fx = inputs["fixture"]
        print(f"Fixture: {fx['home_team']} vs {fx['away_team']} on {fx['date']} in {fx['city']}, {fx['country']} "
              f"(neutral={fx['neutral']})")

    print(f"\n--- Poisson submodel ---")
    print(f"  lambda {team_a}: {lambda_a:.3f}   lambda {team_b}: {lambda_b:.3f}")
    print(f"  {team_a} win: {poisson_result['team_a_win']*100:.1f}%  "
          f"Draw: {poisson_result['draw']*100:.1f}%  "
          f"{team_b} win: {poisson_result['team_b_win']*100:.1f}%")
    print(f"  Most likely scoreline: {poisson_result['most_likely_score']}")

    print(f"\n--- Elo (Davidson) submodel ---")
    print(f"  Elo {team_a}: {elo_result['elo_team_a']:.1f}   Elo {team_b}: {elo_result['elo_team_b']:.1f}   "
          f"nu: {elo_result['davidson_nu']:.2f}")
    print(f"  {team_a} win: {elo_result['team_a_win']*100:.1f}%  "
          f"Draw: {elo_result['draw']*100:.1f}%  "
          f"{team_b} win: {elo_result['team_b_win']*100:.1f}%")

    print(f"\n--- Blended prediction ({int(POISSON_WEIGHT*100)}% Poisson / {int(ELO_WEIGHT*100)}% Elo) ---")
    print(f"  {team_a} win: {blend[0]*100:.1f}%")
    print(f"  Draw:          {blend[1]*100:.1f}%")
    print(f"  {team_b} win: {blend[2]*100:.1f}%")

    outcomes = {f"{team_a} win": blend[0], "Draw": blend[1], f"{team_b} win": blend[2]}
    most_likely = max(outcomes, key=outcomes.get)
    print(f"\n[PREDICTION] Most likely outcome: {most_likely} ({outcomes[most_likely]*100:.1f}%)")

    results = {
        "match": f"{team_a} vs {team_b} (FIFA World Cup 2026 Semifinal)",
        "match_date_local": "2026-07-16 02:00 GMT+7",
        "venue": inputs.get("fixture"),
        "data_as_of": inputs["data_as_of"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "predictions": {
            "team_a": team_a,
            "team_b": team_b,
            "team_a_win": round(float(blend[0]), 4),
            "draw": round(float(blend[1]), 4),
            "team_b_win": round(float(blend[2]), 4),
        },
        "submodels": {
            "poisson": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in poisson_result.items()},
            "elo_davidson": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in elo_result.items()},
        },
        "team_stats": {
            "team_a": {
                "name": team_a,
                "elo": round(inputs["elo"]["team_a"], 1),
                "attack_strength": round(strengths["attack_team_a"], 3),
                "defense_strength": round(strengths["defense_team_a"], 3),
                "form": inputs["form"]["team_a"],
                "poisson_window": inputs["poisson"]["team_a"],
            },
            "team_b": {
                "name": team_b,
                "elo": round(inputs["elo"]["team_b"], 1),
                "attack_strength": round(strengths["attack_team_b"], 3),
                "defense_strength": round(strengths["defense_team_b"], 3),
                "form": inputs["form"]["team_b"],
                "poisson_window": inputs["poisson"]["team_b"],
            },
        },
        "h2h_record": inputs["h2h"],
        "methodology": {
            "blend_weights": {"poisson": POISSON_WEIGHT, "elo": ELO_WEIGHT},
            "poisson_window_years": inputs["poisson"]["window_years_requested"],
            "elo_k_factor": inputs["elo"]["k_factor"],
            "elo_home_advantage": inputs["elo"]["home_advantage"],
            "elo_history_start": inputs["elo"]["history_start"],
            "elo_n_matches_used": inputs["elo"]["n_matches_used"],
            "davidson_nu": inputs["elo"]["davidson_nu"],
        },
        "caveats": [
            "This is a statistical projection generated ahead of kickoff, not a report of an actual result.",
            "Head-to-head record and recent-form figures are shown for context only and do not feed into the blended probability.",
            "The Poisson attack/defense ratios are not opponent-adjusted, so results against weak group-stage opponents can inflate a team's apparent attacking/defensive strength (strength-of-schedule bias).",
            "The Poisson submodel treats each team's goals as statistically independent, ignoring the small real-world negative correlation between two teams' low-scoring outcomes.",
            "The historical dataset has no penalty-shootout field, so any past meeting decided on penalties (e.g. the 1998 World Cup last-16 tie) is recorded as a draw.",
            "No player-level, injury, suspension, or lineup information is modeled.",
        ],
    }

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK] Results saved to {RESULTS_PATH}")

    generate_report.render(results, REPORT_PATH)
    print(f"[OK] Report saved to {REPORT_PATH}")


if __name__ == "__main__":
    main()
