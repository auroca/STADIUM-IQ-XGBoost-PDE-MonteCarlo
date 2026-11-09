
"""STADIUM IQ V7.6 - API de optimizacion multideporte."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
from typing import Literal

import joblib
import numpy as np
import pandas as pd

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from config_deportes import variables_deporte

from multisport_model import (
    ARTIFACT,
    encode_features,
    load_dataset,
    predict_sales,
)

DATA = None
BUNDLE = None
AUTH_DB = Path(__file__).with_name("stadium_iq.db")

EPSILON = 1e-6


@asynccontextmanager
async def lifespan(app: FastAPI):
    global DATA, BUNDLE

    init_auth_db()
    if not ARTIFACT.exists():
        raise RuntimeError(
            "Primero ejecuta: python multisport_model.py train"
        )

    DATA = load_dataset()
    BUNDLE = joblib.load(ARTIFACT)
    yield


app = FastAPI(
    title="STADIUM IQ - Multisport V7.6",
    version="7.6",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


def get_db():
    connection = sqlite3.connect(AUTH_DB)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS saved_events (
            id TEXT NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id),
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (id, user_id)
        );
        """
    )
    return connection


def init_auth_db():
    with get_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS saved_events (
                id TEXT NOT NULL,
                user_id INTEGER NOT NULL REFERENCES users(id),
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (id, user_id)
            );
            """
        )


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 200_000
    )
    return f"{salt.hex()}:{digest.hex()}"


def password_matches(password, encoded):
    try:
        salt_hex, digest_hex = encoded.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 200_000
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Inicia sesión para continuar.")
    token = authorization[7:].strip()
    with get_db() as connection:
        row = connection.execute(
            "SELECT users.id, users.email FROM sessions "
            "JOIN users ON users.id = sessions.user_id WHERE sessions.token = ?",
            (token,),
        ).fetchone()
    if row is None:
        raise HTTPException(401, "La sesión ha caducado. Inicia sesión de nuevo.")
    return row


class AuthCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=128)


class RegisterCredentials(AuthCredentials):
    password: str = Field(min_length=6, max_length=128)


class EventPayload(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    payload: dict


@app.on_event("startup")
def startup_auth_db():
    init_auth_db()


@app.post("/api/v7/auth/register")
def register(credentials: RegisterCredentials):
    email = credentials.email.strip().lower()
    try:
        with get_db() as connection:
            cursor = connection.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, password_hash(credentials.password), now_iso()),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ya existe una cuenta con ese email.")
    return create_session(user_id, email)


@app.post("/api/v7/auth/login")
def login(credentials: AuthCredentials):
    with get_db() as connection:
        row = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (credentials.email.strip().lower(),),
        ).fetchone()
    if row is None or not password_matches(credentials.password, row["password_hash"]):
        raise HTTPException(401, "Email o contraseña incorrectos.")
    return create_session(row["id"], row["email"])


def create_session(user_id, email):
    token = secrets.token_urlsafe(32)
    with get_db() as connection:
        connection.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, now_iso()),
        )
    return {"token": token, "user": {"id": user_id, "email": email}}


@app.get("/api/v7/auth/me")
def me(user=Depends(current_user)):
    return {"id": user["id"], "email": user["email"]}


@app.post("/api/v7/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    if authorization and authorization.startswith("Bearer "):
        with get_db() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token = ?", (authorization[7:].strip(),)
            )
    return {"ok": True}


@app.get("/api/v7/events")
def list_events(user=Depends(current_user)):
    with get_db() as connection:
        rows = connection.execute(
            "SELECT payload FROM saved_events WHERE user_id = ? ORDER BY updated_at DESC",
            (user["id"],),
        ).fetchall()
    return [json.loads(row["payload"]) for row in rows]


@app.put("/api/v7/events/{event_id}")
def save_event(event_id: str, event: EventPayload, user=Depends(current_user)):
    if event_id != event.id:
        raise HTTPException(400, "El identificador del evento no coincide.")
    with get_db() as connection:
        connection.execute(
            "INSERT INTO saved_events (id, user_id, payload, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id, user_id) DO UPDATE SET payload = excluded.payload, "
            "updated_at = excluded.updated_at",
            (event.id, user["id"], json.dumps(event.payload), now_iso()),
        )
    return event.payload


@app.delete("/api/v7/events/{event_id}")
def delete_event(event_id: str, user=Depends(current_user)):
    with get_db() as connection:
        connection.execute(
            "DELETE FROM saved_events WHERE id = ? AND user_id = ?",
            (event_id, user["id"]),
        )
    return {"ok": True}


class CustomPrediction(BaseModel):
    sport_type: Literal["football", "basketball", "tennis", "running"]
    ticket_category: str = Field(min_length=1)
    days_remaining: int = Field(ge=1, le=30)
    model: Literal["rate", "direct"] = "rate"
    category_capacity: int = Field(ge=1, le=100000)
    remaining_capacity: int = Field(ge=0, le=100000)
    current_price: float = Field(gt=0, le=10000)
    reference_price: float | None = Field(default=None, gt=0, le=10000)
    popularity_index: float = Field(ge=0, le=1)
    event_importance: float = Field(ge=0, le=1)
    event_name: str = Field(default="Mi evento", max_length=100)
    derby_rivalry_index: float | None = Field(default=None, ge=0, le=1)
    league_position_home: int | None = Field(default=None, ge=1, le=30)
    league_position_away: int | None = Field(default=None, ge=1, le=30)
    team_win_percentage: float | None = Field(default=None, ge=0, le=1)
    player_ranking: int | None = Field(default=None, ge=1, le=500)
    tournament_round: Literal["R32", "R16", "QF", "SF", "F"] | None = None
    race_distance_km: float | None = Field(default=None, gt=0, le=100)
    elevation_gain_m: float | None = Field(default=None, ge=0, le=5000)


class Prediction(BaseModel):
    event_id: str
    ticket_category_id: str
    days_remaining: int = Field(ge=1, le=365)
    model: Literal["rate", "direct"] = "rate"
    remaining_capacity: int | None = Field(
        default=None, ge=0
    )


def get_snapshot(event_id, ticket_category_id, days):
    if DATA is None:
        raise HTTPException(503, "Dataset no cargado")

    records = DATA.loc[
        (DATA["event_id"] == event_id)
        & (DATA["ticket_category_id"] == ticket_category_id)
        & (DATA["days_remaining"] == days)
    ]

    if records.empty:
        raise HTTPException(
            404, "No existe ese evento, categoria y dia"
        )

    return records.iloc[0].copy()


def context_dict(row, original_stock=None):
    capacity = int(row["category_capacity"])
    stock = int(row["remaining_capacity"])

    return {
        "sport": str(row["sport_type"]),
        "event_id": str(row["event_id"]),
        "category": str(row["ticket_category"]),
        "category_id": str(row["ticket_category_id"]),
        "days_remaining": int(row["days_remaining"]),
        "remaining_capacity": stock,
        "original_remaining_capacity": (
            stock if original_stock is None
            else int(original_stock)
        ),
        "category_capacity": capacity,
        "occupancy_rate": (
            (capacity - stock) / capacity
            if capacity > 0 else 0.0
        ),
        "observed_price": float(row["current_price"]),
        "min_price": float(row["min_price"]),
        "max_price": float(row["max_price"]),
        "is_hypothetical": (
            original_stock is not None
            and stock != original_stock
        ),
    }


def update_inventory(row, stock):
    """Actualiza inventario y derivados conocidos."""
    row = row.copy()
    capacity = int(row["category_capacity"])

    if not 0 <= stock <= capacity:
        raise HTTPException(
            422,
            "El inventario debe estar entre 0 y el aforo"
        )

    row["remaining_capacity"] = stock
    row["cumulative_sales"] = capacity - stock
    row["occupancy_rate"] = (
        (capacity - stock) / capacity
        if capacity > 0 else 0.0
    )

    if "remaining_capacity_pct" in row.index:
        row["remaining_capacity_pct"] = (
            stock / capacity if capacity > 0 else 0.0
        )

    return row


def evaluate_prices(row, model_name, prices):
    scenarios = pd.DataFrame(
        [row.to_dict()] * len(prices)
    )

    scenarios["current_price"] = prices
    scenarios["candidate_price"] = prices
    scenarios["price_vs_base"] = (
        prices / float(row["base_price"]) - 1
    )
    scenarios["discount_active"] = (
        prices < float(row["base_price"])
    ).astype(int)

    x = encode_features(
        scenarios,
        BUNDLE["features"],
    )

    stock = scenarios[
        "remaining_capacity"
    ].to_numpy(float)

    demand = predict_sales(
        BUNDLE["models"][model_name],
        x,
        stock,
        model_name,
    )

    demand = np.nan_to_num(
        np.asarray(demand, dtype=float),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    demand = np.clip(demand, 0, stock)
    revenue = prices * demand

    return demand, revenue


@app.get("/api/v7/health")
def health():
    return {
        "ok": DATA is not None and BUNDLE is not None,
        "version": "7.6",
        "events": int(DATA["event_id"].nunique()),
    }


@app.get("/api/v7/config")
def config():
    pairs = DATA[
        [
            "sport_type",
            "event_id",
            "ticket_category_id",
            "ticket_category",
        ]
    ].drop_duplicates()

    return {
        "events": pairs.sort_values(
            ["sport_type", "event_id", "ticket_category_id"]
        ).to_dict(orient="records")
    }


@app.get("/api/v7/context")
def get_context(
    event_id: str = Query(...),
    ticket_category_id: str = Query(...),
    days_remaining: int = Query(..., ge=1, le=365),
):
    row = get_snapshot(
        event_id, ticket_category_id, days_remaining
    )
    return context_dict(row)


@app.post("/api/v7/optimize")
def optimize(req: Prediction):
    row = get_snapshot(
        req.event_id,
        req.ticket_category_id,
        req.days_remaining,
    )

    original_stock = int(row["remaining_capacity"])
    stock = (
        original_stock
        if req.remaining_capacity is None
        else int(req.remaining_capacity)
    )

    row = update_inventory(row, stock)

    return optimize_row(row, req.model, original_stock)


def optimize_row(row, model_name, original_stock=None, extra_context=None):
    stock = int(row["remaining_capacity"])
    context = context_dict(row, original_stock)
    if extra_context:
        context.update(extra_context)

    # Sin existencias no existe decision de pricing.
    if stock == 0:
        return {
            "status": "sold_out",
            "message": (
                "Todas las entradas de esta categoria "
                "estan agotadas. No es posible generar "
                "ingresos adicionales cambiando el precio."
            ),
            "context": context,
            "model": model_name,
            "optimal": None,
            "reference": None,
            "uplift_percent": None,
            "local_price_sensitivity": None,
            "sensitivity": [],
            "curve": [],
        }

    low = float(row["min_price"])
    high = float(row["max_price"])
    observed = float(row["current_price"])

    if not (
        np.isfinite(low)
        and np.isfinite(high)
        and np.isfinite(observed)
        and 0 < low <= high
        and observed > 0
    ):
        raise HTTPException(
            422, "Precios del evento no validos"
        )

    # Barrido del rango completo mas precio observado exacto.
    grid = np.linspace(low, high, 51)
    prices = np.unique(
        np.append(grid, observed)
    )

    demand, revenue = evaluate_prices(
        row, model_name, prices
    )

    ref_demand, ref_revenue = evaluate_prices(
        row,
        model_name,
        np.array([observed], dtype=float),
    )

    reference = {
        "price": observed,
        "sales": float(ref_demand[0]),
        "revenue": float(ref_revenue[0]),
    }

    curve = [
        {
            "price": float(p),
            "sales": float(q),
            "revenue": float(r),
        }
        for p, q, r in zip(
            prices, demand, revenue
        )
    ]

    # Con inventario, pero sin ventas previstas.
    if float(np.max(demand)) <= EPSILON:
        return {
            "status": "no_demand",
            "message": (
                "El modelo no preve ventas con ninguno "
                "de los precios probados. No hay una "
                "recomendacion de precio fundamentada."
            ),
            "context": context,
            "model": model_name,
            "optimal": None,
            "reference": reference,
            "uplift_percent": None,
            "local_price_sensitivity": None,
            "sensitivity": [],
            "curve": curve,
        }

    best_revenue = float(np.max(revenue))

    # Si varios precios empatan, preferir el mas proximo
    # al observado. Esto evita elegir arbitrariamente
    # el precio minimo.
    tolerance = max(1e-7, best_revenue * 1e-9)

    tied = np.flatnonzero(
        revenue >= best_revenue - tolerance
    )

    best_idx = tied[
        np.argmin(
            np.abs(prices[tied] - observed)
        )
    ]

    optimal = {
        "price": float(prices[best_idx]),
        "sales": float(demand[best_idx]),
        "revenue": float(revenue[best_idx]),
    }

    uplift = (
        100.0 * (
            optimal["revenue"] / reference["revenue"] - 1
        )
        if reference["revenue"] > EPSILON
        else None
    )

    # Sensibilidad predictiva local, no causal.
    pair = np.array(
        [observed * 0.95, observed * 1.05],
        dtype=float,
    )

    pair = np.clip(pair, low, high)
    local_sensitivity = None

    if pair[1] > pair[0]:
        qs, _ = evaluate_prices(
            row, model_name, pair
        )

        if np.mean(qs) > EPSILON:
            local_sensitivity = float(
                (
                    (qs[1] - qs[0]) / np.mean(qs)
                )
                /
                (
                    (pair[1] - pair[0]) / np.mean(pair)
                )
            )

    # Diagnostico: control de forma de la curva y precios en los extremos.
    # Son comprobaciones de coherencia, no prueba de elasticidad causal.
    diffs = np.diff(demand)
    rises = int(np.count_nonzero(diffs > np.maximum(0.05, 0.005 * np.maximum(demand[:-1], 1))))
    boundary_tolerance = max((high - low) / 50, 0.01)
    at_upper = bool(high - optimal["price"] <= boundary_tolerance)
    at_lower = bool(optimal["price"] - low <= boundary_tolerance)
    weak_response = bool(
        local_sensitivity is not None and abs(local_sensitivity) < 0.15
    )
    diagnostics = {
        "demand_increase_steps": rises,
        "price_points": int(len(prices)),
        "optimal_at_upper_bound": at_upper,
        "optimal_at_lower_bound": at_lower,
        "weak_local_response": weak_response,
        "warnings": [],
    }
    if rises:
        diagnostics["warnings"].append(
            "La demanda predicha aumenta en algunos tramos al subir el precio; "
            "revisar la curva antes de interpretar la recomendacion."
        )
    if at_upper:
        diagnostics["warnings"].append(
            "El precio optimo coincide con el maximo evaluado; "
            "puede depender del limite de busqueda."
        )
    if at_lower:
        diagnostics["warnings"].append(
            "El precio optimo coincide con el minimo evaluado; "
            "puede depender del limite de busqueda."
        )
    if weak_response:
        diagnostics["warnings"].append(
            "La demanda estimada responde poco al precio cerca del precio inicial. "
            "El resultado puede estar dominado por el aumento del precio."
        )

    # Sensibilidad al inventario (opcional).
    checks = []

    for name, factor in [
        ("Inventario -5%", 0.95),
        ("Escenario base", 1.0),
        ("Inventario +5%", 1.05),
    ]:
        scenario_stock = int(
            np.clip(
                round(stock * factor),
                0,
                int(row["category_capacity"]),
            )
        )

        scenario = update_inventory(
            row, scenario_stock
        )

        sq, sr = evaluate_prices(
            scenario, model_name, prices
        )

        if float(np.max(sq)) <= EPSILON:
            scenario_best = None
        else:
            scenario_max = float(np.max(sr))
            tied_s = np.flatnonzero(
                sr >= scenario_max -
                max(1e-7, scenario_max * 1e-9)
            )
            si = tied_s[
                np.argmin(
                    np.abs(prices[tied_s] - observed)
                )
            ]
            scenario_best = {
                "price": float(prices[si]),
                "sales": float(sq[si]),
                "revenue": float(sr[si]),
            }

        checks.append({
            "scenario": name,
            "remaining_capacity": scenario_stock,
            "optimal": scenario_best,
        })

    return {
        "status": "ok",
        "message": "Simulacion completada.",
        "context": context,
        "model": model_name,
        "optimal": optimal,
        "reference": reference,
        "uplift_percent": uplift,
        "local_price_sensitivity": local_sensitivity,
        "diagnostics": diagnostics,
        "sensitivity": checks,
        "curve": curve,
        "caveat": (
            "Datos sinteticos. Estimaciones para un dia. "
            "Las variaciones manuales del inventario "
            "son escenarios hipoteticos y no garantizan "
            "la coherencia de todas las variables historicas."
        ),
    }



def custom_template(sport_type, ticket_category, days_remaining):
    """Perfil sintetico representativo, NO evento aportado por el usuario."""
    candidates = DATA.loc[
        (DATA["sport_type"] == sport_type)
        & (DATA["ticket_category"] == ticket_category)
        & (DATA["days_remaining"] == days_remaining)
    ]
    if candidates.empty:
        raise HTTPException(422, "Categoria o dias no disponibles para ese deporte")
    # Un registro completo de referencia, evitando combinar columnas
    # inconsistentes de distintos eventos ficticios.
    med = candidates[["popularity_index", "event_importance", "base_price"]].median()
    dist = (
        ((candidates["popularity_index"] - med["popularity_index"]) ** 2)
        + ((candidates["event_importance"] - med["event_importance"]) ** 2)
        + ((candidates["base_price"] / max(med["base_price"], 1) - 1) ** 2)
    )
    return candidates.loc[dist.idxmin()].copy()


@app.get("/api/v7/custom/config")
def custom_config():
    if DATA is None:
        raise HTTPException(503, "Dataset no cargado")
    categories = DATA[["sport_type", "ticket_category"]].drop_duplicates()
    return {
        "categories": categories.sort_values(["sport_type", "ticket_category"]).to_dict("records"),
        "limits": {"min_days": 1, "max_days": 30, "price_min_factor": 0.8, "price_max_factor": 1.2},
        "note": "Los valores que no introduzcas se toman de un evento sintetico representativo.",
    }


def safe_optional_number(row, field):
    value = row.get(field)
    return None if pd.isna(value) else float(value)


@app.get("/api/v7/custom/defaults")
def custom_defaults(
    sport_type: Literal["football", "basketball", "tennis", "running"],
    ticket_category: str,
    days_remaining: int = Query(30, ge=1, le=30),
):
    row = custom_template(sport_type, ticket_category, days_remaining)
    return {
        "category_capacity": int(row["category_capacity"]),
        "remaining_capacity": int(row["remaining_capacity"]),
        "current_price": round(float(row["base_price"]), 2),
        "reference_price": round(float(row["base_price"]), 2),
        "popularity_index": round(float(row["popularity_index"]), 3),
        "event_importance": round(float(row["event_importance"]), 3),
        "derby_rivalry_index": safe_optional_number(row, "derby_rivalry_index"),
        "league_position_home": safe_optional_number(row, "league_position_home"),
        "league_position_away": safe_optional_number(row, "league_position_away"),
        "team_win_percentage": safe_optional_number(row, "team_win_percentage"),
        "player_ranking": safe_optional_number(row, "player_ranking"),
        "tournament_round": str(row.get("tournament_round")) if pd.notna(row.get("tournament_round")) else "QF",
        "race_distance_km": safe_optional_number(row, "race_distance_km"),
        "elevation_gain_m": safe_optional_number(row, "elevation_gain_m"),
    }


@app.post("/api/v7/custom/optimize")
def optimize_custom(req: CustomPrediction):
    if DATA is None or BUNDLE is None:
        raise HTTPException(503, "Modelo o dataset no cargado")
    if req.remaining_capacity > req.category_capacity:
        raise HTTPException(422, "Las disponibles no pueden superar el aforo")
    row = custom_template(req.sport_type, req.ticket_category, req.days_remaining)
    # Solo se alteran atributos pertenecientes al deporte seleccionado.
    for field in variables_deporte(req.sport_type):
        value = getattr(req, field)
        if value is not None:
            row[field] = value
    row["event_id"] = "CUSTOM_SCENARIO"
    row["ticket_category_id"] = "CUSTOM_CATEGORY"
    row["category_capacity"] = req.category_capacity
    row["total_capacity"] = req.category_capacity  # aprox.: una sola categoria
    reference_price = req.reference_price if req.reference_price is not None else req.current_price
    row["base_price"] = reference_price
    row["current_price"] = req.current_price
    row["min_price"] = round(reference_price * 0.8, 4)
    row["max_price"] = round(reference_price * 1.2, 4)
    row["popularity_index"] = req.popularity_index
    row["event_importance"] = req.event_importance
    # Evitar importar ventas de otro evento: son supuestos neutros.
    row["sales_last_period"] = 0
    row = update_inventory(row, req.remaining_capacity)
    if "sales_velocity" in row.index:
        row["sales_velocity"] = 0
    if "price_vs_base" in row.index:
        row["price_vs_base"] = (
            req.current_price / reference_price - 1
        )
    if "discount_active" in row.index:
        row["discount_active"] = int(
            req.current_price < reference_price
        )
    output = optimize_row(row, req.model, extra_context={
        "is_custom": True,
        "event_name": req.event_name.strip() or "Mi evento",
        "is_hypothetical": True,
        "assumptions": [
            "Evento nuevo: las variables no introducidas usan un perfil sintetico representativo de ese deporte y categoria.",
            "Se supone que el aforo total coincide con el de esta categoria.",
            "Se supone que las ventas del periodo anterior son cero, al no disponer de historial.",
            "El precio de referencia determina el rango de busqueda del 80% al 120%.",
            "La recomendacion corresponde solo al siguiente dia, no al total del evento.",
        ],
    })
    candidates = DATA.loc[
        (DATA["sport_type"] == req.sport_type)
        & (DATA["ticket_category"] == req.ticket_category)
    ]
    pmin = float(candidates["current_price"].min())
    pmax = float(candidates["current_price"].max())
    output["context"]["observed_price_reference_range"] = [round(pmin, 2), round(pmax, 2)]
    output["context"]["reference_price"] = float(reference_price)
    if req.current_price < pmin or req.current_price > pmax:
        output.setdefault("diagnostics", {"warnings": []})["warnings"].append(
            f"El precio introducido ({req.current_price:.2f}) queda fuera de "
            f"los precios sinteticos observados para este deporte y entrada "
            f"({pmin:.2f}-{pmax:.2f}). La extrapolacion puede ser poco fiable."
        )
    output["caveat"] = (
        "ESCENARIO HIPOTETICO con datos de referencia sinteticos. "
        "No validado para eventos reales ni para decisiones comerciales."
    )
    return output

# ============================================================
# INTEGRACIÓN XGBOOST + PROGRAMACIÓN DINÁMICA ESTOCÁSTICA
# ============================================================

from integracion_xgboost_pde import resolver


@app.post("/api/v7/pde/optimize")
def optimize_pde(
    req: Prediction,
    forma_nb: float = Query(default=9.0, gt=0, le=100)
):
    """
    Optimización de precios considerando los días restantes.

    Utiliza:
    - XGBoost para estimar ventas.
    - Binomial negativa para representar incertidumbre.
    - PDE para maximizar los ingresos acumulados esperados.

    Endpoint experimental para eventos del dataset.
    """

    if DATA is None or BUNDLE is None:
        raise HTTPException(
            status_code=503,
            detail="Modelo o dataset no cargado."
        )

    # Límites iniciales para controlar el coste computacional.
    if req.days_remaining > 15:
        raise HTTPException(
            status_code=422,
            detail="La integración experimental admite hasta 15 días."
        )

    # Recuperar evento y categoría desde la API existente.
    row = get_snapshot(
        req.event_id,
        req.ticket_category_id,
        req.days_remaining
    )

    original_stock = int(row["remaining_capacity"])

    stock = (
        original_stock
        if req.remaining_capacity is None
        else int(req.remaining_capacity)
    )

    # Mantener coherencia con la actualización de la API.
    row = update_inventory(row, stock)

    context = context_dict(row, original_stock)

    if stock == 0:
        return {
            "status": "sold_out",
            "message": "No quedan entradas disponibles.",
            "context": context,
            "model": req.model,
            "recommendation": None
        }

    if stock > 1000:
        raise HTTPException(
            status_code=422,
            detail="La integración experimental admite hasta 1000 entradas disponibles."
        )

    estado = row.to_dict()

    try:
        resultado = resolver(
            estado=estado,
            dias=req.days_remaining,
            stock=stock,
            modo=req.model,
            forma_nb=forma_nb
        )

        recomendacion = resultado.recomendacion()

    except (ValueError, KeyError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo calcular la PDE: {error}"
        ) from error

    precio = float(
        recomendacion["precio_recomendado_eur"]
    )

    ventas = float(
        recomendacion["ventas_estimadas_siguiente_dia"]
    )

    ingresos_totales = float(
        recomendacion["ingreso_total_esperado_eur"]
    )

    return {
        "status": "ok",
        "message": "Optimización PDE completada.",
        "context": context,
        "model": req.model,
        "optimization": "stochastic_dynamic_programming",
        "horizon_days": resultado.dias,
        "uncertainty": {
            "distribution": "negative_binomial",
            "shape_parameter": forma_nb,
            "calibrated": False
        },
        "recommendation": {
            "price": precio,
            "expected_sales_next_day": ventas,
            "expected_revenue_next_day": precio * ventas,
            "expected_total_revenue": ingresos_totales
        },
        "candidate_prices": [
            float(p) for p in resultado.precios
        ],
        "caveat": (
            "Resultados experimentales basados en datos "
            "sintéticos. La incertidumbre no está calibrada "
            "con datos reales y algunas variables históricas "
            "permanecen constantes durante la optimización."
        )
    }


@app.post("/api/v7/custom/pde/optimize")
def optimize_custom_pde(
    req: CustomPrediction,
    forma_nb: float = Query(default=9.0, gt=0, le=100)
):
    """PDE experimental para eventos personalizados de STADIUM IQ."""

    if DATA is None or BUNDLE is None:
        raise HTTPException(503, "Modelo o dataset no cargado.")

    if req.remaining_capacity > req.category_capacity:
        raise HTTPException(422, "El inventario supera el aforo.")

    if req.days_remaining > 15:
        raise HTTPException(
            422,
            "La PDE experimental admite hasta 15 días."
        )

    if req.remaining_capacity > 1000:
        raise HTTPException(
            422,
            "La PDE experimental admite hasta 1000 entradas disponibles."
        )

    # Crear el mismo perfil de referencia que utiliza el
    # simulador personalizado existente.
    row = custom_template(
        req.sport_type,
        req.ticket_category,
        req.days_remaining
    )

    for field in variables_deporte(req.sport_type):
        value = getattr(req, field)
        if value is not None:
            row[field] = value

    row["event_id"] = "CUSTOM_SCENARIO"
    row["ticket_category_id"] = "CUSTOM_CATEGORY"
    row["category_capacity"] = req.category_capacity
    row["total_capacity"] = req.category_capacity

    reference_price = (
        req.reference_price
        if req.reference_price is not None
        else req.current_price
    )

    row["base_price"] = reference_price
    row["current_price"] = req.current_price
    row["min_price"] = round(reference_price * 0.8, 4)
    row["max_price"] = round(reference_price * 1.2, 4)

    row["popularity_index"] = req.popularity_index
    row["event_importance"] = req.event_importance

    # No existe un historial de ventas del nuevo evento.
    row["sales_last_period"] = 0

    row = update_inventory(row, req.remaining_capacity)

    if "sales_velocity" in row.index:
        row["sales_velocity"] = 0

    row["price_vs_base"] = (
        req.current_price / reference_price - 1
    )

    if "discount_active" in row.index:
        row["discount_active"] = int(
            req.current_price < reference_price
        )

    context = context_dict(row)
    context.update({
        "is_custom": True,
        "event_name": req.event_name,
        "reference_price": float(reference_price)
    })

    if req.remaining_capacity == 0:
        return {
            "status": "sold_out",
            "context": context,
            "recommendation": None
        }

    try:
        resultado = resolver(
            estado=row.to_dict(),
            dias=req.days_remaining,
            stock=req.remaining_capacity,
            modo=req.model,
            forma_nb=forma_nb
        )

    except (ValueError, KeyError) as error:
        raise HTTPException(
            422,
            f"No se pudo calcular la PDE: {error}"
        ) from error

    recomendacion = resultado.recomendacion()
    precio = float(recomendacion["precio_recomendado_eur"])
    ventas = float(
        recomendacion["ventas_estimadas_siguiente_dia"]
    )

    return {
        "status": "ok",
        "model": req.model,
        "optimization": "stochastic_dynamic_programming",
        "context": context,
        "horizon_days": resultado.dias,
        "recommendation": {
            "price": precio,
            "expected_sales_next_day": ventas,
            "expected_revenue_next_day": precio * ventas,
            "expected_total_revenue": float(
                recomendacion["ingreso_total_esperado_eur"]
            )
        },
        "candidate_prices": [
            float(p) for p in resultado.precios
        ],
        "uncertainty": {
            "distribution": "negative_binomial",
            "shape_parameter": forma_nb,
            "calibrated": False
        },
        "caveat": (
            "Escenario personalizado y experimental. "
            "Los atributos no introducidos provienen de un "
            "perfil sintético de referencia. Las ventas "
            "anteriores se suponen iguales a cero y algunas "
            "variables futuras permanecen constantes. "
            "La dispersión no está calibrada con datos reales."
        )
    }


# ============================================================
# MONTE CARLO - VALIDACIÓN DE ESTRATEGIAS DE PRECIOS
# ============================================================

from simulacion_montecarlo_xgboost import simular


@app.post("/api/v7/custom/montecarlo")
def montecarlo_custom(
    req: CustomPrediction,
    replicas: int = Query(default=100, ge=10, le=500),
    forma_nb: float = Query(default=9.0, gt=0, le=100)
):
    """
    Compara tres estrategias de pricing:
    1. Precio fijo.
    2. XGBoost con optimización inmediata.
    3. XGBoost + PDE.

    Escenarios de demanda: 30 %, 60 % y 100 %.
    """

    if DATA is None or BUNDLE is None:
        raise HTTPException(
            503,
            "Modelo o dataset no cargado."
        )

    if req.remaining_capacity > req.category_capacity:
        raise HTTPException(
            422,
            "Las entradas disponibles superan el aforo."
        )

    if req.days_remaining > 15:
        raise HTTPException(
            422,
            "Monte Carlo admite hasta 15 días en esta versión."
        )

    if req.remaining_capacity > 1000:
        raise HTTPException(
            422,
            "Monte Carlo admite hasta 1000 entradas disponibles."
        )

    if req.remaining_capacity == 0:
        return {
            "status": "sold_out",
            "message": "No quedan entradas disponibles.",
            "scenarios": []
        }

    # Construcción del mismo escenario personalizado
    # utilizado por XGBoost y la PDE.

    row = custom_template(
        req.sport_type,
        req.ticket_category,
        req.days_remaining
    )

    for field in variables_deporte(req.sport_type):
        value = getattr(req, field)

        if value is not None:
            row[field] = value

    row["event_id"] = "CUSTOM_SCENARIO"
    row["ticket_category_id"] = "CUSTOM_CATEGORY"

    row["category_capacity"] = req.category_capacity
    row["total_capacity"] = req.category_capacity

    reference_price = (
        req.reference_price
        if req.reference_price is not None
        else req.current_price
    )

    row["base_price"] = reference_price
    row["current_price"] = req.current_price

    row["min_price"] = round(
        reference_price * 0.8, 4
    )

    row["max_price"] = round(
        reference_price * 1.2, 4
    )

    row["popularity_index"] = req.popularity_index
    row["event_importance"] = req.event_importance

    # Hipótesis para eventos sin historial.
    row["sales_last_period"] = 0

    row = update_inventory(
        row,
        req.remaining_capacity
    )

    if "sales_velocity" in row.index:
        row["sales_velocity"] = 0

    row["price_vs_base"] = (
        req.current_price / reference_price - 1
    )

    if "discount_active" in row.index:
        row["discount_active"] = int(
            req.current_price < reference_price
        )

    # Resolver la PDE una sola vez.
    # La misma política se evaluará bajo distintos
    # escenarios de demanda.

    try:
        resultado = resolver(
            estado=row.to_dict(),
            dias=req.days_remaining,
            stock=req.remaining_capacity,
            modo=req.model,
            forma_nb=forma_nb
        )

        escenarios = []

        for factor in [0.3, 0.6, 1.0]:

            resumen, _ = simular(
                resultado,
                replicas=replicas,
                semilla=42,
                factor_demanda=factor
            )

            escenarios.append({
                "factor_demanda": factor,
                "demanda_porcentaje": int(
                    factor * 100
                ),
                "resultados": resumen.to_dict(
                    orient="records"
                )
            })

    except (ValueError, KeyError, FileNotFoundError) as error:
        raise HTTPException(
            422,
            f"No se pudo ejecutar Monte Carlo: {error}"
        ) from error

    return {
        "status": "ok",
        "event_name": req.event_name,
        "sport": req.sport_type,
        "ticket_category": req.ticket_category,
        "days_remaining": req.days_remaining,
        "remaining_capacity": req.remaining_capacity,
        "model": req.model,
        "replicas": replicas,
        "distribution": "negative_binomial",
        "forma_nb": forma_nb,
        "pde_recommended_price": float(
            resultado.recomendacion()[
                "precio_recomendado_eur"
            ]
        ),
        "scenarios": escenarios,
        "caveat": (
            "Evaluación experimental con datos sintéticos. "
            "Las simulaciones utilizan demanda condicionada "
            "a XGBoost y no constituyen validación externa. "
            "La dispersión de la binomial negativa no está "
            "calibrada. Las estrategias comparadas utilizan "
            "la misma rejilla de cinco precios dentro de "
            "Monte Carlo, distinta de la búsqueda más amplia "
            "del optimizador inmediato de la interfaz."
        )
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host="127.0.0.1", port=8001
    )


