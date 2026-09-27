#!/usr/bin/env python3
"""Genera el atlas interactivo (HTML autocontenido) del grafo fusionado.

Lee el grafo que produce merge_roadmaps.py (output/merged_roadmaps.json) y la
copia de las fuentes (data/raw/) para recuperar la geometría original de cada
roadmap. Escribe output/atlas.html (documento completo, se abre sin servidor)
y, con --fragment, la misma página sin <html>/<head> para publicarla como
artefacto.

Uso:
    python scripts/build_atlas.py --repo-clone /tmp/developer-roadmap
    python scripts/build_atlas.py --fragment /ruta/atlas_fragment.html
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).resolve().parent / "atlas_template.html"
DATA_MARK = "/*__ATLAS_DATA__*/"

TYPE_CODES = {"title": 0, "topic": 1, "subtopic": 2, "label": 3, "paragraph": 4, "button": 5, "checklist-item": 6}
PRIMITIVE_CODES = {"section": 0, "vertical": 1, "horizontal": 2}
RULE_CODES = {"R1": 1, "R2": 2, "R3": 3, "R5": 5}
CHECKLIST_PAD = 10.0


def box(node: dict) -> tuple[float, float, float, float]:
    pos = node["position"]
    measured = node.get("measured") or {}
    width = measured.get("width") if measured.get("width") is not None else node.get("width") or 0
    height = measured.get("height") if measured.get("height") is not None else node.get("height") or 0
    return float(pos["x"]), float(pos["y"]), float(width), float(height)


def label_of(node: dict) -> str:
    label = (node.get("data") or {}).get("label")
    return label if isinstance(label, str) else ""


def content_files(clone: Path | None, slug: str) -> dict[str, str]:
    """id -> nombre de archivo de contenido existente en el clon del repo."""
    if clone is None:
        return {}
    folder = clone / "roadmaps" / slug / "content"
    if not folder.is_dir():
        return {}
    return {f.stem.rsplit("@", 1)[1]: f.name for f in folder.glob("*.md") if "@" in f.stem}


def build_data(graph: dict, raw_dir: Path, clone: Path | None) -> dict:
    manifest = json.loads((raw_dir / "manifest.json").read_text())
    entries = {e["slug"]: e for e in manifest["sources"]}
    slugs = graph["graph"]["roadmaps"]
    slug_index = {s: i for i, s in enumerate(slugs)}

    shared_of_member: dict[str, str] = {}
    graph_nodes = {n["id"]: n for n in graph["nodes"]}
    for key, node in graph_nodes.items():
        if node.get("group") == "shared":
            for member in node["members"]:
                shared_of_member[member["key"]] = key

    instances: list[list] = []
    instance_of: dict[str, int] = {}  # "slug:id" -> índice de instancia
    roadmaps, primitives, checklists = [], [], []
    for slug in slugs:
        doc = json.loads((raw_dir / f"{slug}.json").read_text())
        boxes = [box(n) for n in doc["nodes"]]
        min_x = min(b[0] for b in boxes)
        min_y = min(b[1] for b in boxes)
        max_x = max(b[0] + b[2] for b in boxes)
        max_y = max(b[1] + b[3] for b in boxes)
        files = content_files(clone, slug)
        r = slug_index[slug]
        for node, (x, y, w, h) in zip(doc["nodes"], boxes):
            ntype = node.get("type")
            lx, ly = round(x - min_x, 1), round(y - min_y, 1)
            if ntype in TYPE_CODES:
                key = f"{slug}:{node['id']}"
                extra = {}
                href = (node.get("data") or {}).get("href")
                if isinstance(href, str) and href.startswith("http"):
                    extra["href"] = href
                if node["id"] in files:
                    extra["file"] = files[node["id"]]
                instance_of[key] = len(instances)
                instances.append([r, node["id"], TYPE_CODES[ntype], label_of(node), lx, ly, round(w, 1), round(h, 1), extra])
            elif ntype == "checklist":
                items = (node.get("data") or {}).get("checklists") or []
                checklists.append([r, lx, ly, round(w, 1), round(h, 1)])
                # Los ítems no tienen posición propia: se reparten en filas dentro de su checklist,
                # como los dibuja roadmap.sh.
                row = (h - 2 * CHECKLIST_PAD) / max(1, len(items))
                for i, item in enumerate(items):
                    key = f"{slug}:{item['id']}"
                    instance_of[key] = len(instances)
                    instances.append(
                        [
                            r,
                            item["id"],
                            TYPE_CODES["checklist-item"],
                            item.get("label") or "",
                            round(lx + CHECKLIST_PAD, 1),
                            round(ly + CHECKLIST_PAD + i * row, 1),
                            round(w - 2 * CHECKLIST_PAD, 1),
                            round(row, 1),
                            {"checklist": node["id"]},
                        ]
                    )
            elif ntype in PRIMITIVE_CODES:
                style = ((node.get("data") or {}).get("style") or {}).get("strokeDasharray")
                dashed = 1 if style not in (None, "0", 0, "") else 0
                primitives.append([r, PRIMITIVE_CODES[ntype], lx, ly, round(w, 1), round(h, 1), dashed])
        e = entries[slug]
        title = e.get("title") or slug
        # La tarjeta de aws-best-practices se llama «AWS», igual que el roadmap aws: los de buenas
        # prácticas se rotulan como su slug («… Best Practices») para distinguirlos.
        if e.get("type") == "best-practice" and not title.endswith("Best Practices"):
            title += " Best Practices"
        roadmaps.append(
            {
                "slug": slug,
                "title": title,
                "type": e.get("type"),
                "updatedAt": (e.get("updatedAt") or "")[:10],
                "w": round(max_x - min_x, 1),
                "h": round(max_y - min_y, 1),
                "rawNodes": e.get("nodes"),
                "rawEdges": e.get("edges"),
            }
        )

    # Instancia -> nodo del grafo (compartido o propio).
    graph_key_index: dict[str, int] = {}
    for inst in instances:
        key = f"{slugs[inst[0]]}:{inst[1]}"
        gkey = shared_of_member.get(key, key)
        if gkey not in graph_nodes:
            raise SystemExit(f"la instancia {key} no existe en el grafo")
        inst.append(graph_key_index.setdefault(gkey, len(graph_key_index)))
    missing = set(graph_nodes) - set(graph_key_index)
    if missing:
        raise SystemExit(f"{len(missing)} nodos del grafo sin instancia, p. ej. {sorted(missing)[:3]}")

    def instance_in(gkey: str, slug: str) -> int:
        node = graph_nodes[gkey]
        if node.get("group") == "shared":
            member = next(m for m in node["members"] if m["roadmap"] == slug)
            return instance_of[member["key"]]
        return instance_of[gkey]

    edges = []
    for e in graph["edges"]:
        for prov in e["provenance"]:
            a = instance_in(e["source"], prov["roadmap"])
            b = instance_in(e["target"], prov["roadmap"])
            if e["key"] == "source":
                kind = 1 if prov.get("edgeStyle") == "dashed" else 0
                edges.append([a, b, kind, 0])
            else:
                edges.append([a, b, 2, RULE_CODES[prov["rule"]]])

    shared = []
    for key, node in graph_nodes.items():
        if node.get("group") == "shared":
            shared.append([node["label"], [instance_of[m["key"]] for m in node["members"]]])
    shared.sort(key=lambda s: (-len(s[1]), s[0].casefold()))

    counts = {
        "roadmaps": len(slugs),
        "graphNodes": len(graph_nodes),
        "instances": len(instances),
        "sourceEdges": sum(1 for e in graph["edges"] if e["key"] == "source"),
        "derivedEdges": sum(1 for e in graph["edges"] if e["key"] != "source"),
        "shared": len(shared),
        "sharedInstances": sum(len(s[1]) for s in shared),
        "rules": {rule: sum(1 for e in edges if e[2] == 2 and e[3] == code) for rule, code in RULE_CODES.items()},
    }
    degree = defaultdict(int)
    for e in graph["edges"]:
        degree[e["source"]] += 1
        degree[e["target"]] += 1
    counts["orphans"] = sum(1 for k, n in graph_nodes.items() if degree[k] == 0 and n["type"] != "title")
    return {
        "meta": {
            "snapshot": manifest.get("generated_at"),
            "repoHead": manifest.get("repository_head"),
            "source": "https://roadmap.sh/api/v1-official-roadmap/{slug}",
            "counts": counts,
        },
        "roadmaps": roadmaps,
        "nodes": instances,
        "edges": edges,
        "prims": primitives,
        "checklists": checklists,
        "shared": shared,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--graph", default=str(ROOT / "output" / "merged_roadmaps.json"))
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    parser.add_argument("--repo-clone", help="clon de nilbuild/developer-roadmap: enlaza solo archivos de contenido que existen")
    parser.add_argument("--out", default=str(ROOT / "output" / "atlas.html"))
    parser.add_argument("--fragment", help="escribe además la página sin <html>/<head> (para publicarla como artefacto)")
    args = parser.parse_args()

    graph = json.loads(Path(args.graph).read_text())
    data = build_data(graph, Path(args.raw_dir), Path(args.repo_clone) if args.repo_clone else None)
    # "<" solo aparece dentro de cadenas JSON: escaparlo impide que "</script>" o "<!--" de una etiqueta
    # (p. ej. «Avoid multiple inline JavaScript snippets <script>») altere el bloque para el parser HTML.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(DATA_MARK) != 1:
        raise SystemExit("la plantilla debe contener exactamente un marcador de datos")
    fragment = template.replace(DATA_MARK, payload)
    head, sep, body = fragment.partition("</style>")
    full = (
        '<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f"{head}{sep}\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )
    Path(args.out).write_text(full, encoding="utf-8")
    if args.fragment:
        Path(args.fragment).write_text(fragment, encoding="utf-8")
    c = data["meta"]["counts"]
    print(
        f"atlas: {c['instances']} instancias, {c['graphNodes']} nodos del grafo, {len(data['edges'])} aristas, "
        f"{c['shared']} compartidos, {len(data['prims'])} primitivas; {len(payload):,} bytes de datos"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
