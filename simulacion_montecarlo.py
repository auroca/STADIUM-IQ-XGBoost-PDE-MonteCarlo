"""Evaluación Monte Carlo de tres políticas de precio (fijo, inmediato, PDE).

Cada réplica usa las mismas variables aleatorias U(0,1) por día para las tres
políticas (números aleatorios comunes). La demanda de cada política sigue la
misma familia Gamma-Poisson/NB(r=9) pero con su propia media condicionada al precio.

La evaluación es sintética, bajo hipótesis de demanda configurables; no valida
rentabilidad real. Una categoría por simulación, horizonte diario.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import nbinom

from modelo_demanda import HipotesisDemanda, demanda_media
from optimizacion_simple import DATA, ROOT, precios_candidatos
from programacion_dinamica import cargar_estado, resolver_pde, ResultadoPDE

POLITICAS = ('precio_fijo', 'optimizacion_inmediata', 'PDE')


@dataclass
class ResultadoMonteCarlo:
    trayectorias: pd.DataFrame
    resumen: pd.DataFrame
    pde: ResultadoPDE


def demanda_aleatoria(media: float, uniform: float, forma_gamma: float = 9.0) -> int:
    """Cuantil NB coherente con mezcla Gamma(shape=r, scale=1/r) + Poisson."""
    if not np.isfinite(media) or media < 0 or forma_gamma <= 0:
        raise ValueError('Parámetros de demanda no válidos')
    if not 0 < uniform < 1:
        raise ValueError('uniform debe estar en el intervalo abierto (0,1)')
    if media == 0:
        return 0
    prob = forma_gamma / (forma_gamma + media)
    return int(nbinom.ppf(uniform, forma_gamma, prob))


def evaluar_politicas(
    dias: int,
    inventario: int,
    evento: dict,
    precios: list[float],
    hipotesis: HipotesisDemanda = HipotesisDemanda(1.3, 1., .25),
    *,
    evaluacion: HipotesisDemanda | None = None,
    replicas: int = 1000,
    seed: int = 42,
    forma_gamma: float = 9.0,
    precio_fijo: float | None = None,
) -> ResultadoMonteCarlo:
    """Compara ingresos de políticas completas partiendo del MISMO estado.

    hipotesis: supuestos que usan los optimizadores para decidir.
    evaluacion: mundo de demanda que genera las ventas; si None, coincide con hipotesis.
    Se permite separarlos para ensayar robustez frente a error del modelo.
    """
    if replicas < 1 or not isinstance(replicas, int):
        raise ValueError('replicas debe ser un entero >= 1')
    if dias < 1 or inventario < 0:
        raise ValueError('Estado inicial inválido')
    if forma_gamma <= 0:
        raise ValueError('forma_gamma debe ser positiva')
    if not precios:
        raise ValueError('No se han dado precios')
    evaluacion = evaluacion or hipotesis
    candidatos = sorted({round(float(p), 2) for p in precios})
    if precio_fijo is None:
        precio_fijo = min(candidatos, key=lambda p: abs(p - float(evento['base_price'])))
    if round(precio_fijo, 2) not in candidatos:
        raise ValueError('El precio fijo debe pertenecer a la rejilla de precios')
    if inventario > int(evento['category_capacity']):
        raise ValueError('El inventario inicial supera la capacidad original de categoría')

    pde = resolver_pde(dias, inventario, evento, candidatos, hipotesis, forma_gamma)
    # Tabla precalculada para la política miope: evita repetir el mismo cálculo
    # miles de veces. E[min(D,s)] = suma P(D >= k), k=1..s.
    greedy_precio = np.full((dias + 1, inventario + 1), float(candidatos[0]))
    stock_grid = np.arange(inventario)
    for d in range(1, dias + 1):
        rendimientos = []
        for p in candidatos:
            mu = demanda_media(p, d, inventario, evento, hipotesis=hipotesis)
            prob = forma_gamma / (forma_gamma + mu)
            ventas = np.concatenate(([0.], np.cumsum(nbinom.sf(stock_grid, forma_gamma, prob))))
            # La versión simple redondea ventas a tres decimales e ingresos a céntimos.
            rendimientos.append(np.round(float(p) * np.round(ventas, 3), 2))
        mejores = np.argmax(np.asarray(rendimientos), axis=0)
        greedy_precio[d] = np.asarray(candidatos)[mejores]
    rng = np.random.default_rng(seed)
    # Una misma trayectoria de cuantiles para comparar justamente las estrategias.
    cuantiles = rng.uniform(np.finfo(float).eps, 1. - np.finfo(float).eps,
                           size=(replicas, dias))
    registros = []
    for replica in range(replicas):
        for politica in POLITICAS:
            stock = inventario
            ingresos = 0.
            vendidas = 0
            dia_agotamiento = None
            for j, d in enumerate(range(dias, 0, -1)):
                if stock == 0:
                    # No hay ventas ni ingresos aunque sigan quedando días.
                    continue
                if politica == 'precio_fijo':
                    precio = float(precio_fijo)
                elif politica == 'optimizacion_inmediata':
                    precio = float(greedy_precio[d, stock])
                else:
                    precio = float(pde.precios[pde.precios_optimos[d, stock]])

                mu = demanda_media(precio, d, stock, evento, hipotesis=evaluacion)
                demanda = demanda_aleatoria(mu, float(cuantiles[replica, j]), forma_gamma)
                ventas = min(demanda, stock)
                stock -= ventas
                vendidas += ventas
                ingresos += precio * ventas
                if stock == 0 and dia_agotamiento is None:
                    dia_agotamiento = d

            registros.append({
                'replica': replica + 1,
                'politica': politica,
                'ingresos_eur': round(ingresos, 2),
                'ventas': vendidas,
                'inventario_final': stock,
                'ocupacion_inventario_inicial_pct': 100. * vendidas / inventario if inventario else 0.,
                'agotado': int(stock == 0 and inventario > 0),
                'dias_restantes_al_agotar': dia_agotamiento,
            })
    trayectorias = pd.DataFrame(registros)
    res = []
    for politica in POLITICAS:
        x = trayectorias.loc[trayectorias.politica == politica]
        res.append({
            'politica': politica,
            'replicas': replicas,
            'ingresos_medios_eur': round(x.ingresos_eur.mean(), 2),
            'ingresos_mediana_eur': round(x.ingresos_eur.median(), 2),
            'ingresos_p05_eur': round(x.ingresos_eur.quantile(.05), 2),
            'ingresos_p95_eur': round(x.ingresos_eur.quantile(.95), 2),
            'desviacion_ingresos_eur': round(x.ingresos_eur.std(ddof=0), 2),
            'ventas_medias': round(x.ventas.mean(), 2),
            'ocupacion_media_pct': round(x.ocupacion_inventario_inicial_pct.mean(), 2),
            'inventario_final_medio': round(x.inventario_final.mean(), 2),
            'probabilidad_agotamiento_pct': round(100. * x.agotado.mean(), 2),
        })
    return ResultadoMonteCarlo(trayectorias, pd.DataFrame(res), pde)


def guardar(result: ResultadoMonteCarlo, nombre: str, carpeta: Path) -> list[Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = [carpeta / f'montecarlo_resumen_{nombre}.csv',
             carpeta / f'montecarlo_trayectorias_{nombre}.csv',
             carpeta / f'montecarlo_ingresos_{nombre}.png']
    result.resumen.to_csv(rutas[0], index=False)
    result.trayectorias.to_csv(rutas[1], index=False)
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 5))
        arrays = [result.trayectorias.loc[result.trayectorias.politica == p, 'ingresos_eur'] for p in POLITICAS]
        ax.boxplot(arrays, tick_labels=['Precio fijo', 'Inmediata', 'PDE'], showfliers=False)
        ax.set_title('Monte Carlo: distribución de ingresos por política')
        ax.set_ylabel('Ingresos acumulados (€)')
        ax.grid(axis='y', alpha=.3)
        fig.tight_layout()
        fig.savefig(rutas[2], dpi=160)
        plt.close(fig)
    except ImportError:
        print('Aviso: instala matplotlib para guardar la gráfica PNG')
        rutas.pop()
    return rutas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archivo', type=Path, default=DATA)
    parser.add_argument('--evento', default='EV0001')
    parser.add_argument('--categoria', default='general')
    parser.add_argument('--dia', type=int, default=15)
    parser.add_argument('--replicas', type=int, default=1000)
    parser.add_argument('--semilla', type=int, default=42)
    parser.add_argument('--elasticidad', type=float, default=1.3)
    parser.add_argument('--intensidad', type=float, default=1.0)
    parser.add_argument('--tendencia', type=float, default=.25)
    parser.add_argument('--elasticidad-real-simulada', type=float, default=None,
                        help='Hipótesis diferente para evaluar robustez (si se omite, coincide)')
    parser.add_argument('--guardar', action='store_true')
    args = parser.parse_args()
    evento = cargar_estado(args.archivo, args.evento, args.categoria, args.dia)
    hip = HipotesisDemanda(args.elasticidad, args.intensidad, args.tendencia)
    eval_hip = (HipotesisDemanda(args.elasticidad_real_simulada, args.intensidad, args.tendencia)
                if args.elasticidad_real_simulada is not None else hip)
    precios = precios_candidatos(evento)
    result = evaluar_politicas(args.dia, int(evento['remaining_capacity']), evento,
                                precios, hip, evaluacion=eval_hip, replicas=args.replicas,
                                seed=args.semilla)
    print(f"Evento: {args.evento} | Deporte: {evento['sport_type']} | Categoría: {args.categoria}")
    print(f"Días: {args.dia} | Inventario inicial: {int(evento['remaining_capacity'])}")
    print('Hipótesis del optimizador:', hip)
    print('Hipótesis del simulador de evaluación:', eval_hip)
    print('Números aleatorios comunes por réplica para las tres políticas.')
    print('\nRESULTADOS MONTE CARLO:')
    print(result.resumen.to_string(index=False))
    print(f"\nIngreso esperado teórico PDE (Bellman): {result.pde.valores[args.dia, int(evento['remaining_capacity'])]:.2f} €")
    if args.guardar:
        nombre = f'{args.evento}_{args.categoria}_d{args.dia}'
        for ruta in guardar(result, nombre, ROOT / 'resultados'):
            print('Guardado:', ruta)


if __name__ == '__main__':
    main()
