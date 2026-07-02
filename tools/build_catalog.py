"""Extract widget metadata for the docs catalog by reading widget class attrs."""
import ast, pathlib, re, textwrap

ROOT = pathlib.Path("/Users/chris/code/claude_world/eg4_monitoring/backend/app/widgets")
widgets = []
for f in sorted(ROOT.glob("*.py")):
    if f.name in ("__init__.py", "base.py", "store.py", "registry.py",
                  "refresher.py"):
        continue
    src = f.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        attrs = {}
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                tgt = stmt.targets[0]
                if isinstance(tgt, ast.Name):
                    try:
                        attrs[tgt.id] = ast.literal_eval(stmt.value)
                    except (ValueError, SyntaxError):
                        pass
        wid = attrs.get("id")
        if not wid:
            continue
        widgets.append({
            "id": wid,
            "name": attrs.get("name", wid),
            "description": " ".join(attrs.get("description", "").split()),
            "tab": attrs.get("default_tab", "Local"),
            "refresh_seconds": attrs.get("refresh_seconds", 3600),
            "file": f.name,
        })

widgets.sort(key=lambda w: (w["tab"], w["name"].lower()))
by_tab = {}
for w in widgets:
    by_tab.setdefault(w["tab"], []).append(w)

order = ["Today", "Safety", "Outdoor", "Travel", "Solar",
         "Community", "Lists", "Local"]
def keyfn(t):
    return (order.index(t) if t in order else 999, t)

lines = ["<!-- Generated: see tools/build_catalog.py -->",
         "",
         f"| id | name | tab | refresh | description |",
         f"| -- | ---- | --- | ------- | ----------- |"]
for tab in sorted(by_tab, key=keyfn):
    for w in by_tab[tab]:
        secs = w["refresh_seconds"]
        if secs >= 3600:
            refresh = f"{secs // 3600} h"
        elif secs >= 60:
            refresh = f"{secs // 60} m"
        else:
            refresh = f"{secs} s"
        # Truncate description
        d = w["description"]
        if len(d) > 100:
            d = d[:97] + "…"
        lines.append(f"| `{w['id']}` | {w['name']} | {tab} | {refresh} | {d} |")

print("\n".join(lines))
print(f"\n\nTotal: {len(widgets)} widgets across {len(by_tab)} tabs.")
