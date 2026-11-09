import MonteCarloPanel from "./MonteCarloPanel";
import "./Validation.css";

// El dashboard V8.2 se retira de la pantalla principal de validación.
// Las evaluaciones históricas se conservan en frontend/public/validation/.
export default function Validation() {
  return (
    <main className="validation-page validation-redesign">
      <header className="validation-header validation-redesign-header">
        <div className="validation-eyebrow">STADIUM IQ / Comparador de estrategias</div>
        <h1>¿Qué estrategia genera más ingresos?</h1>
        <p>
          Compara tres políticas de precios para un mismo evento mediante
          simulación Monte Carlo. Analiza ingresos, ocupación e incertidumbre
          utilizando las predicciones de XGBoost.
        </p>
      </header>

      <div className="validation-redesign-steps" aria-label="Metodología de comparación">
        <div><strong>01 · Predecir</strong><span>XGBoost estima las ventas.</span></div>
        <div><strong>02 · Optimizar</strong><span>La PDE considera el inventario y el tiempo.</span></div>
        <div><strong>03 · Evaluar</strong><span>Monte Carlo compara las tres políticas.</span></div>
      </div>

      <MonteCarloPanel />

      <footer className="validation-redesign-footer">
        <strong>Alcance de la evaluación</strong>
        <p>
          Los resultados proceden de datos sintéticos y simulaciones condicionadas
          a XGBoost; no equivalen a una validación con ventas reales. Los antiguos
          indicadores V8.2 se han retirado de esta página para no mezclarlos
          con el análisis Monte Carlo de las tres políticas.
        </p>
      </footer>
    </main>
  );
}
