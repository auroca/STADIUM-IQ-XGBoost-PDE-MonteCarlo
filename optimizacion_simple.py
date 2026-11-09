"""Optimizador inmediato: maximiza ingresos esperados del PRÓXIMO día.

Se usa el mismo modelo de media potencial del generador sintético. La demanda
aleatoria procede de una mezcla Gamma(shape=9,scale=1/9)+Poisson, equivalente
a una binomial negativa de media mu y dispersión shape=9.
No es todavía programación dinámica estocástica.

Ejecutar desde la raíz del proyecto:
 python3 src/optimizacion_simple.py --evento EV0001 --dia 15 --categoria general
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

from modelo_demanda import demanda_media, HipotesisDemanda

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'resultados' / 'dataset_multideporte_EQUIPO.csv'


def ventas_esperadas_limitadas(media: float, inventario: int, forma_gamma: float = 9.0) -> float:
    """E[min(D, inventario)] calculada sin muestreo.

    D sigue binomial negativa por mezcla Gamma-Poisson, suponiendo la misma
    forma_gamma=9 usada por el generador del dataset.
    """
    if not np.isfinite(media) or media < 0 or inventario < 0 or forma_gamma <= 0:
        raise ValueError('Valores no válidos en ventas esperadas')
    if inventario == 0 or media == 0:
        return 0.0
    # P(D=0). Si se anula numéricamente, el inventario es casi seguro agotado.
    p0 = float((forma_gamma / (forma_gamma + media)) ** forma_gamma)
    if p0 == 0:
        return float(inventario)
    prob = p0
    cdf = prob
    esperado = 0.0
    ratio = media / (media + forma_gamma)
    for n in range(1, inventario + 1):
        esperado += max(0.0, 1.0 - cdf)  # P(D >= n)
        prob *= (n - 1 + forma_gamma) / n * ratio
        cdf = min(1.0, cdf + prob)
    return float(np.clip(esperado, 0.0, inventario))


def optimizar_precio(
    dias_restantes: int,
    capacidad_restante: int,
    caracteristicas_evento: dict,
    precios: list[float],
    hipotesis: HipotesisDemanda = HipotesisDemanda(),
) -> tuple[dict, pd.DataFrame]:
    """Retorna (fila mejor precio, tabla ordenada por precio)."""
    if not precios:
        raise ValueError('Proporciona al menos un precio candidato')
    min_p = float(caracteristicas_evento['min_price'])
    max_p = float(caracteristicas_evento['max_price'])
    filas = []
    for precio in sorted(set(round(float(p), 2) for p in precios)):
        if not min_p <= precio <= max_p:
            raise ValueError(f'Precio {precio} fuera de límites [{min_p}, {max_p}]')
        media = demanda_media(precio, dias_restantes, capacidad_restante,
                              caracteristicas_evento, hipotesis=hipotesis)
        ventas = ventas_esperadas_limitadas(media, capacidad_restante)
        filas.append({
            'precio_eur': precio,
            'demanda_potencial_media': round(media, 3),
            'ventas_esperadas': round(ventas, 3),
            'ingresos_esperados_eur': round(precio * ventas, 2),
        })
    tabla = pd.DataFrame(filas)
    mejor = tabla.sort_values(['ingresos_esperados_eur', 'precio_eur'],
                              ascending=[False, True]).iloc[0].to_dict()
    return mejor, tabla


def precios_candidatos(evento: dict) -> list[float]:
    """Misma rejilla de movimientos que usa el generador, entorno del precio base."""
    base = float(evento['base_price'])
    inferior, superior = float(evento['min_price']), float(evento['max_price'])
    return sorted(set(round(float(np.clip(base * (1 + mov), inferior, superior)), 2)
                      for mov in [-.20, -.10, 0.0, .10, .20]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archivo', type=Path, default=DATA)
    parser.add_argument('--evento', default='EV0001')
    parser.add_argument('--categoria', default='general')
    parser.add_argument('--dia', type=int, default=15,
                        help='Días restantes al evento, por defecto 15')
    parser.add_argument('--elasticidad', type=float, default=1.3)
    parser.add_argument('--intensidad', type=float, default=1.0)
    parser.add_argument('--tendencia', type=float, default=.25)
    parser.add_argument('--guardar', action='store_true', help='Guardar tabla CSV')
    args = parser.parse_args()
    if not args.archivo.exists():
        raise SystemExit(f'No existe {args.archivo}; ejecuta antes generar_dataset.py')
    df = pd.read_csv(args.archivo)
    seleccion = df.loc[(df.event_id == args.evento)
                       & (df.ticket_category == args.categoria)
                       & (df.days_remaining == args.dia)]
    if len(seleccion) != 1:
        disponibles = df[['event_id', 'ticket_category']].drop_duplicates().head(10)
        raise SystemExit(f'Selección sin una observación única. Ejemplos:\n{disponibles}')
    estado = seleccion.iloc[0].to_dict()
    # Esta propiedad no existe como columna porque el generador tenía duración fija.
    estado['sales_window_days'] = int(df.loc[
        df.ticket_category_id == estado['ticket_category_id'], 'days_remaining'].max())
    hipotesis = HipotesisDemanda(args.elasticidad, args.intensidad, args.tendencia)
    precios = precios_candidatos(estado)
    mejor, tabla = optimizar_precio(
        int(estado['days_remaining']), int(estado['remaining_capacity']),
        estado, precios, hipotesis)
    print(f"Evento: {args.evento} | Deporte: {estado['sport_type']} | Categoría: {args.categoria}")
    print(f"Días restantes: {args.dia} | Entradas restantes: {estado['remaining_capacity']}")
    print(f"Precio actual registrado (dato sintético): {estado['current_price']:.2f} €")
    print(f'Hipótesis NO observadas: elasticidad={args.elasticidad}, intensidad={args.intensidad}, tendencia={args.tendencia}')
    print('\nCOMPARACIÓN DE PRECIOS (solo próximo día):')
    print(tabla.to_string(index=False))
    print(f"\nPRECIO RECOMENDADO: {mejor['precio_eur']:.2f} €")
    print(f"INGRESOS ESPERADOS EN EL PRÓXIMO DÍA: {mejor['ingresos_esperados_eur']:.2f} €")
    if args.guardar:
        destino = ROOT / 'resultados' / f'comparacion_{args.evento}_{args.categoria}_d{args.dia}.csv'
        tabla.to_csv(destino, index=False)
        print('Comparación guardada en:', destino)


if __name__ == '__main__':
    main()
