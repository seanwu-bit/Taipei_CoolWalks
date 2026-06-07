"""
Weather Integration Engine (Task 4)
==================================

Task 4 integrates:
- CWA station observations
- CWA UV data
- CWA 36-hour forecast
- MOENV AQI / PM2.5 data

For air quality, the module keeps the nearest station reading and also
estimates a smoothed PM2.5 value at the Daan District center using a small
ordinary kriging solver implemented with NumPy-free linear algebra.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests


def _load_env_file() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file()

# CWA
CWA_API_KEY = os.getenv("CWA_API_KEY", "").strip()
TAIPEI_STATION_ID = "466920"
CWA_BASE_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"

# MOENV
MOENV_API_KEY = os.getenv("MOENV_API_KEY", "").strip()
MOENV_BASE_URL = "https://data.moenv.gov.tw/api/v2"
MOENV_AQI_DATASET = "aqx_p_432"

# Study area center: Daan District
DAAN_CENTER_LAT = 25.0264
DAAN_CENTER_LON = 121.5435

TIMEOUT = 10
TAIPEI_TZ = timezone(timedelta(hours=8))


@dataclass
class AirQualityStation:
    site_name: str
    county: str
    aqi: Optional[int]
    status: str
    pollutant: str
    pm25: Optional[float]
    latitude: float
    longitude: float
    publish_time: str
    site_id: str = ""


@dataclass
class WeatherData:
    obs_time: str
    temperature: float
    humidity: int
    wind_speed: float
    wind_direction: float
    precipitation: float
    weather_desc: str
    uv_index: float
    uv_date: str
    forecast_weather: str = ""
    forecast_pop: int = 0
    apparent_temp: float = 0.0
    heat_index: float = 0.0
    wbgt: float = 0.0
    uv_level: str = ""
    uv_color: str = ""
    heat_risk: str = ""
    heat_risk_color: str = ""
    shadow_weight_multiplier: float = 1.0
    aqi: Optional[int] = None
    aqi_status: str = ""
    aqi_pollutant: str = ""
    aqi_color: str = "#8892b0"
    aqi_site_name: str = ""
    air_quality_time: str = ""
    pm25: Optional[float] = None
    pm25_kriging: Optional[float] = None
    pm25_level: str = ""
    pm25_color: str = "#8892b0"
    pm25_method: str = ""
    pm25_neighbor_count: int = 0
    nearby_stations: list = None
    requested_time: str = ""
    weather_time_delta_min: Optional[float] = None
    air_quality_time_delta_min: Optional[float] = None
    climate_time_synced: bool = True


def _parse_datetime_flexible(value: str) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None

    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    if " " in text and "T" not in text:
        candidates.append(text.replace(" ", "T"))

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=TAIPEI_TZ)
            return parsed
        except ValueError:
            continue
    return None


def _delta_minutes(target_time: Optional[datetime], source_time: Optional[datetime]) -> Optional[float]:
    if target_time is None or source_time is None:
        return None
    source_local = source_time.astimezone(target_time.tzinfo or TAIPEI_TZ)
    return round(abs((source_local - target_time).total_seconds()) / 60.0, 1)


def _to_float(value: object) -> Optional[float]:
    if value in (None, "", "x", "X", "-", "NA", "N/A"):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> Optional[int]:
    numeric = _to_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _uv_level(uv: float) -> tuple[str, str]:
    if uv < 3:
        return "Low", "#4caf50"
    if uv < 6:
        return "Moderate", "#ffeb3b"
    if uv < 8:
        return "High", "#ff9800"
    if uv < 11:
        return "Very High", "#f44336"
    return "Extreme", "#9c27b0"


def _heat_risk(wbgt: float) -> tuple[str, str]:
    if wbgt < 25:
        return "Safe", "#4caf50"
    if wbgt < 28:
        return "Caution", "#ffeb3b"
    if wbgt < 31:
        return "Warning", "#ff9800"
    if wbgt < 35:
        return "High Risk", "#f44336"
    return "Extreme Risk", "#9c27b0"


def _aqi_level(aqi: Optional[int]) -> tuple[str, str]:
    if aqi is None:
        return "Unavailable", "#8892b0"
    if aqi <= 50:
        return "Good", "#4caf50"
    if aqi <= 100:
        return "Moderate", "#ffeb3b"
    if aqi <= 150:
        return "Unhealthy SG", "#ff9800"
    if aqi <= 200:
        return "Unhealthy", "#f44336"
    if aqi <= 300:
        return "Very Unhealthy", "#8e24aa"
    return "Hazardous", "#7e0023"


def _pm25_level(pm25: Optional[float]) -> tuple[str, str]:
    if pm25 is None:
        return "Unavailable", "#8892b0"
    if pm25 <= 15.4:
        return "Good", "#4caf50"
    if pm25 <= 35.4:
        return "Moderate", "#ffeb3b"
    if pm25 <= 54.4:
        return "Unhealthy SG", "#ff9800"
    if pm25 <= 150.4:
        return "Unhealthy", "#f44336"
    if pm25 <= 250.4:
        return "Very Unhealthy", "#8e24aa"
    return "Hazardous", "#7e0023"


def _apparent_temp(t: float, rh: int, ws: float) -> float:
    e = (rh / 100.0) * 6.105 * math.exp(17.27 * t / (237.7 + t))
    return round(t + 0.33 * e - 0.70 * ws - 4.00, 1)


def _heat_index(t: float, rh: int) -> float:
    if t < 27:
        return t
    c = [-8.78469475556, 1.61139411, 2.33854883889,
         -0.14611605, -0.012308094, -0.0164248277778,
          0.002211732, 0.00072546, -0.000003582]
    hi = (c[0] + c[1] * t + c[2] * rh + c[3] * t * rh + c[4] * t ** 2
          + c[5] * rh ** 2 + c[6] * t ** 2 * rh + c[7] * t * rh ** 2
          + c[8] * t ** 2 * rh ** 2)
    return round(hi, 1)


def _wbgt_simple(t: float, rh: int) -> float:
    tw = (t * math.atan(0.151977 * (rh + 8.313659) ** 0.5)
          + math.atan(t + rh)
          - math.atan(rh - 1.676331)
          + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh)
          - 4.686035)
    tg = t + 2.0
    return round(0.7 * tw + 0.2 * tg + 0.1 * t, 1)


def _shadow_weight(uv: float, wbgt: float) -> float:
    uv_factor = min(uv / 8.0, 1.5)
    wbgt_factor = max((wbgt - 25) / 10.0, 0.0)
    return round(1.0 + uv_factor + wbgt_factor, 2)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    aug = [row[:] + [vector[i]] for i, row in enumerate(matrix)]

    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(aug[r][i]))
        if abs(aug[pivot][i]) < 1e-12:
            raise ValueError("Singular matrix")
        aug[i], aug[pivot] = aug[pivot], aug[i]

        pivot_value = aug[i][i]
        for j in range(i, n + 1):
            aug[i][j] /= pivot_value

        for r in range(n):
            if r == i:
                continue
            factor = aug[r][i]
            for c in range(i, n + 1):
                aug[r][c] -= factor * aug[i][c]

    return [aug[i][n] for i in range(n)]


def _idw_estimate(
    target_lat: float,
    target_lon: float,
    stations: list[AirQualityStation],
    power: float = 2.0,
) -> Optional[float]:
    weighted_sum = 0.0
    weight_total = 0.0
    for station in stations:
        if station.pm25 is None:
            continue
        dist = _haversine_m(target_lat, target_lon, station.latitude, station.longitude)
        if dist < 1.0:
            return round(station.pm25, 1)
        weight = 1.0 / (dist ** power)
        weighted_sum += weight * station.pm25
        weight_total += weight
    if weight_total <= 0:
        return None
    return round(weighted_sum / weight_total, 1)


def _ordinary_kriging_pm25(
    target_lat: float,
    target_lon: float,
    stations: list[AirQualityStation],
) -> tuple[Optional[float], str]:
    usable = [station for station in stations if station.pm25 is not None]
    if len(usable) < 3:
        return _idw_estimate(target_lat, target_lon, usable), "IDW"

    values = [station.pm25 for station in usable if station.pm25 is not None]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    sill = max(variance, 1.0)

    max_pair_distance = 0.0
    for i, station_i in enumerate(usable):
        for station_j in usable[i + 1:]:
            max_pair_distance = max(
                max_pair_distance,
                _haversine_m(
                    station_i.latitude, station_i.longitude,
                    station_j.latitude, station_j.longitude,
                ),
            )
    corr_range = max(max_pair_distance * 0.6, 5_000.0)
    nugget = sill * 0.05

    def covariance(distance_m: float, identical: bool = False) -> float:
        base = sill * math.exp(-distance_m / corr_range)
        return base + (nugget if identical else 0.0)

    n = len(usable)
    matrix = [[0.0 for _ in range(n + 1)] for _ in range(n + 1)]
    vector = [0.0 for _ in range(n + 1)]

    for i, station_i in enumerate(usable):
        for j, station_j in enumerate(usable):
            dist = _haversine_m(
                station_i.latitude, station_i.longitude,
                station_j.latitude, station_j.longitude,
            )
            matrix[i][j] = covariance(dist, identical=(i == j))
        matrix[i][n] = 1.0
        matrix[n][i] = 1.0

        target_dist = _haversine_m(
            target_lat, target_lon, station_i.latitude, station_i.longitude
        )
        vector[i] = covariance(target_dist)

    try:
        weights = _solve_linear_system(matrix, vector)[:-1]
    except ValueError:
        return _idw_estimate(target_lat, target_lon, usable), "IDW"

    estimate = sum(weight * station.pm25 for weight, station in zip(weights, usable))
    return round(estimate, 1), "Ordinary Kriging"


def _extract_moenv_records(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    records = payload.get("records")
    if isinstance(records, list):
        return [item for item in records if isinstance(item, dict)]
    if isinstance(records, dict):
        nested = records.get("records")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    return []


def _fetch_station_obs() -> dict:
    if not CWA_API_KEY:
        raise ValueError("Missing CWA_API_KEY. Add it to Solar_Geometry/.env or your environment.")
    response = requests.get(
        f"{CWA_BASE_URL}/O-A0001-001",
        params={
            "Authorization": CWA_API_KEY,
            "StationName": "臺北",
            "format": "JSON",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    stations = response.json()["records"]["Station"]
    for station in stations:
        if station["StationId"] == TAIPEI_STATION_ID:
            return station
    return stations[0]


def _fetch_uv() -> tuple[float, str]:
    if not CWA_API_KEY:
        raise ValueError("Missing CWA_API_KEY. Add it to Solar_Geometry/.env or your environment.")
    response = requests.get(
        f"{CWA_BASE_URL}/O-A0005-001",
        params={
            "Authorization": CWA_API_KEY,
            "format": "JSON",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    weather_element = response.json()["records"]["weatherElement"]
    date_str = weather_element.get("Date", "")
    for location in weather_element.get("location", []):
        if location["StationID"] == TAIPEI_STATION_ID:
            return float(location["UVIndex"]), date_str
    return -99.0, date_str


def _fetch_forecast() -> tuple[str, int]:
    if not CWA_API_KEY:
        raise ValueError("Missing CWA_API_KEY. Add it to Solar_Geometry/.env or your environment.")
    response = requests.get(
        f"{CWA_BASE_URL}/F-C0032-001",
        params={
            "Authorization": CWA_API_KEY,
            "locationName": "臺北市",
            "format": "JSON",
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    elements = response.json()["records"]["location"][0]["weatherElement"]
    forecast_weather = ""
    forecast_pop = 0
    for element in elements:
        if element["elementName"] == "Wx":
            forecast_weather = element["time"][0]["parameter"]["parameterName"]
        elif element["elementName"] == "PoP":
            forecast_pop = _to_int(element["time"][0]["parameter"]["parameterName"]) or 0
    return forecast_weather, forecast_pop


def _fetch_air_quality() -> tuple[Optional[AirQualityStation], Optional[float], str, int, list[AirQualityStation]]:
    params = {
        "format": "json",
        "limit": 1000,
        "sort": "publishtime desc",
    }
    if MOENV_API_KEY:
        params["api_key"] = MOENV_API_KEY

    response = requests.get(
        f"{MOENV_BASE_URL}/{MOENV_AQI_DATASET}",
        params=params,
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    records = _extract_moenv_records(response.json())
    stations: list[AirQualityStation] = []
    for row in records:
        latitude = _to_float(row.get("latitude") or row.get("Latitude"))
        longitude = _to_float(row.get("longitude") or row.get("Longitude"))
        pm25 = _to_float(
            row.get("pm2.5_avg") or row.get("PM2.5_AVG")
            or row.get("pm2.5") or row.get("PM2.5")
        )
        aqi = _to_int(row.get("aqi") or row.get("AQI"))
        if latitude is None or longitude is None:
            continue
        if pm25 is None and aqi is None:
            continue

        stations.append(
            AirQualityStation(
                site_name=str(row.get("sitename") or row.get("SiteName") or ""),
                county=str(row.get("county") or row.get("County") or ""),
                aqi=aqi,
                status=str(row.get("status") or row.get("Status") or ""),
                pollutant=str(row.get("pollutant") or row.get("Pollutant") or ""),
                pm25=pm25,
                latitude=latitude,
                longitude=longitude,
                publish_time=str(
                    row.get("publishtime") or row.get("PublishTime")
                    or row.get("datacreationdate") or ""
                ),
                site_id=str(row.get("siteid") or row.get("SiteId") or ""),
            )
        )

    if not stations:
        return None, None, "", 0, []

    stations.sort(
        key=lambda station: _haversine_m(
            DAAN_CENTER_LAT, DAAN_CENTER_LON, station.latitude, station.longitude
        )
    )
    nearest_station = stations[0]

    kriging_neighbors = [
        station for station in stations[:8]
        if station.pm25 is not None
    ]
    pm25_smoothed, method = _ordinary_kriging_pm25(
        DAAN_CENTER_LAT, DAAN_CENTER_LON, kriging_neighbors
    )
    # Return top 20 nearest stations for visualization
    nearby_stations = stations[:20]
    return nearest_station, pm25_smoothed, method, len(kriging_neighbors), nearby_stations


def fetch_weather(
    target_time: Optional[datetime] = None,
    max_time_gap_minutes: Optional[int] = None,
    strict_time_sync: bool = False,
) -> WeatherData:
    station = _fetch_station_obs()
    weather_element = station["WeatherElement"]
    obs_time = station["ObsTime"]["DateTime"]
    temperature = float(weather_element["AirTemperature"])
    humidity = int(float(weather_element["RelativeHumidity"]))
    wind_speed = float(weather_element.get("WindSpeed", 0))
    wind_direction = float(weather_element.get("WindDirection", 0))
    precipitation = float(weather_element["Now"]["Precipitation"])
    weather_desc = weather_element.get("Weather", "")

    uv_index, uv_date = _fetch_uv()
    forecast_weather, forecast_pop = _fetch_forecast()

    apparent_temp = _apparent_temp(temperature, humidity, wind_speed)
    heat_index = _heat_index(temperature, humidity)
    wbgt = _wbgt_simple(temperature, humidity)
    uv_level, uv_color = _uv_level(uv_index if uv_index >= 0 else 0)
    heat_risk, heat_risk_color = _heat_risk(wbgt)
    shadow_weight_multiplier = _shadow_weight(uv_index if uv_index >= 0 else 0, wbgt)

    aqi_station: Optional[AirQualityStation] = None
    pm25_kriging: Optional[float] = None
    pm25_method = ""
    pm25_neighbor_count = 0
    nearby_stations = []
    try:
        aqi_station, pm25_kriging, pm25_method, pm25_neighbor_count, nearby_stations = _fetch_air_quality()
    except requests.RequestException:
        pass

    aqi_level, aqi_color = _aqi_level(aqi_station.aqi if aqi_station else None)
    pm25_value = aqi_station.pm25 if aqi_station else None
    pm25_level, pm25_color = _pm25_level(pm25_kriging if pm25_kriging is not None else pm25_value)
    weather_dt = _parse_datetime_flexible(obs_time)
    air_quality_dt = _parse_datetime_flexible(aqi_station.publish_time if aqi_station else "")
    weather_time_delta_min = _delta_minutes(target_time, weather_dt)
    air_quality_time_delta_min = _delta_minutes(target_time, air_quality_dt)

    climate_time_synced = True
    if max_time_gap_minutes is not None:
        deltas = [delta for delta in [weather_time_delta_min, air_quality_time_delta_min] if delta is not None]
        climate_time_synced = all(delta <= max_time_gap_minutes for delta in deltas)
        if strict_time_sync and not climate_time_synced:
            raise ValueError(
                "Weather/AQI timestamps are not synchronized with the requested simulation time. "
                f"Requested={target_time.isoformat() if target_time else ''}, "
                f"weather_obs={obs_time}, air_quality={aqi_station.publish_time if aqi_station else ''}, "
                f"max_gap={max_time_gap_minutes} min."
            )

    return WeatherData(
        obs_time=obs_time,
        temperature=temperature,
        humidity=humidity,
        wind_speed=wind_speed,
        wind_direction=wind_direction,
        precipitation=precipitation,
        weather_desc=weather_desc,
        uv_index=uv_index,
        uv_date=uv_date,
        forecast_weather=forecast_weather,
        forecast_pop=forecast_pop,
        apparent_temp=apparent_temp,
        heat_index=heat_index,
        wbgt=wbgt,
        uv_level=uv_level,
        uv_color=uv_color,
        heat_risk=heat_risk,
        heat_risk_color=heat_risk_color,
        shadow_weight_multiplier=shadow_weight_multiplier,
        aqi=aqi_station.aqi if aqi_station else None,
        aqi_status=aqi_station.status if aqi_station else "",
        aqi_pollutant=aqi_station.pollutant if aqi_station else "",
        aqi_color=aqi_color,
        aqi_site_name=aqi_station.site_name if aqi_station else "",
        air_quality_time=aqi_station.publish_time if aqi_station else "",
        pm25=pm25_value,
        pm25_kriging=pm25_kriging,
        pm25_level=pm25_level,
        pm25_color=pm25_color,
        pm25_method=pm25_method,
        pm25_neighbor_count=pm25_neighbor_count,
        nearby_stations=nearby_stations,
        requested_time=target_time.isoformat() if target_time else "",
        weather_time_delta_min=weather_time_delta_min,
        air_quality_time_delta_min=air_quality_time_delta_min,
        climate_time_synced=climate_time_synced,
    )
