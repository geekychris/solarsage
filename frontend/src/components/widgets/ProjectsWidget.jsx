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

// ----- New project form (inline expander) -----

function NewProjectForm({ existingNames, onCreate, onCancel, disabled }) {
  const [name, setName] = useState("");
  const [assignee, setAssignee] = useState("");
  const [due, setDue] = useState("");
  const [description, setDescription] = useState("");

  const collide = existingNames.has(name.trim());
  const canSubmit = name.trim().length > 0 && !collide && !disabled;

  return (
    <div className="proj-new">
      <div className="proj-new-row">
        <input
          placeholder="Project name (e.g. Rear patio deck)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
        />
        <input
          placeholder="Assignee (default 'who')"
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
        />
        <input
          type="date"
          value={due}
          onChange={(e) => setDue(e.target.value)}
          title="Target date (optional)"
        />
      </div>
      <textarea
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
      />
      {collide && (
        <div className="proj-warn">
          A project named "{name.trim()}" already exists.
        </div>
      )}
      <div className="proj-new-actions">
        <button onClick={onCancel} disabled={disabled}>Cancel</button>
        <button
          className="primary"
          disabled={!canSubmit}
          onClick={() => onCreate({
            name: name.trim(),
            assignee: assignee.trim(),
            due: due || null,
            description: description.trim(),
            done: false,
            notes: "",
          })}
        >
          Create project
        </button>
      </div>
    </div>
  );
}

// ----- Inline "add task to this project" row -----

function AddTaskRow({ project, onAdd, disabled }) {
  const [text, setText] = useState("");
  const [cost, setCost] = useState("");
  const [assignee, setAssignee] = useState("");
  const [due, setDue] = useState("");

  const submit = () => {
    if (!text.trim()) return;
    onAdd({
      project: project.name,
      text: text.trim(),
      cost: cost ? Number(cost) : null,
      assignee: assignee.trim(),
      due: due || null,
      done: false,
      notes: "",
    });
    setText(""); setCost(""); setDue("");
    // keep assignee sticky in case multiple tasks share one
  };

  return (
    <div className="proj-add-task">
      <input
        className="proj-add-text"
        placeholder="Task"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        disabled={disabled}
      />
      <input
        className="proj-add-cost"
        type="number" step="0.01"
        placeholder="Cost"
        value={cost}
        onChange={(e) => setCost(e.target.value)}
        disabled={disabled}
      />
      <input
        className="proj-add-assignee"
        placeholder={project.assignee ? `Who (default: ${project.assignee})` : "Who"}
        value={assignee}
        onChange={(e) => setAssignee(e.target.value)}
        disabled={disabled}
      />
      <input
        className="proj-add-due"
        type="date"
        value={due}
        onChange={(e) => setDue(e.target.value)}
        title="Due (defaults to project target)"
        disabled={disabled}
      />
      <button onClick={submit} disabled={disabled || !text.trim()}>+ Task</button>
    </div>
  );
}

// ----- One row of a task -----

function ItemRow({ item, onChange, onDelete, disabled }) {
  const dueForCheck = item.effective_due;
  const isPast = dueForCheck && dueForCheck < todayIso() && !item.done;
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
          {item.effective_assignee && (
            <span className="proj-assignee">
              👤 {item.effective_assignee}
              {item.inherited_assignee && (
                <span className="muted"> (project)</span>
              )}
            </span>
          )}
          {item.effective_due && (
            <span className="proj-due">
              📅 {item.effective_due}
              {item.inherited_due && (
                <span className="muted"> (project)</span>
              )}
            </span>
          )}
          {item.notes && <span className="muted">· {item.notes}</span>}
        </div>
      </div>
      <button onClick={onDelete} disabled={disabled} title="Remove">✕</button>
    </div>
  );
}

// ----- One project section (header + tasks + inline add) -----

function ProjectGroup({
  project, taskIndexes, allItems, onItemChange, onItemDelete,
  onAddTask, onEditProject, onDeleteProject, disabled,
}) {
  const [collapsed, setCollapsed] = useState(project.all_done);
  const [showAdd, setShowAdd] = useState(project.item_count === 0);
  return (
    <div className={`proj-group ${project.all_done ? "all-done" : ""}`}>
      <div className="proj-group-head">
        <span
          className="proj-group-toggle"
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? "▸" : "▾"}
        </span>
        <span
          className="proj-group-name"
          onClick={() => setCollapsed((c) => !c)}
        >
          {project.name}
        </span>
        <span className="proj-group-progress">
          {project.done_count}/{project.item_count}
        </span>
        {project.total_cost > 0 && (
          <span className="proj-group-cost" title="done / total committed">
            {fmtCost(project.done_cost)} / {fmtCost(project.total_cost)}
          </span>
        )}
        {project.assignee && (
          <span className="proj-group-assignee">👤 {project.assignee}</span>
        )}
        {project.due && (
          <span className="proj-group-due">🎯 {project.due}</span>
        )}
        {project.overdue_count > 0 && (
          <span className="proj-overdue-badge">{project.overdue_count} overdue</span>
        )}
        <span className="proj-group-actions">
          <button
            className="proj-group-btn"
            onClick={() => onEditProject(project)}
            disabled={disabled}
            title="Edit project"
          >✎</button>
          <button
            className="proj-group-btn danger"
            onClick={() => {
              if (window.confirm(
                `Delete project "${project.name}" and its ${project.item_count} task(s)?`
              )) onDeleteProject(project);
            }}
            disabled={disabled}
            title="Delete project"
          >✕</button>
        </span>
      </div>
      {project.description && !collapsed && (
        <div className="proj-group-desc">{project.description}</div>
      )}
      {!collapsed && (
        <>
          <div className="proj-item-list">
            {taskIndexes.map((i) => (
              <ItemRow
                key={i}
                item={allItems[i]}
                onChange={(next) => onItemChange(i, next)}
                onDelete={() => onItemDelete(i)}
                disabled={disabled}
              />
            ))}
            {project.item_count === 0 && !showAdd && (
              <div className="empty">No tasks yet.</div>
            )}
          </div>
          {showAdd ? (
            <AddTaskRow
              project={project}
              onAdd={onAddTask}
              disabled={disabled}
            />
          ) : (
            <div className="proj-add-toggle">
              <button
                onClick={() => setShowAdd(true)}
                disabled={disabled}
              >+ Add task</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ----- Edit project (inline modal-ish) -----

function EditProjectForm({ project, onSave, onCancel, disabled }) {
  const [assignee, setAssignee] = useState(project.assignee || "");
  const [due, setDue] = useState(project.due || "");
  const [description, setDescription] = useState(project.description || "");
  const [done, setDone] = useState(!!project.done);
  return (
    <div className="proj-edit">
      <div className="proj-edit-title">Edit {project.name}</div>
      <div className="proj-new-row">
        <input
          placeholder="Assignee"
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
        />
        <input
          type="date"
          value={due}
          onChange={(e) => setDue(e.target.value)}
        />
        <label className="proj-edit-done">
          <input
            type="checkbox"
            checked={done}
            onChange={(e) => setDone(e.target.checked)}
          />
          done
        </label>
      </div>
      <textarea
        rows={2}
        placeholder="Description"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="proj-new-actions">
        <button onClick={onCancel} disabled={disabled}>Cancel</button>
        <button
          className="primary"
          disabled={disabled}
          onClick={() => onSave({
            ...project,
            assignee: assignee.trim(),
            due: due || null,
            description: description.trim(),
            done,
          })}
        >Save</button>
      </div>
    </div>
  );
}

// ----- Main widget -----

export default function ProjectsWidget({ data, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const [editingProject, setEditingProject] = useState(null); // name or null

  const saveConfig = useCallback(async (mutator) => {
    setBusy(true);
    try {
      const cur = await api.getWidgetConfig("projects");
      const next = mutator(cur.config || {});
      await api.putWidgetConfig("projects", { ...cur.config, ...next });
      if (onChanged) await onChanged();
    } finally {
      setBusy(false);
    }
  }, [onChanged]);

  if (!data) return <div className="muted">Loading…</div>;
  const items = data.items || [];
  const projects = data.projects || [];
  const stats = data.stats || {};
  const existingNames = new Set(projects.map((p) => p.name));

  const createProject = async (proj) => {
    await saveConfig((cfg) => ({
      projects: [...(cfg.projects || []), proj],
      items: cfg.items || [],
    }));
    setCreatingProject(false);
  };
  const editProject = async (updated) => {
    await saveConfig((cfg) => ({
      projects: (cfg.projects || []).map(
        (p) => (p.name === updated.name ? updated : p),
      ),
      items: cfg.items || [],
    }));
    setEditingProject(null);
  };
  const deleteProject = async (proj) => {
    await saveConfig((cfg) => ({
      projects: (cfg.projects || []).filter((p) => p.name !== proj.name),
      items: (cfg.items || []).filter((it) => it.project !== proj.name),
    }));
  };
  const addTask = async (task) => {
    await saveConfig((cfg) => ({
      projects: cfg.projects || [],
      items: [...(cfg.items || []), task],
    }));
  };
  const changeItem = async (i, next) => {
    await saveConfig((cfg) => {
      const arr = (cfg.items || []).slice();
      arr[i] = next;
      return { projects: cfg.projects || [], items: arr };
    });
  };
  const removeItem = async (i) => {
    await saveConfig((cfg) => ({
      projects: cfg.projects || [],
      items: (cfg.items || []).filter((_, idx) => idx !== i),
    }));
  };

  // Map project name → indexes into the master items[] so ItemRow's
  // onChange/onDelete callbacks can address the correct row.
  const indexesByProject = new Map();
  items.forEach((it, i) => {
    if (!indexesByProject.has(it.project)) {
      indexesByProject.set(it.project, []);
    }
    indexesByProject.get(it.project).push(i);
  });

  return (
    <div className="proj">
      <div className="proj-stats">
        <span>
          {stats.open_project_count || 0} open of {stats.project_count || 0}{" "}
          project{stats.project_count === 1 ? "" : "s"}
        </span>
        <span className="muted">
          · {stats.open_count || 0} open / {stats.item_count || 0} tasks
        </span>
        {stats.total_cost > 0 && (
          <span className="muted">
            · {fmtCost(stats.done_cost)} of {fmtCost(stats.total_cost)} committed
          </span>
        )}
        {stats.overdue_count > 0 && (
          <span className="proj-overdue-badge">{stats.overdue_count} overdue</span>
        )}
        <div style={{ flex: 1 }} />
        {!creatingProject && (
          <button
            className="proj-new-btn"
            onClick={() => setCreatingProject(true)}
            disabled={busy}
          >+ New project</button>
        )}
      </div>

      {creatingProject && (
        <NewProjectForm
          existingNames={existingNames}
          onCreate={createProject}
          onCancel={() => setCreatingProject(false)}
          disabled={busy}
        />
      )}

      <div className="proj-list">
        {projects.map((p) => (
          editingProject === p.name ? (
            <EditProjectForm
              key={p.name}
              project={p}
              onSave={editProject}
              onCancel={() => setEditingProject(null)}
              disabled={busy}
            />
          ) : (
            <ProjectGroup
              key={p.name}
              project={p}
              taskIndexes={indexesByProject.get(p.name) || []}
              allItems={items}
              onItemChange={changeItem}
              onItemDelete={removeItem}
              onAddTask={addTask}
              onEditProject={(pp) => setEditingProject(pp.name)}
              onDeleteProject={deleteProject}
              disabled={busy}
            />
          )
        ))}
        {projects.length === 0 && !creatingProject && (
          <div className="empty">
            No projects yet. Click <strong>+ New project</strong> to start.
          </div>
        )}
      </div>
    </div>
  );
}
