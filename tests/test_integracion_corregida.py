"""Pruebas de regresion del flujo XGBoost -> Bellman -> Monte Carlo."""
import unittest
import numpy as np
import pandas as pd
from scipy.stats import nbinom
from integracion_xgboost_pde import cargar_estado, resolver, tabla_politica
from simulacion_montecarlo_xgboost import simular
from predictor_xgboost import preparar_escenarios_precio


class TestIntegracion(unittest.TestCase):
    def test_variables_precio(self):
        df = pd.DataFrame({'previous_price': [20.0, 20.0]})
        result = preparar_escenarios_precio(df, [15.0, 25.0], 20.0)
        np.testing.assert_allclose(result['price_change_pct'], [-25, 25])
        self.assertEqual(result['discount_active'].tolist(), [1, 0])
        self.assertEqual(result['candidate_price'].tolist(), [15.0, 25.0])

    def test_bellman_un_dia_y_montecarlo(self):
        estado = cargar_estado('dataset_multideporte_EQUIPO.csv', 'EV0001', 'general', 15)
        result = resolver(estado, dias=1, stock=12, max_niveles_stock=13)
        # Para un solo día, la PDE coincide con optimización de ingresos esperados.
        for si, s in enumerate(result.niveles_stock[1:], start=1):
            valores = []
            for j, precio in enumerate(result.precios):
                mu = result.medias_latentes[1, si, j]
                prob = result.forma_nb / (result.forma_nb + mu)
                demanda = np.arange(s)
                ventas = np.dot(demanda, nbinom.pmf(demanda, result.forma_nb, prob))
                ventas += s * nbinom.sf(s - 1, result.forma_nb, prob)
                valores.append(precio * ventas)
            self.assertAlmostEqual(result.valores[1, si], max(valores), places=6)
        self.assertEqual(len(tabla_politica(result)), len(result.niveles_stock)-1)
        resumen, _ = simular(result, replicas=3)
        self.assertEqual(len(resumen), 3)

    def test_inventario_discretizado(self):
        estado = cargar_estado('dataset_multideporte_EQUIPO.csv', 'EV0001', 'general', 15)
        estado['category_capacity'] = 1800
        result = resolver(estado, dias=1, stock=1250, max_niveles_stock=40)
        self.assertEqual(result.indice_stock(1250), len(result.niveles_stock)-1)
        self.assertEqual(len(tabla_politica(result)), len(result.niveles_stock)-1)
        resumen, _ = simular(result, replicas=3)
        self.assertEqual(len(resumen), 3)


if __name__ == '__main__':
    unittest.main()
