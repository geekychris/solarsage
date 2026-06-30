import React from "react";

const MODE_LABEL = {
  occupied: "Occupied 🏠",
  vacant:   "Vacant 🌵",
  arriving: "Arriving ✈️",
};

const MODE_CLASS = {
  occupied: "mode-occupied",
  vacant:   "mode-vacant",
  arriving: "mode-arriving",
};

export default function PropertyModeWidget({ data }) {
  if (!data) return <div className="muted">Loading…</div>;
  const mode = data.mode || "occupied";
  return (
    <div className={`property-mode ${MODE_CLASS[mode]}`}>
      <div className="property-mode-big">{MODE_LABEL[mode] || mode}</div>
      {mode === "arriving" && data.arriving_on && (
        <div style={{ fontSize: 13 }}>
          Arriving <strong>{data.arriving_on}</strong>
          {data.days_until_arrival != null && (
            <span className="muted">
              {" · "}
              {data.days_until_arrival === 0 ? "today" :
                data.days_until_arrival === 1 ? "tomorrow" :
                  `in ${data.days_until_arrival} days`}
            </span>
          )}
        </div>
      )}
      {data.notes && (
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          {data.notes}
        </div>
      )}
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        Edit via Settings ⚙. Other widgets (pre-cool, excess planner) can
        read this state.
      </div>
    </div>
  );
}
