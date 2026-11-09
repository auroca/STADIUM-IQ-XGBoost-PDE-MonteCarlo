
import { useEffect, useState } from "react";
import axios from "axios";
import { API, authHeaders } from "../auth";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import "./Multisport.css";

const SPORTS = [
  ["football", "Fútbol", "sports_soccer"],
  ["basketball", "Baloncesto", "sports_basketball"],
  ["tennis", "Tenis", "sports_tennis"],
  ["running", "Running", "directions_run"]
];

const euro = value =>
  new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR"
  }).format(value ?? 0);

const fmt = (value, decimals = 1) =>
  new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: decimals
  }).format(value ?? 0);

const categoryName = value => ({
  general: "Entrada general",
  premium: "Entrada premium",
  vip: "Entrada VIP",
  standard: "Entrada estándar",
  premium_registration: "Inscripción premium",
  day_session: "Sesión de día",
  evening_session: "Sesión de tarde"
}[String(value).toLowerCase()] || String(value));

const emptyCustom = () => ({
  category_capacity: "",
  remaining_capacity: "",
  current_price: "",
  reference_price: "",
  popularity_index: "",
  event_importance: "",
  derby_rivalry_index: "",
  league_position_home: "",
  league_position_away: "",
  recent_form_home_away: "",
  league_stakes: "",
  star_players_available: "",
  team_win_percentage: "",
  standings_difference: "",
  playoff_phase: "",
  back_to_back_game: "",
  rivalry_index: "",
  player_ranking: "",
  tournament_round: "",
  players_confirmed: "",
  singles_doubles: "",
  tournament_category: "",
  session_schedule: "",
  race_distance_km: "",
  elevation_gain_m: "",
  route_difficulty: "",
  registration_deadline_days: "",
  registration_tier: "",
  participant_services: ""
});

const CUSTOM_CATEGORICAL_FIELDS = [
  "tournament_round",
  "playoff_phase",
  "singles_doubles",
  "tournament_category",
  "session_schedule",
  "registration_tier",
  "route_difficulty"
];

function Icon({ name, size = 20 }) {
  return (
    <span
      className="material-symbols-outlined"
      style={{ fontSize: size }}
      aria-hidden="true"
    >
      {name}
    </span>
  );
}

function Card({ title, value, detail }) {
  return (
    <div className="ms-card">
      <p>{title}</p>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

export default function Multisport() {
  const [sport, setSport] = useState("");
  const [days, setDays] = useState("");
  const [model, setModel] = useState("rate");
  const [chart, setChart] = useState("revenue");

  const [result, setResult] = useState(null);

  // Estados para Programación Dinámica Estocástica
  const [pdeResult, setPdeResult] = useState(null);
  const [pdeLoading, setPdeLoading] = useState(false);
  const [pdeError, setPdeError] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [customCategories, setCustomCategories] = useState([]);
  const [customCategory, setCustomCategory] = useState("");
  const [eventName, setEventName] = useState("");
  const [custom, setCustom] = useState(emptyCustom);
  const [eventMode, setEventMode] = useState("new");
  const [setupStep, setSetupStep] = useState(0);
  const [savedFeedback, setSavedFeedback] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState("");
  const [savedEvents, setSavedEvents] = useState([]);
  const [configLoading, setConfigLoading] = useState(true);

  useEffect(() => {
    setPdeResult(null);
    setPdeError("");
  }, [sport, days, model, custom, customCategory, eventName]);

  const currentSavedEvent = savedEvents.find(
    event => event.id === selectedEventId
  );

  useEffect(() => {
    axios.get(`${API}/api/v7/events`, { headers: authHeaders() })
      .then(response => setSavedEvents(response.data))
      .catch(() =>
        setError("No se pudieron cargar tus eventos guardados.")
      );
  }, []);

  function resetEventForm() {
    setEventName("");
    setSport("");
    setCustomCategory("");
    setCustom(emptyCustom());
    setDays("");
    setSelectedEventId("");
    setEventMode("new");
    setSetupStep(0);
    setResult(null);
    setPdeResult(null);
    setPdeError("");
    setError("");
    setSavedFeedback(false);
  }

  function loadSavedEvent(event) {
    setSelectedEventId(event.id);
    setEventMode("existing");
    setEventName(event.eventName);
    setSport(event.sport);
    setCustomCategory("");
    setDays("");
    setModel("rate");
    setCustom(emptyCustom());
    setResult(null);
    setPdeResult(null);
    setPdeError("");
    setSetupStep(1);
    setError("");
    setSavedFeedback(false);
  }

  async function saveEvent() {
    if (!result || !eventName.trim()) return;

    const now = new Date().toISOString();

    const id = selectedEventId ||
      (typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `event-${savedEvents.length + 1}`);

    const previous = savedEvents.find(event => event.id === id);

    const historyEntry = {
      id: `${id}-${now}`,
      createdAt: now,
      ticketCategory: activeCustomCategory,
      recommendedPrice: result.optimal?.price ?? null,
      referencePrice: result.reference?.price ?? null,
      estimatedSales: result.optimal?.sales ?? null,
      estimatedRevenue: result.optimal?.revenue ?? null,
      model,
      custom: { ...custom },
      days
    };

    const savedEvent = {
      id,
      eventName: eventName.trim(),
      sport,
      ticketCategory: activeCustomCategory,
      days,
      model,
      custom: { ...custom },
      lastResult: result,
      updatedAt: now,
      history: [...(previous?.history || []), historyEntry]
    };

    const nextEvents = [
      ...savedEvents.filter(event => event.id !== id),
      savedEvent
    ];

    try {
      await axios.put(
        `${API}/api/v7/events/${id}`,
        {
          id,
          payload: savedEvent
        },
        { headers: authHeaders() }
      );

      setSavedEvents(nextEvents);
      setSelectedEventId(id);
      setEventMode("existing");
      setError("");
      setSavedFeedback(true);
    } catch {
      setError("No se pudo guardar el evento.");
    }
  }

  function continueToSpecificData() {
    const capacity = Number(custom.category_capacity);
    const remaining = Number(custom.remaining_capacity);
    const referencePrice = Number(custom.reference_price);
    const currentPrice = Number(custom.current_price);
    const popularity = Number(custom.popularity_index);
    const importance = Number(custom.event_importance);

    if (!sport) {
      setError("Selecciona un deporte para continuar.");
      return;
    }

    if (!eventName.trim()) {
      setError("Escribe un nombre para el evento.");
      return;
    }

    if (!activeCustomCategory) {
      setError("Selecciona un tipo de entrada.");
      return;
    }

    if (!days) {
      setError("Indica cuántos días faltan para el evento.");
      return;
    }

    if (!Number.isInteger(capacity) || capacity <= 0) {
      setError("Indica un aforo válido mayor que cero.");
      return;
    }

    if (!Number.isInteger(remaining) || remaining < 0) {
      setError("Indica cuántas entradas quedan disponibles.");
      return;
    }

    if (remaining > capacity) {
      setError("Las entradas disponibles no pueden superar el aforo.");
      return;
    }

    if (
      custom.reference_price === "" ||
      !Number.isFinite(referencePrice) ||
      referencePrice <= 0
    ) {
      setError("Indica un precio de referencia válido.");
      return;
    }

    if (
      custom.current_price === "" ||
      !Number.isFinite(currentPrice) ||
      currentPrice <= 0
    ) {
      setError("Indica un precio actual válido.");
      return;
    }

    if (
      custom.popularity_index === "" ||
      !Number.isFinite(popularity)
    ) {
      setError("Selecciona la popularidad esperada.");
      return;
    }

    if (
      custom.event_importance === "" ||
      !Number.isFinite(importance)
    ) {
      setError("Selecciona la importancia del evento.");
      return;
    }

    setError("");
    setSetupStep(2);
  }

  const updateCustom = (key, value) => {
    setCustom(previous => ({
      ...previous,
      [key]: value
    }));

    setResult(null);
    setPdeResult(null);
    setPdeError("");
    setSavedFeedback(false);
  };

  useEffect(() => {
    axios.get(`${API}/api/v7/custom/config`)
      .then(response =>
        setCustomCategories(response.data.categories || [])
      )
      .catch(() =>
        setError(
          "No se pudo cargar la configuración de entradas. " +
          "Comprueba que el backend esté activo."
        )
      )
      .finally(() => setConfigLoading(false));
  }, []);

  const availableCustomCategories = customCategories
    .filter(x => x.sport_type === sport)
    .map(x => x.ticket_category);

  const activeCustomCategory =
    availableCustomCategories.includes(customCategory)
      ? customCategory
      : "";

  // ============================================================
  // NUEVA FUNCIÓN: OPTIMIZACIÓN XGBOOST + PDE
  // ============================================================

  async function calculatePDE(payload) {
    setPdeResult(null);
    setPdeError("");

    if (
      payload.days_remaining > 15 ||
      payload.remaining_capacity > 100000
    ) {
      setPdeError(
        "La PDE experimental admite hasta 15 días y " +
        "100.000 entradas disponibles. " +
        "La recomendación inmediata sigue disponible."
      );
      return;
    }

    if (payload.remaining_capacity === 0) {
      return;
    }

    setPdeLoading(true);

    try {
      const response = await axios.post(
        `${API}/api/v7/custom/pde/optimize`,
        payload,
        {
          params: {
            forma_nb: 9
          }
        }
      );

      setPdeResult(response.data);

    } catch (err) {
      const detail = err.response?.data?.detail;

      const validationMessage = Array.isArray(detail)
        ? detail
            .map(item => item.msg)
            .filter(Boolean)
            .join(" ")
        : "";

      setPdeError(
        typeof detail === "string"
          ? detail
          : validationMessage ||
            "La PDE no está disponible. Comprueba que el backend " +
            "incluya POST /api/v7/custom/pde/optimize."
      );

    } finally {
      setPdeLoading(false);
    }
  }

  // ============================================================
  // CÁLCULO PRINCIPAL: XGBOOST INMEDIATO + PDE
  // ============================================================

  async function calculate(e) {
    e.preventDefault();

    const capacity = Number(custom.category_capacity);
    const remaining = Number(custom.remaining_capacity);
    const currentPrice = Number(custom.current_price);

    if (!eventName.trim()) {
      setError("Escribe un nombre para el evento.");
      return;
    }

    if (!activeCustomCategory) {
      setError("Selecciona un tipo de entrada.");
      return;
    }

    if (!days) {
      setError("Indica cuántos días faltan para el evento.");
      return;
    }

    if (
      !Number.isFinite(capacity) ||
      capacity <= 0 ||
      !Number.isInteger(capacity)
    ) {
      setError("Indica un aforo válido mayor que cero.");
      return;
    }

    if (
      !Number.isFinite(remaining) ||
      !Number.isInteger(remaining) ||
      remaining < 0
    ) {
      setError("Indica cuántas entradas quedan disponibles.");
      return;
    }

    if (remaining > capacity) {
      setError("Las entradas disponibles no pueden superar el aforo.");
      return;
    }

    if (!Number.isFinite(currentPrice) || currentPrice <= 0) {
      setError("Indica un precio actual válido.");
      return;
    }

    const referencePrice = Number(custom.reference_price);

    if (
      custom.reference_price === "" ||
      !Number.isFinite(referencePrice) ||
      referencePrice <= 0 ||
      referencePrice > 10000
    ) {
      setError(
        "Introduce un precio de referencia válido " +
        "entre 0,01 € y 10.000 €."
      );
      return;
    }

    const popularity = Number(custom.popularity_index);
    const importance = Number(custom.event_importance);

    if (
      !Number.isFinite(popularity) ||
      popularity < 0 ||
      popularity > 1 ||
      !Number.isFinite(importance) ||
      importance < 0 ||
      importance > 1
    ) {
      setError(
        "Selecciona una popularidad y una importancia válidas."
      );
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);
    setPdeResult(null);
    setPdeError("");

    try {
      // Mismo escenario para ambos optimizadores.
      const payload = {
        sport_type: sport,
        ticket_category: activeCustomCategory,
        days_remaining: Number(days),
        event_name: eventName.trim(),
        model,

        ...Object.fromEntries(
          Object.entries(custom).map(([key, value]) => [
            key,
            CUSTOM_CATEGORICAL_FIELDS.includes(key)
              ? (value === "" ? null : value)
              : (
                  value === "" || value == null
                    ? null
                    : Number(value)
                )
          ])
        )
      };

      // Optimizador original de XGBoost.
      const response = await axios.post(
        `${API}/api/v7/custom/optimize`,
        payload
      );

      // PDE complementaria.
      if (response.data.status === "ok") {
        await calculatePDE(payload);
      }

      setResult(response.data);

    } catch (err) {
      const detail = err.response?.data?.detail;

      const validationMessage = Array.isArray(detail)
        ? detail
            .map(item => item.msg)
            .filter(Boolean)
            .join(" ")
        : "";

      setError(
        typeof detail === "string"
          ? detail
          : validationMessage ||
            "No se pudo calcular el escenario."
      );

    } finally {
      setLoading(false);
    }
  }

  const ok = result?.status === "ok";
  const soldOut = result?.status === "sold_out";
  const noDemand = result?.status === "no_demand";

  const optimal = result?.optimal;
  const reference = result?.reference;

  const diff = ok
    ? optimal.revenue - reference.revenue
    : 0;

  const priceChange = ok
    ? (optimal.price / reference.price - 1) * 100
    : 0;

  const direction = ok
    ? priceChange < -0.01
      ? "reducir"
      : priceChange > 0.01
        ? "aumentar"
        : "mantener"
    : "";

  return (
    <main className="ms-main">

      <header className="ms-header">
        <div>
          <div className="ms-eyebrow">
            STADIUM IQ / SIMULADOR MULTIDEPORTE
          </div>

          <h1>
            Encuentra el <span>precio adecuado</span>
          </h1>

          <p>
            Configura el evento, modifica las entradas
            disponibles y explora las recomendaciones.
          </p>
        </div>
      </header>

      <div className="ms-layout">

        <aside className="ms-panel ms-form">
          <h2>Configura tu evento</h2>

          <form onSubmit={calculate}>

            <label className="ms-label">Evento</label>

            <div className="ms-event-actions">
              <button
                type="button"
                className={
                  eventMode === "new" ? "active" : ""
                }
                onClick={resetEventForm}
              >
                <Icon name="add" size={17} />
                Nuevo evento
              </button>

              <button
                type="button"
                className={
                  eventMode === "existing" ? "active" : ""
                }
                onClick={() => setEventMode("existing")}
                disabled={!savedEvents.length}
              >
                <Icon name="folder_open" size={17} />
                Evento existente
              </button>
            </div>

            {eventMode === "existing" && (
              <select
                className="ms-event-select"
                value={selectedEventId}
                onChange={event => {
                  const saved = savedEvents.find(
                    item => item.id === event.target.value
                  );

                  if (saved) loadSavedEvent(saved);
                }}
              >
                <option value="">
                  Selecciona un evento guardado
                </option>

                {savedEvents.map(event => (
                  <option
                    key={event.id}
                    value={event.id}
                  >
                    {event.eventName} ·{" "}
                    {categoryName(event.ticketCategory)}
                  </option>
                ))}
              </select>
            )}

            {eventMode === "new" && setupStep === 0 && (
              <div className="ms-step ms-sport-picker">
                <div className="ms-step-heading">
                  <span className="ms-step-number">01</span>
                  <div>
                    <strong>Elige el deporte</strong>
                    <small>
                      Después te mostraremos solo los datos que necesitas.
                    </small>
                  </div>
                </div>

                <div className="ms-sports">
                  {SPORTS.map(([id, name, icon]) => (
                    <button
                      key={id}
                      type="button"
                      className="ms-sport"
                      onClick={() => {
                        setSport(id);
                        setCustomCategory("");
                        setCustom(emptyCustom());
                        setError("");
                        setResult(null);
                        setPdeResult(null);
                        setPdeError("");
                        setSetupStep(1);
                      }}
                    >
                      <Icon name={icon} size={26} />
                      {name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {(eventMode === "new" || currentSavedEvent) &&
              setupStep === 1 && (

              <div className="ms-step">

                <div className="ms-step-heading">
                  <span className="ms-step-number">01</span>

                  <div>
                    <strong>Datos generales</strong>
                    <small>
                      Identifica el evento y define su
                      situación actual.
                    </small>
                  </div>
                </div>

                {eventMode !== "new" && currentSavedEvent ? (

                  <div className="ms-locked-sport">
                    <Icon
                      name={
                        SPORTS.find(
                          item => item[0] === sport
                        )?.[2]
                      }
                      size={20}
                    />

                    <span>
                      {SPORTS.find(
                        item => item[0] === sport
                      )?.[1]}
                    </span>

                    <small>
                      El deporte no se puede cambiar
                      en un evento guardado.
                    </small>
                  </div>

                ) : eventMode !== "new" ? (

                  <div className="ms-event-select-hint">
                    Selecciona un evento guardado para
                    cargar su deporte.
                  </div>

                ) : null}

                <div className="ms-divider" />

                {eventMode === "new" && (
                  <>
                    <label className="ms-label">
                      Nombre del evento
                    </label>

                    <input
                      className="ms-text-field"
                      type="text"
                      maxLength={100}
                      required
                      value={eventName}
                      onChange={e => {
                        setEventName(e.target.value);
                        setResult(null);
                        setPdeResult(null);
                        setPdeError("");
                      }}
                      placeholder={
                        "Ej. Final del torneo de mi ciudad"
                      }
                    />

                  </>
                )}

                <label className="ms-label">
                  Tipo de entrada
                </label>

                <select
                  required
                  value={activeCustomCategory}
                  disabled={
                    configLoading ||
                    !sport ||
                    !availableCustomCategories.length
                  }
                  onChange={e => {
                    setCustomCategory(e.target.value);
                    setCustom(emptyCustom());
                    setError("");
                    setResult(null);
                    setPdeResult(null);
                    setPdeError("");
                  }}
                >

                  {configLoading && (
                    <option value="">
                      Cargando tipos de entrada...
                    </option>
                  )}

                  {!configLoading && !sport && (
                    <option value="">
                      Selecciona primero un deporte
                    </option>
                  )}

                  {!configLoading &&
                    sport &&
                    !activeCustomCategory && (
                      <option value="">
                        Selecciona el tipo de entrada
                      </option>
                    )}

                  {!configLoading &&
                    sport &&
                    !availableCustomCategories.length && (
                      <option value="">
                        No hay tipos de entrada disponibles
                      </option>
                    )}

                  {availableCustomCategories.map(c => (
                    <option key={c} value={c}>
                      {categoryName(c)}
                    </option>
                  ))}
                </select>

                <p className="ms-muted">
                  Escenario nuevo. Las variables no indicadas
                  utilizan un perfil sintético de referencia
                  del deporte seleccionado.
                </p>

                <div className="ms-divider" />

                <label className="ms-label">
                  Días hasta el evento
                </label>

                <div className="ms-slider-title">
                  <span>Días restantes</span>

                  <strong>
                    {days
                      ? `${days} días`
                      : "Selecciona los días"}
                  </strong>
                </div>

                <input
                  type="range"
                  min={1}
                  max={30}
                  value={days}
                  onChange={e => {
                    setDays(Number(e.target.value));
                    setResult(null);
                    setPdeResult(null);
                    setPdeError("");
                  }}
                />

                <div className="ms-range-labels">
                  <span>1 día</span>
                  <span>30 días</span>
                </div>

                <div className="ms-divider" />

                <label className="ms-label">
                  Entradas disponibles y precios
                </label>

                <div className="ms-custom-fields">

                  <label className="ms-label">
                    Aforo de esta categoría
                  </label>

                  <input
                    type="number"
                    min="1"
                    max="100000"
                    required
                    placeholder="Ej. 1000"
                    value={custom.category_capacity}
                    onChange={e =>
                      updateCustom(
                        "category_capacity",
                        e.target.value
                      )
                    }
                  />

                  <label className="ms-label">
                    Entradas disponibles actualmente
                  </label>

                  <input
                    type="number"
                    min="0"
                    max={custom.category_capacity}
                    required
                    placeholder="Ej. 800"
                    value={custom.remaining_capacity}
                    onChange={e =>
                      updateCustom(
                        "remaining_capacity",
                        e.target.value
                      )
                    }
                  />

                  <label className="ms-label">
                    Precio de referencia del evento (€)
                  </label>

                  <input
                    type="number"
                    min="0.01"
                    max="10000"
                    step="0.01"
                    required
                    placeholder="Ej. 30,87"
                    value={custom.reference_price ?? ""}
                    onChange={e =>
                      updateCustom(
                        "reference_price",
                        e.target.value
                      )
                    }
                  />

                  <label className="ms-label">
                    Precio actual (€)
                  </label>

                  <input
                    type="number"
                    min="0.01"
                    step="0.01"
                    max="10000"
                    required
                    placeholder="Ej. 30,87"
                    value={custom.current_price}
                    onChange={e =>
                      updateCustom(
                        "current_price",
                        e.target.value
                      )
                    }
                  />

                  <label className="ms-label">
                    Popularidad esperada
                  </label>

                  <select
                    required
                    value={String(
                      custom.popularity_index ?? ""
                    )}
                    onChange={e =>
                      updateCustom(
                        "popularity_index",
                        e.target.value
                      )
                    }
                  >
                    <option value="">
                      Selecciona la popularidad
                    </option>
                    <option value="0.25">Baja</option>
                    <option value="0.55">Media</option>
                    <option value="0.85">Alta</option>
                  </select>

                  <label className="ms-label">
                    Importancia del evento
                  </label>

                  <select
                    required
                    value={String(
                      custom.event_importance ?? ""
                    )}
                    onChange={e =>
                      updateCustom(
                        "event_importance",
                        e.target.value
                      )
                    }
                  >
                    <option value="">
                      Selecciona la importancia
                    </option>
                    <option value="0.25">Baja</option>
                    <option value="0.55">Media</option>
                    <option value="0.85">Alta</option>
                  </select>

                  <p className="ms-muted">
                    Baja = 0,25 · Media = 0,55 · Alta = 0,85.
                  </p>

                  <button
                    type="button"
                    className="ms-next-step"
                    onClick={continueToSpecificData}
                  >
                    Continuar con datos de{" "}
                    {SPORTS.find(
                      x => x[0] === sport
                    )?.[1]}

                    <Icon
                      name="arrow_forward"
                      size={18}
                    />
                  </button>

                </div>
              </div>
            )}

            {(eventMode === "new" || currentSavedEvent) &&
              setupStep === 2 && (

              <div className="ms-step">

                <div className="ms-step-heading">
                  <span className="ms-step-number">02</span>

                  <div>
                    <strong>Datos específicos</strong>
                    <small>
                      Completa la información necesaria
                      para simular.
                    </small>
                  </div>
                </div>

                <div className="ms-sport-details">

                  <h3>
                    Características de{" "}
                    {SPORTS.find(
                      x => x[0] === sport
                    )?.[1]}
                  </h3>

                  {sport === "football" && (
                    <>
                      <label className="ms-label">
                        Rivalidad del partido
                      </label>

                      <select
                        required
                        value={String(
                          custom.derby_rivalry_index ?? ""
                        )}
                        onChange={e =>
                          updateCustom(
                            "derby_rivalry_index",
                            e.target.value
                          )
                        }
                      >
                        <option value="">
                          Selecciona la rivalidad
                        </option>
                        <option value="0.2">Baja</option>
                        <option value="0.5">Media</option>
                        <option value="0.85">
                          Derbi / alta
                        </option>
                      </select>

                      <label className="ms-label">
                        Posición del equipo local (1–30)
                      </label>

                      <input
                        required
                        type="number"
                        min="1"
                        max="30"
                        placeholder="Ej. 14"
                        value={
                          custom.league_position_home ?? ""
                        }
                        onChange={e =>
                          updateCustom(
                            "league_position_home",
                            e.target.value
                          )
                        }
                      />

                      <label className="ms-label">
                        Posición del visitante (1–30)
                      </label>

                      <input
                        required
                        type="number"
                        min="1"
                        max="30"
                        placeholder="Ej. 18"
                        value={
                          custom.league_position_away ?? ""
                        }
                        onChange={e =>
                          updateCustom(
                            "league_position_away",
                            e.target.value
                          )
                        }
                      />

                      <label className="ms-label">
                        Forma reciente del equipo (0–100 %)
                      </label>
                      <input
                        required
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        placeholder="Ej. 0,70"
                        value={custom.recent_form_home_away ?? ""}
                        onChange={e =>
                          updateCustom("recent_form_home_away", e.target.value)
                        }
                      />

                      <label className="ms-label">
                        Importancia clasificatoria (0–100 %)
                      </label>
                      <input
                        required
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        placeholder="Ej. 0,80"
                        value={custom.league_stakes ?? ""}
                        onChange={e =>
                          updateCustom("league_stakes", e.target.value)
                        }
                      />

                      <label className="ms-label">
                        Jugadores destacados disponibles
                      </label>
                      <select
                        required
                        value={String(custom.star_players_available ?? "")}
                        onChange={e =>
                          updateCustom("star_players_available", e.target.value)
                        }
                      >
                        <option value="">Selecciona una opción</option>
                        <option value="1">Sí</option>
                        <option value="0">No</option>
                      </select>
                    </>
                  )}

                  {sport === "basketball" && (
                    <>
                      <label className="ms-label">
                        Porcentaje de victorias del equipo
                      </label>

                      <select
                        required
                        value={String(
                          custom.team_win_percentage ?? ""
                        )}
                        onChange={e =>
                          updateCustom(
                            "team_win_percentage",
                            e.target.value
                          )
                        }
                      >
                        <option value="">
                          Selecciona el porcentaje
                        </option>
                        <option value="0.25">25 %</option>
                        <option value="0.5">50 %</option>
                        <option value="0.75">75 %</option>
                      </select>

                      <label className="ms-label">
                        Diferencia en la clasificación
                      </label>
                      <input
                        required
                        type="number"
                        min="-30"
                        max="30"
                        placeholder="Ej. 4"
                        value={custom.standings_difference ?? ""}
                        onChange={e =>
                          updateCustom("standings_difference", e.target.value)
                        }
                      />

                      <label className="ms-label">Fase de playoffs</label>
                      <select
                        required
                        value={custom.playoff_phase ?? ""}
                        onChange={e =>
                          updateCustom("playoff_phase", e.target.value)
                        }
                      >
                        <option value="">Selecciona la fase</option>
                        <option value="regular">Temporada regular</option>
                        <option value="play_in">Play-in</option>
                        <option value="quarterfinal">Cuartos</option>
                        <option value="semifinal">Semifinal</option>
                        <option value="final">Final</option>
                      </select>

                      <label className="ms-label">Partido consecutivo</label>
                      <select
                        required
                        value={String(custom.back_to_back_game ?? "")}
                        onChange={e =>
                          updateCustom("back_to_back_game", e.target.value)
                        }
                      >
                        <option value="">Selecciona una opción</option>
                        <option value="0">No</option>
                        <option value="1">Sí</option>
                      </select>

                      <label className="ms-label">Rivalidad (0–100 %)</label>
                      <input
                        required
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        placeholder="Ej. 0,60"
                        value={custom.rivalry_index ?? ""}
                        onChange={e =>
                          updateCustom("rivalry_index", e.target.value)
                        }
                      />
                    </>
                  )}

                  {sport === "tennis" && (
                    <>
                      <label className="ms-label">
                        Ranking del jugador principal
                      </label>

                      <input
                        required
                        type="number"
                        min="1"
                        max="500"
                        placeholder="Ej. 50"
                        value={
                          custom.player_ranking ?? ""
                        }
                        onChange={e =>
                          updateCustom(
                            "player_ranking",
                            e.target.value
                          )
                        }
                      />

                      <label className="ms-label">
                        Ronda del torneo
                      </label>

                      <select
                        required
                        value={
                          custom.tournament_round ?? ""
                        }
                        onChange={e =>
                          updateCustom(
                            "tournament_round",
                            e.target.value
                          )
                        }
                      >
                        <option value="">
                          Selecciona la ronda
                        </option>
                        <option value="R32">
                          Ronda de 32
                        </option>
                        <option value="R16">
                          Octavos
                        </option>
                        <option value="QF">
                          Cuartos
                        </option>
                        <option value="SF">
                          Semifinal
                        </option>
                        <option value="F">
                          Final
                        </option>
                      </select>

                      <label className="ms-label">Jugadores confirmados</label>
                      <select
                        required
                        value={String(custom.players_confirmed ?? "")}
                        onChange={e =>
                          updateCustom("players_confirmed", e.target.value)
                        }
                      >
                        <option value="">Selecciona una opción</option>
                        <option value="1">Sí</option>
                        <option value="0">No</option>
                      </select>

                      <label className="ms-label">Modalidad</label>
                      <select
                        required
                        value={custom.singles_doubles ?? ""}
                        onChange={e =>
                          updateCustom("singles_doubles", e.target.value)
                        }
                      >
                        <option value="">Selecciona la modalidad</option>
                        <option value="singles">Individual</option>
                        <option value="doubles">Dobles</option>
                      </select>

                      <label className="ms-label">Categoría del torneo</label>
                      <select
                        required
                        value={custom.tournament_category ?? ""}
                        onChange={e =>
                          updateCustom("tournament_category", e.target.value)
                        }
                      >
                        <option value="">Selecciona la categoría</option>
                        <option value="ATP_250">ATP 250</option>
                        <option value="ATP_500">ATP 500</option>
                        <option value="Masters">Masters</option>
                        <option value="Grand_Slam">Grand Slam</option>
                      </select>

                      <label className="ms-label">Horario de la sesión</label>
                      <select
                        required
                        value={custom.session_schedule ?? ""}
                        onChange={e =>
                          updateCustom("session_schedule", e.target.value)
                        }
                      >
                        <option value="">Selecciona el horario</option>
                        <option value="day">Día</option>
                        <option value="evening">Tarde/noche</option>
                      </select>
                    </>
                  )}

                  {sport === "running" && (
                    <>
                      <label className="ms-label">
                        Distancia de carrera
                      </label>

                      <select
                        required
                        value={String(
                          custom.race_distance_km ?? ""
                        )}
                        onChange={e =>
                          updateCustom(
                            "race_distance_km",
                            e.target.value
                          )
                        }
                      >
                        <option value="">
                          Selecciona la distancia
                        </option>
                        <option value="5">5 km</option>
                        <option value="10">10 km</option>
                        <option value="21.0975">
                          Media maratón
                        </option>
                        <option value="42.195">
                          Maratón
                        </option>

                        {![
                          5,
                          10,
                          21.0975,
                          42.195
                        ].includes(
                          Number(
                            custom.race_distance_km ?? 10
                          )
                        ) && (
                          <option
                            value={String(
                              custom.race_distance_km
                            )}
                          >
                            Referencia (
                            {fmt(
                              custom.race_distance_km
                            )} km)
                          </option>
                        )}
                      </select>

                      <label className="ms-label">
                        Desnivel positivo (metros)
                      </label>

                      <input
                        required
                        type="number"
                        min="0"
                        max="5000"
                        placeholder="Ej. 250"
                        value={
                          custom.elevation_gain_m ?? ""
                        }
                        onChange={e =>
                          updateCustom(
                            "elevation_gain_m",
                            e.target.value
                          )
                        }
                      />

                      <label className="ms-label">
                        Dificultad del recorrido (0–100 %)
                      </label>
                      <input
                        required
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        placeholder="Ej. 0,50"
                        value={custom.route_difficulty ?? ""}
                        onChange={e =>
                          updateCustom("route_difficulty", e.target.value)
                        }
                      />

                      <label className="ms-label">
                        Servicios incluidos
                      </label>
                      <select
                        required
                        value={String(custom.participant_services ?? "")}
                        onChange={e =>
                          updateCustom("participant_services", e.target.value)
                        }
                      >
                        <option value="">Selecciona una opción</option>
                        <option value="1">Sí</option>
                        <option value="0">No</option>
                      </select>
                    </>
                  )}

                </div>

                <button
                  type="button"
                  className="ms-back-step"
                  onClick={() => setSetupStep(1)}
                >
                  <Icon
                    name="arrow_back"
                    size={18}
                  />

                  Volver a datos generales
                </button>

              </div>
            )}

            {(eventMode === "new" || currentSavedEvent) &&
              setupStep === 2 && (

              <>
                <div className="ms-divider" />

                <button
                  className="ms-submit"
                  type="submit"
                  disabled={
                    loading ||
                    !activeCustomCategory ||
                    Number(
                      custom.remaining_capacity
                    ) >
                      Number(
                        custom.category_capacity
                      ) ||
                    Number(
                      custom.category_capacity
                    ) <= 0
                  }
                >
                  <Icon
                    name="auto_awesome"
                    size={19}
                  />

                  {loading
                    ? "Calculando..."
                    : "Calcular precio recomendado"}
                </button>
              </>
            )}

          </form>

          {(eventMode === "new" ||
            currentSavedEvent) && (

            <p className="ms-muted">
              Se utilizan datos sintéticos como referencia.
              Los eventos guardados quedan disponibles
              en este navegador.
            </p>
          )}
        </aside>

        {/* ==================================================
            RESULTADOS DE LOS MODELOS
        ================================================== */}

        <section className="ms-results">

          {error && (
            <div
              className="ms-panel ms-error"
              role="alert"
            >
              <Icon
                name="error_outline"
                size={18}
              />
              <span>{error}</span>
            </div>
          )}

          {!result && !error && (
            <div className="ms-panel ms-empty">
              <Icon
                name="monitoring"
                size={54}
              />

              <h2>
                Tu análisis aparecerá aquí
              </h2>

              <p>
                Configura el evento y pulsa
                «Calcular precio recomendado».
              </p>
            </div>
          )}

          {soldOut && (
            <div className="ms-panel ms-status">

              <Icon
                name="confirmation_number"
                size={50}
              />

              <h2>Entradas agotadas</h2>
              <p>{result.message}</p>

              <div className="ms-status-grid">

                <Card
                  title="Entradas disponibles"
                  value="0"
                />

                <Card
                  title="Ocupación"
                  value="100 %"
                />

              </div>

              <p className="ms-muted">
                Puedes aumentar el inventario
                del escenario para estudiar
                una situación hipotética con entradas.
              </p>
            </div>
          )}

          {noDemand && (
            <div className="ms-panel ms-status">

              <Icon
                name="query_stats"
                size={50}
              />

              <h2>Sin demanda prevista</h2>
              <p>{result.message}</p>

              <div className="ms-status-grid">

                <Card
                  title="Entradas disponibles"
                  value={fmt(
                    result.context.remaining_capacity,
                    0
                  )}
                />

                <Card
                  title="Ventas previstas"
                  value="0"
                />

              </div>

              <p className="ms-muted">
                No hemos seleccionado el precio mínimo
                arbitrariamente: no existe una mejora
                económica identificada por el modelo.
              </p>
            </div>
          )}

          {ok && (
            <>

              {/* REFERENCIA INMEDIATA DE XGBOOST */}

              <div className={`ms-panel ms-hero ms-secondary-result${
                pdeResult?.status === "ok"
                  ? " ms-horizon-available"
                  : ""
              }`}>

                <div className="ms-eyebrow">
                  REFERENCIA PARA MAÑANA · XGBOOST
                </div>

                <p>
                  Precio recomendado para mañana{" "}
                  {result.context.is_custom
                    ? "(escenario personalizado)"
                    : ""}
                </p>

                <div className="ms-big-price">
                  {euro(optimal.price)}
                </div>

                <p>
                  Precio observado:{" "}
                  <strong>
                    {euro(reference.price)}
                  </strong>
                </p>

                <div className="ms-explanation">
                  <Icon
                    name="lightbulb"
                    size={23}
                  />

                  {direction === "mantener"
                    ? "El modelo recomienda mantener aproximadamente el precio observado."
                    : `El modelo recomienda ${direction} el precio de ${euro(reference.price)} a ${euro(optimal.price)}. Esto produciría ${fmt(optimal.sales)} ventas estimadas durante el siguiente día comercial.`}
                </div>

                <div className="ms-gain">
                  {result.uplift_percent == null
                    ? "Mejora porcentual no calculable"
                    : `${
                        result.uplift_percent >= 0
                          ? "+"
                          : ""
                      }${fmt(
                        result.uplift_percent
                      )} % de ingresos previstos`}
                </div>

                {result.context.is_custom && (
                  <p className="ms-muted">
                    Evento:{" "}
                    <strong>
                      {result.context.event_name}
                    </strong>
                  </p>
                )}

                <button
                  type="button"
                  className={
                    `ms-save-event${
                      savedFeedback
                        ? " saved"
                        : ""
                    }`
                  }
                  onClick={saveEvent}
                >
                  <Icon
                    name={
                      savedFeedback
                        ? "check_circle"
                        : "save"
                    }
                    size={18}
                  />

                  {savedFeedback
                    ? "Evento guardado correctamente"
                    : currentSavedEvent
                      ? "Guardar nueva recomendación"
                      : "Guardar evento y recomendación"}
                </button>

              </div>

              <div className={`ms-compare${
                pdeResult?.status === "ok"
                  ? " ms-horizon-available"
                  : ""
              }`}>

                <Card
                  title="Mantener el precio"
                  value={euro(reference.revenue)}
                  detail={
                    `${fmt(reference.sales)} entradas ` +
                    `previstas a ${euro(reference.price)}`
                  }
                />

                <Card
                  title="Aplicar la recomendación"
                  value={euro(optimal.revenue)}
                  detail={
                    `${fmt(optimal.sales)} entradas ` +
                    `previstas a ${euro(optimal.price)}`
                  }
                />

              </div>

              {/* ============================================
                  NUEVA SECCIÓN: XGBOOST + PDE
              ============================================ */}

              {pdeLoading && (
                <div
                  className="ms-panel ms-status"
                  role="status"
                >
                  <Icon
                    name="hourglass_top"
                    size={22}
                  />

                  <p>
                    Calculando el plan de precios para los días
                    restantes...
                  </p>
                </div>
              )}

              {pdeError && !pdeLoading && (
                <div
                  className="ms-panel ms-status"
                  role="status"
                >
                  <Icon
                    name="info"
                    size={22}
                  />

                  <h2>
                    Plan para varios días no disponible
                  </h2>

                  <p>{pdeError}</p>

                  <p className="ms-muted">
                    La recomendación para mañana sigue estando
                    disponible.
                  </p>
                </div>
              )}

              {pdeResult?.status === "ok" && (
                <div className="ms-panel ms-hero ms-primary-result">

                  <div className="ms-eyebrow">
                    RECOMENDACIÓN PRINCIPAL · TODO EL PERÍODO
                  </div>

                  <h2>
                    Precio recomendado para aplicar hoy
                  </h2>

                  <div className="ms-big-price">
                    {euro(
                      pdeResult.recommendation.price
                    )}
                  </div>

                  <p className="ms-muted">
                    Este precio busca maximizar los ingresos
                    durante los{" "}
                    {pdeResult.horizon_days} días
                    restantes. Se volverá a calcular cuando
                    cambien las ventas o el inventario.
                  </p>

                  <div className="ms-compare">

                    <Card
                      title="Ventas previstas mañana"
                      value={fmt(
                        pdeResult.recommendation
                          .expected_sales_next_day,
                        2
                      )}
                      detail={
                        "Estimación condicionada al precio recomendado"
                      }
                    />

                    <Card
                      title="Ingresos previstos mañana"
                      value={euro(
                        pdeResult.recommendation
                          .expected_revenue_next_day
                      )}
                    />

                    <Card
                      title="Ingresos estimados del período"
                      value={euro(
                        pdeResult.recommendation
                          .expected_total_revenue
                      )}
                      detail={
                        `Acumulados en ${
                          pdeResult.horizon_days
                        } días`
                      }
                    />

                  </div>

                  <div className="ms-explanation">

                    <Icon
                      name="psychology"
                      size={23}
                    />

                    <span>
                      Esta es la recomendación principal: busca
                      maximizar los ingresos durante todo el período
                      restante. El precio para mañana se muestra como
                      referencia y puede ser diferente.
                    </span>

                  </div>

                  <p className="ms-muted">
                    XGBoost estima las ventas para cada precio y la
                    optimización calcula el mejor plan para todo el
                    período. Se utilizan datos sintéticos.
                  </p>

                </div>
              )}

              {/* DIFERENCIA DE INGRESOS INMEDIATOS */}

              <div className={`ms-panel ms-difference${
                pdeResult?.status === "ok"
                  ? " ms-horizon-available"
                  : ""
              }`}>

                <Icon
                  name="insights"
                  size={24}
                />

                <div>
                  <strong>
                    {diff >= 0 ? "+" : "-"}
                    {euro(Math.abs(diff))}
                  </strong>

                  <p>
                    Diferencia de ingresos prevista
                    durante el próximo día.
                  </p>
                </div>

              </div>

              {/* GRÁFICO ORIGINAL DE XGBOOST */}

              <div className={`ms-panel ms-chart${
                pdeResult?.status === "ok"
                  ? " ms-horizon-available"
                  : ""
              }`}>

                <div className="ms-chart-heading">

                  <div>
                    <div className="ms-eyebrow">
                      ANÁLISIS DE PRECIOS
                    </div>

                    <h2>
                      ¿Cómo cambia el resultado
                      según el precio?
                    </h2>
                  </div>

                  <div className="ms-tabs">

                    <button
                      type="button"
                      className={
                        chart === "revenue"
                          ? "active"
                          : ""
                      }
                      onClick={() =>
                        setChart("revenue")
                      }
                    >
                      Ingresos
                    </button>

                    <button
                      type="button"
                      className={
                        chart === "sales"
                          ? "active"
                          : ""
                      }
                      onClick={() =>
                        setChart("sales")
                      }
                    >
                      Entradas
                    </button>

                  </div>
                </div>

                <div className="ms-plot">

                  <ResponsiveContainer
                    width="100%"
                    height="100%"
                  >
                    <LineChart
                      data={result.curve}
                      margin={{
                        top: 25,
                        right: 25,
                        bottom: 12,
                        left: 8
                      }}
                    >

                      <CartesianGrid
                        stroke="#394461"
                        strokeDasharray="4 4"
                      />

                      <XAxis
                        dataKey="price"
                        type="number"
                        domain={[
                          "dataMin",
                          "dataMax"
                        ]}
                        tick={{
                          fill: "#aabce3"
                        }}
                        tickFormatter={v =>
                          `${fmt(v)}€`
                        }
                      />

                      <YAxis
                        tick={{
                          fill: "#aabce3"
                        }}
                        width={58}
                      />

                      <Tooltip
                        contentStyle={{
                          background: "#202a43",
                          border: "1px solid #65739a",
                          color: "#ffffff"
                        }}
                        labelFormatter={v =>
                          `Precio: ${euro(v)}`
                        }
                        formatter={v =>
                          chart === "revenue"
                            ? euro(v)
                            : `${fmt(v)} entradas`
                        }
                      />

                      <ReferenceLine
                        x={reference.price}
                        stroke="#78b4e8"
                        strokeDasharray="5 5"
                        label={{
                          value: "Observado",
                          fill: "#78b4e8",
                          position: "insideTopLeft"
                        }}
                      />

                      <ReferenceLine
                        x={optimal.price}
                        stroke="#b1a0ff"
                        strokeDasharray="4 4"
                        label={{
                          value: "Recomendado",
                          fill: "#b1a0ff",
                          position: "insideTopRight"
                        }}
                      />

                      <Line
                        type="linear"
                        dataKey={chart}
                        stroke="#b5a4ff"
                        strokeWidth={2.6}
                        dot={false}
                        isAnimationActive={false}
                      />

                    </LineChart>
                  </ResponsiveContainer>

                </div>
              </div>

              {/* EXPLICACIÓN ORIGINAL DEL MODELO */}

              <details className={`ms-panel ms-details${
                pdeResult?.status === "ok"
                  ? " ms-horizon-available"
                  : ""
              }`}>

                <summary>
                  <Icon
                    name="psychology"
                    size={20}
                  />
                  ¿Cómo se ha calculado?
                </summary>

                <p>
                  XGBoost predice las ventas del
                  siguiente día para diferentes precios.
                  El optimizador selecciona el precio
                  con mayores ingresos estimados.
                </p>

                <p>
                  Modelo utilizado:{" "}
                  <strong>
                    Tasa de ventas
                  </strong>
                </p>

                {result.diagnostics && (
                  <p>
                    Tramos donde sube la demanda al
                    subir el precio:{" "}

                    <strong>
                      {
                        result.diagnostics
                          .demand_increase_steps
                      }
                    </strong>

                    {" "}de{" "}

                    {
                      result.diagnostics
                        .price_points - 1
                    }.

                    {" "}Esta comprobación no demuestra
                    una relación causal entre
                    precio y ventas.
                  </p>
                )}

                <p>
                  Sensibilidad local:{" "}

                  <strong>
                    {
                      result.local_price_sensitivity ==
                      null
                        ? "No calculable"
                        : fmt(
                            result.local_price_sensitivity,
                            2
                          )
                    }
                  </strong>
                </p>

                <h3>
                  Estabilidad del precio recomendado
                </h3>

                <div className="ms-checks">

                  {result.sensitivity.map(s => (
                    <div key={s.scenario}>

                      <span>
                        {s.scenario}
                      </span>

                      <strong>
                        {s.optimal
                          ? euro(s.optimal.price)
                          : "Sin recomendación"}
                      </strong>

                      <small>
                        {fmt(
                          s.remaining_capacity,
                          0
                        )}{" "}
                        entradas disponibles
                      </small>

                    </div>
                  ))}

                </div>

              </details>

            </>
          )}

        </section>
      </div>
    </main>
  );
}
