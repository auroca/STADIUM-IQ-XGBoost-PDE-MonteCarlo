
"""Monte Carlo coherente con XGBoost + PDE con demanda binomial negativa.

La 'realidad' simulada usa un modelo condicionado a XGBoost: NO es una
validación externa. El parámetro forma_nb no está calibrado empíricamente.
"""
from __future__ import annotations
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom
from integracion_xgboost_pde import cargar_estado, resolver

ROOT = Path(__file__).resolve().parent


def simular(resultado, replicas=500, semilla=42, factor_demanda=1.0):
    if replicas < 1 or not np.isfinite(factor_demanda) or factor_demanda <= 0:
        raise ValueError('Indica réplicas >= 1 y factor_demanda > 0')
    dias, stock_inicial = resultado.dias, resultado.stock
    precios, tasas, medias = resultado.precios, resultado.probabilidades, resultado.medias_latentes
    forma_nb = resultado.forma_nb
    greedy = np.argmax(tasas*resultado.niveles_stock[None,:,None]*precios, axis=2)
    fijo = int(np.argmin(np.abs(precios - float(resultado.estado['base_price']))))
    politicas = ('precio_fijo','XGBoost_inmediato','XGBoost_PDE')
    rng = np.random.default_rng(semilla)
    uniformes = rng.uniform(1e-12, 1-1e-12, size=(replicas,dias))
    registros = []
    for rep in range(replicas):
        for nombre in politicas:
            stock, ingreso, vendidas = stock_inicial, 0.0, 0
            for i, d in enumerate(range(dias, 0, -1)):
                if stock <= 0:
                    break
                si = resultado.indice_stock(stock)
                if nombre == 'precio_fijo':
                    j = fijo
                elif nombre == 'XGBoost_inmediato':
                    j = int(greedy[d,si])
                else:
                    j = int(resultado.politica[d,si])
                # El escenario de sensibilidad cambia la media latente, NO la tasa
                # de ventas censuradas. De esta forma sigue siendo una distribución NB.
                mu = max(0.0, float(medias[d,si,j])*factor_demanda)
                prob = forma_nb/(forma_nb+mu)
                demanda = int(nbinom.ppf(uniformes[rep,i], forma_nb, prob))
                ventas = min(stock, demanda)
                ingreso += ventas*float(precios[j])
                vendidas += ventas
                stock -= ventas
            registros.append({'replica':rep+1,'politica':nombre,
                              'ingresos_eur':round(ingreso,2), 'ventas':vendidas,
                              'inventario_final':stock,
                              'ocupacion_pct':100*vendidas/stock_inicial,
                              'agotado':int(stock==0)})
    trayectorias = pd.DataFrame(registros)
    resumen=[]
    for name in politicas:
        a = trayectorias[trayectorias.politica==name]
        resumen.append({'politica':name,'replicas':replicas,
                        'ingresos_medios_eur':round(a.ingresos_eur.mean(),2),
                        'ingresos_p05_eur':round(a.ingresos_eur.quantile(.05),2),
                        'ingresos_p95_eur':round(a.ingresos_eur.quantile(.95),2),
                        'desviacion_ingresos_eur':round(a.ingresos_eur.std(ddof=0),2),
                        'ocupacion_media_pct':round(a.ocupacion_pct.mean(),2),
                        'stock_final_medio':round(a.inventario_final.mean(),2),
                        'probabilidad_agotamiento_pct':round(100*a.agotado.mean(),2)})
    return pd.DataFrame(resumen), trayectorias


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archivo',type=Path,default=ROOT/'dataset_multideporte_EQUIPO.csv')
    parser.add_argument('--evento',default='EV0001')
    parser.add_argument('--categoria',default='general')
    parser.add_argument('--dia',type=int,default=15)
    parser.add_argument('--modo',choices=['rate','direct'],default='rate')
    parser.add_argument('--forma-nb',type=float,default=9.0)
    parser.add_argument('--replicas',type=int,default=500)
    parser.add_argument('--semilla',type=int,default=42)
    parser.add_argument('--factor-demanda',type=float,default=1.0)
    parser.add_argument('--guardar',action='store_true')
    args=parser.parse_args()
    estado=cargar_estado(args.archivo,args.evento,args.categoria,args.dia)
    resultado=resolver(estado,modo=args.modo,forma_nb=args.forma_nb)
    resumen,trayectorias=simular(resultado,args.replicas,args.semilla,args.factor_demanda)
    print(f'Monte Carlo XGBoost + PDE (NB) | {args.evento} / {args.categoria} | días={resultado.dias}, stock={resultado.stock}')
    print(f'Dispersión NB hipotética r={args.forma_nb:g} | factor-demanda={args.factor_demanda:g}')
    print('SIMULACIÓN CONDICIONADA A XGBoost: no es validación independiente.')
    print(resumen.to_string(index=False))
    if args.guardar:
        destino=ROOT/'resultados';destino.mkdir(exist_ok=True)
        nombre=f'{args.evento}_{args.categoria}_d{args.dia}_r{args.forma_nb:g}_f{args.factor_demanda:g}'
        for tabla,prefijo in ((resumen,'montecarlo_XGB_NB_resumen'),(trayectorias,'montecarlo_XGB_NB_trayectorias')):
            ruta=destino/f'{prefijo}_{nombre}.csv';tabla.to_csv(ruta,index=False);print('Guardado:',ruta)
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig,ax=plt.subplots(figsize=(9,5))
            orden=['precio_fijo','XGBoost_inmediato','XGBoost_PDE']
            ax.boxplot([trayectorias.loc[trayectorias.politica==p,'ingresos_eur'] for p in orden],
                       tick_labels=['Fijo','XGBoost inmediato','XGBoost + PDE'], showfliers=False)
            ax.set_ylabel('Ingresos acumulados (€)')
            ax.set_title('Monte Carlo con demanda NB condicionada a XGBoost')
            fig.tight_layout()
            ruta=destino/f'montecarlo_XGB_NB_grafico_{nombre}.png';fig.savefig(ruta,dpi=150);plt.close(fig)
            print('Guardado:',ruta)
        except ImportError:
            print('Aviso: instala matplotlib para generar el gráfico')


if __name__=='__main__':
    main()
