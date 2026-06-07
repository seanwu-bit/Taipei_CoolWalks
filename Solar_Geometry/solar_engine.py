"""
Solar Geometry Engine
=====================
Core module for computing solar position (altitude & azimuth) given a
departure time and geographic coordinates.

Dependencies
------------
    pip install pysolar

Public API
----------
    get_solar_position(dt, lat, lon)            -> SolarPosition
    get_solar_positions_over_walk(dt, lat, lon) -> list[SolarPosition]
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pysolar.solar import get_altitude, get_azimuth


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SolarPosition:
    """Immutable snapshot of the sun's position at a specific moment."""

    time: datetime          # UTC-aware datetime
    latitude: float         # degrees, positive = North
    longitude: float        # degrees, positive = East
    elevation: float        # degrees above horizon (altitude)
    azimuth: float          # degrees clockwise from North (0–360)
    offset_minutes: int = 0 # minutes elapsed since departure

    def __str__(self) -> str:
        local_str = self.time.strftime("%Y-%m-%d %H:%M:%S %Z")
        return (
            f"[T+{self.offset_minutes:>3}min | {local_str}] "
            f"Elevation={self.elevation:+.2f}°  Azimuth={self.azimuth:.2f}°"
        )


# ---------------------------------------------------------------------------
# Core calculation helpers
# ---------------------------------------------------------------------------

def _ensure_utc(dt: datetime) -> datetime:
    """Return *dt* as a UTC-aware datetime.

    * If *dt* is already timezone-aware it is converted to UTC.
    * If *dt* is naive it is assumed to be UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_azimuth(raw_azimuth: float) -> float:
    """Normalize Pysolar azimuth to [0, 360) degrees.

    Pysolar already returns azimuth clockwise from North, so the only
    normalization needed here is wrapping the value into the canonical range.
    """
    return raw_azimuth % 360.0


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_solar_position(
    dt: datetime,
    lat: float,
    lon: float,
    offset_minutes: int = 0,
) -> SolarPosition:
    """Calculate the sun's elevation and azimuth for a single moment.

    Parameters
    ----------
    dt : datetime
        Departure (or target) time.  May be timezone-aware or naive (UTC).
    lat : float
        Geographic latitude in decimal degrees (–90 … +90).
    lon : float
        Geographic longitude in decimal degrees (–180 … +180).
    offset_minutes : int, optional
        Minutes to add to *dt* before computing solar position.
        Useful for labelling time-slice results.

    Returns
    -------
    SolarPosition
        Frozen dataclass with elevation and azimuth at the requested moment.

    Raises
    ------
    ValueError
        If *lat* or *lon* are out of valid range.
    """
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"Latitude must be in [-90, 90], got {lat}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"Longitude must be in [-180, 180], got {lon}")

    utc_dt = _ensure_utc(dt) + timedelta(minutes=offset_minutes)

    elevation = get_altitude(lat, lon, utc_dt)
    azimuth = _normalize_azimuth(get_azimuth(lat, lon, utc_dt))

    return SolarPosition(
        time=utc_dt,
        latitude=lat,
        longitude=lon,
        elevation=round(elevation, 4),
        azimuth=round(azimuth, 4),
        offset_minutes=offset_minutes,
    )


def get_solar_positions_over_walk(
    departure_time: datetime,
    lat: float,
    lon: float,
    interval_minutes: int = 15,
    total_minutes: int = 60,
) -> list[SolarPosition]:
    """Generate solar positions for multiple time slices during a walk.

    Starting from *departure_time*, the function samples solar position at
    every *interval_minutes* up to (and including) *total_minutes*.

    Parameters
    ----------
    departure_time : datetime
        The moment the user starts walking.
    lat : float
        Geographic latitude in decimal degrees.
    lon : float
        Geographic longitude in decimal degrees.
    interval_minutes : int, optional
        Sampling interval in minutes (default: 15).
    total_minutes : int, optional
        Maximum walk duration in minutes (default: 60).

    Returns
    -------
    list[SolarPosition]
        Chronologically ordered list of SolarPosition snapshots, including
        t=0 (departure) through t=total_minutes.

    Examples
    --------
    >>> from datetime import datetime, timezone
    >>> positions = get_solar_positions_over_walk(
    ...     departure_time=datetime(2025, 6, 21, 8, 0, tzinfo=timezone.utc),
    ...     lat=25.0478,
    ...     lon=121.5319,
    ... )
    >>> for pos in positions:
    ...     print(pos)
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be a positive integer.")
    if total_minutes < 0:
        raise ValueError("total_minutes must be non-negative.")

    offsets: list[int] = list(range(0, total_minutes + 1, interval_minutes))
    # always include the final minute if not already present
    if total_minutes not in offsets:
        offsets.append(total_minutes)

    return [
        get_solar_position(departure_time, lat, lon, offset)
        for offset in offsets
    ]
