import React, { useEffect, useState, useCallback } from "react";
import { api } from "../../api.js";

function formatLocal(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatTimeOnly(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function describeReminder(r) {
  const m = r.minutes_before;
  if (m === 0) return "at start";
  if (m < 60) return `${m}m before`;
  if (m % 60 === 0) return `${m / 60}h before`;
  return `${Math.round((m / 60) * 10) / 10}h before`;
}

function ReminderEditor({ event, onSaved }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(
    () => event.reminders.map((r) => r.minutes_before).join(", ")
  );
  const [busy, setBusy] = useState(false);

  const save = useCallback(async () => {
    setBusy(true);
    try {
      const reminders = draft
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => {
          const n = parseInt(s, 10);
          if (Number.isNaN(n)) return null;
          return { minutes_before: n, mode: "tts" };
        })
        .filter(Boolean);
      await api.setEventReminders(event.id, reminders);
      setOpen(false);
      onSaved();
    } finally {
      setBusy(false);
    }
  }, [draft, event.id, onSaved]);

  if (!open) {
    return (
      <button className="reminder-edit-btn" onClick={() => setOpen(true)}>
        Edit reminders
      </button>
    );
  }
  return (
    <div className="reminder-editor">
      <input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="60, 240"
        title="Minutes before — comma separated"
      />
      <button onClick={save} disabled={busy}>
        {busy ? "…" : "Save"}
      </button>
      <button onClick={() => setOpen(false)}>Cancel</button>
    </div>
  );
}

function EventRow({ event, onChanged }) {
  const isPast = new Date(event.starts_at) < new Date();
  const [busy, setBusy] = useState(false);

  const speak = useCallback(async () => {
    setBusy(true);
    try {
      await api.testSayEvent(event.id);
    } finally {
      setBusy(false);
    }
  }, [event.id]);

  const toggleSnooze = useCallback(async () => {
    await api.updateEvent(event.id, { snoozed: !event.snoozed });
    onChanged();
  }, [event.id, event.snoozed, onChanged]);

  return (
    <div className={`event-row ${event.is_special ? "special" : "routine"} ${isPast ? "past" : ""}`}>
      <div className="event-time">
        {formatTimeOnly(event.starts_at)}
      </div>
      <div className="event-main">
        <div className="event-title">
          {event.is_special && <span className="event-star">★</span>}
          {event.title}
          {event.snoozed && <span className="muted"> (snoozed)</span>}
        </div>
        <div className="event-reminders">
          {event.reminders.length === 0 ? (
            <span className="muted">no reminders</span>
          ) : (
            event.reminders.map((r) => (
              <span
                key={r.id}
                className={`reminder-badge ${r.fired_at ? "fired" : ""}`}
                title={r.fired_at ? `fired ${new Date(r.fired_at * 1000).toLocaleString()}` : ""}
              >
                {describeReminder(r)}
              </span>
            ))
          )}
          <ReminderEditor event={event} onSaved={onChanged} />
        </div>
      </div>
      <div className="event-actions">
        <button onClick={speak} disabled={busy} title="Speak now">
          🔊
        </button>
        <button onClick={toggleSnooze} title={event.snoozed ? "Un-snooze" : "Snooze"}>
          {event.snoozed ? "↻" : "💤"}
        </button>
      </div>
    </div>
  );
}

function prettyDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "long", month: "short", day: "numeric",
  });
}

function DaySection({ day, isToday, load }) {
  const events = day.events || [];
  const upcoming = isToday
    ? events.filter((e) => new Date(e.starts_at) >= new Date())
    : events;
  const past = isToday
    ? events.filter((e) => new Date(e.starts_at) < new Date())
    : [];
  const label = isToday ? "TODAY" : "TOMORROW";
  return (
    <div className="events-day">
      <div className="events-day-head">
        <span className="events-day-label">{label}</span>
        <span className="muted" style={{ fontSize: 11 }}>
          {prettyDate(day.date)} · {events.length} event{events.length === 1 ? "" : "s"}
        </span>
      </div>
      {events.length === 0 && (
        <div className="muted" style={{ fontSize: 12 }}>
          Nothing scheduled.
        </div>
      )}
      {upcoming.length > 0 && upcoming.map((e) => (
        <EventRow key={e.id} event={e} onChanged={load} />
      ))}
      {past.length > 0 && (
        <details className="events-section" style={{ marginTop: 4 }}>
          <summary className="muted" style={{ fontSize: 12 }}>
            Earlier today ({past.length})
          </summary>
          {past.map((e) => (
            <EventRow key={e.id} event={e} onChanged={load} />
          ))}
        </details>
      )}
    </div>
  );
}

export default function EventsWidget() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [ingesting, setIngesting] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.eventsUpcoming(2);
      setData(r);
      setErr("");
    } catch (ex) {
      setErr(ex.message || "failed to load events");
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  const reingest = useCallback(async () => {
    setIngesting(true);
    try {
      await api.ingestHoa();
      await load();
    } finally {
      setIngesting(false);
    }
  }, [load]);

  if (err) return <div className="error">{err}</div>;
  if (!data) return <div className="muted">Loading…</div>;
  const days = data.days || [];
  const totalEvents = days.reduce((n, d) => n + (d.events || []).length, 0);

  return (
    <div className="events-widget">
      <div className="events-head">
        <div className="muted" style={{ fontSize: 12 }}>
          {totalEvents} event{totalEvents === 1 ? "" : "s"} across today + tomorrow
        </div>
        <button onClick={reingest} disabled={ingesting} title="Re-scan HOA PDF">
          {ingesting ? "…" : "Re-scan HOA"}
        </button>
      </div>
      {days.map((d, i) => (
        <DaySection key={d.date} day={d} isToday={i === 0} load={load} />
      ))}
    </div>
  );
}
