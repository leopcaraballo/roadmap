# Diagrama único de 18 roadmaps de roadmap.sh

Fusiona en un solo grafo, y en un solo diagrama, estos 18 roadmaps:

- linux
- network-engineer
- software-architect
- devops
- docker
- java
- spring-boot
- api-design
- aws
- shell-bash
- claude-code
- aws-best-practices
- frontend-performance-best-practices
- api-security-best-practices
- backend-performance-best-practices
- seo
- cyber-security
- software-design-architecture

Los datos salen de `https://roadmap.sh/api/v1-official-roadmap/{slug}`. Es el endpoint que usan los scripts de sincronización de [nilbuild/developer-roadmap](https://github.com/nilbuild/developer-roadmap), que ya no guarda los JSON de los grafos.

## Salidas (`output/`)

| Archivo | Contenido |
|---|---|
| `atlas.html` | Atlas interactivo: los 18 lienzos originales en mosaico, con búsqueda, filtros por roadmap, capas y conceptos compartidos. Se abre en el navegador, sin servidor |
| `merged_roadmaps.svg` | Diagrama único renderizado con `fdp` (lienzo compacto) |
| `merged_roadmaps_hierarchical.svg` | El mismo diagrama con `dot` (jerárquico, muy alto) |
| `merged_roadmaps_summary.svg` | Resumen legible: title, topic y label de los 18 roadmaps |
| `merged_roadmaps.mmd` / `merged_roadmaps_summary.mmd` | Mermaid con un `subgraph` por roadmap; el completo necesita `mermaid.config.json` |
| `merged_roadmaps.dot` / `merged_roadmaps_summary.dot` | Graphviz |
| `merged_roadmaps.json` / `merged_roadmaps.graphml` | Grafo fusionado (node-link de NetworkX / GraphML) |
| `merged_nodes.csv`, `skipped_merges.csv`, `derived_edges.csv`, `orphans.csv` | Fusiones, fusiones omitidas, aristas inferidas y nodos sin aristas |
| `INFORME.md` | Regla de fusión, cifras antes y después, validaciones y limitaciones |

`data/raw/` guarda la copia exacta de los 18 JSON y `manifest.json`, con la URL, la fecha y el SHA-256 de cada uno.

## Regenerar

```bash
pip install -r requirements.txt
python scripts/merge_roadmaps.py            # reutiliza data/raw
python scripts/merge_roadmaps.py --refresh  # vuelve a descargar las fuentes
```

Con `--render` se generan también los SVG (requiere Graphviz). Con `--mmdc` además se valida el Mermaid con mermaid-cli.

Para regenerar el atlas a partir del grafo:

```bash
python scripts/build_atlas.py                                    # enlaza el contenido de cada tema sin comprobarlo
python scripts/build_atlas.py --repo-clone /tmp/developer-roadmap  # enlaza solo los archivos de contenido que existen
```
