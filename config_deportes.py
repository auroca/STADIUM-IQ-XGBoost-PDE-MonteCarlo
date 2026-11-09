
"""Configuracion central de deportes para STADIUM IQ."""

DEPORTES = {
    "football": {
        "nombre": "Futbol",
        "variables": (
            "derby_rivalry_index",
            "league_position_home",
            "league_position_away",
            "recent_form_home_away",
            "league_stakes",
            "star_players_available",
        ),
    },
    "basketball": {
        "nombre": "Baloncesto",
        "variables": (
            "team_win_percentage",
            "standings_difference",
            "playoff_phase",
            "back_to_back_game",
            "rivalry_index",
        ),
    },
    "tennis": {
        "nombre": "Tenis",
        "variables": (
            "player_ranking",
            "tournament_round",
            "players_confirmed",
            "singles_doubles",
            "tournament_category",
            "session_schedule",
        ),
    },
    "running": {
        "nombre": "Running",
        "variables": (
            "race_distance_km",
            "elevation_gain_m",
            "route_difficulty",
            "registration_deadline_days",
            "registration_tier",
            "participant_services",
        ),
    },
}


def variables_deporte(deporte):
    """Devuelve las variables especificas de cada deporte."""
    try:
        return DEPORTES[deporte]["variables"]
    except KeyError as exc:
        raise ValueError(
            f"Deporte no configurado: {deporte}"
        ) from exc
