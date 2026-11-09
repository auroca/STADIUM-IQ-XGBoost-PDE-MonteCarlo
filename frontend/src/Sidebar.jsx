
import { NavLink } from "react-router-dom";

const navigation = [
  {
    path: "/",
    icon: "dashboard",
    label: "Inicio",
    end: true
  },
  {
    path: "/multisport",
    icon: "tune",
    label: "Simulador multideporte"
  },
  {
    path: "/history",
    icon: "history",
    label: "Historial de eventos"
  },
  {
    path: "/validation",
    icon: "monitoring",
    label: "Comparador"
  },
  {
    path: "/simulator",
    icon: "sports_soccer",
    label: "Simulador original"
  }
];

export default function Sidebar({ user, onLogout }) {
  return (
    <aside className="stadium-sidebar">

      <div className="brand">
        <span className="brand-mark material-symbols-outlined">
          stadium
        </span>

        <div>
          <strong>
            STADIUM<span>IQ</span>
          </strong>

          <small>PRICING INTELLIGENCE</small>
        </div>
      </div>

      <div className="nav-caption">
        PLATAFORMA
      </div>

      <nav aria-label="Navegación principal">
        {navigation.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            className={({ isActive }) =>
              `nav-entry ${isActive ? "active" : ""}`
            }
          >
            <span className="material-symbols-outlined">
              {item.icon}
            </span>

            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-bottom">
        <div className="sidebar-user">
          <span className="material-symbols-outlined">account_circle</span>
          <span>{user.email}</span>
          <button type="button" onClick={onLogout} aria-label="Cerrar sesión" title="Cerrar sesión">
            <span className="material-symbols-outlined">logout</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
