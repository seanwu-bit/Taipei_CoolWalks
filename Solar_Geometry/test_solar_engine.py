"""
Tests for Solar_Geometry.solar_engine
"""

from datetime import datetime, timezone, timedelta

import pytest

from solar_engine import (
    SolarPosition,
    get_solar_position,
    get_solar_positions_over_walk,
    _normalize_azimuth,
    _ensure_utc,
)


# ---------------------------------------------------------------------------
# _ensure_utc
# ---------------------------------------------------------------------------

class TestEnsureUtc:
    def test_naive_becomes_utc(self):
        naive = datetime(2025, 6, 21, 6, 0, 0)
        result = _ensure_utc(naive)
        assert result.tzinfo == timezone.utc
        assert result.replace(tzinfo=None) == naive

    def test_aware_converted_to_utc(self):
        cst = timezone(timedelta(hours=8))  # UTC+8
        aware = datetime(2025, 6, 21, 14, 0, 0, tzinfo=cst)
        result = _ensure_utc(aware)
        assert result.tzinfo == timezone.utc
        assert result.hour == 6  # 14:00 CST = 06:00 UTC


# ---------------------------------------------------------------------------
# _normalize_azimuth
# ---------------------------------------------------------------------------

class TestNormalizeAzimuth:
    def test_north_zero_stays_zero(self):
        assert _normalize_azimuth(0.0) == 0.0

    def test_negative_wraps_correctly(self):
        assert _normalize_azimuth(-90.0) == 270.0

    def test_positive_180_stays_180(self):
        assert _normalize_azimuth(180.0) == 180.0

    def test_output_always_in_0_360(self):
        for raw in range(-180, 361, 10):
            result = _normalize_azimuth(float(raw))
            assert 0.0 <= result < 360.0


# ---------------------------------------------------------------------------
# get_solar_position
# ---------------------------------------------------------------------------

class TestGetSolarPosition:
    LAT = 25.0478
    LON = 121.5319
    NOON_UTC = datetime(2025, 6, 21, 4, 0, 0, tzinfo=timezone.utc)

    def test_returns_solar_position_instance(self):
        pos = get_solar_position(self.NOON_UTC, self.LAT, self.LON)
        assert isinstance(pos, SolarPosition)

    def test_elevation_is_positive_at_midday(self):
        pos = get_solar_position(self.NOON_UTC, self.LAT, self.LON)
        assert pos.elevation > 0

    def test_azimuth_in_valid_range(self):
        pos = get_solar_position(self.NOON_UTC, self.LAT, self.LON)
        assert 0.0 <= pos.azimuth < 360.0

    def test_offset_shifts_time(self):
        pos0 = get_solar_position(self.NOON_UTC, self.LAT, self.LON, offset_minutes=0)
        pos30 = get_solar_position(self.NOON_UTC, self.LAT, self.LON, offset_minutes=30)
        assert pos30.time == pos0.time + timedelta(minutes=30)
        assert pos30.offset_minutes == 30

    def test_offset_minutes_stored(self):
        pos = get_solar_position(self.NOON_UTC, self.LAT, self.LON, offset_minutes=15)
        assert pos.offset_minutes == 15

    def test_naive_datetime_accepted(self):
        naive = datetime(2025, 6, 21, 4, 0, 0)
        pos = get_solar_position(naive, self.LAT, self.LON)
        assert pos.elevation > 0

    def test_invalid_latitude_raises(self):
        with pytest.raises(ValueError, match="Latitude"):
            get_solar_position(self.NOON_UTC, 91.0, self.LON)

    def test_invalid_longitude_raises(self):
        with pytest.raises(ValueError, match="Longitude"):
            get_solar_position(self.NOON_UTC, self.LAT, 200.0)


# ---------------------------------------------------------------------------
# get_solar_positions_over_walk
# ---------------------------------------------------------------------------

class TestGetSolarPositionsOverWalk:
    LAT = 25.0478
    LON = 121.5319
    START = datetime(2025, 6, 21, 1, 0, 0, tzinfo=timezone.utc)

    def test_default_returns_five_slices(self):
        results = get_solar_positions_over_walk(self.START, self.LAT, self.LON)
        assert len(results) == 5

    def test_all_items_are_solar_position(self):
        results = get_solar_positions_over_walk(self.START, self.LAT, self.LON)
        assert all(isinstance(p, SolarPosition) for p in results)

    def test_first_offset_is_zero(self):
        results = get_solar_positions_over_walk(self.START, self.LAT, self.LON)
        assert results[0].offset_minutes == 0

    def test_last_offset_equals_total_minutes(self):
        results = get_solar_positions_over_walk(
            self.START, self.LAT, self.LON, total_minutes=30
        )
        assert results[-1].offset_minutes == 30

    def test_custom_interval(self):
        results = get_solar_positions_over_walk(
            self.START, self.LAT, self.LON,
            interval_minutes=10, total_minutes=30
        )
        offsets = [p.offset_minutes for p in results]
        assert offsets == [0, 10, 20, 30]

    def test_non_divisible_total_appended(self):
        results = get_solar_positions_over_walk(
            self.START, self.LAT, self.LON,
            interval_minutes=15, total_minutes=35
        )
        offsets = [p.offset_minutes for p in results]
        assert 35 in offsets

    def test_results_are_chronological(self):
        results = get_solar_positions_over_walk(self.START, self.LAT, self.LON)
        times = [p.time for p in results]
        assert times == sorted(times)

    def test_invalid_interval_raises(self):
        with pytest.raises(ValueError, match="interval_minutes"):
            get_solar_positions_over_walk(self.START, self.LAT, self.LON, interval_minutes=0)

    def test_zero_total_minutes_returns_single_entry(self):
        results = get_solar_positions_over_walk(
            self.START, self.LAT, self.LON, total_minutes=0
        )
        assert len(results) == 1
        assert results[0].offset_minutes == 0
