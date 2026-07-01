import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

export default function ShoppingListWidget({ data }) {
  const [newText, setNewText] = useState("");
  const [newCat, setNewCat] = useState("");
  const [busy, setBusy] = useState(false);

  const saveAll = useCallback(async (items) => {
    setBusy(true);
    try {
      const cur = await api.getWidgetConfig("shopping_list");
      await api.putWidgetConfig("shopping_list", { ...cur.config, items });
    } finally {
      setBusy(false);
    }
  }, []);

  if (!data) return <div className="muted">Loading…</div>;
  const items = data.items || [];

  const add = async () => {
    if (!newText.trim()) return;
    await saveAll([...items, {
      text: newText.trim(),
      category: newCat.trim() || "Other",
      checked: false, notes: "",
    }]);
    setNewText("");
  };
  const toggle = async (i) => {
    const next = items.slice();
    next[i] = { ...next[i], checked: !next[i].checked };
    await saveAll(next);
  };
  const remove = async (i) => {
    await saveAll(items.filter((_, idx) => idx !== i));
  };
  const clearChecked = async () => {
    await saveAll(items.filter((it) => !it.checked));
  };

  const checkedCount = items.filter((it) => it.checked).length;

  return (
    <div className="shopping">
      <div className="shopping-add">
        <input
          placeholder="Item"
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          disabled={busy}
        />
        <input
          placeholder="Category"
          value={newCat}
          onChange={(e) => setNewCat(e.target.value)}
          style={{ width: 90 }}
          disabled={busy}
        />
        <button onClick={add} disabled={busy || !newText.trim()}>+</button>
      </div>
      {items.length === 0 && (
        <div className="muted">Nothing on the list.</div>
      )}
      <div className="shopping-list">
        {items.map((it, i) => (
          <div key={i} className={`shopping-item ${it.checked ? "checked" : ""}`}>
            <input
              type="checkbox"
              checked={it.checked || false}
              onChange={() => toggle(i)}
              disabled={busy}
            />
            <span className="shopping-text">{it.text}</span>
            <span className="shopping-cat">{it.category}</span>
            <button onClick={() => remove(i)} disabled={busy} title="Remove">✕</button>
          </div>
        ))}
      </div>
      {checkedCount > 0 && (
        <button onClick={clearChecked} disabled={busy} className="shopping-clear">
          Clear {checkedCount} checked
        </button>
      )}
    </div>
  );
}
