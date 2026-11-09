
import { Link } from "react-router-dom";
import "./Dashboard.css";

const sections = [
  {
    icon: "tune",
    tag: "PREDICCIÓN Y OPTIMIZACIÓN",
    title: "Simulador de precios",
    description:
      "Configura un evento y recibe una recomendación de precio basada en la demanda estimada.",
    path: "/multisport",
    action: "Abrir simulador",
    main: true
  },
  {
    icon: "monitoring",
    tag: "EVALUACIÓN EXPERIMENTAL",
    title: "Comparador de estrategias",
    description:
      "Compara estrategias de precio y consulta el comportamiento de las simulaciones.",
    path: "/validation",
    action: "Ver resultados"
  },
  {
    icon: "history",
    tag: "SEGUIMIENTO",
    title: "Historial de eventos",
    description:
      "Guarda tus eventos y revisa las recomendaciones calculadas.",
    path: "/history",
    action: "Ver historial"
  }
];

export default function Dashboard() {
  return (
    <main className="dashboard-page">

      <header className="dashboard-hero">
        <div className="dashboard-eyebrow">
          SMART STADIUM PRICING
        </div>

        <h1>
          Decisiones de precio
          <span> basadas en datos.</span>
        </h1>

        <p>
          Una herramienta para analizar la demanda de entradas
          deportivas y tomar mejores decisiones de precio.
        </p>

        <div className="dashboard-hero-actions">
          <Link
            to="/multisport"
            className="dashboard-primary-button"
          >
            Abrir simulador
            <span className="material-symbols-outlined">
              arrow_forward
            </span>
          </Link>

          <Link
            to="/validation"
            className="dashboard-secondary-button"
          >
            Ver resultados
          </Link>
        </div>
      </header>

      <section className="dashboard-section">
        <div className="dashboard-section-heading">
          <div>
            <span>PLATAFORMA</span>
            <h2>Explora STADIUM IQ</h2>
          </div>
        </div>

        <div className="dashboard-cards">
          {sections.map((section) => (
            <Link
              to={section.path}
              key={section.path}
              className={`dashboard-card ${
                section.main ? "featured" : ""
              }`}
            >
              <div className="dashboard-card-icon">
                <span className="material-symbols-outlined">
                  {section.icon}
                </span>
              </div>

              <div className="dashboard-card-tag">
                {section.tag}
              </div>

              <h3>{section.title}</h3>

              <p>{section.description}</p>

              <div className="dashboard-card-link">
                {section.action}
                <span className="material-symbols-outlined">
                  arrow_forward
                </span>
              </div>
            </Link>
          ))}
        </div>
      </section>

    </main>
  );
}
