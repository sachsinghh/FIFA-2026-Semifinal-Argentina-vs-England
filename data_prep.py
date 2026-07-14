"""
Data preparation for Argentina vs England World Cup 2026 semifinal prediction.
Downloads real historical international match results, builds Elo rating history,
calibrates a Davidson tie-adjusted Bradley-Terry draw parameter, computes Poisson
attack/defense strengths, and gathers head-to-head + recent-form context.
"""

import json
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_CSV_PATH = os.path.join(DATA_DIR, "results_raw.csv")
MODEL_INPUTS_PATH = os.path.join(DATA_DIR, "model_inputs.json")

CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"

TEAM_A = "Argentina"
TEAM_B = "England"

INITIAL_ELO = 1500.0
K_FACTOR = 32.0
HOME_ADVANTAGE = 65.0
POISSON_WINDOW_YEARS = 5
MIN_WINDOW_MATCHES = 15
FORM_WINDOW = 10

os.makedirs(DATA_DIR, exist_ok=True)


def load_raw_data(force_refresh=False):
    if not force_refresh and os.path.exists(RAW_CSV_PATH):
        print(f"[OK] Using cached data at {RAW_CSV_PATH}")
        df = pd.read_csv(RAW_CSV_PATH)
    else:
        print(f"Downloading historical match data from {CSV_URL} ...")
        df = pd.read_csv(CSV_URL)
        df.to_csv(RAW_CSV_PATH, index=False)
        print(f"[OK] Downloaded {len(df)} rows and cached to {RAW_CSV_PATH}")

    df["date"] = pd.to_datetime(df["date"])

    # Drop unplayed / placeholder rows (future fixtures with NaN scores),
    # including the target Argentina vs England semifinal row itself.
    before = len(df)
    df = df.dropna(subset=["home_team", "away_team", "home_score", "away_score"])
    df["home_score"] = df["home_score"].astype(int)
    df["away_score"] = df["away_score"].astype(int)
    dropped = before - len(df)
    print(f"[OK] Dropped {dropped} unplayed/incomplete rows, {len(df)} played matches remain")

    if "neutral" not in df.columns:
        df["neutral"] = False
    df["neutral"] = df["neutral"].fillna(False).astype(bool)

    df = df.sort_values("date").reset_index(drop=True)
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    return df


def build_elo_history(df):
    """Chronologically build Elo ratings for every team. Returns final rating dict
    and a per-match record of pre-match Elo (home/away, adjusted for home advantage)
    plus the actual result, for later Davidson calibration."""
    print("\nCalculating Elo ratings...")
    elo = {}
    records = []

    for row in df.itertuples(index=False):
        home, away = row.home_team, row.away_team
        home_goals, away_goals = row.home_score, row.away_score
        is_neutral = bool(row.neutral)

        home_elo = elo.get(home, INITIAL_ELO)
        away_elo = elo.get(away, INITIAL_ELO)

        home_adv = 0.0 if is_neutral else HOME_ADVANTAGE
        expected_home = 1.0 / (1.0 + 10 ** (((away_elo) - (home_elo + home_adv)) / 400.0))

        if home_goals > away_goals:
            actual_home = 1.0
            result = "H"
        elif home_goals < away_goals:
            actual_home = 0.0
            result = "A"
        else:
            actual_home = 0.5
            result = "D"

        gd = home_goals - away_goals
        mult = min(1 + (abs(gd) - 1) / 8, 1.75) if gd != 0 else 1.0

        records.append({
            "home_elo_pre": home_elo,
            "away_elo_pre": away_elo,
            "home_adv_applied": home_adv,
            "result": result,
        })

        home_elo_new = home_elo + K_FACTOR * mult * (actual_home - expected_home)
        away_elo_new = away_elo + K_FACTOR * mult * ((1 - actual_home) - (1 - expected_home))

        elo[home] = home_elo_new
        elo[away] = away_elo_new

    print(f"[OK] Elo history built for {len(elo)} teams")
    return elo, pd.DataFrame(records)


def calibrate_davidson_nu(elo_records_df):
    """MLE grid search for the Davidson tie parameter nu, using pre-match
    home-advantage-adjusted Elo and each match's actual outcome. Pure numpy."""
    print("\nCalibrating Davidson tie parameter (nu) via MLE grid search...")

    pi_h = 10 ** ((elo_records_df["home_elo_pre"] + elo_records_df["home_adv_applied"]) / 400.0)
    pi_a = 10 ** (elo_records_df["away_elo_pre"] / 400.0)
    outcome = elo_records_df["result"].values

    is_h = outcome == "H"
    is_a = outcome == "A"
    is_d = outcome == "D"

    nus = np.arange(0.10, 2.01, 0.01)
    best_nu, best_ll = None, -np.inf

    sqrt_pipa = np.sqrt(pi_h * pi_a)
    for nu in nus:
        denom = pi_h + pi_a + nu * sqrt_pipa
        p_h = pi_h / denom
        p_a = pi_a / denom
        p_d = nu * sqrt_pipa / denom

        ll = (
            np.log(p_h[is_h]).sum()
            + np.log(p_a[is_a]).sum()
            + np.log(p_d[is_d]).sum()
        )
        if ll > best_ll:
            best_ll = ll
            best_nu = nu

    print(f"[OK] Calibrated nu = {best_nu:.2f} (log-likelihood {best_ll:.1f})")
    return float(best_nu)


def compute_poisson_strengths(df, team, as_of_date, window_years=POISSON_WINDOW_YEARS):
    """Rolling-window attack/defense strength for a team, expanding the window
    if too few matches are found."""
    years = window_years
    while True:
        window_start = as_of_date - pd.DateOffset(years=years)
        mask_home = (df["home_team"] == team) & (df["date"] > window_start) & (df["date"] <= as_of_date)
        mask_away = (df["away_team"] == team) & (df["date"] > window_start) & (df["date"] <= as_of_date)

        goals_for = pd.concat([df.loc[mask_home, "home_score"], df.loc[mask_away, "away_score"]])
        goals_against = pd.concat([df.loc[mask_home, "away_score"], df.loc[mask_away, "home_score"]])

        n_matches = len(goals_for)
        if n_matches >= MIN_WINDOW_MATCHES or years >= 12:
            break
        years += 3

    league_window = df[(df["date"] > window_start) & (df["date"] <= as_of_date)]
    league_avg_goals = pd.concat([league_window["home_score"], league_window["away_score"]]).mean()

    return {
        "n_matches": int(n_matches),
        "window_years": years,
        "goals_for_avg": float(goals_for.mean()) if n_matches else 0.0,
        "goals_against_avg": float(goals_against.mean()) if n_matches else 0.0,
        "league_avg_goals": float(league_avg_goals),
    }


def compute_form(df, team, as_of_date, n=FORM_WINDOW):
    mask = ((df["home_team"] == team) | (df["away_team"] == team)) & (df["date"] <= as_of_date)
    team_matches = df[mask].sort_values("date").tail(n)

    points, gf, ga = 0, 0, 0
    for row in team_matches.itertuples(index=False):
        if row.home_team == team:
            f, a = row.home_score, row.away_score
        else:
            f, a = row.away_score, row.home_score
        gf += f
        ga += a
        if f > a:
            points += 3
        elif f == a:
            points += 1

    n_matches = len(team_matches)
    return {
        "n_matches": int(n_matches),
        "ppg": round(points / n_matches, 3) if n_matches else 0.0,
        "gf_avg": round(gf / n_matches, 3) if n_matches else 0.0,
        "ga_avg": round(ga / n_matches, 3) if n_matches else 0.0,
    }


def compute_h2h(df, team_a, team_b):
    mask = (
        ((df["home_team"] == team_a) & (df["away_team"] == team_b))
        | ((df["home_team"] == team_b) & (df["away_team"] == team_a))
    )
    matches = df[mask].sort_values("date")

    a_wins = draws = b_wins = 0
    for row in matches.itertuples(index=False):
        if row.home_team == team_a:
            a_goals, b_goals = row.home_score, row.away_score
        else:
            a_goals, b_goals = row.away_score, row.home_score
        if a_goals > b_goals:
            a_wins += 1
        elif a_goals < b_goals:
            b_wins += 1
        else:
            draws += 1

    last_match = None
    if len(matches) > 0:
        last = matches.iloc[-1]
        last_match = {
            "date": str(last["date"].date()),
            "home_team": last["home_team"],
            "away_team": last["away_team"],
            "home_score": int(last["home_score"]),
            "away_score": int(last["away_score"]),
            "tournament": last.get("tournament", "Unknown"),
        }

    return {
        f"{team_a.lower()}_wins": a_wins,
        "draws": draws,
        f"{team_b.lower()}_wins": b_wins,
        "total_meetings": int(len(matches)),
        "last_match": last_match,
    }


def find_fixture_context(raw_df, team_a, team_b):
    """Look at the raw (pre-dropna) data for the unplayed fixture row to surface venue info."""
    mask = (
        ((raw_df["home_team"] == team_a) & (raw_df["away_team"] == team_b))
        | ((raw_df["home_team"] == team_b) & (raw_df["away_team"] == team_a))
    ) & (raw_df["home_score"].isna())
    rows = raw_df[mask]
    if len(rows) == 0:
        return None
    row = rows.iloc[-1]
    return {
        "date": str(pd.to_datetime(row["date"]).date()),
        "home_team": row["home_team"],
        "away_team": row["away_team"],
        "city": row.get("city", "Unknown"),
        "country": row.get("country", "Unknown"),
        "neutral": bool(row.get("neutral", True)),
        "tournament": row.get("tournament", "Unknown"),
    }


def main():
    df = load_raw_data()

    raw_df = pd.read_csv(RAW_CSV_PATH)
    raw_df["date"] = pd.to_datetime(raw_df["date"])
    fixture = find_fixture_context(raw_df, TEAM_A, TEAM_B)
    if fixture:
        print(f"\n[OK] Found target fixture row: {fixture['home_team']} vs {fixture['away_team']} "
              f"on {fixture['date']} in {fixture['city']}, {fixture['country']} (neutral={fixture['neutral']})")

    elo_final, elo_records_df = build_elo_history(df)
    davidson_nu = calibrate_davidson_nu(elo_records_df)

    as_of_date = df["date"].max()
    print(f"\nData as of (last played match): {as_of_date.date()}")

    elo_a = elo_final.get(TEAM_A, INITIAL_ELO)
    elo_b = elo_final.get(TEAM_B, INITIAL_ELO)
    print(f"\nCurrent Elo ratings:")
    print(f"  {TEAM_A}: {elo_a:.1f}")
    print(f"  {TEAM_B}: {elo_b:.1f}")

    poisson_a = compute_poisson_strengths(df, TEAM_A, as_of_date)
    poisson_b = compute_poisson_strengths(df, TEAM_B, as_of_date)
    print(f"\nPoisson window stats ({POISSON_WINDOW_YEARS}y, expands if sparse):")
    print(f"  {TEAM_A}: {poisson_a}")
    print(f"  {TEAM_B}: {poisson_b}")

    form_a = compute_form(df, TEAM_A, as_of_date)
    form_b = compute_form(df, TEAM_B, as_of_date)
    print(f"\nRecent form (last {FORM_WINDOW} matches):")
    print(f"  {TEAM_A}: {form_a}")
    print(f"  {TEAM_B}: {form_b}")

    h2h = compute_h2h(df, TEAM_A, TEAM_B)
    print(f"\nHead-to-head ({TEAM_A} vs {TEAM_B}):")
    print(f"  {h2h}")

    model_inputs = {
        "team_a": TEAM_A,
        "team_b": TEAM_B,
        "data_as_of": str(as_of_date.date()),
        "fixture": fixture,
        "elo": {
            "team_a": elo_a,
            "team_b": elo_b,
            "davidson_nu": davidson_nu,
            "k_factor": K_FACTOR,
            "home_advantage": HOME_ADVANTAGE,
            "history_start": str(df["date"].min().date()),
            "n_matches_used": int(len(df)),
        },
        "poisson": {
            "team_a": poisson_a,
            "team_b": poisson_b,
            "window_years_requested": POISSON_WINDOW_YEARS,
        },
        "form": {
            "team_a": form_a,
            "team_b": form_b,
        },
        "h2h": h2h,
    }

    with open(MODEL_INPUTS_PATH, "w") as f:
        json.dump(model_inputs, f, indent=2)
    print(f"\n[OK] Saved model inputs to {MODEL_INPUTS_PATH}")


if __name__ == "__main__":
    main()
