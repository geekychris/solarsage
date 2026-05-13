// Clear-sky envelope — direct port of backend/app/solar.py.
// Returns the theoretical max PV power (W) at a given lat/lon and local datetime.

const SOLAR_CONSTANT = 1361; // W/m² at top of atmosphere

function dayOfYear(date) {
  const start = new Date(Date.UTC(date.getUTCFullYear(), 0, 0));
  const diff = date - start;
  return Math.floor(diff / 86_400_000);
}

function solarDeclinationRad(date) {
  const N = dayOfYear(date);
  // Cooper's approximation
  return (23.45 * Math.PI / 180) * Math.sin(((2 * Math.PI) / 365) * (N - 81));
}

function equationOfTimeMin(date) {
  const N = dayOfYear(date);
  const B = ((2 * Math.PI) / 365) * (N - 81);
  return 9.87 * Math.sin(2 * B) - 7.53 * Math.cos(B) - 1.5 * Math.sin(B);
}

export function clearskyPowerW(lat, lon, localDateTime, peakKw) {
  // localDateTime is a Date instance whose UTC fields encode the local wall-clock
  const tzGuess = Math.round(-localDateTime.getTimezoneOffset()); // not used, see below
  // We trust the caller to pass a Date in local-wall-clock-as-UTC form.
  const date = localDateTime;
  const dec = solarDeclinationRad(date);
  const latRad = (lat * Math.PI) / 180;
  const eotMin = equationOfTimeMin(date);

  // Local solar time minutes
  const hr = date.getUTCHours();
  const min = date.getUTCMinutes();
  const localTimeMin = hr * 60 + min;
  // Apply longitude correction relative to local standard meridian. We don't
  // know the offset here in pure form — but the caller passes a wall-clock
  // local, so EOT is the main correction we need.
  const solarTimeMin = localTimeMin + eotMin;
  const hourAngleDeg = (solarTimeMin / 4) - 180;
  const hourAngleRad = (hourAngleDeg * Math.PI) / 180;

  const sinAlt =
    Math.sin(latRad) * Math.sin(dec) +
    Math.cos(latRad) * Math.cos(dec) * Math.cos(hourAngleRad);
  if (sinAlt <= 0) return 0;

  // Simple atmospheric attenuation model
  const airMass = 1 / sinAlt;
  const ghi = Math.max(0, SOLAR_CONSTANT * Math.pow(0.7, Math.pow(airMass, 0.678)) * sinAlt);
  // Map GHI (W/m²) → installation output via peak_kw rated at 1000 W/m².
  return Math.max(0, (ghi / 1000) * peakKw * 1000);
}
