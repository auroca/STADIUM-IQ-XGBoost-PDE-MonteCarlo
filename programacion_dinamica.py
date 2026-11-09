"""Programación dinámica estocástica (PDE) de precio por día e inventario.

Estado: (días restantes, entradas disponibles). Acción: precio de rejilla fija.
Demanda potencial de cada día: mezcla Gamma-Poisson del generador original
(equivale a binomial negativa con forma Gamma=9). Ventas = min(D, stock).
Objetivo: maximizar el ingreso esperado total hasta el evento.

No se considera todavía una restricción de variación respecto al precio previo,
ni categorías interdependientes, ni objetivo mínimo de ocupación.

Ejemplo (desde la raíz):
 python3 src/programacion_dinamica.py --evento EV0001 --categoria general --dia 15 --guardar
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

from modelo_demanda import HipotesisDemanda, demanda_media
from optimizacion_simple import DATA, ROOT, optimizar_precio, precios_candidatos


@dataclass
class ResultadoPDE:
    """Política óptima para todos los días y todos los stocks <= stock_inicial."""
    valores: np.ndarray  # valores[d, s], d=0..dias, s=0..capacidad
    precios_optimos: np.ndarray  # índices de rejilla[d, s]
    precios: np.ndarray
    dias: int
    capacidad: int

    def recomendar(self, dias_restantes: int, capacidad_restante: int) -> dict:
        if not 1 <= dias_restantes <= self.dias:
            raise ValueError('Días restantes fuera del horizonte calculado')
        if not 0 <= capacidad_restante <= self.capacidad:
            raise ValueError('Capacidad restante fuera del estado calculado')
        p = float(self.precios[self.precios_optimos[dias_restantes, capacidad_restante]])
        return {
            'dias_restantes': dias_restantes,
            'capacidad_restante': capacidad_restante,
            'precio_recomendado_eur': p,
            'ingreso_total_esperado_eur': float(self.valores[dias_restantes, capacidad_restante]),
        }


def resolver_pde(
    dias_restantes: int,
    capacidad_restante: int,
    caracteristicas_evento: dict,
    precios: list[float],
    hipotesis: HipotesisDemanda = HipotesisDemanda(),
    forma_gamma: float = 9.0,
) -> ResultadoPDE:
    """Resuelve Bellman mediante programación hacia atrás.

    V[d,s] = max_p E[p min(D,s) + V[d-1, s-min(D,s)]].
    Distribución D: NB(r=forma_gamma, mean=demanda_media(p,d,s,...)).
    La media no depende del stock restante; se usa la capacidad ORIGINAL.
    """
    if not isinstance(dias_restantes, int) or dias_restantes < 1:
        raise ValueError('Se requiere un horizonte de al menos 1 día')
    if not isinstance(capacidad_restante, int) or capacidad_restante < 0:
        raise ValueError('Inventario inicial no válido')
    if forma_gamma <= 0:
        raise ValueError('forma_gamma debe ser positiva')
    if not precios:
        raise ValueError('Indica al menos un precio candidato')
    if 'max_price_change_pct' in caracteristicas_evento:
        # La restricción requiere ampliar el estado con precio anterior; no fingir que se aplica.
        pass
    rejilla = np.array(sorted({round(float(p), 2) for p in precios}), dtype=float)
    if not np.all(np.isfinite(rejilla)) or np.any(rejilla <= 0):
        raise ValueError('Todos los precios deben ser positivos y finitos')
    minimo = float(caracteristicas_evento['min_price'])
    maximo = float(caracteristicas_evento['max_price'])
    if np.any(rejilla < minimo - 1e-8) or np.any(rejilla > maximo + 1e-8):
        raise ValueError('Hay precios candidatos fuera de los límites comerciales')

    S, T = capacidad_restante, dias_restantes
    valores = np.zeros((T + 1, S + 1), dtype=float)
    elecciones = np.zeros((T + 1, S + 1), dtype=np.int32)
    k = np.arange(S + 1)

    for d in range(1, T + 1):
        anterior = valores[d - 1]
        alternativas = np.empty((len(rejilla), S + 1), dtype=float)
        for i, precio in enumerate(rejilla):
            mu = demanda_media(precio, d, S, caracteristicas_evento,
                               hipotesis=hipotesis)
            if not np.isfinite(mu) or mu < 0:
                raise ValueError('Media de demanda no válida')
            if mu == 0:
                alternativas[i] = anterior
                continue
            # Gamma-Poisson: NB(r, prob=r/(r+mu)).
            prob = forma_gamma / (forma_gamma + mu)
            pmf = nbinom.pmf(k, forma_gamma, prob)
            # E[V(d-1, s-min(D,s))], stock=0 -> V[d-1,0]=0.
            # Para D < s, stock siguiente s-D. Para D >= s, stock siguiente 0.
            futuro = np.convolve(anterior, pmf, mode='full')[:S + 1]
            # E[min(D,s)] = sum_{j=1}^s P(D >= j)
            ventas_esperadas = np.concatenate(([0.0], np.cumsum(nbinom.sf(k[:-1], forma_gamma, prob))))
            alternativas[i] = precio * ventas_esperadas + futuro
        elecciones[d] = np.argmax(alternativas, axis=0)
        valores[d] = alternativas[elecciones[d], np.arange(S + 1)]
    return ResultadoPDE(valores, elecciones, rejilla, T, S)


def cargar_estado(archivo: Path, evento: str, categoria: str, dia: int) -> dict:
    if not archivo.exists():
        raise FileNotFoundError(f'No se encuentra {archivo}')
    df = pd.read_csv(archivo)
    seleccion = df.loc[(df.event_id == evento) & (df.ticket_category == categoria)
                       & (df.days_remaining == dia)]
    if len(seleccion) != 1:
        raise ValueError('No existe una única observación con evento, categoría y día indicados')
    estado = seleccion.iloc[0].to_dict()
    estado['sales_window_days'] = int(df.loc[
        df.ticket_category_id == estado['ticket_category_id'], 'days_remaining'].max())
    return estado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archivo', type=Path, default=DATA)
    parser.add_argument('--evento', default='EV0001')
    parser.add_argument('--categoria', default='general')
    parser.add_argument('--dia', type=int, default=15)
    parser.add_argument('--elasticidad', type=float, default=1.3)
    parser.add_argument('--intensidad', type=float, default=1.0)
    parser.add_argument('--tendencia', type=float, default=0.25)
    parser.add_argument('--guardar', action='store_true')
    args = parser.parse_args()
    estado = cargar_estado(args.archivo, args.evento, args.categoria, args.dia)
    stock = int(estado['remaining_capacity'])
    hip = HipotesisDemanda(args.elasticidad, args.intensidad, args.tendencia)
    rejilla = precios_candidatos(estado)
    resultado = resolver_pde(args.dia, stock, estado, rejilla, hip)
    optimo = resultado.recomendar(args.dia, stock)
    greedy, tabla = optimizar_precio(args.dia, stock, estado, rejilla, hip)
    print(f"Evento {args.evento} | Deporte: {estado['sport_type']} | Categoría: {args.categoria}")
    print(f'Días restantes: {args.dia} | Inventario: {stock}')
    print('HIPÓTESIS de demanda no observadas:', hip)
    print('Precios candidatos:', [round(float(p), 2) for p in resultado.precios])
    print(f"Precio óptimo PDE hoy: {optimo['precio_recomendado_eur']:.2f} €")
    print(f"Ingreso TOTAL esperado PDE hasta el evento: {optimo['ingreso_total_esperado_eur']:.2f} €")
    print(f"Precio óptimo INMEDIATO hoy: {greedy['precio_eur']:.2f} €")
    print(f"Ingreso esperado solo del PRÓXIMO DÍA (inmediato): {greedy['ingresos_esperados_eur']:.2f} €")
    print('NOTA: los ingresos totales y diarios NO son magnitudes comparables directamente.')
    print('NOTA: no se aplican límites de variación diaria ni objetivos de ocupación.')
    if args.guardar:
        destino = ROOT / 'resultados'
        destino.mkdir(exist_ok=True)
        politica = []
        for d in range(1, args.dia + 1):
            for s in range(stock + 1):
                politica.append(resultado.recomendar(d, s))
        ruta = destino / f'politica_PDE_{args.evento}_{args.categoria}_d{args.dia}.csv'
        pd.DataFrame(politica).to_csv(ruta, index=False)
        print('Política guardada:', ruta)


if __name__ == '__main__':
    main()
