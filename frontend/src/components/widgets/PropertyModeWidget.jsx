import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

const MODES = [
  { key: "occupied", label: "Occupied 🏠" },
  { key: "vacant",   label: "Vacant 🌵" },
  { key: "arriving", label: "Arriving ✈️" },
];

const MODE_CLASS = {
  occupied: "mode-occupied",
  vacant:   "mode-vacant",
  arriving: "mode-arriving",
};

const MODE_LABEL = Object.fromEntries(MODES.map(({ key, label }) => [key, label]));

export default function PropertyModeWidget({ data, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftDate, setDraftDate] = useState("");
  const [draftNotes, setDraftNotes] = useState("");

  const save = useCallback(async (patch) => {
    setBusy(true);
    try {
      const cur = await api.getWidgetConfig("property_mode");
      await api.putWidgetConfig("property_mode", { ...cur.config, ...patch });
      if (onChanged) await onChanged();
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  if (!data) return <div className="muted">Loading…</div>;
  const mode = data.mode || "occupied";

  async function switchMode(next) {
    if (next === mode) return;
    const patch = { mode: next };
    // Clear the arriving date when leaving arriving mode so it doesn't
    // linger as a stale value the next time someone toggles back.
    if (mode === "arriving" && next !== "arriving") {
      patch.arriving_on = null;
    }
    await save(patch);
  }

  function openEditor() {
    setDraftDate(data.arriving_on || "");
    setDraftNotes(data.notes || "");
    setEditing(true);
  }

  async function saveEditor() {
    await save({
      arriving_on: draftDate || null,
      notes: draftNotes,
    });
    setEditing(false);
  }

  return (
    <div className={`property-mode ${MODE_CLASS[mode]}`}>
      <div className="property-mode-big">{MODE_LABEL[mode] || mode}</div>

      <div className="property-mode-toggle">
        {MODES.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className={mode === key ? "active" : ""}
            disabled={busy}
            onClick={() => switchMode(key)}
            title={mode === key ? "Currently selected" : `Switch to ${label}`}
          >
            {label}
          </button>
        ))}
      </div>

      {!editing && (
        <>
          {mode === "arriving" && data.arriving_on && (
            <div style={{ fontSize: 13, marginTop: 6 }}>
              Arriving <strong>{data.arriving_on}</strong>
              {data.days_until_arrival != null && (
                <span className="muted">
                  {" · "}
                  {data.days_until_arrival === 0 ? "today" :
                    data.days_until_arrival === 1 ? "tomorrow" :
                      data.days_until_arrival < 0 ?
                        `${-data.days_until_arrival} days ago` :
                        `in ${data.days_until_arrival} days`}
                </span>
              )}
            </div>
          )}
          {mode === "arriving" && !data.arriving_on && (
            <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              No arrival date set — click <em>Edit details</em>.
            </div>
          )}
          {data.notes && (
            <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
              {data.notes}
            </div>
          )}
          <div style={{ marginTop: 6 }}>
            <button
              type="button"
              className="property-mode-edit"
              disabled={busy}
              onClick={openEditor}
            >Edit details</button>
          </div>
        </>
      )}

      {editing && (
        <div className="property-mode-editor">
          {mode === "arriving" && (
            <label>
              Arrival date{" "}
              <input
                type="date"
                value={draftDate}
                onChange={(e) => setDraftDate(e.target.value)}
                disabled={busy}
              />
            </label>
          )}
          <label>
            Notes{" "}
            <input
              type="text"
              value={draftNotes}
              onChange={(e) => setDraftNotes(e.target.value)}
              placeholder="Optional — e.g. Kyle arriving Friday"
              disabled={busy}
            />
          </label>
          <div className="property-mode-editor-actions">
            <button
              type="button"
              onClick={() => setEditing(false)}
              disabled={busy}
            >Cancel</button>
            <button
              type="button"
              className="primary"
              onClick={saveEditor}
              disabled={busy}
            >Save</button>
          </div>
        </div>
      )}

      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        Other widgets (pre-cool, excess planner, reminders) read this
        state and adjust their behaviour.
      </div>
    </div>
  );
}
