import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

function ContactRow({ c, onEdit, onDelete }) {
  const [showNotes, setShowNotes] = useState(false);
  return (
    <div className={`contact-row loc-${c.location || "other"}`}>
      <div className="contact-main">
        <div className="contact-name">
          {c.name}
          <span className="contact-loc">{(c.location || "").toUpperCase()}</span>
        </div>
        {c.phone && (
          <a href={`tel:${c.phone}`} className="contact-detail">📞 {c.phone}</a>
        )}
        {c.email && (
          <a href={`mailto:${c.email}`} className="contact-detail">✉ {c.email}</a>
        )}
        {(c.tags || []).length > 0 && (
          <div className="contact-tags">
            {c.tags.map((t, i) => <span key={i} className="contact-tag">{t}</span>)}
          </div>
        )}
        {c.notes && (
          <>
            <button
              className="contact-notes-toggle"
              onClick={() => setShowNotes(!showNotes)}
            >
              {showNotes ? "hide" : "notes"}
            </button>
            {showNotes && (
              <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                {c.notes}
              </div>
            )}
          </>
        )}
      </div>
      <div className="contact-actions">
        <button onClick={onEdit} title="Edit">✎</button>
        <button onClick={onDelete} title="Delete">✕</button>
      </div>
    </div>
  );
}

function ContactForm({ initial, onSave, onCancel }) {
  const [c, setC] = useState(initial || {
    name: "", phone: "", email: "", location: "mx", tags: [], notes: "",
  });
  const [tagText, setTagText] = useState((c.tags || []).join(", "));
  return (
    <div className="contact-form">
      <input
        placeholder="Name"
        value={c.name}
        onChange={(e) => setC({ ...c, name: e.target.value })}
      />
      <input
        placeholder="Phone"
        value={c.phone || ""}
        onChange={(e) => setC({ ...c, phone: e.target.value })}
      />
      <input
        placeholder="Email"
        value={c.email || ""}
        onChange={(e) => setC({ ...c, email: e.target.value })}
      />
      <select
        value={c.location || "mx"}
        onChange={(e) => setC({ ...c, location: e.target.value })}
      >
        <option value="mx">MX</option>
        <option value="us">US</option>
        <option value="other">Other</option>
      </select>
      <input
        placeholder="Tags (comma-separated)"
        value={tagText}
        onChange={(e) => {
          setTagText(e.target.value);
          setC({ ...c, tags: e.target.value.split(/[,\s]+/).map((t) => t.trim()).filter(Boolean) });
        }}
      />
      <textarea
        placeholder="Notes"
        rows={2}
        value={c.notes || ""}
        onChange={(e) => setC({ ...c, notes: e.target.value })}
      />
      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
        <button onClick={onCancel}>Cancel</button>
        <button onClick={() => onSave(c)} className="primary">Save</button>
      </div>
    </div>
  );
}

export default function ContactsWidget({ data }) {
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null); // {index, contact} or {new:true}

  const saveAll = useCallback(async (contacts) => {
    setBusy(true);
    try {
      const cur = await api.getWidgetConfig("contacts");
      await api.putWidgetConfig("contacts", { ...cur.config, contacts });
    } finally {
      setBusy(false);
    }
  }, []);

  if (!data) return <div className="muted">Loading…</div>;
  const contacts = data.contacts || [];
  const q = filter.toLowerCase();
  const filtered = q
    ? contacts.filter((c) => JSON.stringify(c).toLowerCase().includes(q))
    : contacts;

  const handleSave = async (c) => {
    let next;
    if (editing.new) next = [...contacts, c];
    else {
      next = contacts.slice();
      next[editing.index] = c;
    }
    await saveAll(next);
    setEditing(null);
  };
  const handleDelete = async (i) => {
    if (!confirm("Delete this contact?")) return;
    await saveAll(contacts.filter((_, idx) => idx !== i));
  };

  return (
    <div className="contacts">
      <div className="contacts-toolbar">
        <input
          type="search"
          placeholder="Filter…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button
          onClick={() => setEditing({ new: true })}
          disabled={busy || editing !== null}
        >
          + Add
        </button>
      </div>
      {editing && (
        <ContactForm
          initial={editing.new ? null : contacts[editing.index]}
          onSave={handleSave}
          onCancel={() => setEditing(null)}
        />
      )}
      <div className="contacts-list">
        {filtered.length === 0 && (
          <div className="muted">No contacts match.</div>
        )}
        {filtered.map((c) => {
          const i = contacts.indexOf(c);
          return (
            <ContactRow
              key={i}
              c={c}
              onEdit={() => setEditing({ index: i })}
              onDelete={() => handleDelete(i)}
            />
          );
        })}
      </div>
    </div>
  );
}
