
"""PDE con XGBoost y demanda potencial binomial negativa (versión experimental).

XGBoost predice VENTAS OBSERVABLES, censuradas por el inventario disponible.
Para cada estado y precio se ajusta la MEDIA LATENTE de D~NegBin(r, p)
para igualar E[min(D, stock)] a la predicción de ventas de XGBoost.
La forma r controla la dispersión y ES UNA HIPÓTESIS, NO HA SIDO CALIBRADA
empíricamente. No se presupone que XGBoost haya aprendido una distribución.

Limitación: el estado Bellman incluye días e inventario; las features de
histórico/marketing que no son deterministas permanecen en el snapshot inicial.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

from predictor_xgboost import cargar_xgboost, preparar_escenarios_precio
from multisport_model import NUMERIC, CATEGORICAL, encode_features, predict_sales

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'dataset_multideporte_EQUIPO.csv'


def cargar_estado(archivo: Path | str, evento: str, categoria: str, dias: int) -> dict:
    archivo = Path(archivo)
    if not archivo.is_file():
        raise FileNotFoundError(f'No se encuentra: {archivo}')
    df = pd.read_csv(archivo)
    columnas = {'event_id', 'ticket_category', 'days_remaining'}
    if not columnas.issubset(df.columns):
        raise ValueError(f'CSV incorrecto. Faltan columnas: {columnas - set(df.columns)}')
    subset = df[(df['event_id'] == evento) & (df['ticket_category'] == categoria) &
                (df['days_remaining'] == dias)]
    if len(subset) != 1:
        raise ValueError(f'Se esperaba una fila de {evento}, {categoria}, día {dias}; hay {len(subset)}')
    return subset.iloc[0].to_dict()


def precios_candidatos(estado: dict) -> np.ndarray:
    base = float(estado['base_price'])
    menor, mayor = float(estado['min_price']), float(estado['max_price'])
    valores = [max(menor, min(mayor, base * factor)) for factor in (.8, .9, 1., 1.1, 1.2)]
    return np.array(sorted(set(round(v, 2) for v in valores)), dtype=float)


def media_ventas_limitadas(media_latente, stock, forma_nb: float):
    """E[min(D,stock)], D~NB, parametrizada por E[D]=media_latente."""
    mu, s = np.broadcast_arrays(np.asarray(media_latente, float), np.asarray(stock, float))
    if forma_nb <= 0:
        raise ValueError('forma_nb debe ser positiva')
    p = forma_nb / (forma_nb + mu)
    # E[D 1(D<stock)] + stock P(D>=stock).
    return mu * nbinom.cdf(s-2, forma_nb+1, p) + s * nbinom.sf(s-1, forma_nb, p)


def inferir_medias_latentes(ventas_estimadas, stock, forma_nb: float = 9.0):
    """Invertir E[min(NB(mu), stock)] ~= ventas XGBoost.

    Para medias cercanas al 100 % del stock la media latente está mal
    identificada: se aproxima numéricamente, sin atribuir precisión espuria.
    """
    y, s = np.broadcast_arrays(np.asarray(ventas_estimadas, float), np.asarray(stock, float))
    if np.any(~np.isfinite(y)) or np.any(~np.isfinite(s)) or np.any(s < 0):
        raise ValueError('Ventas/stock inválidos')
    if np.any(y < -1e-8) or np.any(y > s + 1e-8):
        raise ValueError('Ventas estimadas fuera del intervalo 0..stock')
    y = np.clip(y, 0.0, s)
    # La saturación perfecta no determina una media única.
    objetivo = np.minimum(y, s * (1.0 - 1e-8))
    bajo = np.zeros_like(objetivo)
    alto = np.maximum(1.0, s * 2.0)
    for _ in range(24):
        insuficiente = media_ventas_limitadas(alto, s, forma_nb) < objetivo
        if not insuficiente.any():
            break
        alto = np.where(insuficiente, alto * 2.0, alto)
    else:
        raise ValueError('No se ha podido acotar la media latente')
    for _ in range(36):
        medio = (bajo + alto) / 2
        cantidad = media_ventas_limitadas(medio, s, forma_nb)
        bajo = np.where(cantidad < objetivo, medio, bajo)
        alto = np.where(cantidad >= objetivo, medio, alto)
    return np.where(objetivo <= 0, 0.0, (bajo + alto) / 2)


@dataclass
class ResultadoIntegracion:
    politica: np.ndarray
    valores: np.ndarray
    probabilidades: np.ndarray  # tasa ventas observables XGBoost
    medias_latentes: np.ndarray # medias de demanda NB identificadas numéricamente
    precios: np.ndarray
    estado: dict
    modo: str
    forma_nb: float
    niveles_stock: np.ndarray
    stock_inicial: int

    @property
    def dias(self):
        return self.politica.shape[0] - 1

    @property
    def stock(self):
        return self.stock_inicial

    def indice_stock(self, stock: float) -> int:
        if stock < 0 or stock > self.stock_inicial:
            raise ValueError('Inventario fuera del estado calculado')
        return int(np.abs(self.niveles_stock - stock).argmin())

    def recomendacion(self):
        d, s = self.dias, self.stock
        si = self.indice_stock(s)
        j = int(self.politica[d, si])
        return {
            'precio_recomendado_eur': float(self.precios[j]),
            'ventas_estimadas_siguiente_dia': float(self.probabilidades[d, si, j] * s),
            'ingreso_total_esperado_eur': float(self.valores[d, si]),
        }


def calcular_probabilidades(estado: dict, dias: int, niveles_stock: np.ndarray,
                            precios: np.ndarray, modo: str = 'rate') -> np.ndarray:
    paquete = cargar_xgboost()
    if modo not in paquete['models']:
        raise ValueError('Modo de XGBoost desconocido')
    if dias < 1 or len(niveles_stock) < 2:
        raise ValueError('Días/inventario fuera del rango permitido')
    n_precios = len(precios)
    tasas = np.zeros((dias+1, len(niveles_stock), n_precios), dtype=float)
    capacidad, base = float(estado['category_capacity']), float(estado['base_price'])
    if not (base > 0 and capacidad > 0):
        raise ValueError('Capacidad o precio base inválidos')
    for d in range(1, dias + 1):
        stocks = np.repeat(niveles_stock[1:], n_precios)
        ps = np.tile(precios, len(niveles_stock) - 1)
        df = pd.DataFrame([estado] * len(ps))
        for col in NUMERIC:
            if col not in df.columns:
                df[col] = np.nan
        for col in CATEGORICAL:
            if col not in df.columns:
                df[col] = 'no_aplica'
        df['days_remaining'] = d
        df['remaining_capacity'] = stocks
        df['cumulative_sales'] = capacidad - stocks
        df['occupancy_rate'] = (capacidad - stocks) / capacidad
        df = preparar_escenarios_precio(df, ps, base)
        periodo = int(estado.get('sales_window_days', 30))
        transcurridos = max(1, periodo-d+1)
        df['sales_period'] = ('early' if transcurridos <= periodo/3 else
                              'middle' if transcurridos <= 2*periodo/3 else 'late')
        x = encode_features(df, columns=paquete['features'])
        ventas = np.asarray(predict_sales(paquete['models'][modo], x, stocks, modo))
        if not np.isfinite(ventas).all():
            raise ValueError('Predicción no finita de XGBoost')
        tasas[d, 1:, :] = np.clip(ventas/stocks, 0, 1).reshape(len(niveles_stock) - 1, n_precios)
    return tasas


def resolver(estado: dict, dias: int | None = None, stock: int | None = None,
             modo: str = 'rate', forma_nb: float = 9.0,
             max_niveles_stock: int = 1001) -> ResultadoIntegracion:
    if not np.isfinite(forma_nb) or forma_nb <= 0:
        raise ValueError('forma_nb debe ser positiva')
    dias = int(dias if dias is not None else estado['days_remaining'])
    stock = int(stock if stock is not None else estado['remaining_capacity'])
    if stock < 1 or stock > int(estado['category_capacity']):
        raise ValueError('Inventario fuera del rango de la categoría')
    if max_niveles_stock < 2:
        raise ValueError('max_niveles_stock debe ser al menos 2')
    n_niveles = min(stock, max_niveles_stock - 1)
    niveles_stock = np.unique(np.rint(np.linspace(0, stock, n_niveles + 1)).astype(int))
    precios = precios_candidatos(estado)
    tasas = calcular_probabilidades(estado, dias, niveles_stock, precios, modo)
    medias = np.zeros_like(tasas)
    stocks = niveles_stock[1:].astype(float)[:, None]
    for d in range(1, dias+1):
        medias[d, 1:, :] = inferir_medias_latentes(tasas[d, 1:, :] * stocks, stocks, forma_nb)

    v = np.zeros((dias+1, len(niveles_stock)), dtype=float)
    pi = np.zeros((dias+1, len(niveles_stock)), dtype=np.int32)
    for d in range(1, dias + 1):
        for si, s in enumerate(niveles_stock[1:], start=1):
            alternativas = np.empty(len(precios))
            for j, precio in enumerate(precios):
                mu = float(medias[d, si, j])
                # Bellman estocástico: esperanza sobre todas las ventas posibles.
                # P(D >= s) se agrupa como la transición a inventario cero.
                p_nb = forma_nb / (forma_nb + mu)
                k = np.arange(int(s), dtype=int)
                probs = nbinom.pmf(k, forma_nb, p_nb)
                prob_agotar = float(nbinom.sf(int(s) - 1, forma_nb, p_nb))
                ventas = float(np.dot(k, probs) + s * prob_agotar)
                futuros = np.interp(s - k, niveles_stock, v[d - 1])
                futuro = float(np.dot(probs, futuros) + prob_agotar * v[d - 1, 0])
                alternativas[j] = precio * ventas + futuro
            mejor = int(np.argmax(alternativas))
            pi[d, si], v[d, si] = mejor, alternativas[mejor]
    return ResultadoIntegracion(
        pi, v, tasas, medias, precios, estado, modo, forma_nb,
        niveles_stock, stock
    )


def tabla_politica(resultado: ResultadoIntegracion) -> pd.DataFrame:
    filas = []
    for d in range(1, resultado.dias+1):
        for si, s in enumerate(resultado.niveles_stock[1:], start=1):
            j = int(resultado.politica[d, si])
            filas.append({
                'dias_restantes': d,
                'inventario_restante': s,
                'precio_optimo_eur': float(resultado.precios[j]),
                'ventas_esperadas_proximo_dia': s*float(resultado.probabilidades[d, si, j]),
                'demanda_potencial_media_estimada': float(resultado.medias_latentes[d, si, j]),
                'ingresos_acumulados_esperados_eur': float(resultado.valores[d, si]),
            })
    return pd.DataFrame(filas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archivo', type=Path, default=DATA)
    parser.add_argument('--evento', default='EV0001')
    parser.add_argument('--categoria', default='general')
    parser.add_argument('--dia', type=int, default=15)
    parser.add_argument('--modo', choices=['rate', 'direct'], default='rate')
    parser.add_argument('--forma-nb', type=float, default=9.0,
                        help='Parámetro hipotético de dispersión; NO calibrado con datos observados')
    parser.add_argument('--guardar', action='store_true')
    args = parser.parse_args()
    estado = cargar_estado(args.archivo, args.evento, args.categoria, args.dia)
    result = resolver(estado, modo=args.modo, forma_nb=args.forma_nb)
    print(f"Evento: {args.evento} | Categoría: {args.categoria} | Deporte: {estado['sport_type']}")
    print(f'Días: {result.dias} | Inventario restante: {result.stock}')
    print('Precios candidatos:', [f'{p:.2f} €' for p in result.precios])
    print('Modelo de incertidumbre: binomial negativa; forma=', result.forma_nb)
    print('Resultados XGBoost + PDE:', result.recomendacion())
    if args.guardar:
        destino = ROOT/'resultados'
        destino.mkdir(exist_ok=True)
        ruta = destino/f'politica_XGB_PDE_NB_{args.evento}_{args.categoria}_d{args.dia}_r{args.forma_nb:g}.csv'
        tabla_politica(result).to_csv(ruta, index=False)
        print('Política guardada:', ruta)


if __name__ == '__main__':
    main()
