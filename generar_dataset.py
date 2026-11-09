"""Generador sintético de snapshots diarios para pricing deportivo.

Una fila = un evento + una categoría de producto + el estado AL INICIO de un día.
El objetivo sales_next_period representa lo ocurrido durante ese día.
Los factores latentes del generador no se exportan como features.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / 'resultados'
SPORTS = ('football', 'basketball', 'tennis', 'running')
SPORT_CATEGORY = {
    'football': ('general', 'premium'),
    'basketball': ('general', 'premium'),
    'tennis': ('day_session', 'evening_session'),
    'running': ('standard', 'premium_registration'),
}
COLUMNS_IDS = ['snapshot_id', 'event_id', 'ticket_category_id', 'observation_date']
TARGET_COL = 'sales_next_period'
EXCLUDE_FEATURES = {
    'snapshot_id', 'event_id', 'ticket_category_id', 'observation_date',
    'sales_next_period', 'potential_demand_next_period', 'revenue_next_period_eur',
    'cumulative_sales_after_period', 'remaining_capacity_after_period',
    'revenue_after_period_eur', 'price_policy_name',
    'event_date', 'sales_start_date',
}


def verify_probability(name: str, value: float) -> None:
    if not 0 <= value <= 1:
        raise ValueError(f'{name} fuera del intervalo [0,1]: {value}')


def event_context(rng: np.random.Generator, sport: str) -> dict:
    """Atributos de evento, fijados ANTES de la simulación de sus ventas."""
    popularity = float(rng.uniform(0.15, 0.95))
    importance = float(rng.uniform(0.2, 1))
    is_outdoor = sport in ('football', 'running', 'tennis')
    rainy = float(rng.uniform(0, 0.8)) if is_outdoor else 0.0
    context = {
        'sport_type': sport,
        'event_format': 'race' if sport == 'running' else ('tournament' if sport == 'tennis' else 'match'),
        'competition_level': str(rng.choice(['local', 'national', 'international'])),
        'competition_phase': str(rng.choice(['regular', 'quarterfinal', 'semifinal', 'final'])),
        'popularity_index': popularity,
        'event_importance': importance,
        'venue_type': 'outdoor' if is_outdoor else 'indoor',
        'weather_temperature': round(float(rng.uniform(8, 31)), 1),
        'rain_probability': round(rainy, 3),
        'is_televised': int(rng.random() < (0.60 if sport != 'running' else 0.15)),
        'is_holiday_period': int(rng.random() < 0.15),
        'competing_events': int(rng.random() < 0.22),
        'marketing_campaign': int(rng.random() < 0.35),
        'is_holiday': int(rng.random() < 0.15),
        'league_position_home': pd.NA,
        'league_position_away': pd.NA,
        'derby_rivalry_index': pd.NA,
        'recent_form_home_away': pd.NA,
        'league_stakes': pd.NA,
        'star_players_available': pd.NA,
        'team_win_percentage': pd.NA,
        'standings_difference': pd.NA,
        'playoff_phase': pd.NA,
        'back_to_back_game': pd.NA,
        'rivalry_index': pd.NA,
        'tournament_round': pd.NA,
        'player_ranking': pd.NA,
        'players_confirmed': pd.NA,
        'singles_doubles': pd.NA,
        'tournament_category': pd.NA,
        'session_schedule': pd.NA,
        'race_distance_km': pd.NA,
        'elevation_gain_m': pd.NA,
        'route_difficulty': pd.NA,
        'registration_deadline_days': pd.NA,
        'registration_tier': pd.NA,
        'participant_services': pd.NA,
    }
    if sport == 'football':
        context.update(
            league_position_home=int(rng.integers(1, 21)),
            league_position_away=int(rng.integers(1, 21)),
            derby_rivalry_index=round(float(rng.uniform(0, 1)), 3),
            recent_form_home_away=round(float(rng.uniform(0, 1)), 3),
            league_stakes=round(float(rng.uniform(0, 1)), 3),
            star_players_available=int(rng.random() < .8),
        )
    elif sport == 'basketball':
        context.update(
            team_win_percentage=round(float(rng.uniform(.2, .9)), 3),
            standings_difference=int(rng.integers(-15, 16)),
            playoff_phase=str(rng.choice(['regular', 'play_in', 'quarterfinal', 'semifinal', 'final'])),
            back_to_back_game=int(rng.random() < .18),
            rivalry_index=round(float(rng.uniform(0, 1)), 3),
        )
    elif sport == 'tennis':
        context.update(
            tournament_round=str(rng.choice(['R32', 'R16', 'QF', 'SF', 'F'])),
            player_ranking=int(rng.integers(1, 201)),
            players_confirmed=int(rng.random() < .92),
            singles_doubles=str(rng.choice(['singles', 'doubles'])),
            tournament_category=str(rng.choice(['ATP_250', 'ATP_500', 'Masters', 'Grand_Slam'])),
            session_schedule=str(rng.choice(['day', 'evening'])),
        )
    elif sport == 'running':
        km = float(rng.choice([5, 10, 21.0975, 42.195]))
        context.update(
            race_distance_km=km,
            elevation_gain_m=round(float(rng.uniform(0, 500)), 1),
            route_difficulty=round(float(rng.uniform(0.1, 0.95)), 3),
            participant_services=int(rng.random() < .7),
        )
    return context


def category_config(rng: np.random.Generator, sport: str, name: str) -> dict:
    base_prices = {'football': 32., 'basketball': 24., 'tennis': 38., 'running': 35.}
    multip = 1.55 if name in ('premium', 'premium_registration', 'evening_session') else 1.0
    base_price = round(base_prices[sport] * multip * float(rng.uniform(.8, 1.2)), 2)
    capacity = int(rng.integers(140, 901)) if sport != 'running' else int(rng.integers(200, 1601))
    return {
        'ticket_category': name,
        'category_capacity': capacity,
        'base_price': base_price,
        'min_price': round(base_price * .65, 2),
        'max_price': round(base_price * 1.65, 2),
        'competitor_price': round(base_price * float(rng.uniform(.85, 1.15)), 2),
        'is_premium_experience': int(name in ('premium', 'premium_registration', 'evening_session')),
        'hospitality_included': int(name == 'premium'),
        'visibility_category': (
            'not_applicable' if sport == 'running' else
            ('high' if name in ('premium', 'evening_session') else 'standard')
        ),
    }


def hidden_demand_mean(
    *, price: float, reference_price: float, capacity: int, periods: int,
    days_remaining: int, popularity: float, importance: float,
    sensitivity: float, intensity: float, time_trend: float,
    sport: str, sport_signal: float, rain_probability: float, is_outdoor: bool,
) -> float:
    """Generador del mundo simulado. Coeficientes no estimados de datos reales."""
    progress = 1.0 - days_remaining / periods
    # Elasticidad constante, heterogénea y desconocida para el predictor.
    price_factor = (price / reference_price) ** (-sensitivity)
    time_factor = np.exp(time_trend * (progress - .5))
    context = np.exp(0.8 * (popularity - .5) + .45 * (importance - .5))
    weather = np.exp(-.28 * rain_probability) if is_outdoor else 1.0
    sport_factor = np.exp(sport_signal)
    return max(0.0, capacity / periods * intensity * price_factor * time_factor * context * weather * sport_factor)


def generate(n_events: int = 120, days: int = 30, seed: int = 42) -> pd.DataFrame:
    if n_events <= 0 or days <= 0:
        raise ValueError('n_events y days deben ser positivos')
    rng = np.random.default_rng(seed)
    start = pd.Timestamp('2027-03-01')
    result = []
    idx = 0
    for event_no in range(1, n_events + 1):
        sport = SPORTS[(event_no - 1) % len(SPORTS)]
        attributes = event_context(rng, sport)
        event_date = start + pd.Timedelta(days=int(rng.integers(40, 450)))
        sales_start = event_date - pd.Timedelta(days=days)
        event_id = f'EV{event_no:04d}'
        attrs = attributes.copy()
        attrs['event_month'] = int(event_date.month)
        attrs['event_day_of_week'] = int(event_date.weekday())
        attrs['is_weekend'] = int(event_date.weekday() >= 5)
        attrs['event_date'] = event_date.date().isoformat()
        attrs['sales_start_date'] = sales_start.date().isoformat()

        # Parámetros LATENTES, solo del simulador, no se exportan.
        elasticity = float(rng.uniform(.45, 2.3))
        intensity = float(rng.uniform(.45, 1.9))
        time_trend = float(rng.uniform(-.6, 1.1))
        event_noise = float(rng.uniform(.8, 1.25))
        if sport == 'football':
            table_signal = (
                (21 - float(attrs['league_position_home'])) / 20
                + (21 - float(attrs['league_position_away'])) / 20
            ) / 2
            signal = (
                .22 * (float(attrs['derby_rivalry_index']) - .5)
                + .18 * (table_signal - .5)
                + .16 * (float(attrs['recent_form_home_away']) - .5)
                +                 .24 * (float(attrs['league_stakes']) - .5)
                + .14 * (float(attrs['star_players_available']) - .5)
            )
        elif sport == 'basketball':
            playoff_weight = {
                'regular': 0.0,
                'play_in': 0.04,
                'quarterfinal': 0.08,
                'semifinal': 0.12,
                'final': 0.18,
            }[attrs['playoff_phase']]
            signal = (
                .25 * (float(attrs['team_win_percentage']) - .5)
                + .28 * np.tanh(float(attrs['standings_difference']) / 8)
                + playoff_weight
                - .35 * float(attrs['back_to_back_game'])
                + .20 * (float(attrs['rivalry_index']) - .5)
            )
        elif sport == 'tennis':
            round_weight = {
                'R32': 0.0, 'R16': 0.03, 'QF': 0.08, 'SF': 0.14, 'F': 0.20
            }[attrs['tournament_round']]
            category_weight = {
                'ATP_250': 0.0, 'ATP_500': 0.04,
                'Masters': 0.09, 'Grand_Slam': 0.16
            }[attrs['tournament_category']]
            signal = (
                -.001 * (int(attrs['player_ranking']) - 50)
                + round_weight
                + category_weight
                + .16 * float(attrs['players_confirmed'])
                + .07 * (attrs['singles_doubles'] == 'doubles')
                + .06 * (attrs['session_schedule'] == 'evening')
            )
        else:
            signal = (
                .08 * np.log1p(float(attrs['race_distance_km']))
                + .45 * float(attrs['route_difficulty'])
                + .16 * (float(attrs['elevation_gain_m']) / 500)
                + .30 * float(attrs['participant_services'])
            )

        for category_no, category_name in enumerate(SPORT_CATEGORY[sport], start=1):
            config = category_config(rng, sport, category_name)
            remaining = config['category_capacity']
            sold_so_far = 0
            revenue_so_far = 0.0
            sales_history: list[int] = []
            previous_price = config['base_price']
            # Política exploratoria ficticia: precios varían por día.
            # Se elige ANTES de generar demanda del día, evita utilizar el target futuro.
            for current_day in range(1, days + 1):
                idx += 1
                days_remaining = days - current_day + 1
                observation = sales_start + pd.Timedelta(days=current_day - 1)
                shift = float(rng.choice([-.20, -.10, 0, .10, .20]))
                price = round(float(np.clip(
                    config['base_price'] * (1 + shift),
                    config['min_price'], config['max_price']
                )), 2)
                verify_probability('popularidad', float(attrs['popularity_index']))
                demand_signal = signal
                if sport == 'running':
                    registration_signal = (
                        .05 * np.tanh((days_remaining - 15) / 10)
                        + (0.04 if current_day <= days / 3 else
                           (0.0 if current_day <= 2 * days / 3 else -0.04))
                    )
                    demand_signal += registration_signal
                mean = hidden_demand_mean(
                    price=price, reference_price=config['base_price'],
                    capacity=config['category_capacity'], periods=days,
                    days_remaining=days_remaining,
                    popularity=float(attrs['popularity_index']),
                    importance=float(attrs['event_importance']),
                    sensitivity=elasticity, intensity=intensity * event_noise,
                    time_trend=time_trend, sport=sport, sport_signal=demand_signal,
                    rain_probability=float(attrs['rain_probability']),
                    is_outdoor=attrs['venue_type'] == 'outdoor',
                )
                # Demanda sobredispersa respecto a Poisson: heterogeneidad diaria.
                daily_random_multiplier = float(rng.gamma(shape=9., scale=1./9.))
                potential_demand = int(rng.poisson(mean * daily_random_multiplier))
                sales = min(potential_demand, remaining)
                sales_velocity = float(np.mean(sales_history[-7:])) if sales_history else 0.0
                row = {
                    'snapshot_id': f'SN{idx:07d}',
                    'event_id': event_id,
                    'ticket_category_id': f'{event_id}_CAT{category_no}',
                    'observation_date': observation.date().isoformat(),
                    'day_number': current_day,
                    'days_remaining': days_remaining,
                    'sales_window_days': days,
                    'prediction_horizon_days': 1,
                    'is_final_week': int(days_remaining <= 7),
                    'is_last_minute': int(days_remaining <= 3),
                    'day_of_week': int(observation.weekday()),
                    'sales_period': 'early' if current_day <= days/3 else ('middle' if current_day <= 2*days/3 else 'late'),
                    **attrs,
                    **config,
                    'previous_price': previous_price,
                    'price_change_pct': round((price / previous_price - 1) * 100, 5),
                    'registration_deadline_days': days_remaining if sport == 'running' else pd.NA,
                    'registration_tier': (
                        'early' if current_day <= days / 3 else
                        ('standard' if current_day <= 2 * days / 3 else 'late')
                    ) if sport == 'running' else pd.NA,
                    'total_capacity': config['category_capacity'],
                    'remaining_capacity': remaining,
                    'cumulative_sales': sold_so_far,
                    'sales_last_period': sales_history[-1] if sales_history else 0,
                    'sales_velocity': round(sales_velocity, 3),
                    'occupancy_rate': round(sold_so_far / config['category_capacity'], 5),
                    'remaining_capacity_pct': round(remaining / config['category_capacity'], 5),
                    'is_low_availability': int(remaining / config['category_capacity'] <= .1),
                    'scarcity_level': 'critical' if remaining / config['category_capacity'] <= .1 else ('high' if remaining / config['category_capacity'] <= .3 else ('medium' if remaining / config['category_capacity'] <= .6 else 'low')),
                    'current_price': price,
                    'candidate_price': price,
                    'price_vs_base': round(price / config['base_price'] - 1, 5),
                    'discount_active': int(price < config['base_price']),
                    'revenue_so_far': round(revenue_so_far, 2),
                    'revenue_per_capacity': round(revenue_so_far / config['category_capacity'], 3),
                    'remaining_revenue_potential': round(remaining * price, 2),
                    'price_policy_name': 'synthetic_exploration',
                    # Targets and future observations below must NEVER become features.
                    'sales_next_period': sales,
                    'potential_demand_next_period': potential_demand,
                    'revenue_next_period_eur': round(price * sales, 2),
                    'cumulative_sales_after_period': sold_so_far + sales,
                    'remaining_capacity_after_period': remaining - sales,
                    'revenue_after_period_eur': round(revenue_so_far + price * sales, 2),
                }
                result.append(row)
                remaining -= sales
                sold_so_far += sales
                revenue_so_far += price * sales
                sales_history.append(sales)
                previous_price = price
    return pd.DataFrame(result)


def encoded_version(readable: pd.DataFrame) -> pd.DataFrame:
    features = readable.drop(columns=sorted(EXCLUDE_FEATURES & set(readable.columns)))
    # No añadir event_id como feature: identificaría cada evento artificialmente.
    cats = features.select_dtypes(include=['object', 'string']).columns.tolist()
    encoded = pd.get_dummies(features, columns=cats, dummy_na=False, dtype=int)
    numeric = encoded.columns.tolist()
    encoded[numeric] = encoded[numeric].apply(pd.to_numeric, errors='coerce')
    # NaN explícitos para variables deportivas no aplicables (XGBoost los admite).
    identifiers = readable[['event_id', 'snapshot_id']].reset_index(drop=True)
    target = readable[[TARGET_COL]].astype(int).reset_index(drop=True)
    return pd.concat([identifiers, encoded.reset_index(drop=True), target], axis=1)


def check_dataset(df: pd.DataFrame, encoded: pd.DataFrame, n_events: int, days: int) -> None:
    assert len(df) == n_events * 2 * days
    assert df['event_id'].nunique() == n_events
    assert df['snapshot_id'].is_unique
    assert df['ticket_category_id'].nunique() == n_events * 2
    assert (df['sales_next_period'] >= 0).all()
    assert (df['sales_next_period'] <= df['remaining_capacity']).all()
    assert ((df['cumulative_sales'] + df['remaining_capacity']) == df['total_capacity']).all()
    assert ((df['remaining_capacity'] - df['sales_next_period']) == df['remaining_capacity_after_period']).all()
    assert ((df['revenue_next_period_eur'] - df['current_price'] * df['sales_next_period']).abs() < 1e-7).all()
    assert df['sport_type'].nunique() == len(SPORTS)
    assert len(encoded) == len(df)
    assert TARGET_COL in encoded.columns
    assert not set(('potential_demand_next_period', 'revenue_next_period_eur', 'cumulative_sales_after_period')) & set(encoded.columns)
    assert df.groupby('ticket_category_id').size().eq(days).all()
    # Verificar coherencia temporal del inventario entre snapshots de una categoría.
    for _, g in df.groupby('ticket_category_id', sort=False):
        assert np.array_equal(g['remaining_capacity'].to_numpy()[1:], g['remaining_capacity_after_period'].to_numpy()[:-1])
        assert np.array_equal(g['cumulative_sales'].to_numpy()[1:], g['cumulative_sales_after_period'].to_numpy()[:-1])


def save_dictionary(df: pd.DataFrame, out: Path) -> None:
    """Actualiza el catálogo maestro compartido con el documento de variables.

    Las variables propuestas que no están en este dataset siguen registradas
    como Pendiente; nunca se confunden con columnas ya implementadas.
    """
    catalog = Path(__file__).with_name('catalogo_variables.csv')
    if catalog.exists():
        master = pd.read_csv(catalog, dtype=str, keep_default_na=False)
    else:
        master = pd.DataFrame({
            'variable': df.columns,
            'estado_implementacion': 'Pendiente',
            'tipo_csv': '',
            'uso': '',
            'nulos': '',
            'ejemplo': '',
        })
    expected = {'variable', 'estado_implementacion', 'tipo_csv', 'uso', 'nulos', 'ejemplo'}
    assert expected.issubset(master.columns)
    assert master['variable'].is_unique
    assert set(df.columns).issubset(set(master['variable'])), 'Columnas del generador ausentes del catálogo'
    for i, row in master.iterrows():
        name = row['variable']
        if name in df:
            series = df[name]
            master.at[i, 'estado_implementacion'] = 'Implementada'
            master.at[i, 'tipo_csv'] = ('string/categorical' if series.dtype == 'object'
                                         else ('int' if pd.api.types.is_integer_dtype(series.dtype) else 'float'))
            master.at[i, 'nulos'] = str(int(series.isna().sum()))
            master.at[i, 'ejemplo'] = str(series.dropna().iloc[0]) if series.notna().any() else ''
        else:
            master.at[i, 'estado_implementacion'] = 'Pendiente'
            master.at[i, 'nulos'] = ''
            master.at[i, 'ejemplo'] = ''
    master.to_csv(out / 'diccionario_variables.csv', index=False, encoding='utf-8-sig')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--eventos', type=int, default=480)
    parser.add_argument('--dias', type=int, default=30)
    parser.add_argument('--semilla', type=int, default=42)
    parser.add_argument('--salida', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True)
    readable = generate(args.eventos, args.dias, args.semilla)
    encoded = encoded_version(readable)
    check_dataset(readable, encoded, args.eventos, args.dias)
    readable.to_csv(args.salida / 'dataset_multideporte_EQUIPO.csv', index=False)
    encoded.to_csv(args.salida / 'dataset_multideporte_XGBOOST_encoded.csv', index=False)
    save_dictionary(readable, args.salida)
    print('PRUEBAS: todas correctas')
    print(f'Eventos: {readable.event_id.nunique()}')
    print(f'Categorias por evento: 2; dias por categoria: {args.dias}')
    print(f'Filas: {len(readable):,}; columnas legibles: {len(readable.columns)}')
    print(f'Columnas codificadas: {len(encoded.columns)}')
    print('Deportes:', ', '.join(sorted(readable.sport_type.unique())))
    print('Archivos:', args.salida.resolve())
    print('\nPrimeras observaciones:')
    print(readable[['event_id','sport_type','ticket_category','days_remaining','current_price','remaining_capacity','sales_next_period']].head(8).to_string(index=False))


if __name__ == '__main__':
    main()
