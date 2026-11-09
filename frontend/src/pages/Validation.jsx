
import { useEffect, useMemo, useState } from "react";
import MonteCarloPanel from "./MonteCarloPanel";

import {
  ResponsiveContainer,
  CartesianGrid,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend
} from "recharts";

import "./Validation.css";

const SPORT_NAMES = {
  football: "Fútbol",
  basketball: "Baloncesto",
  tennis: "Tenis",
  running: "Running"
};

const euro = (value) =>
  new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0
  }).format(Number(value) || 0);

const number = (value, decimals = 1) =>
  Number(value || 0).toLocaleString("es-ES", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });

function parseCSV(text) {
  const lines = [];
  let fields = [];
  let field = "";
  let quoted = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (char === '"') {
      if (quoted && text[i + 1] === '"') {
        field += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      fields.push(field);
      field = "";
    } else if (
      (char === "\n" || char === "\r") &&
      !quoted
    ) {
      if (char === "\r" && text[i + 1] === "\n") {
        i++;
      }

      fields.push(field);

      if (fields.some((x) => x !== "")) {
        lines.push(fields);
      }

      fields = [];
      field = "";
    } else {
      field += char;
    }
  }

  fields.push(field);

  if (fields.some((x) => x !== "")) {
    lines.push(fields);
  }

  if (!lines.length) return [];

  const [headers, ...rows] = lines;
  headers[0] = headers[0].replace(/^\uFEFF/, "");

  return rows.map((cells) =>
    Object.fromEntries(
      headers.map((header, index) => [
        header,
        cells[index] ?? ""
      ])
    )
  );
}

async function loadFile(filename, csv = false) {
  const url =
    `${import.meta.env.BASE_URL}validation/${filename}`;

  const response = await fetch(url, {
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`No se encuentra ${filename}`);
  }

  const text = await response.text();

  return csv ? parseCSV(text) : JSON.parse(text);
}

function buildDailySeries(records) {
  if (!records.length) return [];

  const byPolicy = {
    precio_fijo: new Map(),
    ajuste_diario: new Map()
  };

  records.forEach((record) => {
    const policy = byPolicy[record.policy];

    if (!policy) return;

    const day = Number(record.days_remaining);

    policy.set(day, {
      income: Number(record.revenue_cumulative),
      stock: Number(record.remaining),
      price: Number(record.price)
    });
  });

  const allDays = records.map((r) =>
    Number(r.days_remaining)
  );

  const startingDay = Math.max(...allDays);

  const lastKnown = {
    precio_fijo: null,
    ajuste_diario: null
  };

  const result = [];

  for (let day = startingDay; day >= 1; day--) {
    for (const policy of Object.keys(byPolicy)) {
      const point = byPolicy[policy].get(day);

      if (point) {
        lastKnown[policy] = point;
      }
    }

    const fixed = lastKnown.precio_fijo;
    const dynamic = lastKnown.ajuste_diario;

    result.push({
      jornada: startingDay - day + 1,
      diasRestantes: day,

      ingresosFijos: fixed?.income ?? null,
      ingresosDinamicos: dynamic?.income ?? null,

      stockFijo: fixed?.stock ?? null,
      stockDinamico: dynamic?.stock ?? null,

      precioFijo: fixed?.price ?? null,
      precioDinamico: dynamic?.price ?? null
    });
  }

  return result;
}

export default function Validation() {
  const [summary, setSummary] = useState(null);
  const [repetitions, setRepetitions] = useState([]);
  const [details, setDetails] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState([]);

  const [selectedCategory, setSelectedCategory] =
    useState("");

  const [chartMode, setChartMode] =
    useState("income");

  useEffect(() => {
    let active = true;

    async function load() {
      // V8.2 - Resultados con ruido aleatorio compartido
      const requests = [
        ["v8_2_resumen.json", false],
        ["v8_2_repeticiones.csv", true],
        ["v8_2_detalle.csv", true]
      ];

      const results = await Promise.allSettled(
        requests.map(([filename, csv]) =>
          loadFile(filename, csv)
        )
      );

      if (!active) return;

      const missing = [];

      results.forEach((result, index) => {
        if (result.status === "rejected") {
          missing.push(requests[index][0]);
        }
      });

      if (results[0].status === "fulfilled") {
        setSummary(results[0].value);
      }

      if (results[1].status === "fulfilled") {
        setRepetitions(results[1].value);
      }

      if (results[2].status === "fulfilled") {
        setDetails(results[2].value);
      }

      setErrors(missing);
      setLoading(false);
    }

    load();

    return () => {
      active = false;
    };
  }, []);

  const categories = useMemo(() => {
    const unique = new Map();

    details.forEach((record) => {
      const key =
        `${record.event_id}|${record.ticket_category_id}`;

      if (!unique.has(key)) {
        unique.set(key, {
          key,
          label:
            `${record.event_id} · ${record.ticket_category_id}`
        });
      }
    });

    return [...unique.values()];
  }, [details]);

  const chosen = categories.some(
    (category) => category.key === selectedCategory
  )
    ? selectedCategory
    : categories[0]?.key || "";

  const daily = useMemo(() => {
    if (!chosen) return [];

    const [eventId, categoryId] = chosen.split("|");

    const filtered = details.filter(
      (record) =>
        record.event_id === eventId &&
        record.ticket_category_id === categoryId
    );

    return buildDailySeries(filtered);
  }, [details, chosen]);

  const sportData = useMemo(() => {
    if (!summary) return [];

    return Object.entries(summary.deportes || {})
      .map(([sport, value]) => ({
        sport: SPORT_NAMES[sport] || sport,
        improvement: Number(
          value?.mejora_pct?.media ?? 0
        )
      }))
      .sort(
        (a, b) => b.improvement - a.improvement
      );
  }, [summary]);

  const repetitionData = useMemo(
    () =>
      repetitions.map((record) => ({
        repetition: Number(record.repeticion),
        improvement: Number(record.mejora_pct)
      })),
    [repetitions]
  );

  const ending = daily[daily.length - 1];

  const finalFixed = ending?.ingresosFijos ?? 0;
  const finalDynamic = ending?.ingresosDinamicos ?? 0;

  const categoryImprovement =
    finalFixed > 0
      ? (finalDynamic / finalFixed - 1) * 100
      : null;

  const fixedSoldOut = daily.find(
    (point) => point.stockFijo === 0
  );

  const dynamicSoldOut = daily.find(
    (point) => point.stockDinamico === 0
  );

  const showingIncome = chartMode === "income";

  return (
    <main className="validation-page">
      <header className="validation-header">
        <div className="validation-eyebrow">
          STADIUM IQ / VALIDACIÃ“N
        </div>

        <h1>¿Funciona el precio dinámico?</h1>

        <p>
          Comparamos precios fijos frente a ajustes
          diarios decididos por XGBoost.
        </p>
      </header>

      {loading && (
        <div className="validation-notice">
          Cargando resultados de validación...
        </div>
      )}

      {errors.length > 0 && !loading && (
        <div className="validation-notice">
          Faltan archivos en{" "}
          <code>frontend/public/validation/</code>:{" "}
          {errors.join(", ")}
        </div>
      )}

      {summary && (
        <>
          <section className="validation-kpis">
            <article className="validation-kpi">
              <span>Mejora media de ingresos</span>

              <strong className="positive">
                {summary.mejora_global_pct.media >= 0
                  ? "+"
                  : ""}
                {number(
                  summary.mejora_global_pct.media,
                  2
                )} %
              </strong>

              <small>
                Precio dinámico frente a precio fijo
              </small>
            </article>

            <article className="validation-kpi">
              <span>Simulaciones con mejora</span>

              <strong>
                {summary.repeticiones_con_mejora}/
                {summary.repeticiones}
              </strong>

              <small>
                Repeticiones con resultado positivo
              </small>
            </article>

            <article className="validation-kpi">
              <span>Categorías ganadoras</span>

              <strong>
                {number(
                  summary.categorias_ganadas.media,
                  1
                )}/
                {summary.categorias}
              </strong>

              <small>
                Promedio por repetición
              </small>
            </article>

            <article className="validation-kpi">
              <span>Variabilidad</span>

              <strong>
                {number(
                  summary.mejora_global_pct.desviacion,
                  2
                )} pp
              </strong>

              <small>
                Desviación estándar de la mejora
              </small>
            </article>
          </section>

          <section className="validation-grid">
            <article className="validation-panel">
              <h2>Resultados por deporte</h2>

              <p>
                Mejora media de ingresos simulados.
              </p>

              <div className="validation-chart">
                <ResponsiveContainer
                  width="100%"
                  height="100%"
                >
                  <BarChart
                    data={sportData}
                    layout="vertical"
                    margin={{
                      top: 10,
                      right: 22,
                      bottom: 5,
                      left: 8
                    }}
                  >
                    <CartesianGrid
                      stroke="#28354c"
                      horizontal={false}
                    />

                    <XAxis
                      type="number"
                      tick={{ fill: "#9baac6" }}
                      tickFormatter={(v) => `${v}%`}
                    />

                    <YAxis
                      dataKey="sport"
                      type="category"
                      width={88}
                      tick={{ fill: "#dae3f5" }}
                    />

                    <Tooltip
                      formatter={(value) => [
                        `${number(value, 2)} %`,
                        "Mejora"
                      ]}
                    />

                    <Bar
                      dataKey="improvement"
                      fill="#a899ff"
                      radius={[0, 6, 6, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="validation-panel">
              <h2>Estabilidad de los resultados</h2>

              <p>
                Mejora obtenida en cada repetición.
              </p>

              {repetitionData.length ? (
                <div className="validation-chart">
                  <ResponsiveContainer
                    width="100%"
                    height="100%"
                  >
                    <LineChart
                      data={repetitionData}
                      margin={{
                        top: 10,
                        right: 20,
                        bottom: 5,
                        left: 0
                      }}
                    >
                      <CartesianGrid
                        stroke="#28354c"
                      />

                      <XAxis
                        dataKey="repetition"
                        tick={{ fill: "#9baac6" }}
                        allowDecimals={false}
                      />

                      <YAxis
                        domain={["auto", "auto"]}
                        tick={{ fill: "#9baac6" }}
                        tickFormatter={(v) => `${v}%`}
                      />

                      <Tooltip
                        formatter={(value) => [
                          `${number(value, 2)} %`,
                          "Mejora"
                        ]}
                      />

                      <Line
                        dataKey="improvement"
                        stroke="#69dcba"
                        strokeWidth={3}
                        dot={{ r: 3 }}
                        activeDot={{ r: 6 }}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="validation-placeholder">
                  No se ha cargado el archivo
                  de repeticiones.
                </div>
              )}
            </article>
          </section>
        </>
      )}

      <section className="validation-panel validation-wide">
        <div className="validation-panel-top">
          <div>
            <h2>Evolución durante la venta</h2>

            <p>
              Comparación de las dos estrategias
              para un evento y categoría.
            </p>
          </div>

          {categories.length > 0 && (
            <label className="validation-select-label">
              Evento y categoría

              <select
                value={chosen}
                onChange={(event) =>
                  setSelectedCategory(event.target.value)
                }
              >
                {categories.map((category) => (
                  <option
                    key={category.key}
                    value={category.key}
                  >
                    {category.label}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        {daily.length > 0 ? (
          <>
            <div className="validation-category-kpis">
              <div>
                <span>Ingresos con precio fijo</span>
                <strong>{euro(finalFixed)}</strong>
              </div>

              <div>
                <span>Ingresos con precio dinámico</span>
                <strong>{euro(finalDynamic)}</strong>
              </div>

              <div>
                <span>Diferencia en este escenario</span>
                <strong
                  className={
                    categoryImprovement >= 0
                      ? "positive"
                      : "negative"
                  }
                >
                  {categoryImprovement === null
                    ? "No disponible"
                    : `${
                        categoryImprovement >= 0
                          ? "+"
                          : ""
                      }${number(
                        categoryImprovement,
                        2
                      )} %`}
                </strong>
              </div>
            </div>

            <div className="validation-chart-toolbar">
              <div>
                <h3>
                  {showingIncome
                    ? "Ingresos acumulados"
                    : "Entradas disponibles"}
                </h3>

                <p>
                  {showingIncome
                    ? "Si se agotan las entradas, los ingresos dejan de crecer."
                    : "Inventario restante de cada estrategia."}
                </p>
              </div>

              <div className="validation-toggle">
                <button
                  type="button"
                  className={
                    showingIncome ? "selected" : ""
                  }
                  onClick={() =>
                    setChartMode("income")
                  }
                >
                  Ingresos
                </button>

                <button
                  type="button"
                  className={
                    !showingIncome ? "selected" : ""
                  }
                  onClick={() =>
                    setChartMode("stock")
                  }
                >
                  Entradas
                </button>
              </div>
            </div>

            <div className="validation-chart validation-large">
              <ResponsiveContainer
                width="100%"
                height="100%"
              >
                <LineChart
                  data={daily}
                  margin={{
                    top: 15,
                    right: 25,
                    bottom: 15,
                    left: 15
                  }}
                >
                  <CartesianGrid
                    stroke="#28354c"
                  />

                  <XAxis
                    dataKey="jornada"
                    tick={{ fill: "#9baac6" }}
                    allowDecimals={false}
                    label={{
                      value: "Jornada de venta",
                      position: "insideBottom",
                      offset: -8,
                      fill: "#9baac6"
                    }}
                  />

                  <YAxis
                    tick={{ fill: "#9baac6" }}
                    domain={[0, "auto"]}
                    tickFormatter={(v) =>
                      showingIncome
                        ? `${number(v / 1000, 0)}k â‚¬`
                        : number(v, 0)
                    }
                  />

                  <Tooltip
                    formatter={(value, name) => [
                      showingIncome
                        ? euro(value)
                        : `${number(value, 0)} entradas`,
                      name
                    ]}
                    labelFormatter={(day) =>
                      `Jornada ${day}`
                    }
                  />

                  <Legend
                    verticalAlign="top"
                    height={30}
                  />

                  <Line
                    type="monotone"
                    dataKey={
                      showingIncome
                        ? "ingresosFijos"
                        : "stockFijo"
                    }
                    name="Precio fijo"
                    stroke="#8ba3d5"
                    strokeWidth={2.5}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />

                  <Line
                    type="monotone"
                    dataKey={
                      showingIncome
                        ? "ingresosDinamicos"
                        : "stockDinamico"
                    }
                    name="Precio dinámico"
                    stroke="#ac96ff"
                    strokeWidth={3}
                    dot={false}
                    connectNulls={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="validation-stock-info">
              <div>
                <strong>Precio fijo</strong>
                <span>
                  {fixedSoldOut
                    ? `Entradas agotadas en la jornada ${fixedSoldOut.jornada}`
                    : `${number(
                        ending.stockFijo,
                        0
                      )} entradas restantes`}
                </span>
              </div>

              <div>
                <strong>Precio dinámico</strong>
                <span>
                  {dynamicSoldOut
                    ? `Entradas agotadas en la jornada ${dynamicSoldOut.jornada}`
                    : `${number(
                        ending.stockDinamico,
                        0
                      )} entradas restantes`}
                </span>
              </div>
            </div>

            <p className="validation-chart-note">
              Cuando una estrategia agota las entradas,
              su inventario permanece en cero y sus
              ingresos acumulados permanecen constantes.
              Se conserva el último resultado de la
              simulación hasta el final del período.
            </p>
          </>
        ) : (
          <div className="validation-placeholder">
            Copia v8_2_detalle.csv en
            frontend/public/validation/ para
            visualizar la evolución diaria.
          </div>
        )}
      </section>

      {/* NUEVA SECCIÓN: MONTE CARLO */}
      <MonteCarloPanel />

      <footer className="validation-footer">
        <strong>Interpretación de los resultados</strong>

        <p>
          Evaluación con datos sintéticos. Se han
          utilizado factores aleatorios compartidos
          entre las dos políticas para mejorar la
          comparabilidad. Las repeticiones mantienen
          los mismos eventos de prueba y el mismo
          modelo XGBoost. La estrategia dinámica
          maximiza ingresos previstos de cada día,
          no necesariamente los ingresos totales
          del evento.
        </p>
      </footer>
    </main>
  );
}
