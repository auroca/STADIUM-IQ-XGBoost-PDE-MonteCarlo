"""Interfaz de demanda compartida con el generador sintético.

Devuelve DEMANDA POTENCIAL media para un día; no aplica límite de inventario.
Parámetros latentes no disponibles en el CSV se fijan como HIPÓTESIS.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp
from typing import Mapping, Any
import pandas as pd

from generar_dataset import hidden_demand_mean


@dataclass(frozen=True)
class HipotesisDemanda:
    elasticidad: float = 1.0
    intensidad: float = 1.0
    tendencia_temporal: float = 0.25

    def __post_init__(self):
        if self.elasticidad < 0 or self.intensidad < 0:
            raise ValueError('Elasticidad e intensidad deben ser >= 0')


def _valor(datos: Mapping[str, Any], nombre: str, defecto=None):
    valor = datos.get(nombre, defecto)
    if valor is None or (not isinstance(valor, (dict, list)) and pd.isna(valor)):
        return defecto
    return valor


def _senal_deporte(datos: Mapping[str, Any]) -> float:
    """Misma contribución deportiva que el generador original."""
    deporte = _valor(datos, 'sport_type')
    if deporte == 'football':
        return 0.30 * (float(_valor(datos, 'derby_rivalry_index', .5)) - .5)
    if deporte == 'basketball':
        return 0.35 * (float(_valor(datos, 'team_win_percentage', .5)) - .5)
    if deporte == 'tennis':
        ranking = int(_valor(datos, 'player_ranking', 50))
        ronda = _valor(datos, 'tournament_round', 'R32')
        return -.001 * (ranking - 50) + (.15 if ronda in ('SF', 'F') else 0)
    if deporte == 'running':
        return -.15 * (float(_valor(datos, 'route_difficulty', .5)) - .5)
    raise ValueError(f'Deporte aún no compatible con este generador: {deporte!r}')


def demanda_media(
    precio: float,
    dias_restantes: int,
    capacidad_restante: int,
    caracteristicas_evento: Mapping[str, Any],
    *,
    hipotesis: HipotesisDemanda = HipotesisDemanda(),
) -> float:
    """Media de compradores POTENCIALES en el próximo día.

    capacidad_restante: estado actual (para validar; NO reduce la demanda potencial).
    category_capacity: capacidad ORIGINAL y escala del generador.
    sales_window_days: duración de comercialización (30 por defecto).
    """
    if precio <= 0 or capacidad_restante < 0:
        raise ValueError('Precio debe ser >0 e inventario >=0')
    base_price = float(_valor(caracteristicas_evento, 'base_price', 0))
    capacidad_total = int(_valor(caracteristicas_evento, 'category_capacity',
                                _valor(caracteristicas_evento, 'total_capacity', 0)))
    total_dias = int(_valor(caracteristicas_evento, 'sales_window_days', 30))
    if base_price <= 0 or capacidad_total <= 0 or total_dias <= 0:
        raise ValueError('Faltan base_price, category_capacity o sales_window_days válidos')
    if capacidad_restante > capacidad_total or not 1 <= dias_restantes <= total_dias:
        raise ValueError('Inventario o días restantes fuera de rango')
    return float(hidden_demand_mean(
        price=float(precio), reference_price=base_price,
        capacity=capacidad_total, periods=total_dias,
        days_remaining=int(dias_restantes),
        popularity=float(_valor(caracteristicas_evento, 'popularity_index', .5)),
        importance=float(_valor(caracteristicas_evento, 'event_importance', .5)),
        sensitivity=hipotesis.elasticidad,
        intensity=hipotesis.intensidad,
        time_trend=hipotesis.tendencia_temporal,
        sport=str(_valor(caracteristicas_evento, 'sport_type', '')),
        sport_signal=_senal_deporte(caracteristicas_evento),
        rain_probability=float(_valor(caracteristicas_evento, 'rain_probability', 0)),
        is_outdoor=str(_valor(caracteristicas_evento, 'venue_type', 'indoor')) == 'outdoor',
    ))
