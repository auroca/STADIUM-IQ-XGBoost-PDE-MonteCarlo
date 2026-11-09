"""Validacion interna multideporte STADIUM IQ (demanda condicionada a XGBoost).
Colocar en la raiz del proyecto y ejecutar con su .venv.
No utiliza datos reales ni constituye validacion externa.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from integracion_xgboost_pde import cargar_estado, resolver
from simulacion_montecarlo_xgboost import simular

ROOT = Path(__file__).resolve().parent
DATOS = ROOT / 'dataset_multideporte_EQUIPO.csv'


def seleccionar_eventos(datos: Path, dia: int, por_deporte: int, stock_min: int, stock_max: int):
    cols = ['event_id', 'sport_type', 'ticket_category', 'days_remaining', 'remaining_capacity']
    df = pd.read_csv(datos, usecols=cols)
    df = df.loc[(df.days_remaining == dia) &
                (df.remaining_capacity >= stock_min) &
                (df.remaining_capacity <= stock_max)].copy()
    df['distancia_stock'] = (df.remaining_capacity - 100).abs()
    # Seleccion reproducible: prioriza inventarios comparables, sin repetir evento por deporte
    seleccion = []
    for deporte in ('football', 'basketball', 'tennis', 'running'):
        subset = df[df.sport_type == deporte].sort_values(
            ['distancia_stock', 'event_id', 'ticket_category'])
        subset = subset.drop_duplicates(subset=['event_id']).head(por_deporte)
        if len(subset) < por_deporte:
            raise ValueError(f'No hay suficientes eventos de {deporte} con el rango de stock elegido')
        seleccion.extend(subset.to_dict('records'))
    return seleccion


def analizar_pares(trayectorias: pd.DataFrame):
    t = trayectorias.pivot(index='replica', columns='politica', values='ingresos_eur')
    diferencia = (t['XGBoost_PDE'] - t['XGBoost_inmediato']).to_numpy(float)
    n = len(diferencia)
    media = float(diferencia.mean())
    se = float(diferencia.std(ddof=1) / np.sqrt(n)) if n > 1 else float('nan')
    # Aproximacion normal, NO reemplaza una prueba de robustez frente a distintos eventos
    return {
        'diferencia_pde_vs_inmediato_eur': round(media, 2),
        'ic95_pareado_inferior_eur': round(media - 1.96 * se, 2),
        'ic95_pareado_superior_eur': round(media + 1.96 * se, 2),
        'porcentaje_replicas_pde_supera_inmediato': round(100 * (diferencia > 0).mean(), 2),
        'porcentaje_replicas_empate': round(100 * (diferencia == 0).mean(), 2),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archivo', type=Path, default=DATOS)
    ap.add_argument('--dia', type=int, default=10)
    ap.add_argument('--replicas', type=int, default=300)
    ap.add_argument('--por-deporte', type=int, default=2)
    ap.add_argument('--stock-min', type=int, default=50)
    ap.add_argument('--stock-max', type=int, default=150)
    ap.add_argument('--forma-nb', type=float, default=9.0)
    ap.add_argument('--semilla', type=int, default=42)
    ap.add_argument('--modo', choices=['rate', 'direct'], default='rate')
    ap.add_argument('--factor-demanda', type=float, default=1.0)
    args = ap.parse_args()
    if args.replicas < 2 or args.por_deporte < 1:
        ap.error('Usa al menos 2 replicas y 1 evento por deporte')
    seleccion = seleccionar_eventos(args.archivo, args.dia, args.por_deporte,
                                    args.stock_min, args.stock_max)
    salida = ROOT / 'resultados' / 'validacion_multideporte'
    salida.mkdir(parents=True, exist_ok=True)
    filas = []
    todas_trayectorias = []
    print(f'Se evaluaran {len(seleccion)} casos. Esto puede requerir calculo intensivo.\n', flush=True)
    for i, item in enumerate(seleccion, 1):
        ev, cat, dep = item['event_id'], item['ticket_category'], item['sport_type']
        print(f'[{i}/{len(seleccion)}] {dep}: {ev} / {cat}, stock={item["remaining_capacity"]}', flush=True)
        estado = cargar_estado(args.archivo, ev, cat, args.dia)
        resultado = resolver(estado, modo=args.modo, forma_nb=args.forma_nb)
        resumen, tray = simular(resultado, replicas=args.replicas,
                               semilla=args.semilla, factor_demanda=args.factor_demanda)
        metricas = analizar_pares(tray)
        valores = resumen.set_index('politica')
        fijo = float(valores.loc['precio_fijo', 'ingresos_medios_eur'])
        inm = float(valores.loc['XGBoost_inmediato', 'ingresos_medios_eur'])
        pde = float(valores.loc['XGBoost_PDE', 'ingresos_medios_eur'])
        filas.append({
            'deporte': dep, 'evento': ev, 'categoria': cat,
            'dias': resultado.dias, 'stock_inicial': resultado.stock,
            'precio_fijo_ingresos_medios_eur': fijo,
            'inmediato_ingresos_medios_eur': inm,
            'pde_ingresos_medios_eur': pde,
            'mejora_pde_vs_fijo_pct': round(100 * (pde / fijo - 1), 2) if fijo > 0 else np.nan,
            'mejora_pde_vs_inmediato_pct': round(100 * (pde / inm - 1), 2) if inm > 0 else np.nan,
            'ocupacion_pde_pct': float(valores.loc['XGBoost_PDE', 'ocupacion_media_pct']),
            'agotamiento_pde_pct': float(valores.loc['XGBoost_PDE', 'probabilidad_agotamiento_pct']),
            **metricas
        })
        tray.insert(0, 'deporte', dep)
        tray.insert(1, 'evento', ev)
        tray.insert(2, 'categoria', cat)
        todas_trayectorias.append(tray)
        # Guardar progreso tras cada evento, sin perder las ejecuciones previas
        pd.DataFrame(filas).to_csv(salida / 'resumen_eventos.csv', index=False)
        pd.concat(todas_trayectorias, ignore_index=True).to_csv(
            salida / 'trayectorias.csv', index=False)
        print(f'    PDE={pde:.2f} EUR | inmediato={inm:.2f} EUR | '
              f'diferencia pareada={metricas["diferencia_pde_vs_inmediato_eur"]:+.2f} EUR', flush=True)
    df = pd.DataFrame(filas)
    resumen_deportes = df.groupby('deporte', as_index=False).agg(
        casos=('evento','count'),
        media_mejora_pde_vs_inmediato_pct=('mejora_pde_vs_inmediato_pct','mean'),
        media_mejora_pde_vs_fijo_pct=('mejora_pde_vs_fijo_pct','mean'),
        media_ocupacion_pde_pct=('ocupacion_pde_pct','mean'))
    resumen_deportes.to_csv(salida / 'resumen_deportes.csv', index=False)
    print('\nRESUMEN POR DEPORTE (promedios descriptivos de eventos seleccionados):')
    print(resumen_deportes.round(2).to_string(index=False))
    print(f'\nArchivos: {salida}')
    print('IMPORTANTE: simulacion condicionada a XGBoost; sin validacion externa.')
    print('IC95: aproximacion normal por evento, calculada con diferencias emparejadas.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise
