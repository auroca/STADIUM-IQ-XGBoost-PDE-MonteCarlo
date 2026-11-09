"""Adaptador entre el modelo XGBoost multideporte y la PDE.

Colocar junto a multisport_model.py y multisport_model.joblib.
La salida es VENTA ESPERADA limitada por inventario, NO demanda potencial.
"""
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from multisport_model import NUMERIC, CATEGORICAL, encode_features, predict_sales

RUTA_MODELO = Path(__file__).resolve().with_name("multisport_model.joblib")


@lru_cache(maxsize=1)
def cargar_xgboost():
    """Carga una sola vez los modelos entrenados y las columnas originales."""
    if not RUTA_MODELO.is_file():
        raise FileNotFoundError(f"No encuentro el modelo: {RUTA_MODELO}")
    paquete = joblib.load(RUTA_MODELO)
    if not {"models", "features"}.issubset(paquete):
        raise ValueError("El archivo joblib no tiene el formato esperado.")
    return paquete


def preparar_escenarios_precio(escenarios: pd.DataFrame, precios, base: float) -> pd.DataFrame:
    """Actualiza de manera coherente las features dependientes del precio.

    El precio anterior es el observado en el snapshot; el estado de Bellman
    actual no modela cambios de precio anteriores entre días futuros.
    """
    precios = np.asarray(precios, dtype=float)
    if base <= 0 or not np.isfinite(base) or not np.isfinite(precios).all() or np.any(precios <= 0):
        raise ValueError("Los precios deben ser positivos y finitos")
    escenarios = escenarios.copy()
    escenarios["current_price"] = precios
    escenarios["candidate_price"] = precios
    escenarios["price_vs_base"] = precios / base - 1.0
    escenarios["discount_active"] = (precios < base).astype(int)
    if "previous_price" in escenarios.columns:
        anterior = pd.to_numeric(escenarios["previous_price"], errors="coerce")
        escenarios["price_change_pct"] = np.where(
            anterior.notna() & (anterior > 0),
            100.0 * (precios / anterior.replace(0, np.nan) - 1.0),
            np.nan,
        )
    else:
        escenarios["price_change_pct"] = np.nan
    return escenarios


def predecir_ventas(estado: dict, precios, modo: str = "rate") -> pd.DataFrame:
    """Predice ventas del SIGUIENTE período para varios precios candidatos.

    estado: diccionario con los datos del evento y su inventario actual.
    precios: lista de precios (en euros).
    modo: 'rate' (predeterminado en la API) o 'direct'.
    """
    paquete = cargar_xgboost()
    if modo not in paquete["models"]:
        raise ValueError("El modo debe ser 'rate' o 'direct'.")

    faltan = [c for c in ("base_price", "remaining_capacity", "days_remaining", "sport_type", "ticket_category") if c not in estado]
    if faltan:
        raise ValueError(f"Faltan variables del estado: {faltan}")

    precios = np.asarray(precios, dtype=float).reshape(-1)
    if len(precios) == 0 or not np.isfinite(precios).all() or (precios <= 0).any():
        raise ValueError("Indica precios candidatos positivos y finitos.")

    base = float(estado["base_price"])
    stock = float(estado["remaining_capacity"])
    if not np.isfinite(base) or base <= 0 or not np.isfinite(stock) or stock < 0:
        raise ValueError("Precio base o inventario no válido.")
    if "min_price" in estado and (precios < float(estado["min_price"]) - 1e-8).any():
        raise ValueError("Hay precios por debajo del mínimo comercial.")
    if "max_price" in estado and (precios > float(estado["max_price"]) + 1e-8).any():
        raise ValueError("Hay precios por encima del máximo comercial.")

    escenarios = pd.DataFrame([estado] * len(precios))
    for columna in NUMERIC:
        if columna not in escenarios.columns:
            escenarios[columna] = np.nan
    for columna in CATEGORICAL:
        if columna not in escenarios.columns:
            escenarios[columna] = "no_aplica"

    # Recalcular las variables que cambian cuando probamos otro precio.
    escenarios = preparar_escenarios_precio(escenarios, precios, base)
    escenarios["remaining_capacity"] = stock

    # El inventario de un estado nuevo cambia también la ocupación.
    if "category_capacity" in estado:
        capacidad = float(estado["category_capacity"])
        if capacidad <= 0 or stock > capacidad:
            raise ValueError("Inventario y capacidad de la categoría incompatibles.")
        escenarios["cumulative_sales"] = capacidad - stock
        escenarios["occupancy_rate"] = (capacidad - stock) / capacidad

    columnas = paquete["features"]
    x = encode_features(escenarios, columns=columnas)
    ventas = predict_sales(paquete["models"][modo], x, np.full(len(precios), stock), modo)
    ventas = np.clip(np.nan_to_num(np.asarray(ventas, dtype=float), nan=0.0), 0.0, stock)

    return pd.DataFrame({
        "precio_eur": precios,
        "ventas_estimadas_siguiente_periodo": ventas,
        "ingresos_estimados_siguiente_periodo_eur": precios * ventas,
    })


def predecir_venta(estado: dict, precio: float, modo: str = "rate") -> float:
    """Versión para un único precio. Devuelve ventas esperadas del próximo período."""
    tabla = predecir_ventas(estado, [precio], modo=modo)
    return float(tabla.iloc[0]["ventas_estimadas_siguiente_periodo"])


if __name__ == "__main__":
    # Prueba técnica con datos ilustrativos; NO es una validación del modelo.
    ejemplo = {
        "sport_type": "football", "ticket_category": "general",
        "days_remaining": 15, "popularity_index": 0.7,
        "event_importance": 0.6, "category_capacity": 500,
        "remaining_capacity": 200, "base_price": 30.0,
        "min_price": 20.0, "max_price": 45.0,
        "sales_last_period": 12, "event_month": 5,
        "event_day_of_week": 5, "is_weekend": 1,
    }
    print("PRUEBA TÉCNICA: valores ilustrativos, no un evento real")
    print(predecir_ventas(ejemplo, [24, 30, 36]).to_string(index=False))
