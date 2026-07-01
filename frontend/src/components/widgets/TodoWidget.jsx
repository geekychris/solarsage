import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

function priorityLabel(p) {
  return ({ 1: "1 · urgent", 2: "2 · high", 3: "3 · med",
            4: "4 · low", 5: "5 · someday" })[p] || "";
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function TodoItem({ item, onChange, onDelete, disabled }) {
  const isPast = item.due && item.due < todayIso() && !item.done;
  return (
    <div className={`todo-item ${item.done ? "done" : ""} ${isPast ? "overdue" : ""}`}>
      <input
        type="checkbox"
        checked={!!item.done}
        onChange={(e) => onChange({ ...item, done: e.target.checked })}
        disabled={disabled}
      />
      <div className="todo-body">
        <div className="todo-text">{item.text}</div>
        <div className="todo-meta">
          {item.priority && (
            <span className={`todo-pri pri-${item.priority}`}>
              P{item.priority}
            </span>
          )}
          {item.due && <span className="todo-due">📅 {item.due}</span>}
          {item.notes && <span className="muted">· {item.notes}</span>}
        </div>
      </div>
      <button onClick={onDelete} disabled={disabled} title="Remove">✕</button>
    </div>
  );
}

export default function TodoWidget({ data, onChanged }) {
  const [newText, setNewText] = useState("");
  const [newPri, setNewPri] = useState(3);
  const [newDue, setNewDue] = useState("");
  const [busy, setBusy] = useState(false);

  const saveAll = useCallback(async (items) => {
    setBusy(true);
    try {
      const cur = await api.getWidgetConfig("todo");
      await api.putWidgetConfig("todo", { ...cur.config, items });
      if (onChanged) await onChanged();
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  if (!data) return <div className="muted">Loading…</div>;
  const items = data.items || [];
  const stats = data.stats || {};

  const add = async () => {
    if (!newText.trim()) return;
    await saveAll([...items, {
      text: newText.trim(),
      priority: newPri || 3,
      due: newDue || null,
      done: false,
      notes: "",
    }]);
    setNewText(""); setNewDue("");
  };
  const change = async (i, next) => {
    const arr = items.slice();
    arr[i] = next;
    await saveAll(arr);
  };
  const remove = async (i) => {
    await saveAll(items.filter((_, idx) => idx !== i));
  };

  // Sort: open first (by priority then due), done at bottom
  const sorted = items.map((it, i) => ({ ...it, _i: i })).sort((a, b) => {
    if (a.done !== b.done) return a.done ? 1 : -1;
    const pa = a.priority || 3, pb = b.priority || 3;
    if (pa !== pb) return pa - pb;
    return (a.due || "9999") < (b.due || "9999") ? -1 : 1;
  });

  return (
    <div className="todo">
      <div className="todo-stats">
        <span>{stats.open || 0} open</span>
        {stats.overdue > 0 && (
          <span className="todo-overdue-badge">
            {stats.overdue} overdue
          </span>
        )}
        <span className="muted">· {stats.total || 0} total</span>
      </div>
      <div className="todo-add">
        <input
          placeholder="New task"
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          disabled={busy}
        />
        <select value={newPri} onChange={(e) => setNewPri(parseInt(e.target.value, 10))}>
          {[1,2,3,4,5].map((p) => <option key={p} value={p}>P{p}</option>)}
        </select>
        <input
          type="date"
          value={newDue}
          onChange={(e) => setNewDue(e.target.value)}
          disabled={busy}
        />
        <button onClick={add} disabled={busy || !newText.trim()}>+</button>
      </div>
      <div className="todo-list">
        {sorted.map((it) => (
          <TodoItem
            key={it._i}
            item={it}
            onChange={(next) => change(it._i, next)}
            onDelete={() => remove(it._i)}
            disabled={busy}
          />
        ))}
      </div>
    </div>
  );
}
