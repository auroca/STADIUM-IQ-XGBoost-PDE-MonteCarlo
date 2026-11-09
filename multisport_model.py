
"""V7: experimento multideporte independiente del simulador V6.

Uso:
    python multisport_model.py train
    python multisport_model.py simulate --sport football --event EV0001 --category 1
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from xgboost import XGBRegressor


ROOT = Path(__file__).resolve().parent
CSV = ROOT / "dataset_multideporte_EQUIPO.csv"
ARTIFACT = ROOT / "multisport_model.joblib"
REPORT = ROOT / "multisport_model_metrics.json"

NUMERIC = [
    "days_remaining", "sales_window_days", "prediction_horizon_days",
    "day_of_week", "popularity_index", "event_importance",
    "weather_temperature", "rain_probability", "is_televised",
    "is_holiday_period", "is_holiday", "competing_events", "marketing_campaign",
    "event_month", "event_day_of_week", "is_weekend",
    "category_capacity", "base_price", "is_premium_experience",
    "hospitality_included", "total_capacity", "remaining_capacity",
    "cumulative_sales", "sales_last_period", "occupancy_rate",
    "current_price", "candidate_price", "previous_price", "price_change_pct",
    "competitor_price", "price_vs_base", "discount_active",
    "league_position_home", "league_position_away", "recent_form_home_away",
    "derby_rivalry_index", "league_stakes", "star_players_available",
    "team_win_percentage", "standings_difference", "back_to_back_game",
    "rivalry_index", "player_ranking", "players_confirmed",
    "race_distance_km", "elevation_gain_m", "registration_deadline_days",
    "participant_services", "route_difficulty",
]

CATEGORICAL = [
    "sport_type", "event_format", "competition_level",
    "competition_phase", "venue_type", "tournament_round",
    "playoff_phase", "ticket_category", "sales_period",
    "singles_doubles", "tournament_category", "session_schedule",
    "registration_tier",
]

TARGET = "sales_next_period"


def load_dataset():
    if not CSV.exists():
        raise FileNotFoundError(
            f"Falta {CSV.name}. Copia el CSV EQUIPO de Aurora junto a este script."
        )

    df = pd.read_csv(CSV)

    required = set(
        NUMERIC + CATEGORICAL +
        [TARGET, "event_id", "ticket_category_id", "min_price", "max_price"]
    )
    missing = sorted(required - set(df.columns))

    if missing:
        raise ValueError(f"Faltan columnas: {missing}")

    df = df.copy()

    for col in NUMERIC + [TARGET, "min_price", "max_price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=[TARGET, "remaining_capacity", "current_price"])

    if df.empty:
        raise ValueError("Dataset sin registros válidos")

    if (df[TARGET] < 0).any() or (
        df[TARGET] > df["remaining_capacity"]
    ).any():
        raise ValueError("Ventas fuera del rango permitido por el inventario")

    return df


def encode_features(df, columns=None):
    numeric = df[NUMERIC].apply(pd.to_numeric, errors="coerce")
    categorical = df[CATEGORICAL].astype("string").fillna("no_aplica")
    x = pd.concat(
        [numeric, pd.get_dummies(categorical, dtype=int)],
        axis=1
    )

    # XGBoost admite valores NaN.
    if columns is not None:
        x = x.reindex(columns=columns, fill_value=0)

    return x.astype(float)


def build_model(columns, n_estimators=350):
    # El precio tiene una restricción monótona negativa.
    constraints = {
        name: -1
        for name in columns
        if name in {"current_price", "price_vs_base"}
    }

    return XGBRegressor(
        n_estimators=n_estimators,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.9,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=-1,
        monotone_constraints=constraints,
    )


def metrics(real, predicted):
    return {
        "mae_entradas": round(
            float(mean_absolute_error(real, predicted)), 3
        ),
        "rmse_entradas": round(
            float(np.sqrt(mean_squared_error(real, predicted))), 3
        ),
        "r2": round(float(r2_score(real, predicted)), 4),
    }


def predict_sales(model, x, stock, mode):
    raw = model.predict(x)

    if mode == "rate":
        raw = np.clip(raw, 0, 1) * stock

    return np.minimum(np.maximum(raw, 0), stock)


def train():
    df = load_dataset()

    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.2,
        random_state=42
    )

    train_ix, test_ix = next(
        splitter.split(df, groups=df["event_id"])
    )

    tr = df.iloc[train_ix]
    te = df.iloc[test_ix]

    xtr = encode_features(tr)
    xte = encode_features(te, xtr.columns.tolist())

    stock_tr = tr["remaining_capacity"].to_numpy(float)
    stock_te = te["remaining_capacity"].to_numpy(float)

    ytr = tr[TARGET].to_numpy(float)
    yte = te[TARGET].to_numpy(float)

    models = {}
    results = {}

    for mode in ("direct", "rate"):
        if mode == "direct":
            target_tr = ytr
        else:
            target_tr = np.divide(
                ytr,
                stock_tr,
                out=np.zeros_like(ytr),
                where=stock_tr > 0
            )

        model = build_model(xtr.columns.tolist())
        model.fit(xtr, target_tr)

        pred = predict_sales(model, xte, stock_te, mode)

        results[mode] = metrics(yte, pred)
        results[mode]["por_deporte"] = {
            sport: metrics(
                yte[te["sport_type"].to_numpy() == sport],
                pred[te["sport_type"].to_numpy() == sport]
            )
            for sport in sorted(te["sport_type"].unique())
        }

        models[mode] = model

    baseline = np.minimum(
        np.maximum(float(np.mean(ytr)) * np.ones(len(te)), 0),
        stock_te
    )

    results["baseline_media"] = metrics(yte, baseline)

    results["particion"] = {
        "eventos_entrenamiento": int(tr["event_id"].nunique()),
        "eventos_prueba": int(te["event_id"].nunique()),
        "filas_entrenamiento": int(len(tr)),
        "filas_prueba": int(len(te)),
        "semilla": 42,
    }

    joblib.dump(
        {
            "models": models,
            "features": xtr.columns.tolist()
        },
        ARTIFACT
    )

    REPORT.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(
        f"\nModelos: {ARTIFACT.name} | "
        f"Métricas: {REPORT.name}"
    )
    print(
        "AVISO: métricas en datos sintéticos, "
        "no precisión de mercado real."
    )


def simulate(sport, event, category, mode):
    if not ARTIFACT.exists():
        raise FileNotFoundError(
            "Primero ejecuta: python multisport_model.py train"
        )

    df = load_dataset()
    candidates = df[df["sport_type"] == sport]

    if event:
        candidates = candidates[candidates["event_id"] == event]

    if category:
        candidates = candidates[
            candidates["ticket_category_id"]
            .astype(str)
            .str.endswith(f"_CAT{category}")
        ]

    if candidates.empty:
        raise ValueError(
            "No existen observaciones con los filtros indicados"
        )

    row = candidates.sort_values(
        "days_remaining",
        ascending=False
    ).iloc[0]

    payload = joblib.load(ARTIFACT)
    model = payload["models"][mode]

    lower = float(row["min_price"])
    upper = float(row["max_price"])

    if not (0 < lower <= upper):
        raise ValueError("Los límites del precio son inválidos")

    prices = np.linspace(lower, upper, 51)

    scenarios = pd.DataFrame(
        [row.to_dict()] * len(prices)
    )
    scenarios["current_price"] = prices

    stock = scenarios[
        "remaining_capacity"
    ].to_numpy(float)

    x = encode_features(
        scenarios,
        payload["features"]
    )

    sales = predict_sales(model, x, stock, mode)

    outcome = pd.DataFrame({
        "precio_eur": prices,
        "ventas_estimadas_dia": sales,
        "ingresos_estimados_dia_eur": prices * sales,
    })

    chosen = outcome.loc[
        outcome["ingresos_estimados_dia_eur"].idxmax()
    ]

    print(
        f"Contexto: {row.event_id} / {row.ticket_category_id}; "
        f"{int(row.days_remaining)} días restantes; "
        f"{int(row.remaining_capacity)} plazas disponibles"
    )

    print(
        f"Modelo: {mode} | "
        f"precio recomendado: {chosen.precio_eur:.2f} EUR"
    )

    print(
        "Ventas esperadas mañana: "
        f"{chosen.ventas_estimadas_dia:.1f}"
    )

    print(
        "Ingresos esperados mañana: "
        f"{chosen.ingresos_estimados_dia_eur:.2f} EUR"
    )

    print(
        "La optimización es de UN día, "
        "no de todos los días hasta el evento."
    )

    print(
        "Las simulaciones fuera del soporte de precios "
        "observado son extrapolaciones."
    )

    return outcome


def main():
    parser = argparse.ArgumentParser(
        description="V7 — XGBoost multideporte"
    )

    parser.add_argument(
        "action", choices=["train", "simulate"]
    )

    parser.add_argument(
        "--sport",
        default="football",
        choices=[
            "football", "basketball", "tennis", "running"
        ]
    )

    parser.add_argument("--event", default=None)

    parser.add_argument(
        "--category", type=int, default=1, choices=[1, 2]
    )

    parser.add_argument(
        "--mode",
        default="rate",
        choices=["direct", "rate"]
    )

    args = parser.parse_args()

    if args.action == "train":
        train()
    else:
        simulate(
            args.sport,
            args.event,
            args.category,
            args.mode
        )


if __name__ == "__main__":
    main()
