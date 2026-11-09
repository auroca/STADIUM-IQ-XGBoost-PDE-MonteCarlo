
import { useEffect, useState } from "react";
import axios from "axios";
import { API, authHeaders } from "../auth";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

const euro = value =>
  new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR"
  }).format(value ?? 0);

const fmt = (value, decimals = 1) =>
  new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: decimals
  }).format(value ?? 0);

const STRATEGIES = {
  precio_fijo: "Precio fijo",
  XGBoost_inmediato: "XGBoost inmediato",
  XGBoost_PDE: "XGBoost + PDE"
};

const COLORS = {
  precio_fijo: "#8794b5",
  XGBoost_inmediato: "#a99aff",
  XGBoost_PDE: "#65d9bb"
};

const panelStyle = {
  background: "#171f33",
  border: "1px solid #394461",
  borderRadius: 16,
  padding: 24,
  color: "#e9edff"
};

const mutedStyle = {
  color: "#b8c6e5",
  lineHeight: 1.6
};

function makePayload(event) {
  const custom = event.custom || {};

  const fields = Object.fromEntries(
    Object.entries(custom).map(([key, value]) => [
      key,
      key === "tournament_round"
        ? (value === "" || value == null ? null : value)
        : (value === "" || value == null
            ? null
            : Number(value))
    ])
  );

  return {
    sport_type: event.sport,
    ticket_category: event.ticketCategory,
    days_remaining: Number(event.days),
    event_name: event.eventName || "Mi evento",
    model: event.model || "rate",
    ...fields
  };
}

function validatePayload(payload) {
  if (!payload.sport_type || !payload.ticket_category) {
    return "Falta el deporte o la categoría.";
  }

  if (
    !Number.isInteger(payload.days_remaining) ||
    payload.days_remaining < 1 ||
    payload.days_remaining > 15
  ) {
    return "Monte Carlo admite entre 1 y 15 días.";
  }

  if (
    !Number.isInteger(payload.remaining_capacity) ||
    payload.remaining_capacity < 1 ||
    payload.remaining_capacity > 5000
  ) {
    return "Introduce entre 1 y 5000 entradas disponibles.";
  }

  if (
    !Number.isInteger(payload.category_capacity) ||
    payload.category_capacity < payload.remaining_capacity
  ) {
    return "El aforo del evento no es válido.";
  }

  if (
    !(payload.current_price > 0) ||
    !(
      (payload.reference_price ?? payload.current_price) > 0
    )
  ) {
    return "El evento necesita precios válidos.";
  }

  if (
    !Number.isFinite(payload.popularity_index) ||
    !Number.isFinite(payload.event_importance)
  ) {
    return "Faltan datos de popularidad o importancia.";
  }

  return null;
}

function Metric({ title, value, detail }) {
  return (
    <div style={{
      background: "#202a43",
      border: "1px solid #394461",
      borderRadius: 12,
      padding: 18
    }}>
      <p style={{
        ...mutedStyle,
        fontSize: 13,
        margin: "0 0 10px"
      }}>
        {title}
      </p>

      <strong style={{ fontSize: 22 }}>
        {value}
      </strong>

      {detail && (
        <p style={{
          ...mutedStyle,
          fontSize: 12,
          marginBottom: 0
        }}>
          {detail}
        </p>
      )}
    </div>
  );
}

export default function MonteCarloPanel() {
  const [events, setEvents] = useState([]);
  const [selectedId, setSelectedId] = useState("");

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [error, setError] = useState("");

  // El escenario principal es siempre XGBoost al 100 %.
  const [scenario, setScenario] = useState(100);

  // Los escenarios alternativos son opcionales.
  const [sensitivityOpen, setSensitivityOpen] = useState(false);

  useEffect(() => {
    let active = true;

    axios.get(`${API}/api/v7/events`, {
      headers: authHeaders()
    })
      .then(response => {
        if (!active) return;

        setEvents(
          Array.isArray(response.data) ? response.data : []
        );
      })
      .catch(() => {
        if (active) {
          setError("No se pudieron cargar los eventos guardados.");
        }
      })
      .finally(() => {
        if (active) setLoadingEvents(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const selectedEvent = events.find(
    event => event.id === selectedId
  );

  const activeScenario = result?.scenarios?.find(
    item => Number(item.demanda_porcentaje) === scenario
  );

  const rows = activeScenario?.resultados || [];

  const fixed = rows.find(
    row => row.politica === "precio_fijo"
  );

  const immediate = rows.find(
    row => row.politica === "XGBoost_inmediato"
  );

  const pde = rows.find(
    row => row.politica === "XGBoost_PDE"
  );

  const chartData = rows.map(row => ({
    key: row.politica,
    name: STRATEGIES[row.politica] || row.politica,
    ingresos: row.ingresos_medios_eur
  }));

  // Un empate se determina con la precision de ingresos mostrada (centimos).
  const maxIngresos = rows.length
    ? Math.max(...rows.map(row => Number(row.ingresos_medios_eur)))
    : null;

  const ganadoras = maxIngresos === null
    ? []
    : rows.filter(row =>
        Math.abs(Number(row.ingresos_medios_eur) - maxIngresos) < 0.005
      );

  const etiquetaGanadoras = ganadoras.length > 1
    ? `Empate en ingresos medios: ${ganadoras.map(row =>
        STRATEGIES[row.politica] || row.politica
      ).join(" y ")}`
    : ganadoras.length === 1
      ? STRATEGIES[ganadoras[0].politica] || ganadoras[0].politica
      : "No disponible";

  const difference =
    pde && immediate
      ? pde.ingresos_medios_eur -
        immediate.ingresos_medios_eur
      : null;

  const improvement =
    pde && fixed && fixed.ingresos_medios_eur > 0
      ? (
          pde.ingresos_medios_eur /
          fixed.ingresos_medios_eur - 1
        ) * 100
      : null;

  async function runSimulation() {
    if (!selectedEvent) {
      setError("Selecciona un evento guardado.");
      return;
    }

    const payload = makePayload(selectedEvent);
    const validationError = validatePayload(payload);

    if (validationError) {
      setError(validationError);
      setResult(null);
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);
    setScenario(100);
    setSensitivityOpen(false);

    try {
      const response = await axios.post(
        `${API}/api/v7/custom/montecarlo`,
        payload,
        {
          params: {
            replicas: 100,
            forma_nb: 9
          }
        }
      );

      if (response.data.status !== "ok") {
        throw new Error(
          response.data.message ||
          "La simulación no ha finalizado correctamente."
        );
      }

      setResult(response.data);

    } catch (err) {
      const detail = err.response?.data?.detail;

      setError(
        typeof detail === "string"
          ? detail
          : err.message ||
            "No se pudo ejecutar Monte Carlo."
      );

    } finally {
      setLoading(false);
    }
  }

  function toggleSensitivity() {
    if (sensitivityOpen) {
      setScenario(100);
    }

    setSensitivityOpen(!sensitivityOpen);
  }

  return (
    <section style={{
      ...panelStyle,
      marginTop: 0
    }}>
      <div style={{
        fontSize: 12,
        fontWeight: 700,
        letterSpacing: 1.5,
        color: "#aa9bff"
      }}>
        CONFIGURACIÓN Y RESULTADOS DEL ESCENARIO
      </div>

      <h2 style={{ marginTop: 12 }}>
        Comparador de estrategias
      </h2>

      <p style={mutedStyle}>
        Selecciona un evento guardado y compara precio fijo,
        XGBoost inmediato y XGBoost + PDE bajo la misma
        configuración de simulación.
      </p>

      {/* SELECCIÓN DEL EVENTO */}

      <div style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 16,
        alignItems: "end",
        marginTop: 24
      }}>
        <label style={{
          flex: "1 1 250px",
          display: "grid",
          gap: 8
        }}>
          <span>Evento guardado</span>

          <select
            value={selectedId}
            disabled={loadingEvents || loading}
            onChange={e => {
              setSelectedId(e.target.value);
              setResult(null);
              setError("");
              setScenario(100);
              setSensitivityOpen(false);
            }}
            style={{
              padding: 13,
              borderRadius: 8,
              background: "#202a43",
              border: "1px solid #65739a",
              color: "#fff"
            }}
          >
            <option value="">
              {loadingEvents
                ? "Cargando eventos..."
                : "Selecciona un evento"}
            </option>

            {events.map(event => (
              <option key={event.id} value={event.id}>
                {event.eventName || event.id}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={runSimulation}
          disabled={loading || !selectedId}
          style={{
            padding: "14px 20px",
            background: "#a99aff",
            color: "#17172c",
            border: 0,
            borderRadius: 8,
            fontWeight: 700,
            cursor: loading ? "wait" : "pointer"
          }}
        >
          {loading
            ? "Simulando..."
            : "Ejecutar Monte Carlo"}
        </button>
      </div>

      {selectedEvent && (
        <p style={{
          ...mutedStyle,
          fontSize: 13
        }}>
          {selectedEvent.sport} ·{" "}
          {selectedEvent.days} días ·{" "}
          {fmt(
            selectedEvent.custom?.remaining_capacity,
            0
          )} entradas disponibles
        </p>
      )}

      {!loadingEvents && events.length === 0 && (
        <p style={mutedStyle}>
          Guarda primero un evento desde el simulador
          multideporte para poder evaluarlo.
        </p>
      )}

      {error && (
        <div role="alert" style={{
          padding: 16,
          marginTop: 20,
          border: "1px solid #ef9a9a",
          borderRadius: 10
        }}>
          {error}
        </div>
      )}

      {result && (
        <>
          {/* ESCENARIO PRINCIPAL */}

          <div style={{
            marginTop: 30,
            padding: 18,
            borderRadius: 12,
            background: "#202a43",
            border: "1px solid #65739a"
          }}>
            <strong style={{
              color: "#aa9bff",
              fontSize: 13
            }}>
              ESCENARIO BASE · PREVISIÓN XGBOOST
            </strong>

            <h3 style={{ margin: "12px 0" }}>
              Demanda prevista por el modelo
            </h3>

            <p style={{
              ...mutedStyle,
              marginBottom: 0
            }}>
              Monte Carlo utiliza como referencia las
              predicciones de XGBoost y genera resultados
              aleatorios mediante una distribución
              binomial negativa. El factor de demanda
              de este escenario es 1,0.
            </p>
          </div>

          {/* ANÁLISIS DE SENSIBILIDAD OPCIONAL */}

          <div style={{ marginTop: 24 }}>
            <button
              type="button"
              onClick={toggleSensitivity}
              style={{
                padding: "12px 16px",
                background: "#202a43",
                color: "#e9edff",
                border: "1px solid #65739a",
                borderRadius: 8,
                cursor: "pointer"
              }}
            >
              {sensitivityOpen
                ? "Ocultar análisis de sensibilidad"
                : "Mostrar análisis de sensibilidad"}
            </button>

            {sensitivityOpen && (
              <div style={{ marginTop: 16 }}>
                <p style={mutedStyle}>
                  Estas pruebas modifican hipoteticamente la
                  demanda (30 %, 60 % y 130 % del pronostico)
                  para estudiar la sensibilidad de las politicas.
                  No se recalculan las politicas para cada escenario.
                </p>

                <div style={{
                  display: "flex",
                  gap: 10,
                  flexWrap: "wrap"
                }}>
                  {(result.scenarios || []).map(item => Number(item.demanda_porcentaje))
                    .filter((factor, index, values) =>
                      [30, 60, 100, 130].includes(factor) &&
                      values.indexOf(factor) === index
                    ).sort((a, b) => a - b).map(factor => (
                    <button
                      key={factor}
                      type="button"
                      onClick={() => setScenario(factor)}
                      style={{
                        padding: "10px 16px",
                        borderRadius: 8,
                        border: "1px solid #65739a",
                        background:
                          scenario === factor
                            ? "#a99aff"
                            : "#202a43",
                        color:
                          scenario === factor
                            ? "#17172c"
                            : "#e9edff",
                        cursor: "pointer"
                      }}
                    >
                      {factor === 100
                        ? "Demanda prevista"
                        : `Demanda al ${factor} %`}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* RESULTADOS */}

          <div style={{ marginTop: 30 }}>
            <h3>
              {scenario === 100
                ? "Resultados con la demanda prevista"
                : `Resultados con demanda al ${scenario} %`}
            </h3>

            <p style={mutedStyle}>
              {result.replicas} simulaciones por estrategia.
              Ingresos acumulados durante{" "}
              {result.days_remaining} días.
            </p>
          </div>

          {/* TRES POLÍTICAS CON LA MISMA IMPORTANCIA VISUAL */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: 14,
            marginTop: 20
          }}>
            {[
              { data: fixed, label: "Precio fijo", color: COLORS.precio_fijo },
              { data: immediate, label: "XGBoost inmediato", color: COLORS.XGBoost_inmediato },
              { data: pde, label: "XGBoost + PDE", color: COLORS.XGBoost_PDE }
            ].map(({ data, label, color }) => (
              <div key={label} style={{
                background: "#202a43",
                border: "1px solid #394461",
                borderTop: `3px solid ${color}`,
                borderRadius: 12,
                padding: 20,
                minWidth: 0
              }}>
                <div style={{ color: "#b8c6e5", fontSize: 13, marginBottom: 10 }}>
                  {label}
                </div>
                <div style={{ fontSize: "clamp(23px, 2vw, 32px)", fontWeight: 800 }}>
                  {data ? euro(data.ingresos_medios_eur) : "No disponible"}
                </div>
                <div style={{ color: "#b8c6e5", fontSize: 12, marginTop: 9 }}>
                  {data ? `Ocupación: ${fmt(data.ocupacion_media_pct)} %` : "Ingresos medios simulados"}
                </div>
              </div>
            ))}
          </div>

          <div style={{
            padding: 18,
            marginTop: 18,
            background: "#202a43",
            border: "1px solid #394461",
            borderRadius: 12
          }}>
            <div style={{ fontSize: 12, color: "#b8c6e5", marginBottom: 8 }}>
              CONCLUSIÓN DEL ESCENARIO
            </div>
            <strong style={{ fontSize: 18 }}>{etiquetaGanadoras}</strong>
            <p style={{ ...mutedStyle, margin: "10px 0 0" }}>
              {pde && fixed && immediate ? (
                <>
                  PDE frente a precio fijo: {improvement >= 0 ? "+" : ""}{fmt(improvement, 2)} %.
                  {" "}PDE frente a XGBoost inmediato: {difference >= 0 ? "+" : ""}{euro(difference)}.
                  {" "}Se comparan ingresos medios simulados, no precios recomendados para hoy.
                </>
              ) : "Completa una simulación para obtener la comparación."}
            </p>
            {ganadoras.length > 1 && (
              <p style={{ ...mutedStyle, margin: "8px 0 0", fontSize: 12 }}>
                El empate se refiere a ingresos medios redondeados; los indicadores de riesgo pueden ser diferentes.
              </p>
            )}
          </div>

          {/* GRÁFICO COMPARATIVO */}

          <div style={{
            width: "100%",
            height: 330,
            marginTop: 28
          }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
                margin={{
                  top: 20,
                  right: 10,
                  bottom: 40,
                  left: 5
                }}
              >
                <CartesianGrid
                  stroke="#394461"
                  strokeDasharray="4 4"
                />

                <XAxis
                  dataKey="name"
                  interval={0}
                  height={55}
                  tick={{
                    fill: "#b8c6e5",
                    fontSize: 11
                  }}
                />

                <YAxis
                  tick={{ fill: "#b8c6e5" }}
                  tickFormatter={value => fmt(value, 0)}
                />

                <Tooltip
                  formatter={value => euro(value)}
                  contentStyle={{
                    background: "#202a43",
                    border: "1px solid #65739a",
                    color: "#fff"
                  }}
                />

                <Bar
                  dataKey="ingresos"
                  name="Ingresos medios"
                  radius={[6, 6, 0, 0]}
                >
                  {chartData.map(item => (
                    <Cell
                      key={item.key}
                      fill={
                        COLORS[item.key] || "#a99aff"
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* TABLA DE RESULTADOS */}

          <div style={{
            overflowX: "auto",
            marginTop: 25
          }}>
            <table style={{
              width: "100%",
              minWidth: 650,
              borderCollapse: "collapse"
            }}>
              <thead>
                <tr>
                  {[
                    "Estrategia",
                    "Ingresos medios",
                    "Ocupación",
                    "Agotamiento",
                    "Percentil 5 %",
                    "Percentil 95 %"
                  ].map(label => (
                    <th
                      key={label}
                      style={{
                        padding: "12px 8px",
                        textAlign: "left",
                        borderBottom:
                          "1px solid #65739a",
                        color: "#b8c6e5",
                        fontSize: 12
                      }}
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {rows.map(row => (
                  <tr key={row.politica}>
                    <td style={{ padding: "14px 8px" }}>
                      {STRATEGIES[row.politica]}
                    </td>

                    <td style={{ padding: "14px 8px" }}>
                      {euro(row.ingresos_medios_eur)}
                    </td>

                    <td style={{ padding: "14px 8px" }}>
                      {fmt(row.ocupacion_media_pct)} %
                    </td>

                    <td style={{ padding: "14px 8px" }}>
                      {fmt(
                        row.probabilidad_agotamiento_pct
                      )} %
                    </td>

                    <td style={{ padding: "14px 8px" }}>
                      {euro(row.ingresos_p05_eur)}
                    </td>

                    <td style={{ padding: "14px 8px" }}>
                      {euro(row.ingresos_p95_eur)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* EXPLICACIÓN METODOLÓGICA */}

          <div style={{
            marginTop: 28,
            padding: 18,
            background: "#202a43",
            border: "1px solid #394461",
            borderRadius: 12
          }}>
            <h3>¿Cómo interpretar los resultados?</h3>

            <p style={mutedStyle}>
              XGBoost genera las predicciones de ventas.
              La PDE calcula una política de precios
              considerando los días restantes y el
              inventario. Monte Carlo evalúa el
              comportamiento de esa política.
            </p>

            <p style={mutedStyle}>
              La distribución binomial negativa introduce
              variabilidad aleatoria en la demanda.
              Los escenarios opcionales del 30 %, 60 %
              y 130 % representan cambios hipotéticos
              respecto a la previsión. Las políticas
              se calculan con la demanda de referencia.
            </p>

            <p style={mutedStyle}>
              Las simulaciones están condicionadas
              al modelo XGBoost. No constituyen una
              validación independiente con ventas reales.
              La dispersión r={result.forma_nb} tampoco
              ha sido calibrada empíricamente.
            </p>

            <p style={mutedStyle}>
              En esta comparación las tres estrategias
              utilizan la misma rejilla de cinco
              precios. El optimizador inmediato de la
              pantalla principal utiliza una búsqueda
              más amplia.
            </p>
          </div>

        </>
      )}
    </section>
  );
}
