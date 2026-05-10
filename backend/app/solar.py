"""Solar position + clear-sky envelope.

Uses the NOAA solar position algorithm (Spencer 1971 / Michalsky variant) —
accurate to within a fraction of a degree for solar elevation, which is plenty
for "how much PV could I theoretically be making right now". No external
dependencies.

The clear-sky model is intentionally simple: peak inverter rating times the
sine of solar elevation, with an empirical air-mass attenuation. It produces a
plausible upper-bound envelope, not a calibrated irradiance forecast.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class SunPosition:
    elevation_deg: float
    azimuth_deg: float
    declination_deg: float


def sun_position(lat_deg: float, lon_deg: float, dt: datetime) -> SunPosition:
    """Solar position at given UTC datetime. lat north +, lon east +."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)

    # Fractional year (radians)
    doy = dt_utc.timetuple().tm_yday
    hour_frac = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    gamma = 2 * math.pi / 365 * (doy - 1 + (hour_frac - 12) / 24)

    # Equation of time (minutes)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    # Declination (radians)
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    # Time offset (minutes), then true solar time (minutes)
    time_offset = eqtime + 4 * lon_deg
    tst = hour_frac * 60 + time_offset
    # Hour angle (degrees, -180 = midnight, 0 = noon)
    ha = (tst / 4) - 180
    ha_rad = math.radians(ha)
    lat_rad = math.radians(lat_deg)

    cos_zen = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.cos(ha_rad)
    cos_zen = max(-1.0, min(1.0, cos_zen))
    zen = math.acos(cos_zen)
    elevation = math.degrees(math.pi / 2 - zen)

    # Azimuth (clockwise from north)
    sin_az = -math.cos(decl) * math.sin(ha_rad) / max(math.sin(zen), 1e-9)
    cos_az = (math.sin(decl) - math.sin(lat_rad) * math.cos(zen)) / max(
        math.cos(lat_rad) * math.sin(zen), 1e-9
    )
    sin_az = max(-1.0, min(1.0, sin_az))
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.degrees(math.atan2(sin_az, cos_az)) % 360

    return SunPosition(elevation, az, math.degrees(decl))


def clearsky_power_w(lat_deg: float, lon_deg: float, dt: datetime, peak_kw: float) -> float:
    """Theoretical clear-sky PV power in watts.

    Model: peak_kw * sin(elevation) * exp(-airmass_attenuation). Returns 0 when
    the sun is below the horizon. The exp term gently penalizes low-angle sun
    (more atmosphere to traverse) so the envelope opens up gradually after
    sunrise and tapers before sunset, instead of jumping straight to peak.
    """
    pos = sun_position(lat_deg, lon_deg, dt)
    if pos.elevation_deg <= 0:
        return 0.0
    sin_el = math.sin(math.radians(pos.elevation_deg))
    # Kasten-Young air mass approximation
    airmass = 1.0 / (sin_el + 0.50572 * (6.07995 + pos.elevation_deg) ** -1.6364)
    # Attenuation factor — empirical, peaks at ~0.78 at zenith, drops fast at horizon
    attenuation = 0.7 ** (airmass ** 0.678)
    return max(0.0, peak_kw * 1000 * sin_el * attenuation)


def sunrise_sunset(lat_deg: float, lon_deg: float, dt: datetime) -> tuple[datetime, datetime] | None:
    """Approximate sunrise/sunset UTC for the day of `dt`. None at high latitudes
    with no sunrise/sunset that day."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    midnight = dt_utc.replace(hour=12, minute=0, second=0, microsecond=0)  # noon-anchored for stability
    # Compute declination & eqtime at noon for the day
    pos = sun_position(lat_deg, lon_deg, midnight)
    decl = math.radians(pos.declination_deg)
    lat_rad = math.radians(lat_deg)
    # Hour angle of sunrise (refraction-corrected zenith = 90.833°)
    cos_h = (math.cos(math.radians(90.833)) - math.sin(lat_rad) * math.sin(decl)) / (
        math.cos(lat_rad) * math.cos(decl)
    )
    if cos_h > 1 or cos_h < -1:
        return None  # polar day / night
    ha = math.degrees(math.acos(cos_h))
    # Solar noon UTC (minutes from midnight) = 720 - 4*lon - eqtime
    # Recover eqtime from sun_position math:
    doy = dt_utc.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (doy - 1 + 0.5)  # at noon
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    solar_noon = 720 - 4 * lon_deg - eqtime  # minutes UTC
    sunrise_min = solar_noon - 4 * ha
    sunset_min = solar_noon + 4 * ha

    def from_minutes(m: float) -> datetime:
        midnight_utc = dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight_utc.replace(microsecond=0) + _td(minutes=m)

    return from_minutes(sunrise_min), from_minutes(sunset_min)


def _td(minutes: float):
    from datetime import timedelta
    return timedelta(minutes=minutes)
