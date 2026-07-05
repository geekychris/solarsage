import React, { useState, useCallback } from "react";
import { api } from "../../api.js";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function fmtCost(n) {
  if (n == null || n === "" || Number.isNaN(Number(n))) return "";
  return "$" + Number(n).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
}

function ItemRow({ item, onChange, onDelete, disabled }) {
  const isPast = item.due && item.due < todayIso() && !item.done;
  return (
    <div className={`proj-item ${item.done ? "done" : ""} ${isPast ? "overdue" : ""}`}>
      <input
        type="checkbox"
        checked={!!item.done}
        onChange={(e) => onChange({ ...item, done: e.target.checked })}
        disabled={disabled}
      />
      <div className="proj-item-body">
        <div className="proj-item-text">{item.text}</div>
        <div className="proj-item-meta">
          {item.cost != null && item.cost !== "" && (
            <span className="proj-cost">{fmtCost(item.cost)}</span>
          )}
          {item.assignee && <span className="proj-assignee">👤 {item.assignee}</span>}
          {item.due && <span className="proj-due">📅 {item.due}</span>}
          {item.notes && <span className="muted">· {item.notes}</span>}
        </div>
      </div>
      <button onClick={onDelete} disabled={disabled} title="Remove">✕</button>
    </div>
  );
}

function ProjectGroup({ project, items, onChange, onDelete, disabled }) {
  const [collapsed, setCollapsed] = useState(project.all_done);
  return (
    <div className={`proj-group ${project.all_done ? "all-done" : ""}`}>
      <div
        className="proj-group-head"
        onClick={() => setCollapsed((c) => !c)}
      >
        <span className="proj-group-toggle">{collapsed ? "▸" : "▾"}</span>
        <span className="proj-group-name">{project.project}</span>
        <span className="proj-group-progress">
          {project.done_count}/{project.item_count}
        </span>
        {project.total_cost > 0 && (
          <span className="proj-group-cost" title="done / total committed">
            {fmtCost(project.done_cost)} / {fmtCost(project.total_cost)}
          </span>
        )}
        {project.next_due && (
          <span className="proj-group-due">📅 {project.next_due}</span>
        )}
        {project.overdue_count > 0 && (
          <span className="proj-overdue-badge">{project.overdue_count} overdue</span>
        )}
        {project.assignees.length > 0 && (
          <span className="muted proj-group-assignees">
            👤 {project.assignees.join(", ")}
          </span>
        )}
      </div>
      {!collapsed && (
        <div className="proj-item-list">
          {items.map((it) => (
            <ItemRow
              key={it._i}
              item={it}
              onChange={(next) => onChange(it._i, next)}
              onDelete={() => onDelete(it._i)}
              disabled={disabled}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ProjectsWidget({ data, onChanged }) {
  const [newProject, setNewProject] = useState("");
  const [newText, setNewText] = useState("");
  const [newCost, setNewCost] = useState("");
  const [newAssignee, setNewAssignee] = useState("");
  const [newDue, setNewDue] = useState("");
  const [busy, setBusy] = useState(false);

  const saveAll = useCallback(async (items) => {
    setBusy(true);
    try {
      const cur = await api.getWidgetConfig("projects");
      await api.putWidgetConfig("projects", { ...cur.config, items });
      if (onChanged) await onChanged();
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  if (!data) return <div className="muted">Loading…</div>;
  const items = data.items || [];
  const projects = data.projects || [];
  const stats = data.stats || {};

  const add = async () => {
    const proj = newProject.trim();
    const text = newText.trim();
    if (!proj || !text) return;
    const item = {
      project: proj,
      text: text,
      cost: newCost ? Number(newCost) : null,
      assignee: newAssignee.trim(),
      due: newDue || null,
      done: false,
      notes: "",
    };
    await saveAll([...items, item]);
    setNewText(""); setNewCost(""); setNewDue("");
    // keep newProject + newAssignee so multiple items in a row are easy
  };
  const change = async (i, next) => {
    const arr = items.slice();
    arr[i] = next;
    await saveAll(arr);
  };
  const remove = async (i) => {
    await saveAll(items.filter((_, idx) => idx !== i));
  };

  // Pre-index items with their original array position so the group
  // components can call change/delete against the master list.
  const indexed = items.map((it, i) => ({ ...it, _i: i }));
  const byProject = new Map();
  for (const it of indexed) {
    if (!byProject.has(it.project)) byProject.set(it.project, []);
    byProject.get(it.project).push(it);
  }

  // Suggest project names for the new-item picker
  const projectNames = projects.map((p) => p.project);

  return (
    <div className="proj">
      <div className="proj-stats">
        <span>{stats.project_count || 0} project{stats.project_count === 1 ? "" : "s"}</span>
        <span className="muted">· {stats.open_count || 0} open / {stats.item_count || 0}</span>
        {stats.total_cost > 0 && (
          <span className="muted">
            · {fmtCost(stats.done_cost)} of {fmtCost(stats.total_cost)} committed
          </span>
        )}
        {stats.overdue_count > 0 && (
          <span className="proj-overdue-badge">{stats.overdue_count} overdue</span>
        )}
      </div>

      <div className="proj-add">
        <input
          className="proj-add-project"
          placeholder="Project (e.g. Rear patio deck)"
          value={newProject}
          onChange={(e) => setNewProject(e.target.value)}
          list="proj-project-suggestions"
          disabled={busy}
        />
        <datalist id="proj-project-suggestions">
          {projectNames.map((p) => <option key={p} value={p} />)}
        </datalist>
        <input
          className="proj-add-text"
          placeholder="Task"
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          disabled={busy}
        />
        <input
          className="proj-add-cost"
          type="number"
          step="0.01"
          placeholder="Cost"
          value={newCost}
          onChange={(e) => setNewCost(e.target.value)}
          disabled={busy}
        />
        <input
          className="proj-add-assignee"
          placeholder="Who"
          value={newAssignee}
          onChange={(e) => setNewAssignee(e.target.value)}
          disabled={busy}
        />
        <input
          className="proj-add-due"
          type="date"
          value={newDue}
          onChange={(e) => setNewDue(e.target.value)}
          disabled={busy}
        />
        <button onClick={add} disabled={busy || !newProject.trim() || !newText.trim()}>
          +
        </button>
      </div>

      <div className="proj-list">
        {projects.map((p) => (
          <ProjectGroup
            key={p.project}
            project={p}
            items={byProject.get(p.project) || []}
            onChange={change}
            onDelete={remove}
            disabled={busy}
          />
        ))}
        {projects.length === 0 && (
          <div className="empty">
            No projects yet. Add one above — the project name groups items.
          </div>
        )}
      </div>
    </div>
  );
}
