import React, { useState } from "react";
import { api } from "../../api.js";

const DURATION_PRESETS = [
  { label: "30 m", minutes: 30 },
  { label: "1 h",  minutes: 60 },
  { label: "2 h",  minutes: 120 },
  { label: "4 h",  minutes: 240 },
  { label: "6 h",  minutes: 360 },
  { label: "8 h",  minutes: 480 },
  { label: "10 h", minutes: 600 },
];

const MODE_UI = {
  duration: "For…",
  until_today: "Until (today)",
  until_datetime: "Until date+time",
};

function pad(n) { return String(n).padStart(2, "0"); }

function nowLocalDatetimeInput() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function nowLocalTimeInput() {
  const d = new Date();
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fmtMinutesLeft(m) {
  if (m == null) return "";
  if (m < 60) return `${m}m left`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem ? `${h}h ${rem}m left` : `${h}h left`;
}

function fmtOverrideAt(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function pickerToUntilString({ mode, duration, timeToday, dateTime }) {
  if (mode === "duration") return { duration_minutes: duration };
  if (mode === "until_today") {
    if (!/^\d{2}:\d{2}$/.test(timeToday)) return null;
    const now = new Date();
    const [h, m] = timeToday.split(":").map(Number);
    const target = new Date(now.getFullYear(), now.getMonth(), now.getDate(), h, m, 0);
    if (target <= now) target.setDate(target.getDate() + 1); // roll to tomorrow
    return { until: fmtLocalDbString(target) };
  }
  if (mode === "until_datetime") {
    if (!dateTime) return null;
    const parsed = new Date(dateTime);
    if (isNaN(parsed.getTime())) return null;
    return { until: fmtLocalDbString(parsed) };
  }
  return null;
}

function fmtLocalDbString(d) {
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:00`
  );
}

function OverridePicker({ room, onSubmit, onCancel, busy }) {
  const [mode, setMode] = useState("duration");
  const [duration, setDuration] = useState(60);
  const [timeToday, setTimeToday] = useState(nowLocalTimeInput());
  const [dateTime, setDateTime] = useState(nowLocalDatetimeInput());

  function send(state) {
    const payload = pickerToUntilString({ mode, duration, timeToday, dateTime });
    if (!payload) return;
    onSubmit({ room: room.room, state, ...payload });
  }

  return (
    <div className="sv-smart-ac-override">
      <div style={{ fontSize: 12, marginBottom: 6 }}>
        Override <strong>{room.name || room.room}</strong> — smart_ac will
        leave it alone for the picked window.
      </div>

      <div className="ac-override-modes">
        {Object.entries(MODE_UI).map(([k, label]) => (
          <button
            key={k}
            type="button"
            className={mode === k ? "active" : ""}
            onClick={() => setMode(k)}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "duration" && (
        <div className="sv-smart-ac-duration">
          {DURATION_PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              className={duration === p.minutes ? "active" : ""}
              onClick={() => setDuration(p.minutes)}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
      {mode === "until_today" && (
        <div style={{ marginTop: 6 }}>
          <label style={{ fontSize: 12 }}>
            Until{" "}
            <input
              type="time"
              value={timeToday}
              onChange={(e) => setTimeToday(e.target.value)}
              style={{ fontSize: 13 }}
            />
            {" "}today (rolls to tomorrow if in the past).
          </label>
        </div>
      )}
      {mode === "until_datetime" && (
        <div style={{ marginTop: 6 }}>
          <label style={{ fontSize: 12 }}>
            Until{" "}
            <input
              type="datetime-local"
              value={dateTime}
              onChange={(e) => setDateTime(e.target.value)}
              style={{ fontSize: 13 }}
            />
          </label>
          <div className="muted" style={{ fontSize: 11 }}>
            Backend caps at 10 days out.
          </div>
        </div>
      )}

      <div className="sv-smart-ac-actions">
        <button
          type="button"
          className="sv-smart-ac-btn danger"
          disabled={busy}
          onClick={() => send("off")}
        >
          Turn OFF
        </button>
        <button
          type="button"
          className="sv-smart-ac-btn primary"
          disabled={busy}
          onClick={() => send("on")}
        >
          Turn ON
        </button>
        <button
          type="button"
          className="sv-smart-ac-btn"
          disabled={busy}
          onClick={() =>
            onSubmit({ room: room.room, state: room.on ? "on" : "off", duration_minutes: 0 })
          }
          title="Clear the override; smart_ac resumes control on next tick"
        >
          Release
        </button>
        <button
          type="button"
          className="sv-smart-ac-btn ghost"
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function AcOverrideWidget({ data, onChanged }) {
  const [openRoom, setOpenRoom] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!data) return <div className="muted">Loading…</div>;
  if (data.note) return <div className="muted">{data.note}</div>;
  const rooms = data.rooms || [];

  async function submit(payload) {
    setBusy(true);
    setErr("");
    try {
      await api.smartAcOverride(payload);
      if (onChanged) await onChanged();
      setOpenRoom(null);
    } catch (ex) {
      setErr(ex.message || "override failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="sv-smart-ac">
      <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
        AC override — click a room, then pick a duration OR a target date/time.
        smart_ac won't touch it until the window ends.
        {data.smart_ac_mode ? ` · mode: ${data.smart_ac_mode}` : ""}
      </div>
      <div className="sv-smart-ac-grid">
        {rooms.map((r) => {
          const overrideStr = r.override_until
            ? `pinned → ${fmtOverrideAt(r.override_until)} (${fmtMinutesLeft(r.override_minutes_left)})`
            : (r.scheduler_reason || "");
          return (
            <button
              key={r.room}
              type="button"
              className={`sv-smart-ac-chip ${r.on ? "on" : "off"} ${r.override_until ? "pinned" : ""}`}
              title={`${r.entity_id} — ${r.state}${overrideStr ? " · " + overrideStr : ""}`}
              disabled={busy}
              onClick={() => setOpenRoom(r.room === openRoom ? null : r.room)}
            >
              <div className="sv-smart-ac-name">{r.name || r.room}</div>
              <div className="sv-smart-ac-watts">
                {r.on ? `${(Number(r.watts) / 1000).toFixed(2)} kW` : "off"}
              </div>
              {r.override_until && (
                <div className="sv-smart-ac-rated" title={fmtOverrideAt(r.override_until)}>
                  {fmtMinutesLeft(r.override_minutes_left)}
                </div>
              )}
            </button>
          );
        })}
      </div>
      {err && <div className="error-inline">{err}</div>}
      {openRoom && (() => {
        const r = rooms.find((x) => x.room === openRoom);
        if (!r) return null;
        return (
          <OverridePicker
            room={r}
            busy={busy}
            onSubmit={submit}
            onCancel={() => setOpenRoom(null)}
          />
        );
      })()}
    </div>
  );
}
