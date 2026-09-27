#!/usr/bin/env python3
"""Fusiona 18 roadmaps de roadmap.sh en un único grafo y genera el diagrama.

Fuente de datos: https://roadmap.sh/api/v1-official-roadmap/{slug}. Es el
endpoint que consumen los scripts de sincronización de
nilbuild/developer-roadmap (scripts/sync-content-to-repo.ts y
scripts/sync-repo-to-database.ts); las rutas antiguas
src/data/roadmaps/{slug}/{slug}.json ya no existen en ese repositorio.

Etapas: copia local de las fuentes -> validación -> filtrado de tipos ->
inferencia geométrica (capa aparte) -> fusión por etiqueta exacta solo entre
roadmaps -> exportación (node-link JSON, GraphML, Mermaid, DOT, CSV) ->
validaciones -> INFORME.md.

Uso:
    python scripts/merge_roadmaps.py --refresh      # descarga y genera todo
    python scripts/merge_roadmaps.py                # reutiliza data/raw
    python scripts/merge_roadmaps.py --render --mmdc /ruta/a/mmdc \\
        --puppeteer-config puppeteer.json --repo-clone /tmp/developer-roadmap
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import re
import shlex
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parent.parent

# Orden en que el usuario listó los roadmaps; se usa en todas las salidas.
SLUGS = [
    "linux",
    "network-engineer",
    "software-architect",
    "devops",
    "docker",
    "java",
    "spring-boot",
    "api-design",
    "aws",
    "shell-bash",
    "claude-code",
    "aws-best-practices",
    "frontend-performance-best-practices",
    "api-security-best-practices",
    "backend-performance-best-practices",
    "seo",
    "cyber-security",
    "software-design-architecture",
]

API_URL = "https://roadmap.sh/api/v1-official-roadmap/{slug}"
PAGE_URL = "https://roadmap.sh/{slug}"
REPO_URL = "https://github.com/nilbuild/developer-roadmap.git"
REPO_WEB = "https://github.com/nilbuild/developer-roadmap"
RAW_REPO = "https://raw.githubusercontent.com/nilbuild/developer-roadmap/master"
LEGACY_URLS = {
    "legacy_md": RAW_REPO + "/src/data/roadmaps/{slug}/{slug}.md",
    "legacy_json": RAW_REPO + "/src/data/roadmaps/{slug}/{slug}.json",
    "legacy_content": RAW_REPO + "/public/roadmap-content/{slug}.json",
}
# Base de la antigua Opción B (topicId -> contenido): hoy responde 200 con un cuerpo "not_found".
SITE_CONTENT_URL = "https://roadmap.sh/roadmap-content/{slug}.json"
USER_AGENT = "Mozilla/5.0 (compatible; roadmap-merge/1.0)"

# Alcance de nodos confirmado por el usuario.
KEPT_TYPES = ("title", "topic", "subtopic", "label", "paragraph", "button")
CHECKLIST_TYPE = "checklist"
CHECKLIST_ITEM_TYPE = "checklist-item"
EXCLUDED_TYPES = ("vertical", "horizontal", "section", "linksgroup", "legend")
KNOWN_TYPES = set(KEPT_TYPES) | {CHECKLIST_TYPE} | set(EXCLUDED_TYPES)

# Regla de fusión «A exacta, solo entre roadmaps».
MERGEABLE_TYPES = ("topic", "subtopic")

# Inferencia geométrica.
LINE_TYPES = ("vertical", "horizontal")
STACK_GAP_PX = 4.0
LINE_GAP_PX = 6.0
SECTION_TOLERANCE_PX = 2.0
GEO_RULES = ("R1", "R3", "R2", "R5")  # orden de precedencia
RULE_TEXT = {
    "R1": "pila: el subtopic forma una cadena de subtopics adyacentes (hueco ≤ 4 px) "
    "con un único padre explícito",
    "R3": "sección enlazada: la sección mínima que contiene la pila tiene una arista "
    "explícita **discontinua** con exactamente un topic",
    "R2": "encabezado de sección: la sección mínima que contiene la pila contiene "
    "exactamente un label y ningún topic",
    "R5": "línea conectora: una línea vertical u horizontal toca la pila (≤ 6 px) "
    "y exactamente un topic",
}

MERMAID_DEFAULT_MAX_EDGES = 500
MERMAID_DEFAULT_MAX_TEXT = 50_000
LARGE_GRAPH_NODES = 2000

LAYER_SOURCE = "source"
LAYER_DERIVED = "derived_geometric"

# Revisión manual de las aristas inferidas: solo se cita en el informe si la
# huella de la ejecución coincide con la del conjunto revisado.
REVIEWED_DERIVED_FINGERPRINT = "fad90138d763cfeb1ecd435a22d9fe52386edd8e15cb2c91d759b8e31a7f8c97"
REVIEW_NOTE = (
    "**Revisión manual** (hecha por el asistente el 2026-09-27 sobre esta misma huella `fad90138d763`): se revisaron "
    "todos los grupos padre → hijos inferidos, comparando la etiqueta del padre con las de sus hijos. Resultado: "
    "R1 66/66 grupos coherentes, R2 38/38, R3 5/5 y R5 28/28. Antes de restringir R3 a aristas discontinuas, 4 de sus "
    "9 grupos eran incorrectos, y los 4 usaban una arista sólida. Por ejemplo, en linux asignaba «Users and Groups» y "
    "«Managing Permissions» a «Service Management (systemd)», cuando la sección está pegada a «User Management». "
    "Es un juicio cualitativo sobre las etiquetas, no una validación formal."
)

TYPE_STYLE = {
    # tipo: (relleno, borde, texto)
    "title": ("#ffffff", "#ffffff", "#000000"),
    "topic": ("#fdff00", "#000000", "#000000"),
    "subtopic": ("#ffe599", "#000000", "#000000"),
    "label": ("#ffffff", "#ffffff", "#000000"),
    "paragraph": ("#ffffff", "#9e9e9e", "#000000"),
    "button": ("#4136d6", "#4136d6", "#ffffff"),
    CHECKLIST_ITEM_TYPE: ("#e8f5e9", "#43a047", "#000000"),
    "shared": ("#c9e7ff", "#1565c0", "#000000"),
}
SOURCE_EDGE_COLOR = "#2b78e4"
DERIVED_EDGE_COLOR = "#8a8a8a"


class StopError(Exception):
    """Condición que obliga a detenerse sin generar diagramas."""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def http_get(url: str, timeout: int = 60, attempts: int = 3) -> tuple[int | None, bytes]:
    """GET con reintentos solo ante errores de red; devuelve (status, cuerpo)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read() if err.fp else b""
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            last_error = err
            time.sleep(2 ** (attempt + 1))
    print(f"  ! red: {url}: {last_error}", file=sys.stderr)
    return None, b""


def git_ls_remote_head() -> str | None:
    try:
        out = subprocess.run(
            ["git", "ls-remote", REPO_URL, "HEAD"], capture_output=True, text=True, timeout=120, check=True
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    return out.split()[0] if out.strip() else None


def label_of(node: dict) -> str:
    label = (node.get("data") or {}).get("label")
    return label if isinstance(label, str) else ""


def merge_key(label: str) -> str:
    """Clave de la regla A exacta: NFKC + casefold + espacios colapsados; conserva puntuación."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", label).casefold()).strip()


def node_box(node: dict) -> tuple[float, float, float, float] | None:
    pos = node.get("position") or {}
    measured = node.get("measured") or {}
    width = measured.get("width") if measured.get("width") is not None else node.get("width")
    height = measured.get("height") if measured.get("height") is not None else node.get("height")
    if not all(isinstance(v, (int, float)) for v in (pos.get("x"), pos.get("y"), width, height)):
        return None
    x, y = float(pos["x"]), float(pos["y"])
    return (x, y, x + float(width), y + float(height))


def box_gap(a, b) -> float:
    dx = max(0.0, b[0] - a[2], a[0] - b[2])
    dy = max(0.0, b[1] - a[3], a[1] - b[3])
    return math.hypot(dx, dy)


def box_inside(inner, outer, tol: float = SECTION_TOLERANCE_PX) -> bool:
    return (
        inner[0] >= outer[0] - tol
        and inner[1] >= outer[1] - tol
        and inner[2] <= outer[2] + tol
        and inner[3] <= outer[3] + tol
    )


def box_area(b) -> float:
    return (b[2] - b[0]) * (b[3] - b[1])


def pct(num: int, den: int) -> str:
    return f"{100 * num / den:.1f}".replace(".", ",") + " %" if den else "n/d"


def md(value) -> str:
    """Celda de tabla Markdown: escapa la barra vertical."""
    return str(value).replace("|", "\\|")


def secs(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " s"


def fmt(n: int | float) -> str:
    """Número con separador de miles español (punto)."""
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else str(n)


# ---------------------------------------------------------------------------
# 1. Fuentes: copia local, manifiesto y validación
# ---------------------------------------------------------------------------


def refresh_snapshot(raw_dir: Path) -> dict:
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": utc_now(),
        "api_url_template": API_URL,
        "repository": REPO_WEB,
        "repository_head": git_ls_remote_head(),
        "user_agent": USER_AGENT,
        "sources": [],
    }
    for slug in SLUGS:
        url = API_URL.format(slug=slug)
        status, body = http_get(url)
        entry: dict = {
            "slug": slug,
            "url": url,
            "page_url": PAGE_URL.format(slug=slug),
            "fetched_at": utc_now(),
            "http_status": status,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "file": f"{slug}.json",
        }
        path = raw_dir / entry["file"]
        if status == 200:
            path.write_bytes(body)
            try:
                doc = json.loads(body)
                entry.update(
                    type=doc.get("type"),
                    title=(doc.get("title") or {}).get("card"),
                    updatedAt=doc.get("updatedAt"),
                    nodes=len(doc.get("nodes") or []),
                    edges=len(doc.get("edges") or []),
                )
            except ValueError as err:
                entry["parse_error"] = str(err)
        elif path.exists():
            path.unlink()  # no dejar una copia antigua que parezca vigente
        entry["page_http_status"] = http_get(PAGE_URL.format(slug=slug), timeout=60)[0]
        for key, template in LEGACY_URLS.items():
            entry[f"{key}_http_status"] = http_get(template.format(slug=slug), timeout=30)[0]
        site_status, site_body = http_get(SITE_CONTENT_URL.format(slug=slug), timeout=30)
        entry["site_content_http_status"] = site_status
        entry["site_content_not_found"] = b'"type":"not_found"' in site_body
        manifest["sources"].append(entry)
        print(f"  {slug:38s} HTTP {status}  nodos={entry.get('nodes')}  aristas={entry.get('edges')}")
    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def validate_source(slug: str, doc) -> list[str]:
    if not isinstance(doc, dict):
        return ["el JSON no es un objeto"]
    errors = []
    if doc.get("error"):
        errors.append(f"la API devolvió un error: {doc['error']}")
    if doc.get("slug") != slug:
        errors.append(f"slug inesperado en el documento: {doc.get('slug')!r}")
    nodes, edges = doc.get("nodes"), doc.get("edges")
    if not isinstance(nodes, list):
        errors.append("no hay array 'nodes'")
    if not isinstance(edges, list):
        errors.append("no hay array 'edges'")
    if errors:
        return errors
    ids = [n.get("id") if isinstance(n, dict) else None for n in nodes]
    if any(not isinstance(i, str) or not i for i in ids):
        errors.append("hay nodos sin id")
    duplicated = sorted(i for i, c in Counter(ids).items() if c > 1 and i)
    if duplicated:
        errors.append(f"ids de nodo duplicados: {duplicated[:5]}")
    id_set = set(ids)
    dangling = [e for e in edges if e.get("source") not in id_set or e.get("target") not in id_set]
    if dangling:
        errors.append(f"{len(dangling)} aristas con extremos inexistentes")
    for n in nodes:
        pos = n.get("position") or {}
        if not isinstance(pos.get("x"), (int, float)) or not isinstance(pos.get("y"), (int, float)):
            errors.append(f"el nodo {n.get('id')} no tiene position numérica")
            break
    return errors


def load_sources(raw_dir: Path) -> tuple[dict, dict, dict]:
    manifest_path = raw_dir / "manifest.json"
    if not manifest_path.exists():
        raise StopError(f"no existe {manifest_path}; ejecuta con --refresh")
    manifest = json.loads(manifest_path.read_text())
    entries = {e["slug"]: e for e in manifest.get("sources", [])}
    docs, problems = {}, {}
    for slug in SLUGS:
        entry = entries.get(slug)
        if entry is None:
            problems[slug] = ["no figura en el manifiesto"]
            continue
        if entry.get("http_status") != 200:
            problems[slug] = [f"la API respondió HTTP {entry.get('http_status')}"]
            continue
        path = raw_dir / entry["file"]
        if not path.exists():
            problems[slug] = [f"falta la copia {path.name}"]
            continue
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != entry.get("sha256"):
            problems[slug] = ["el SHA-256 de la copia no coincide con el manifiesto"]
            continue
        try:
            doc = json.loads(body)
        except ValueError as err:
            problems[slug] = [f"JSON inválido: {err}"]
            continue
        errors = validate_source(slug, doc)
        if errors:
            problems[slug] = errors
            continue
        docs[slug] = doc
    return docs, problems, manifest


# ---------------------------------------------------------------------------
# 2. Nodos y aristas en alcance (por roadmap)
# ---------------------------------------------------------------------------


def build_scope(slug: str, doc: dict) -> tuple[dict, list, Counter, list]:
    nodes: dict[str, dict] = {}
    raw_ids = {n["id"] for n in doc["nodes"]}
    stats: Counter = Counter()
    for n in doc["nodes"]:
        ntype = n.get("type")
        stats[f"raw:{ntype}"] += 1
        if ntype in KEPT_TYPES:
            attrs = {
                "roadmap": slug,
                "source_id": n["id"],
                "type": ntype,
                "label": label_of(n),
                "x": float(n["position"]["x"]),
                "y": float(n["position"]["y"]),
            }
            for field in ("width", "height"):
                if isinstance(n.get(field), (int, float)):
                    attrs[field] = float(n[field])
            measured = n.get("measured") or {}
            for field in ("width", "height"):
                if isinstance(measured.get(field), (int, float)):
                    attrs[f"measured_{field}"] = float(measured[field])
            href = (n.get("data") or {}).get("href")
            if isinstance(href, str) and href:
                attrs["href"] = href
            nodes[f"{slug}:{n['id']}"] = attrs
        elif ntype == CHECKLIST_TYPE:
            items = (n.get("data") or {}).get("checklists") or []
            for index, item in enumerate(items):
                item_id = item.get("id")
                if not isinstance(item_id, str) or not item_id:
                    raise StopError(f"{slug}: ítem de checklist sin id en {n['id']}")
                key = f"{slug}:{item_id}"
                if key in nodes or item_id in raw_ids:
                    raise StopError(f"{slug}: el id de ítem {item_id} colisiona con otro nodo")
                nodes[key] = {
                    "roadmap": slug,
                    "source_id": item_id,
                    "type": CHECKLIST_ITEM_TYPE,
                    "label": item.get("label") if isinstance(item.get("label"), str) else "",
                    "checklist_id": n["id"],
                    "checklist_index": index,
                }
            stats["checklist_items"] += len(items)
        else:
            stats[f"excluded:{ntype}"] += 1

    type_of = {n["id"]: n.get("type") for n in doc["nodes"]}
    edges = []
    dropped = []
    for e in doc["edges"]:
        u, v = f"{slug}:{e['source']}", f"{slug}:{e['target']}"
        if u in nodes and v in nodes:
            original = {k: val for k, val in e.items() if k not in ("source", "target")}
            edges.append(
                (
                    u,
                    v,
                    {
                        "roadmap": slug,
                        "edge_id": e.get("id"),
                        "edgeStyle": (e.get("data") or {}).get("edgeStyle"),
                        "original": original,
                    },
                )
            )
        else:
            dropped.append((e.get("id"), type_of.get(e["source"]), type_of.get(e["target"])))
    stats["edges_in_scope"] = len(edges)
    stats["edges_dropped"] = len(dropped)
    return nodes, edges, stats, dropped


# ---------------------------------------------------------------------------
# 3. Inferencia geométrica (por roadmap, sobre datos crudos)
# ---------------------------------------------------------------------------


def infer_geometric(slug: str, doc: dict, scope_edges: list, rules: set[str]) -> tuple[list, Counter, dict]:
    raw = {n["id"]: n for n in doc["nodes"]}
    box = {nid: node_box(n) for nid, n in raw.items()}
    by_type: dict[str, list[str]] = defaultdict(list)
    for nid, n in raw.items():
        if box[nid] is not None:
            by_type[n.get("type")].append(nid)
    topics, subs = by_type["topic"], by_type["subtopic"]
    labels, sections = by_type["label"], by_type["section"]
    lines = [nid for t in LINE_TYPES for nid in by_type[t]]

    explicit_parent: dict[str, set[str]] = defaultdict(set)
    section_topics: dict[str, set[str]] = defaultdict(set)
    section_edges: dict[str, list[str]] = defaultdict(list)
    section_path_edges: dict[str, int] = Counter()
    for e in doc["edges"]:
        a, b = e["source"], e["target"]
        types = (raw[a].get("type"), raw[b].get("type"))
        if set(types) == {"topic", "subtopic"}:
            sub, top = (b, a) if types[0] == "topic" else (a, b)
            explicit_parent[sub].add(top)
        if set(types) == {"topic", "section"}:
            sec, top = (b, a) if types[0] == "topic" else (a, b)
            # En el origen, topic–subtopic es siempre discontinua y topic–topic siempre
            # sólida: una arista sólida hacia una sección marca el camino, no contención.
            if (e.get("data") or {}).get("edgeStyle") == "dashed":
                section_topics[sec].add(top)
                section_edges[sec].append(e.get("id"))
            else:
                section_path_edges[sec] += 1

    incident = Counter()
    for u, v, _ in scope_edges:
        incident[u] += 1
        incident[v] += 1

    def is_orphan(nid: str) -> bool:
        return incident[f"{slug}:{nid}"] == 0

    stats: Counter = Counter()
    stats["subtopics_without_geometry"] = sum(
        1 for nid, n in raw.items() if n.get("type") == "subtopic" and box[nid] is None
    )

    # Pilas: componentes conexas de subtopics adyacentes.
    stack_of: dict[str, int] = {}
    stacks: list[list[str]] = []
    for start in subs:
        if start in stack_of:
            continue
        stack_of[start] = len(stacks)
        members, pending = [start], [start]
        while pending:
            current = pending.pop()
            for other in subs:
                if other not in stack_of and box_gap(box[current], box[other]) <= STACK_GAP_PX:
                    stack_of[other] = len(stacks)
                    members.append(other)
                    pending.append(other)
        stacks.append(members)

    # Evidencia de referencia (aristas explícitas) para R1 y para la regla descartada.
    ground = Counter()
    parented = [s for s in subs if explicit_parent.get(s)]
    for i, a in enumerate(parented):
        for b in parented[i + 1 :]:
            if box_gap(box[a], box[b]) <= STACK_GAP_PX:
                ground["adjacent_pairs"] += 1
                if explicit_parent[a] & explicit_parent[b]:
                    ground["adjacent_pairs_same_parent"] += 1
    for members in stacks:
        explicit = set().union(*(explicit_parent.get(m, set()) for m in members))
        if not explicit:
            continue
        ground["parented_stacks"] += 1
        if len(explicit) > 1:
            ground["conflicting_stacks"] += 1
        if topics:
            nearest = min(topics, key=lambda t: min(box_gap(box[m], box[t]) for m in members))
            ground["nearest_topic_hits"] += nearest in explicit

    derived = []
    for members in stacks:
        orphans = [m for m in members if is_orphan(m)]
        if not orphans:
            continue
        stats["orphan_subtopics"] += len(orphans)
        explicit = set().union(*(explicit_parent.get(m, set()) for m in members))
        choice = None
        if explicit:
            if len(explicit) == 1 and "R1" in rules:
                parent = next(iter(explicit))
                choice = ("R1", parent, {"siblings_with_explicit_parent": sorted(m for m in members if explicit_parent.get(m))})
            elif len(explicit) > 1:
                stats["R1_conflict"] += len(orphans)
        else:
            enclosing = [s for s in sections if all(box_inside(box[m], box[s]) for m in members)]
            section = min(enclosing, key=lambda s: box_area(box[s])) if enclosing else None
            if section and not section_topics.get(section) and section_path_edges.get(section):
                stats["R3_skipped_solid_edge"] += len(orphans)
            if section and "R3" in rules and len(section_topics.get(section, ())) == 1:
                choice = (
                    "R3",
                    next(iter(section_topics[section])),
                    {"section": section, "section_edges": section_edges[section]},
                )
            elif section and "R2" in rules:
                inside_labels = [lb for lb in labels if box_inside(box[lb], box[section])]
                inside_topics = [t for t in topics if box_inside(box[t], box[section])]
                if len(inside_labels) == 1 and not inside_topics:
                    choice = ("R2", inside_labels[0], {"section": section})
            if choice is None and "R5" in rules:
                touching = [ln for ln in lines if any(box_gap(box[m], box[ln]) <= LINE_GAP_PX for m in members)]
                bridged = {t for ln in touching for t in topics if box_gap(box[ln], box[t]) <= LINE_GAP_PX}
                if len(bridged) == 1:
                    topic = next(iter(bridged))
                    used = sorted(ln for ln in touching if box_gap(box[ln], box[topic]) <= LINE_GAP_PX)
                    choice = ("R5", topic, {"lines": used})
        if choice is None:
            stats["unresolved"] += len(orphans)
            continue
        rule, parent, evidence = choice
        stats[rule] += len(orphans)
        for child in orphans:
            derived.append(
                (
                    f"{slug}:{parent}",
                    f"{slug}:{child}",
                    {
                        "roadmap": slug,
                        "relation": "contains",
                        "rule": rule,
                        "validated": rule == "R1",
                        "evidence": evidence,
                    },
                )
            )
    return derived, stats, dict(ground)


# ---------------------------------------------------------------------------
# 4. Fusión y grafo final
# ---------------------------------------------------------------------------


def edge_style_convention(docs: dict) -> Counter:
    """Cuenta estilos de arista por par de tipos: evidencia de la convención del origen."""
    counts: Counter = Counter()
    for doc in docs.values():
        type_of = {n["id"]: n.get("type") for n in doc["nodes"]}
        for e in doc["edges"]:
            pair = "–".join(sorted((type_of[e["source"]], type_of[e["target"]])))
            if pair in ("subtopic–topic", "topic–topic", "section–topic"):
                counts[(pair, (e.get("data") or {}).get("edgeStyle"))] += 1
    return counts


def shared_id_stats(docs: dict) -> dict:
    """Ids de nodo repetidos entre roadmaps (evidencia contra la fusión por id)."""
    seen: dict[str, list] = defaultdict(list)
    for slug in SLUGS:
        for n in docs.get(slug, {}).get("nodes", []):
            seen[n["id"]].append((slug, n.get("type"), label_of(n)))
    shared = {i: v for i, v in seen.items() if len({s for s, _, _ in v}) > 1}
    different = {i: v for i, v in shared.items() if len({lab for _, _, lab in v}) > 1}
    content = sorted(i for i, v in different.items() if all(t in MERGEABLE_TYPES for _, t, _ in v))
    example = content[0] if content else (sorted(different)[0] if different else None)
    labels = "; ".join(f"«{lab}» en {s}" for s, _, lab in different.get(example, []))
    return {"shared": len(shared), "different_labels": len(different), "example_id": example, "example_labels": labels}


def literal_rule_collapse(all_nodes: dict) -> dict:
    """Nodos topic/subtopic que la Opción A literal (sin puntuación) dejaría con clave vacía."""
    hits = [
        a
        for a in all_nodes.values()
        if a["type"] in MERGEABLE_TYPES and a["label"].strip() and not re.sub(r"[^\w\s]", "", a["label"]).strip()
    ]
    return {
        "count": len(hits),
        "roadmaps": sorted({a["roadmap"] for a in hits}, key=SLUGS.index),
        "examples": sorted({a["label"].strip() for a in hits}),
    }


def derived_fingerprint(derived_edges: list) -> str:
    lines = sorted(f"{u}|{v}|{p['rule']}" for u, v, p in derived_edges)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def plan_merge(all_nodes: dict) -> tuple[dict, dict, dict]:
    groups: dict[str, list[str]] = defaultdict(list)
    for key, attrs in all_nodes.items():
        if attrs["type"] in MERGEABLE_TYPES:
            k = merge_key(attrs["label"])
            if k:
                groups[k].append(key)
    representative, merged, skipped = {}, {}, {}
    for k, keys in groups.items():
        roadmaps = [all_nodes[x]["roadmap"] for x in keys]
        if len(set(roadmaps)) < 2:
            continue
        if len(roadmaps) != len(set(roadmaps)):
            skipped[k] = keys  # etiqueta repetida dentro de algún roadmap: no se fusiona
            continue
        canonical = f"shared:{k}"
        ordered = sorted(keys, key=lambda x: SLUGS.index(all_nodes[x]["roadmap"]))
        merged[canonical] = {"key": k, "members": ordered}
        for x in keys:
            representative[x] = canonical
    return representative, merged, skipped


def build_graph(all_nodes, source_edges, derived_edges, representative, merged) -> tuple[nx.MultiDiGraph, Counter]:
    G = nx.MultiDiGraph()
    for key, attrs in all_nodes.items():
        if key not in representative:
            G.add_node(key, **attrs, group=attrs["roadmap"], roadmaps=[attrs["roadmap"]])
    for canonical, info in merged.items():
        members = info["members"]
        first = all_nodes[members[0]]
        member_records = []
        for m in members:
            a = all_nodes[m]
            record = {"key": m, "roadmap": a["roadmap"], "source_id": a["source_id"], "type": a["type"], "label": a["label"]}
            for field in ("x", "y", "width", "height"):
                if field in a:
                    record[field] = a[field]
            member_records.append(record)
        G.add_node(
            canonical,
            type="|".join(sorted({all_nodes[m]["type"] for m in members})),
            label=first["label"],
            group="shared",
            merge_key=info["key"],
            roadmaps=[all_nodes[m]["roadmap"] for m in members],
            members=member_records,
        )

    stats = Counter()
    for layer, edges in ((LAYER_SOURCE, source_edges), (LAYER_DERIVED, derived_edges)):
        for u, v, prov in edges:
            ru, rv = representative.get(u, u), representative.get(v, v)
            if G.has_edge(ru, rv, key=layer):
                data = G.edges[ru, rv, layer]
                data["provenance"].append(prov)
                if prov["roadmap"] not in data["roadmaps"]:
                    data["roadmaps"].append(prov["roadmap"])
                stats[f"dedup:{layer}"] += 1
            else:
                G.add_edge(ru, rv, key=layer, layer=layer, roadmaps=[prov["roadmap"]], provenance=[prov])
    for u, v, layer, data in G.edges(keys=True, data=True):
        provs = data["provenance"]
        if layer == LAYER_SOURCE:
            styles = {p.get("edgeStyle") for p in provs}
            data["edge_style"] = styles.pop() if len(styles) == 1 else "mixed"
        else:
            data["relation"] = "contains"
            data["rules"] = sorted({p["rule"] for p in provs})
            data["validated"] = all(p["validated"] for p in provs)
    return G, stats


# ---------------------------------------------------------------------------
# 5. Exportaciones
# ---------------------------------------------------------------------------


def flatten_attrs(attrs: dict) -> dict:
    flat = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, (bool, int, float, str)):
            flat[key] = value
        else:
            flat[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return flat


def write_graphml(G: nx.MultiDiGraph, path: Path) -> None:
    H = nx.MultiDiGraph()
    H.graph.update(flatten_attrs(G.graph))
    for n, data in G.nodes(data=True):
        H.add_node(n, **flatten_attrs(data))
    for u, v, k, data in G.edges(keys=True, data=True):
        H.add_edge(u, v, key=k, **flatten_attrs(data))
    nx.write_graphml(H, path, encoding="utf-8")


def ordered_nodes(G: nx.MultiDiGraph, nodes) -> list:
    """Orden estable: roadmap -> posición (y, x) -> ítems de checklist agrupados."""

    def sort_key(n):
        d = G.nodes[n]
        group = d["group"]
        rank = len(SLUGS) if group == "shared" else SLUGS.index(group)
        if d["type"] == CHECKLIST_ITEM_TYPE:
            return (rank, 1, d.get("checklist_id", ""), d.get("checklist_index", 0), 0.0, 0.0, n)
        return (rank, 0, "", 0, d.get("y", 0.0), d.get("x", 0.0), n)

    return sorted(nodes, key=sort_key)


def style_class(data: dict) -> str:
    if data["group"] == "shared":
        return "shared"
    return data["type"] if data["type"] in TYPE_STYLE else "paragraph"


def mermaid_text(text: str) -> str:
    if not text.strip():
        return " "
    s = re.sub(r"\s+", " ", text)
    s = s.replace("#", "#35;")
    for char, code in (('"', "#34;"), ("<", "#60;"), (">", "#62;"), ("&", "#38;"), ("`", "#96;")):
        s = s.replace(char, code)
    return s


def dot_text(text: str) -> str:
    s = re.sub(r"\s+", " ", text)
    return s.replace("\\", "\\\\").replace('"', '\\"')


def roadmap_titles(docs: dict) -> dict:
    return {slug: ((doc.get("title") or {}).get("card") or slug) for slug, doc in docs.items()}


def diagram_parts(G: nx.MultiDiGraph, node_filter=None) -> tuple[list, list]:
    nodes = [n for n in G.nodes if node_filter is None or node_filter(n, G.nodes[n])]
    keep = set(nodes)
    edges = [(u, v, k, d) for u, v, k, d in G.edges(keys=True, data=True) if u in keep and v in keep]
    order = {LAYER_SOURCE: 0, LAYER_DERIVED: 1}
    edges.sort(key=lambda e: (order[e[2]], e[0], e[1]))
    return ordered_nodes(G, nodes), edges


def write_mermaid(G, nodes, edges, titles, path: Path, heading: str) -> dict:
    ids = {n: f"n{i}" for i, n in enumerate(nodes)}
    by_group: dict[str, list] = defaultdict(list)
    for n in nodes:
        by_group[G.nodes[n]["group"]].append(n)
    lines = [
        "---",
        f"title: {heading}",
        "---",
        "%% Fuente: https://roadmap.sh/api/v1-official-roadmap/{slug} (ver data/raw/manifest.json)",
        "%% Aristas: --> fuente sólida · -.-> fuente discontinua · gris punteado = contención inferida por geometría",
        "flowchart LR",
    ]
    groups = [g for g in SLUGS if g in by_group] + (["shared"] if "shared" in by_group else [])
    for group in groups:
        if group == "shared":
            sg_title = f"Nodos fusionados entre roadmaps ({len(by_group[group])})"
        else:
            sg_title = f"{titles.get(group, group)} · {group}"
        lines.append(f'  subgraph sg_{re.sub(r"[^A-Za-z0-9]", "_", group)}["{mermaid_text(sg_title)}"]')
        lines.append("    direction TB")
        checklists: dict[str, list] = defaultdict(list)
        for n in by_group[group]:
            d = G.nodes[n]
            if d["type"] == CHECKLIST_ITEM_TYPE and group != "shared":
                checklists[d["checklist_id"]].append(n)
                continue
            lines.append(f'    {ids[n]}{mermaid_shape(d, mermaid_text(d["label"]))}')
        for index, (checklist_id, items) in enumerate(checklists.items()):
            lines.append(f'    subgraph ck_{re.sub(r"[^A-Za-z0-9]", "_", group)}_{index}[" "]')
            for n in items:
                lines.append(f'      {ids[n]}["{mermaid_text(G.nodes[n]["label"])}"]')
            lines.append("    end")
        lines.append("  end")
    derived_indexes = []
    for index, (u, v, layer, data) in enumerate(edges):
        if layer == LAYER_DERIVED:
            arrow = "-.->"
            derived_indexes.append(index)
        else:
            arrow = "-.->" if data.get("edge_style") == "dashed" else "-->"
        lines.append(f"  {ids[u]} {arrow} {ids[v]}")
    for cls, (fill, stroke, color) in TYPE_STYLE.items():
        lines.append(f"  classDef {cls.replace('-', '_')} fill:{fill},stroke:{stroke},color:{color}")
    by_class: dict[str, list] = defaultdict(list)
    for n in nodes:
        by_class[style_class(G.nodes[n]).replace("-", "_")].append(ids[n])
    for cls, members in by_class.items():
        for i in range(0, len(members), 200):
            lines.append(f"  class {','.join(members[i:i + 200])} {cls}")
    for i in range(0, len(derived_indexes), 200):
        chunk = ",".join(str(x) for x in derived_indexes[i : i + 200])
        lines.append(f"  linkStyle {chunk} stroke:{DERIVED_EDGE_COLOR},stroke-width:1px,stroke-dasharray:2 3")
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    return {"chars": len(text), "edges": len(edges), "nodes": len(nodes)}


def mermaid_shape(data: dict, text: str) -> str:
    if data["type"] == "button":
        return f'(["{text}"])'
    if data["type"] == "title":
        return f'[["{text}"]]'
    return f'["{text}"]'


def write_dot(G, nodes, edges, titles, path: Path, heading: str) -> dict:
    ids = {n: f"n{i}" for i, n in enumerate(nodes)}
    by_group: dict[str, list] = defaultdict(list)
    for n in nodes:
        by_group[G.nodes[n]["group"]].append(n)
    out = [
        "// Fuente: https://roadmap.sh/api/v1-official-roadmap/{slug} (ver data/raw/manifest.json)",
        "// Aristas: sólida/discontinua = fuente; punteada gris = contención inferida por geometría",
        'digraph "merged_roadmaps" {',
        f'  graph [rankdir=LR, newrank=true, compound=true, fontname="Helvetica", fontsize=28, labelloc=t, label="{dot_text(heading)}"];',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, margin="0.08,0.03"];',
        f'  edge [color="{SOURCE_EDGE_COLOR}", arrowsize=0.6];',
    ]
    groups = [g for g in SLUGS if g in by_group] + (["shared"] if "shared" in by_group else [])
    for group in groups:
        if group == "shared":
            cl_title = f"Nodos fusionados entre roadmaps ({len(by_group[group])})"
        else:
            cl_title = f"{titles.get(group, group)} · {group}"
        cid = re.sub(r"[^A-Za-z0-9]", "_", group)
        out.append(f'  subgraph "cluster_{cid}" {{')
        out.append(f'    label="{dot_text(cl_title)}"; fontsize=20; style="rounded"; color="#555555";')
        checklists: dict[str, list] = defaultdict(list)
        for n in by_group[group]:
            d = G.nodes[n]
            if d["type"] == CHECKLIST_ITEM_TYPE and group != "shared":
                checklists[d["checklist_id"]].append(n)
                continue
            out.append(f"    {dot_node(ids[n], d)}")
        for index, (checklist_id, items) in enumerate(checklists.items()):
            out.append(f'    subgraph "cluster_{cid}_ck_{index}" {{ label=""; style="dashed"; color="#43a047";')
            for n in items:
                out.append(f"      {dot_node(ids[n], G.nodes[n])}")
            out.append("    }")
        out.append("  }")
    for u, v, layer, data in edges:
        if layer == LAYER_DERIVED:
            attrs = f'style=dotted, color="{DERIVED_EDGE_COLOR}"'
        else:
            attrs = "style=dashed" if data.get("edge_style") == "dashed" else "style=solid"
        out.append(f'  "{ids[u]}" -> "{ids[v]}" [{attrs}];')
    out.append("}")
    text = "\n".join(out) + "\n"
    path.write_text(text, encoding="utf-8")
    return {"chars": len(text), "edges": len(edges), "nodes": len(nodes)}


def dot_node(node_id: str, data: dict) -> str:
    fill, stroke, color = TYPE_STYLE[style_class(data)]
    label = dot_text(data["label"]) if data["label"].strip() else " "
    extra = ""
    if data["type"] == "title" and data["group"] != "shared":
        extra = ", fontsize=16, penwidth=0"
    elif data["type"] == "label" and data["group"] != "shared":
        extra = ", penwidth=0"
    return f'"{node_id}" [label="{label}", fillcolor="{fill}", color="{stroke}", fontcolor="{color}"{extra}];'


def write_csv(path: Path, header: list[str], rows) -> int:
    count = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


# ---------------------------------------------------------------------------
# 6. Renderizado (opcional) y procedencia
# ---------------------------------------------------------------------------


def run_timed(cmd: list[str], timeout: int) -> dict:
    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        ok = proc.returncode == 0
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
    except subprocess.TimeoutExpired:
        ok, detail = False, [f"tiempo agotado ({timeout} s)"]
    except OSError as err:
        ok, detail = False, [str(err)]
    return {"cmd": " ".join(shlex.quote(c) for c in cmd), "ok": ok, "seconds": round(time.monotonic() - start, 1), "detail": detail}


def svg_size(path: Path) -> str | None:
    match = re.search(r'<svg width="([\d.]+)pt" height="([\d.]+)pt"', path.read_text(encoding="utf-8", errors="replace")[:4000])
    return f"{fmt(round(float(match.group(1))))} × {fmt(round(float(match.group(2))))} pt" if match else None


def render_all(out_dir: Path, args) -> dict:
    # fdp da un lienzo compacto (≈1:1) con los 18 roadmaps alrededor del grupo de
    # fusionados; dot conserva la jerarquía pero produce una tira muy alta.
    jobs = [
        ("merged_roadmaps_summary.svg", "merged_roadmaps_summary.dot", "dot"),
        ("merged_roadmaps.svg", "merged_roadmaps.dot", "fdp"),
        ("merged_roadmaps_hierarchical.svg", "merged_roadmaps.dot", "dot"),
    ]
    results = {}
    for svg_name, dot_name, engine in jobs:
        svg_path = out_dir / svg_name
        result = run_timed([engine, "-Tsvg", str(out_dir / dot_name), "-o", str(svg_path)], args.render_timeout)
        result["engine"] = engine
        if result["ok"] and svg_path.exists():
            result["svg_bytes"] = svg_path.stat().st_size
            result["size"] = svg_size(svg_path)
        results[f"graphviz:{svg_name}"] = result
        print(f"  graphviz {svg_name}: {'OK' if result['ok'] else 'FALLO'} ({engine}, {result['seconds']} s, {result.get('size')})")
    if args.mmdc:
        work = Path(args.render_dir)
        work.mkdir(parents=True, exist_ok=True)
        base = shlex.split(args.mmdc)
        if args.puppeteer_config:
            base += ["-p", args.puppeteer_config]
        jobs = [
            ("mermaid:summary (config por defecto)", out_dir / "merged_roadmaps_summary.mmd", work / "summary.svg", []),
            (
                "mermaid:completo (mermaid.config.json)",
                out_dir / "merged_roadmaps.mmd",
                work / "full.svg",
                ["-c", str(out_dir / "mermaid.config.json")],
            ),
        ]
        for label, src, dst, extra in jobs:
            result = run_timed(base + ["-i", str(src), "-o", str(dst)] + extra, args.render_timeout)
            if result["ok"] and dst.exists():
                result["svg_bytes"] = dst.stat().st_size
            results[label] = result
            print(f"  {label}: {'OK' if result['ok'] else 'FALLO'} ({result['seconds']} s)")
    return results


def provenance_check(clone: Path, docs: dict) -> dict:
    result = {"clone": str(clone), "head": None, "roadmaps": {}}
    try:
        result["head"] = subprocess.run(
            ["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    for slug, doc in docs.items():
        content_dir = clone / "roadmaps" / slug / "content"
        file_ids = set()
        if content_dir.is_dir():
            for f in content_dir.glob("*.md"):
                if "@" in f.stem:
                    file_ids.add(f.stem.rsplit("@", 1)[1])
        node_ids = {n["id"] for n in doc["nodes"] if n.get("type") in ("topic", "subtopic")}
        result["roadmaps"][slug] = {
            "content_dir_exists": content_dir.is_dir(),
            "content_files": len(file_ids),
            "topic_subtopic_nodes": len(node_ids),
            "nodes_with_file": len(node_ids & file_ids),
            "files_without_node": len(file_ids - {n["id"] for n in doc["nodes"]}),
        }
    return result


# ---------------------------------------------------------------------------
# 7. Informe
# ---------------------------------------------------------------------------


def write_report(path: Path, ctx: dict) -> None:
    m = ctx["manifest"]
    L: list[str] = []
    add = L.append
    totals = ctx["totals"]
    add("# Informe: diagrama único de 18 roadmaps de roadmap.sh")
    add("")
    add(f"Generado: {ctx['generated_at']} · Script: `scripts/merge_roadmaps.py` · Copia de fuentes: `data/raw/` ({m.get('generated_at')})")
    add("")
    add("## Resumen")
    add("")
    add(f"- Roadmaps cargados: **{len(ctx['docs'])}/{len(SLUGS)}**; excluidos: **{len(ctx['problems'])}**.")
    add(
        f"- Antes: {fmt(totals['raw_nodes'])} nodos y {fmt(totals['raw_edges'])} aristas en los JSON de origen; "
        f"en alcance: {fmt(totals['scope_nodes'])} nodos y {fmt(totals['scope_edges'])} aristas."
    )
    add(
        f"- Después: **{fmt(totals['out_nodes'])} nodos**, **{fmt(totals['out_source_edges'])} aristas de fuente** y "
        f"**{fmt(totals['out_derived_edges'])} aristas inferidas por geometría** (capa aparte). "
        f"Nodos fusionados entre roadmaps: **{fmt(len(ctx['merged']))}**."
    )
    add(
        "- Diagrama único: `merged_roadmaps.mmd` y `merged_roadmaps.dot`, con un grupo por roadmap y un grupo para los nodos fusionados. "
        "Renderizados: `merged_roadmaps.svg` (motor `fdp`: lienzo compacto con los roadmaps alrededor de los nodos fusionados) y "
        "`merged_roadmaps_hierarchical.svg` (motor `dot`: conserva la jerarquía, pero es una tira muy alta)."
    )
    add(
        f"- Resumen legible: `merged_roadmaps_summary.*` ({fmt(ctx['summary_info']['nodes'])} nodos, "
        f"{fmt(ctx['summary_info']['edges'])} aristas). Las 70 `section` no tienen etiqueta, así que el resumen usa title, topic y label."
    )
    if totals["out_nodes"] > LARGE_GRAPH_NODES:
        add(
            f"- **Aviso:** el grafo tiene más de {fmt(LARGE_GRAPH_NODES)} nodos; el diagrama completo solo es legible con zoom. "
            "Para una lectura general usa el resumen."
        )
    add("")

    add("## Fuente de datos y procedencia")
    add("")
    head = m.get("repository_head")
    add(
        f"- Los archivos `src/data/roadmaps/{{slug}}/{{slug}}.md`/`.json` y `public/roadmap-content/{{slug}}.json` ya no existen en "
        f"[{REPO_WEB.split('github.com/')[1]}]({REPO_WEB}) (HEAD `{head or 'n/d'}`); la tabla muestra el HTTP de esas rutas en la descarga."
    )
    if head:
        add(
            f"- Los scripts del propio repo leen el grafo de `https://roadmap.sh/api/v1-official-roadmap/{{slug}}`: "
            f"[sync-content-to-repo.ts]({REPO_WEB}/blob/{head}/scripts/sync-content-to-repo.ts) y "
            f"[sync-repo-to-database.ts]({REPO_WEB}/blob/{head}/scripts/sync-repo-to-database.ts). Esa es la fuente usada."
        )
    add("- Cada JSON descargado se guarda tal cual en `data/raw/{slug}.json`; su SHA-256 está en `data/raw/manifest.json`.")
    add("")
    add("| Roadmap | Tipo | updatedAt | Nodos | Aristas | HTTP API | HTTP página | HTTP .md antiguo | HTTP .json antiguo | HTTP roadmap-content antiguo | SHA-256 (12) |")
    add("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for e in m["sources"]:
        add(
            f"| {e['slug']} | {e.get('type', '')} | {e.get('updatedAt', '')} | {e.get('nodes', '')} | {e.get('edges', '')} | "
            f"{e.get('http_status')} | {e.get('page_http_status')} | {e.get('legacy_md_http_status')} | "
            f"{e.get('legacy_json_http_status')} | {e.get('legacy_content_http_status')} | `{e.get('sha256', '')[:12]}` |"
        )
    add("")
    prov = ctx.get("provenance")
    if prov:
        tot_nodes = sum(r["topic_subtopic_nodes"] for r in prov["roadmaps"].values())
        tot_hits = sum(r["nodes_with_file"] for r in prov["roadmaps"].values())
        add(
            f"Cruce con el repo (clon local `{prov['clone']}`, HEAD `{prov.get('head') or 'n/d'}`): "
            f"{fmt(tot_hits)} de {fmt(tot_nodes)} nodos topic/subtopic ({pct(tot_hits, tot_nodes)}) tienen su archivo "
            "`roadmaps/{slug}/content/*@{id}.md`."
        )
        add("")
        add("| Roadmap | Nodos topic/subtopic | Con archivo de contenido | Archivos sin nodo en la API |")
        add("|---|---:|---:|---:|")
        missing_dirs = []
        for slug in SLUGS:
            r = prov["roadmaps"].get(slug)
            if not r:
                continue
            if not r["content_dir_exists"]:
                missing_dirs.append(slug)
                add(f"| {slug} | {r['topic_subtopic_nodes']} | sin directorio en el repo | — |")
            else:
                add(f"| {slug} | {r['topic_subtopic_nodes']} | {r['nodes_with_file']} ({pct(r['nodes_with_file'], r['topic_subtopic_nodes'])}) | {r['files_without_node']} |")
        add("")
        if missing_dirs:
            add(
                f"{', '.join(f'`{s}`' for s in missing_dirs)} no tienen `roadmaps/{{slug}}/content/` en ese commit del repo: "
                "su grafo solo existe en la API, y sus nodos checklist no tienen etiqueta ni contenido propio."
            )
            add("")

    add("## Roadmaps excluidos")
    add("")
    if ctx["problems"]:
        for slug, errs in ctx["problems"].items():
            add(f"- `{slug}`: {'; '.join(errs)}")
    else:
        add("Ninguno: los 18 JSON se cargaron y pasaron la validación de origen (HTTP 200, `slug` correcto, arrays `nodes`/`edges`, ids únicos, aristas con extremos existentes y posiciones numéricas).")
    add("")

    add("## Alcance de nodos")
    add("")
    add("- Incluidos: `title`, `topic`, `subtopic`, `label`, `paragraph`, `button` y un nodo `checklist-item` por cada ítem de `data.checklists[]` (id y etiqueta reales).")
    add("- Excluidos (primitivas de dibujo sin contenido propio): `vertical`, `horizontal`, `section`, `linksgroup`, `legend`. Los contenedores `checklist` se sustituyen por sus ítems.")
    add("")
    add("| Tipo | Nodos en origen | Tratamiento |")
    add("|---|---:|---|")
    for t, c in ctx["type_counts"].most_common():
        treatment = "incluido" if t in KEPT_TYPES else ("sustituido por sus ítems" if t == CHECKLIST_TYPE else "excluido")
        add(f"| {t} | {fmt(c)} | {treatment} |")
    add(f"| checklist-item (derivado de `data.checklists[]`) | {fmt(ctx['checklist_items'])} | incluido |")
    add("")
    add(f"Aristas descartadas por tocar un tipo excluido: {fmt(totals['dropped_edges'])} ({ctx['dropped_pairs']}).")
    add("")

    add("## Regla de fusión")
    add("")
    add("**A exacta, solo entre roadmaps** (confirmada por el usuario):")
    add("")
    add("1. Solo participan nodos `topic` y `subtopic`.")
    add("2. Clave: etiqueta normalizada con NFKC, `casefold` y espacios colapsados y recortados. **La puntuación se conserva.**")
    add("3. Las claves vacías nunca se fusionan.")
    add("4. Una clave se fusiona solo si aparece en ≥2 roadmaps distintos y como máximo una vez en cada uno. Si se repite dentro de algún roadmap, esa clave no se fusiona en ningún sitio.")
    add("5. `title`, `label`, `paragraph`, `button` y `checklist-item` nunca se fusionan.")
    add("")
    ids = ctx["shared_ids"]
    site = [e for e in m["sources"] if "site_content_not_found" in e]
    add(
        "Alternativas descartadas antes de fusionar. **Opción B** (mismo `topicId`): "
        + (
            f"`roadmap.sh/roadmap-content/{{slug}}.json` responde HTTP {', '.join(sorted({str(e.get('site_content_http_status')) for e in site}))} "
            f"con un cuerpo `not_found` en {sum(1 for e in site if e['site_content_not_found'])}/{len(site)} roadmaps; "
            if site
            else ""
        )
        + f"además, {fmt(ids['shared'])} ids aparecen en más de un roadmap y {fmt(ids['different_labels'])} de ellos con etiquetas distintas "
        f"(p. ej. `{ids['example_id']}`: {ids['example_labels']}), porque los roadmaps se crean copiando plantillas. "
    )
    lit = ctx["literal_collapse"]
    if lit["count"]:
        L[-1] += (
            f"**Opción A literal** (quitando la puntuación): {fmt(lit['count'])} nodos topic/subtopic de {', '.join(lit['roadmaps'])} "
            f"quedaban con clave vacía y se habrían unido en uno solo ({', '.join(f'`{x}`' for x in lit['examples'])})."
        )
    add("")
    add(
        f"Resultado: {fmt(len(ctx['merged']))} nodos fusionados que agrupan {fmt(sum(len(v['members']) for v in ctx['merged'].values()))} nodos de origen. "
        f"Claves coincidentes entre roadmaps que no se fusionaron por repetirse dentro de un roadmap: {fmt(len(ctx['skipped']))} "
        f"({', '.join(f'«{k}»' for k in sorted(ctx['skipped']))}; detalle en `skipped_merges.csv`). "
        "Algunas serían equivalencias reales, como herramientas o protocolos; la regla elegida las deja sin fusionar a propósito."
    )
    add("")
    add("Nodos fusionados presentes en más roadmaps (la lista completa está en `merged_nodes.csv`):")
    add("")
    add("| Etiqueta | Nº roadmaps | Roadmaps |")
    add("|---|---:|---|")
    top = sorted(ctx["merged"].items(), key=lambda kv: (-len(kv[1]["members"]), kv[1]["key"]))[:25]
    for canonical, info in top:
        rms = [ctx["all_nodes"][x]["roadmap"] for x in info["members"]]
        add(f"| {md(ctx['all_nodes'][info['members'][0]]['label'])} | {len(rms)} | {', '.join(rms)} |")
    add("")

    add("## Inferencia geométrica de contención (capa `derived_geometric`)")
    add("")
    geo = ctx["geo_stats"]
    ground = ctx["ground"]
    add(
        "Solo se aplica a subtopics sin aristas en su roadmap. Usa `position` (absoluta, no hay `parentId`) y `measured`; "
        "se ignora `positionAbsolute` porque es un campo heredado que no coincide con `position` en parte de los nodos. "
        "Cada arista derivada lleva `rule`, `validated` y `evidence` (ids de la sección, la línea o los hermanos usados)."
    )
    add("")
    add("| Regla | Descripción | Subtopics conectados | Validación con aristas explícitas |")
    add("|---|---|---:|---|")
    for rule in GEO_RULES:
        if rule == "R1":
            validation = (
                f"{fmt(ground.get('parented_stacks', 0))} pilas con padre explícito; {fmt(ground.get('conflicting_stacks', 0))} con padres distintos. "
                f"{fmt(ground.get('adjacent_pairs_same_parent', 0))}/{fmt(ground.get('adjacent_pairs', 0))} parejas adyacentes comparten padre."
            )
        elif rule == "R3":
            validation = "No validable directamente; se apoya en la convención de estilos del origen (ver abajo)."
        else:
            validation = "No validable: no hay aristas explícitas equivalentes que sirvan de referencia."
        state = "" if rule in ctx["rules"] else " (desactivada)"
        add(f"| {rule}{state} | {RULE_TEXT[rule]} | {fmt(geo.get(rule, 0))} | {validation} |")
    add(
        f"| — | Regla descartada: topic más cercano a la pila | 0 | Acierta {fmt(ground.get('nearest_topic_hits', 0))}/{fmt(ground.get('parented_stacks', 0))} "
        f"({pct(ground.get('nearest_topic_hits', 0), ground.get('parented_stacks', 0))}) en pilas con padre conocido; no se usa. |"
    )
    add("")
    add(
        f"Subtopics huérfanos en origen: {fmt(geo.get('orphan_subtopics', 0))}; conectados por inferencia: "
        f"{fmt(sum(geo.get(r, 0) for r in GEO_RULES))}; sin regla aplicable: {fmt(geo.get('unresolved', 0))}"
        + (f"; pilas con padres en conflicto: {fmt(geo.get('R1_conflict', 0))}" if geo.get("R1_conflict") else "")
        + ". Detalle en `derived_edges.csv`."
    )
    add("")
    conv = ctx["style_convention"]
    add(
        "**Convención de estilos del origen**, en la que se apoya R3: aristas topic–subtopic "
        f"{fmt(conv.get(('subtopic–topic', 'dashed'), 0))} discontinuas y {fmt(conv.get(('subtopic–topic', 'solid'), 0))} sólidas; "
        f"topic–topic {fmt(conv.get(('topic–topic', 'solid'), 0))} sólidas y {fmt(conv.get(('topic–topic', 'dashed'), 0))} discontinuas; "
        f"topic–section {fmt(conv.get(('section–topic', 'dashed'), 0))} discontinuas y {fmt(conv.get(('section–topic', 'solid'), 0))} sólidas. "
        "Es decir, la discontinua asocia un topic con sus subtopics y la sólida marca el camino entre topics. "
        "Por eso R3 solo acepta aristas discontinuas"
        + (
            f"; {fmt(geo.get('R3_skipped_solid_edge', 0))} subtopics estaban en secciones enlazadas solo por aristas sólidas y pasaron a las reglas siguientes."
            if geo.get("R3_skipped_solid_edge")
            else "."
        )
    )
    add("")
    if ctx["fingerprint"] == REVIEWED_DERIVED_FINGERPRINT and REVIEW_NOTE:
        add(REVIEW_NOTE)
    else:
        add(
            "Revisión manual: no hay una revisión registrada para este conjunto de aristas inferidas "
            f"(huella `{ctx['fingerprint'][:12]}`); revisa `derived_edges.csv`."
        )
    add("")

    add("## Cifras antes y después por roadmap")
    add("")
    add("| Roadmap | Nodos origen | Aristas origen | Nodos en alcance | Aristas en alcance | Nodos fusionados | Aristas inferidas | Huérfanos finales* |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|")
    for slug in SLUGS:
        r = ctx["per_roadmap"].get(slug)
        if r:
            add(
                f"| {slug} | {r['raw_nodes']} | {r['raw_edges']} | {r['scope_nodes']} | {r['scope_edges']} | "
                f"{r['merged_members']} | {r['derived']} | {r['final_orphans']} |"
            )
    add(
        f"| **Total** | **{fmt(totals['raw_nodes'])}** | **{fmt(totals['raw_edges'])}** | **{fmt(totals['scope_nodes'])}** | "
        f"**{fmt(totals['scope_edges'])}** | **{fmt(totals['merged_members'])}** | **{fmt(totals['out_derived_edges'])}** | "
        f"**{fmt(totals['final_orphans'])}** |"
    )
    add("")
    add(
        "\\* Sin contar títulos. Se cuenta sobre el grafo final: un nodo fusionado deja de ser huérfano si tiene aristas en otro roadmap. "
        f"Los nodos fusionados que siguen huérfanos ({fmt(ctx['shared_orphans'])}) no figuran en ninguna fila, pero sí en el total."
    )
    add("")

    add("## Validaciones")
    add("")
    add("| Comprobación | Estado | Detalle |")
    add("|---|---|---|")
    for check in ctx["checks"]:
        add(f"| {md(check['name'])} | {check['status']} | {md(check['detail'])} |")
    add("")
    if ctx.get("renders"):
        add("Renderizado:")
        add("")
        add("| Salida | Resultado | Tiempo | Detalle |")
        add("|---|---|---:|---|")
        for name, r in ctx["renders"].items():
            detail = f"motor {r['engine']}" if "engine" in r else ""
            if r.get("size"):
                detail += f", lienzo {r['size']}"
            if r.get("svg_bytes"):
                detail += f"{', ' if detail else ''}SVG de {fmt(r['svg_bytes'])} bytes"
            if not r["ok"]:
                detail += f"{', ' if detail else ''}{' / '.join(r['detail'])}"
            add(f"| {md(name)} | {'OK' if r['ok'] else 'FALLO'} | {secs(r['seconds'])} | {md(detail)} |")
        add("")

    add("## Limitaciones")
    add("")
    add("- **Etiquetas genéricas fusionadas.** La regla fusiona por texto, no por significado. Ejemplos comprobados: «Introduction» une introducciones de roadmaps distintos, y «Loops» en claude-code trata el comando `/loop`, no los bucles de Java o Bash. Revisa `merged_nodes.csv`.")
    add("- **Inferencia geométrica.** R2, R3 y R5 no se pueden validar con los datos; R1 solo se valida por la consistencia de las pilas con padre explícito. Las aristas inferidas no son datos del origen y están marcadas como tales.")
    add("- **Huérfanos restantes.** Parte de la jerarquía de roadmap.sh solo existe como disposición visual. Los subtopics sin regla aplicable, los ítems de checklist (agrupados en su checklist) y otros nodos quedan sin aristas y figuran en `orphans.csv`.")
    add(f"- **Tamaño.** Con más de {fmt(LARGE_GRAPH_NODES)} nodos, el diagrama completo no es legible sin zoom.")
    add(
        f"- **Límites de Mermaid.** Por defecto Mermaid limita a {MERMAID_DEFAULT_MAX_EDGES} aristas (`maxEdges`) y {fmt(MERMAID_DEFAULT_MAX_TEXT)} caracteres (`maxTextSize`). "
        "Son claves `secure`: no se pueden cambiar desde el diagrama, así que el `.mmd` completo necesita `mermaid.config.json` (por ejemplo, `mmdc -c`)."
    )
    add("- **Datos vivos.** La API cambia; las cifras corresponden a la copia de `data/raw/` y se reproducen sin `--refresh`.")
    add(
        "- **Layout de `fdp` no determinista.** Con Graphviz 2.43, dos renders del mismo `.dot` dan disposiciones y tamaños de lienzo distintos, "
        "con los mismos nodos, aristas y clusters. El `.dot` sí es idéntico entre ejecuciones; `dot` es estable."
    )
    add("- **Muestra de procedencia.** El cruce API↔repo solo comprueba que existe un archivo de contenido para cada id; no compara su texto.")
    add("")
    add("## Cómo regenerar")
    add("")
    add("```bash")
    add("pip install -r requirements.txt")
    add("python scripts/merge_roadmaps.py            # con la copia de data/raw")
    add("python scripts/merge_roadmaps.py --refresh  # descargando de nuevo las 18 fuentes")
    add("fdp -Tsvg output/merged_roadmaps.dot -o output/merged_roadmaps.svg                # vista compacta")
    add("dot -Tsvg output/merged_roadmaps.dot -o output/merged_roadmaps_hierarchical.svg   # jerárquica (muy alta)")
    add("dot -Tsvg output/merged_roadmaps_summary.dot -o output/merged_roadmaps_summary.svg")
    add("mmdc -c output/mermaid.config.json -i output/merged_roadmaps.mmd -o merged_roadmaps.mmd.svg")
    add("```")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="descarga de nuevo las 18 fuentes a data/raw")
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    parser.add_argument("--out", default=str(ROOT / "output"))
    parser.add_argument("--rules", default=",".join(GEO_RULES), help="reglas geométricas activas (R1,R3,R2,R5; vacío = ninguna)")
    parser.add_argument("--render", action="store_true", help="renderiza con Graphviz (y mermaid-cli si se indica --mmdc)")
    parser.add_argument("--mmdc", help="comando de mermaid-cli, p. ej. '/ruta/node_modules/.bin/mmdc'")
    parser.add_argument("--puppeteer-config", help="configuración de puppeteer para mmdc")
    parser.add_argument("--render-dir", default="/tmp/merge_roadmaps_render", help="dónde dejar los SVG de validación de mmdc")
    parser.add_argument("--render-timeout", type=int, default=900)
    parser.add_argument("--repo-clone", help="clon local de nilbuild/developer-roadmap para el cruce de procedencia")
    args = parser.parse_args()

    rules = {r.strip() for r in args.rules.split(",") if r.strip()}
    unknown_rules = rules - set(GEO_RULES)
    if unknown_rules:
        parser.error(f"reglas desconocidas: {sorted(unknown_rules)}")
    raw_dir, out_dir = Path(args.raw_dir), Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = utc_now()

    try:
        if args.refresh:
            print("Descargando fuentes…")
            refresh_snapshot(raw_dir)
        docs, problems, manifest = load_sources(raw_dir)
        print(f"Fuentes válidas: {len(docs)}/{len(SLUGS)}")
        for slug, errs in problems.items():
            print(f"  EXCLUIDO {slug}: {'; '.join(errs)}")
        if not docs:
            raise StopError("ninguna fuente pasó la validación; no se genera ningún diagrama")
        unknown = sorted({n.get("type") for d in docs.values() for n in d["nodes"]} - KNOWN_TYPES, key=str)
        if unknown:
            raise StopError(f"tipos de nodo no previstos: {unknown}. Hace falta decidir su tratamiento antes de fusionar.")

        # 2-3. Alcance e inferencia por roadmap.
        all_nodes: dict[str, dict] = {}
        source_edges, derived_edges = [], []
        per_roadmap: dict[str, dict] = {}
        type_counts, geo_stats, ground = Counter(), Counter(), Counter()
        dropped_pairs, checklist_items = Counter(), 0
        for slug in SLUGS:
            if slug not in docs:
                continue
            doc = docs[slug]
            nodes, edges, stats, dropped = build_scope(slug, doc)
            derived, gstats, gground = infer_geometric(slug, doc, edges, rules)
            all_nodes.update(nodes)
            source_edges += edges
            derived_edges += derived
            type_counts.update(n.get("type") for n in doc["nodes"])
            geo_stats.update(gstats)
            ground.update(gground)
            checklist_items += stats["checklist_items"]
            for _, ta, tb in dropped:
                dropped_pairs[f"{ta}→{tb}"] += 1
            per_roadmap[slug] = {
                "raw_nodes": len(doc["nodes"]),
                "raw_edges": len(doc["edges"]),
                "scope_nodes": len(nodes),
                "scope_edges": len(edges),
                "derived": len(derived),
            }

        # 4. Fusión.
        representative, merged, skipped = plan_merge(all_nodes)
        G, dedup = build_graph(all_nodes, source_edges, derived_edges, representative, merged)
        for slug, r in per_roadmap.items():
            r["merged_members"] = sum(1 for k, a in all_nodes.items() if a["roadmap"] == slug and k in representative)

        titles = roadmap_titles(docs)
        out_source = sum(1 for *_, k in G.edges(keys=True) if k == LAYER_SOURCE)
        out_derived = sum(1 for *_, k in G.edges(keys=True) if k == LAYER_DERIVED)
        G.graph.update(
            {
                "name": "merged_roadmaps",
                "generated_at": generated_at,
                "source": API_URL,
                "snapshot_generated_at": manifest.get("generated_at"),
                "repository_head": manifest.get("repository_head"),
                "roadmaps": [s for s in SLUGS if s in docs],
                "excluded_roadmaps": sorted(problems),
                "merge_rule": "A exacta, solo entre roadmaps: topic/subtopic; NFKC+casefold+espacios; puntuación conservada; "
                "≥2 roadmaps y ≤1 vez por roadmap; claves vacías nunca",
                "geometric_rules": sorted(rules, key=GEO_RULES.index),
                "layers": [LAYER_SOURCE, LAYER_DERIVED],
            }
        )

        # 5. Exportaciones.
        node_link = nx.node_link_data(G, edges="edges")
        (out_dir / "merged_roadmaps.json").write_text(json.dumps(node_link, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        write_graphml(G, out_dir / "merged_roadmaps.graphml")
        heading = f"Diagrama único · {len(docs)} roadmaps de roadmap.sh"
        full_nodes, full_edges = diagram_parts(G)
        full_mmd = write_mermaid(G, full_nodes, full_edges, titles, out_dir / "merged_roadmaps.mmd", heading)
        write_dot(G, full_nodes, full_edges, titles, out_dir / "merged_roadmaps.dot", heading)

        def in_summary(n, d):
            return bool(set(d["type"].split("|")) & ({"topic"} if d["group"] == "shared" else {"title", "topic", "label"}))

        sum_nodes, sum_edges = diagram_parts(G, in_summary)
        sum_heading = f"Resumen · {len(docs)} roadmaps de roadmap.sh (title, topic y label)"
        summary_mmd = write_mermaid(G, sum_nodes, sum_edges, titles, out_dir / "merged_roadmaps_summary.mmd", sum_heading)
        write_dot(G, sum_nodes, sum_edges, titles, out_dir / "merged_roadmaps_summary.dot", sum_heading)
        mermaid_config = {
            "maxEdges": max(MERMAID_DEFAULT_MAX_EDGES, full_mmd["edges"] + 1000),
            "maxTextSize": max(MERMAID_DEFAULT_MAX_TEXT, full_mmd["chars"] * 2),
            "flowchart": {"htmlLabels": True, "useMaxWidth": False},
        }
        (out_dir / "mermaid.config.json").write_text(json.dumps(mermaid_config, indent=2) + "\n")

        write_csv(
            out_dir / "merged_nodes.csv",
            ["shared_id", "label", "types", "n_roadmaps", "roadmaps", "member_keys"],
            (
                [c, G.nodes[c]["label"], G.nodes[c]["type"], len(info["members"]), ";".join(G.nodes[c]["roadmaps"]), ";".join(info["members"])]
                for c, info in sorted(merged.items(), key=lambda kv: (-len(kv[1]["members"]), kv[0]))
            ),
        )
        write_csv(
            out_dir / "skipped_merges.csv",
            ["merge_key", "n_nodes", "roadmaps", "node_keys"],
            (
                [k, len(keys), ";".join(sorted({all_nodes[x]["roadmap"] for x in keys}, key=SLUGS.index)), ";".join(keys)]
                for k, keys in sorted(skipped.items())
            ),
        )
        write_csv(
            out_dir / "derived_edges.csv",
            ["roadmap", "rule", "validated", "parent_key", "parent_type", "parent_label", "child_key", "child_label", "evidence"],
            (
                [
                    p["roadmap"],
                    p["rule"],
                    p["validated"],
                    u,
                    all_nodes[u]["type"],
                    all_nodes[u]["label"],
                    v,
                    all_nodes[v]["label"],
                    json.dumps(p["evidence"], ensure_ascii=False),
                ]
                for u, v, p in derived_edges
            ),
        )
        degree = Counter()
        for u, v in G.edges():
            degree[u] += 1
            degree[v] += 1
        final_orphans = [n for n in G.nodes if degree[n] == 0 and G.nodes[n]["type"] != "title"]
        write_csv(
            out_dir / "orphans.csv",
            ["node_key", "group", "roadmaps", "type", "label"],
            ([n, G.nodes[n]["group"], ";".join(G.nodes[n]["roadmaps"]), G.nodes[n]["type"], G.nodes[n]["label"]] for n in ordered_nodes(G, final_orphans)),
        )
        for slug, r in per_roadmap.items():
            r["final_orphans"] = sum(1 for n in final_orphans if G.nodes[n]["group"] == slug)
        shared_orphans = sum(1 for n in final_orphans if G.nodes[n]["group"] == "shared")

        # 6. Validaciones.
        totals = {
            "raw_nodes": sum(len(d["nodes"]) for d in docs.values()),
            "raw_edges": sum(len(d["edges"]) for d in docs.values()),
            "scope_nodes": len(all_nodes),
            "scope_edges": len(source_edges),
            "dropped_edges": sum(dropped_pairs.values()),
            "out_nodes": G.number_of_nodes(),
            "out_source_edges": out_source,
            "out_derived_edges": out_derived,
            "merged_members": len(representative),
            "final_orphans": len(final_orphans),
        }
        checks = []

        def check(name, ok, detail, warn=False):
            checks.append({"name": name, "status": "OK" if ok else ("ADVERTENCIA" if warn else "FALLO"), "detail": detail})

        check("Fuentes cargadas", not problems, f"{len(docs)}/{len(SLUGS)} roadmaps válidos", warn=True)
        check(
            "Nodos: salida ≤ alcance",
            totals["out_nodes"] <= totals["scope_nodes"],
            f"{fmt(totals['out_nodes'])} ≤ {fmt(totals['scope_nodes'])} (en origen: {fmt(totals['raw_nodes'])})",
        )
        check(
            "Aristas de fuente: salida ≤ alcance ≤ origen",
            out_source <= totals["scope_edges"] <= totals["raw_edges"],
            f"{fmt(out_source)} ≤ {fmt(totals['scope_edges'])} ≤ {fmt(totals['raw_edges'])}; "
            f"las {fmt(out_derived)} inferidas se cuentan aparte",
        )
        source_labels = {a["label"] for a in all_nodes.values()}
        bad_labels = [n for n, d in G.nodes(data=True) if d["label"] not in source_labels]
        check("Etiquetas: todas existen en el origen", not bad_labels, f"{len(bad_labels)} etiquetas ajenas")
        no_members = [n for n, d in G.nodes(data=True) if d["group"] == "shared" and not d.get("members")]
        check("Nodos fusionados con miembros de origen", not no_members, f"{len(merged)} nodos fusionados, {len(no_members)} sin miembros")
        original_edges = {(s, e.get("id")): (f"{s}:{e['source']}", f"{s}:{e['target']}") for s, d in docs.items() for e in d["edges"]}
        bad_edges = 0
        for u, v, k, d in G.edges(keys=True, data=True):
            if k != LAYER_SOURCE:
                continue
            for p in d["provenance"]:
                ends = original_edges.get((p["roadmap"], p["edge_id"]))
                if ends is None or (representative.get(ends[0], ends[0]), representative.get(ends[1], ends[1])) != (u, v):
                    bad_edges += 1
        check("Aristas de fuente trazables a una arista original", bad_edges == 0, f"{bad_edges} sin correspondencia")
        bad_derived = [
            (u, v)
            for u, v, p in derived_edges
            if not p.get("rule") or not p.get("evidence") or u not in all_nodes or all_nodes[v]["type"] != "subtopic"
        ]
        check("Aristas inferidas con regla y evidencia", not bad_derived, f"{fmt(len(derived_edges))} inferidas, {len(bad_derived)} incompletas")
        orphan_types = Counter(G.nodes[n]["type"] for n in final_orphans)
        check(
            "Nodos huérfanos (sin contar títulos)",
            not final_orphans,
            f"{fmt(len(final_orphans))} tras la inferencia: "
            + ", ".join(f"{t} {fmt(c)}" for t, c in orphan_types.most_common())
            + (f"; {shared_orphans} en el grupo de fusionados" if shared_orphans else "")
            + ". Lista en `orphans.csv`",
            warn=True,
        )
        rt = nx.node_link_graph(json.loads((out_dir / "merged_roadmaps.json").read_text()), edges="edges")
        gm = nx.read_graphml(out_dir / "merged_roadmaps.graphml", force_multigraph=True)
        rt_ok = (rt.number_of_nodes(), rt.number_of_edges()) == (G.number_of_nodes(), G.number_of_edges())
        gm_ok = (gm.number_of_nodes(), gm.number_of_edges()) == (G.number_of_nodes(), G.number_of_edges())
        check(
            "Ida y vuelta node-link JSON y GraphML",
            rt_ok and gm_ok,
            f"JSON {rt.number_of_nodes()}/{rt.number_of_edges()}, GraphML {gm.number_of_nodes()}/{gm.number_of_edges()}, "
            f"grafo {G.number_of_nodes()}/{G.number_of_edges()} (nodos/aristas)",
        )
        check(
            f"Tamaño ≤ {fmt(LARGE_GRAPH_NODES)} nodos",
            totals["out_nodes"] <= LARGE_GRAPH_NODES,
            f"{fmt(totals['out_nodes'])} nodos: se genera además el resumen",
            warn=True,
        )
        check(
            "Resumen dentro de los límites por defecto de Mermaid",
            summary_mmd["edges"] <= MERMAID_DEFAULT_MAX_EDGES and summary_mmd["chars"] <= MERMAID_DEFAULT_MAX_TEXT,
            f"{fmt(summary_mmd['edges'])} aristas (≤ {MERMAID_DEFAULT_MAX_EDGES}), {fmt(summary_mmd['chars'])} caracteres (≤ {fmt(MERMAID_DEFAULT_MAX_TEXT)})",
            warn=True,
        )
        check(
            "Completo dentro de los límites por defecto de Mermaid",
            full_mmd["edges"] <= MERMAID_DEFAULT_MAX_EDGES and full_mmd["chars"] <= MERMAID_DEFAULT_MAX_TEXT,
            f"{fmt(full_mmd['edges'])} aristas, {fmt(full_mmd['chars'])} caracteres: requiere `mermaid.config.json`",
            warn=True,
        )

        provenance = provenance_check(Path(args.repo_clone), docs) if args.repo_clone else None
        renders = render_all(out_dir, args) if args.render else None
        if renders:
            for name, r in renders.items():
                check(f"Render {name}", r["ok"], secs(r["seconds"]), warn=True)

        ctx = {
            "generated_at": generated_at,
            "manifest": manifest,
            "docs": docs,
            "problems": problems,
            "totals": totals,
            "merged": merged,
            "skipped": skipped,
            "all_nodes": all_nodes,
            "type_counts": type_counts,
            "checklist_items": checklist_items,
            "dropped_pairs": ", ".join(f"{k}: {v}" for k, v in dropped_pairs.most_common()) or "ninguna",
            "geo_stats": geo_stats,
            "ground": ground,
            "rules": rules,
            "per_roadmap": per_roadmap,
            "checks": checks,
            "summary_info": summary_mmd,
            "renders": renders,
            "provenance": provenance,
            "style_convention": edge_style_convention(docs),
            "shared_ids": shared_id_stats(docs),
            "literal_collapse": literal_rule_collapse(all_nodes),
            "fingerprint": derived_fingerprint(derived_edges),
            "shared_orphans": shared_orphans,
        }
        write_report(out_dir / "INFORME.md", ctx)
        (out_dir / "validation.json").write_text(
            json.dumps({"generated_at": generated_at, "totals": totals, "checks": checks, "renders": renders, "dedup": dict(dedup)}, indent=2, ensure_ascii=False)
            + "\n"
        )
    except StopError as err:
        print(f"DETENIDO: {err}", file=sys.stderr)
        return 2

    print(f"Nodos: {fmt(totals['raw_nodes'])} origen → {fmt(totals['scope_nodes'])} alcance → {fmt(totals['out_nodes'])} salida")
    print(f"Aristas fuente: {fmt(totals['raw_edges'])} origen → {fmt(totals['scope_edges'])} alcance → {fmt(out_source)} salida; inferidas: {fmt(out_derived)}")
    print(f"Fusionados: {len(merged)} (claves omitidas por repetición interna: {len(skipped)})")
    print(f"Inferidas por regla: {', '.join(f'{r}={geo_stats.get(r, 0)}' for r in GEO_RULES)}; sin regla: {geo_stats.get('unresolved', 0)}; huella {ctx['fingerprint'][:12]}")
    for c in checks:
        print(f"  [{c['status']}] {c['name']}: {c['detail']}")
    return 1 if any(c["status"] == "FALLO" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
