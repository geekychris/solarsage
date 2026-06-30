import React from "react";

const WMO_ICONS = {
  0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
  45: "🌫️", 48: "🌫️",
  51: "🌦️", 53: "🌦️", 55: "🌧️",
  61: "🌧️", 63: "🌧️", 65: "🌧️",
  71: "🌨️", 73: "🌨️", 75: "❄️",
  80: "🌧️", 81: "🌧️", 82: "⛈️",
  95: "⛈️", 96: "⛈️", 99: "⛈️",
};

function icon(code) {
  return WMO_ICONS[code] || "🌡️";
}

function unitTemp(units) { return units === "us" ? "°F" : "°C"; }
function unitWind(units) { return units === "us" ? "mph" : "km/h"; }
function unitPrecip(units) { return units === "us" ? "in" : "mm"; }

function dayLabel(dateStr, idx) {
  if (idx === 0) return "Today";
  if (idx === 1) return "Tomorrow";
  return new Date(dateStr + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "short",
  });
}

export default function WeatherWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const c = data.current || {};
  const days = data.daily || [];
  const u = data.units || "us";

  return (
    <div className="weather">
      <div className="weather-now">
        <span className="weather-icon">{icon(c.weather_code)}</span>
        <div className="weather-now-main">
          <span className="weather-big">
            {c.temp != null ? `${Math.round(c.temp)}${unitTemp(u)}` : "—"}
          </span>
          {c.feels_like != null && (
            <span className="muted" style={{ fontSize: 12 }}>
              feels {Math.round(c.feels_like)}{unitTemp(u)}
            </span>
          )}
        </div>
        <div className="weather-now-meta">
          <span>☁ {c.cloud_pct ?? "—"}%</span>
          <span>💧 {c.humidity_pct ?? "—"}%</span>
          <span>💨 {c.wind_speed != null ? `${Math.round(c.wind_speed)} ${unitWind(u)}` : "—"}</span>
        </div>
      </div>
      <div className="weather-days">
        {days.map((d, i) => (
          <div key={d.date} className="weather-day">
            <div className="weather-day-label">{dayLabel(d.date, i)}</div>
            <div className="weather-day-icon">{icon(d.weather_code)}</div>
            <div className="weather-day-temps">
              <span className="weather-high">{Math.round(d.high)}°</span>
              <span className="muted">{Math.round(d.low)}°</span>
            </div>
            <div className="weather-day-meta">
              {d.precip_prob != null && d.precip_prob > 0 && (
                <span>💧 {d.precip_prob}%</span>
              )}
              {d.cloud_mean_pct != null && (
                <span className="muted">☁ {Math.round(d.cloud_mean_pct)}%</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
