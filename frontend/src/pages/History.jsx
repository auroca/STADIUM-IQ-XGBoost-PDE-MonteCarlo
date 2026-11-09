import { useEffect, useState } from "react";
import axios from "axios";
import { API, authHeaders } from "../auth";

import "./History.css";

const euro = value =>
  new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR"
  }).format(value ?? 0);

const fmt = value =>
  new Intl.NumberFormat("es-ES", {
    maximumFractionDigits: 1
  }).format(value ?? 0);

const levelName = (value, levels) => {
  const numericValue = Number(value);
  const level = levels.find(([index]) => numericValue === index);
  return level?.[1] || value;
};

const sportName = {
  football: "Fútbol",
  basketball: "Baloncesto",
  tennis: "Tenis",
  running: "Running"
};

const categoryName = value => ({
  general: "Entrada general",
  premium: "Entrada premium",
  standard: "Entrada estándar",
  premium_registration: "Inscripción premium",
  day_session: "Sesión de día",
  evening_session: "Sesión de tarde"
}[String(value).toLowerCase()] || (value ? String(value) : "No especificado"));

export default function History() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [expandedEntryId, setExpandedEntryId] = useState("");
  const [confirmAction, setConfirmAction] = useState(null);
  const selected = events.find(event => event.id === selectedId);

  useEffect(() => {
    axios.get(`${API}/api/v7/events`, { headers: authHeaders() })
      .then(response => setEvents(response.data))
      .catch(() => setError("No se pudo cargar tu historial. Comprueba la conexión con el backend."))
      .finally(() => setLoading(false));
  }, []);

  function deleteEvent() {
    if (!selected) {
      return;
    }

    setActionLoading(true);
    axios.delete(`${API}/api/v7/events/${selected.id}`, { headers: authHeaders() })
      .then(() => {
        setEvents(events.filter(event => event.id !== selected.id));
        setSelectedId("");
        setExpandedEntryId("");
        setConfirmAction(null);
      })
      .catch(() => setError("No se pudo borrar el evento. Inténtalo de nuevo."))
      .finally(() => setActionLoading(false));
  }

  function deleteEntry(entryId) {
    if (!selected) {
      return;
    }

    const nextEvents = events.map(event => (
      event.id === selected.id
        ? { ...event, history: (event.history || []).filter(entry => entry.id !== entryId) }
        : event
    ));
    setActionLoading(true);
    axios.put(`${API}/api/v7/events/${selected.id}`, {
      id: selected.id,
      payload: nextEvents.find(event => event.id === selected.id)
    }, { headers: authHeaders() }).then(() => {
      setEvents(nextEvents);
      setExpandedEntryId("");
      setConfirmAction(null);
    }).catch(() => setError("No se pudo borrar el cálculo. Inténtalo de nuevo."))
      .finally(() => setActionLoading(false));
  }

  const getCharacteristics = (custom, ticketCategory) => [
    ["Aforo", custom?.category_capacity],
    ["Entradas disponibles", custom?.remaining_capacity],
    ["Precio de referencia", custom?.reference_price, " €"],
    ["Precio actual", custom?.current_price, " €"],
    ["Tipo de entrada", categoryName(ticketCategory)],
    ["Popularidad", levelName(custom?.popularity_index, [[0.25, "Baja"], [0.55, "Media"], [0.85, "Alta"]])],
    ["Importancia", levelName(custom?.event_importance, [[0.25, "Baja"], [0.55, "Media"], [0.85, "Alta"]])],
    ["Rivalidad", levelName(custom?.derby_rivalry_index, [[0.2, "Baja"], [0.5, "Media"], [0.85, "Alta"]])],
    ["Posición local", custom?.league_position_home],
    ["Posición visitante", custom?.league_position_away],
    ["Porcentaje de victorias", custom?.team_win_percentage == null || custom.team_win_percentage === ""
      ? null
      : `${fmt(Number(custom.team_win_percentage) * 100)} %`],
    ["Ranking del jugador", custom?.player_ranking],
    ["Ronda", custom?.tournament_round],
    ["Distancia", custom?.race_distance_km, " km"],
    ["Desnivel", custom?.elevation_gain_m, " m"]
  ].filter(([, value]) => value !== "" && value != null);

  return (
    <main className="history-main">
      <header className="history-header">
        <div className="ms-eyebrow">STADIUM IQ / HISTORIAL</div>
        <h1>Historial de <span>eventos</span></h1>
        <p>Consulta las recomendaciones guardadas y su evolución por evento.</p>
      </header>

      {loading ? (
        <section className="history-empty"><h2>Cargando historial...</h2></section>
      ) : error ? (
        <section className="history-empty">
          <span className="material-symbols-outlined">error_outline</span>
          <h2>No se pudo cargar el historial</h2>
          <p>{error}</p>
        </section>
      ) : !events.length ? (
        <section className="history-empty">
          <span className="material-symbols-outlined">history</span>
          <h2>Aún no hay eventos guardados</h2>
          <p>Calcula una recomendación en el simulador y guárdala para verla aquí.</p>
        </section>
      ) : (
        <div className="history-layout">
          {error && <div className="history-action-error" role="alert">{error}</div>}
          <aside className="history-events">
            <h2>Mis eventos</h2>
            {events.map(event => (
              <button
                type="button"
                key={event.id}
                className={event.id === selectedId ? "selected" : ""}
                onClick={() => {
                  setSelectedId(event.id);
                  setExpandedEntryId("");
                }}
              >
                <strong>{event.eventName}</strong>
                <small>
                  {sportName[event.sport]}
                </small>
              </button>
            ))}
          </aside>

          {selected ? (
            <section className="history-detail">
              <div className="ms-eyebrow">HISTORIAL DEL EVENTO</div>
              <div className="history-detail-heading">
                <div>
                  <h2>{selected.eventName}</h2>
                  <p className="history-meta">
                    {sportName[selected.sport]}
                  </p>
                </div>
                <button
                  type="button"
                  className="history-delete-button"
                  onClick={() => setConfirmAction({
                    type: "event",
                    title: "¿Borrar este evento?",
                    message: `Se eliminará "${selected.eventName}" y todo su historial.`
                  })}
                  disabled={actionLoading}
                >
                  <span className="material-symbols-outlined">delete</span>
                  Borrar evento
                </button>
              </div>
              <div className="history-list">
                {[...(selected.history || [])].reverse().map(entry => (
                  <article className="history-entry" key={entry.id}>
                    <div className="history-entry-summary">
                      <div>
                        <strong>{euro(entry.recommendedPrice)}</strong>
                        <small>{new Date(entry.createdAt).toLocaleString("es-ES")}</small>
                      </div>
                      <span>
                        {fmt(entry.estimatedSales)} entradas · {euro(entry.estimatedRevenue)}
                      </span>
                      <button
                        type="button"
                        className="history-entry-toggle"
                        aria-expanded={expandedEntryId === entry.id}
                        onClick={() => setExpandedEntryId(
                          expandedEntryId === entry.id ? "" : entry.id
                        )}
                      >
                        {expandedEntryId === entry.id
                          ? "Ocultar datos"
                          : "Ver datos de este cálculo"}
                        <span className="material-symbols-outlined">
                          {expandedEntryId === entry.id ? "expand_less" : "expand_more"}
                        </span>
                      </button>
                      <button
                        type="button"
                        className="history-entry-delete"
                        aria-label="Borrar cálculo"
                        title="Borrar cálculo"
                        onClick={() => setConfirmAction({
                          type: "entry",
                          entryId: entry.id,
                          title: "¿Borrar este cálculo?",
                          message: "Esta recomendación se eliminará del historial del evento."
                        })}
                        disabled={actionLoading}
                      >
                        <span className="material-symbols-outlined">delete</span>
                      </button>
                    </div>
                    {expandedEntryId === entry.id && (
                      <div className="history-entry-characteristics">
                        {getCharacteristics(
                          entry.custom || selected.custom,
                          entry.ticketCategory
                        ).map(
                          ([label, value, suffix = ""]) => (
                            <div key={label}>
                              <small>{label}</small>
                              <strong>{value}{suffix}</strong>
                            </div>
                          )
                        )}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </section>
          ) : (
            <section className="history-empty">
              <span className="material-symbols-outlined">touch_app</span>
              <h2>Selecciona un evento</h2>
              <p>Elige un evento de la lista para consultar su historial de simulaciones.</p>
            </section>
          )}
        </div>
      )}

      {confirmAction && (
        <div className="history-modal-backdrop" role="presentation">
          <section
            className="history-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="history-modal-title"
          >
            <span className="material-symbols-outlined history-modal-icon">delete</span>
            <h2 id="history-modal-title">{confirmAction.title}</h2>
            <p>{confirmAction.message}</p>
            <div className="history-modal-actions">
              <button type="button" className="history-modal-cancel" onClick={() => setConfirmAction(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className="history-modal-confirm"
                disabled={actionLoading}
                onClick={() => confirmAction.type === "event"
                  ? deleteEvent()
                  : deleteEntry(confirmAction.entryId)}
              >
                Borrar
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
