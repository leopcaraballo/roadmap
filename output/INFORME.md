# Informe: diagrama único de 18 roadmaps de roadmap.sh

Generado: 2026-09-27T04:52:18Z · Script: `scripts/merge_roadmaps.py` · Copia de fuentes: `data/raw/` (2026-09-27T04:45:52Z)

## Resumen

- Roadmaps cargados: **18/18**; excluidos: **0**.
- Antes: 2.462 nodos y 736 aristas en los JSON de origen; en alcance: 2.331 nodos y 724 aristas.
- Después: **2.201 nodos**, **724 aristas de fuente** y **516 aristas inferidas por geometría** (capa aparte). Nodos fusionados entre roadmaps: **106**.
- Diagrama único: `merged_roadmaps.mmd` y `merged_roadmaps.dot`, con un grupo por roadmap y un grupo para los nodos fusionados. Renderizados: `merged_roadmaps.svg` (motor `fdp`: lienzo compacto con los roadmaps alrededor de los nodos fusionados) y `merged_roadmaps_hierarchical.svg` (motor `dot`: conserva la jerarquía, pero es una tira muy alta).
- Resumen legible: `merged_roadmaps_summary.*` (409 nodos, 229 aristas). Las 70 `section` no tienen etiqueta, así que el resumen usa title, topic y label.
- **Aviso:** el grafo tiene más de 2.000 nodos; el diagrama completo solo es legible con zoom. Para una lectura general usa el resumen.

## Fuente de datos y procedencia

- Los archivos `src/data/roadmaps/{slug}/{slug}.md`/`.json` y `public/roadmap-content/{slug}.json` ya no existen en [nilbuild/developer-roadmap](https://github.com/nilbuild/developer-roadmap) (HEAD `68253fc20036740210ed99f6513abd16a678d18f`); la tabla muestra el HTTP de esas rutas en la descarga.
- Los scripts del propio repo leen el grafo de `https://roadmap.sh/api/v1-official-roadmap/{slug}`: [sync-content-to-repo.ts](https://github.com/nilbuild/developer-roadmap/blob/68253fc20036740210ed99f6513abd16a678d18f/scripts/sync-content-to-repo.ts) y [sync-repo-to-database.ts](https://github.com/nilbuild/developer-roadmap/blob/68253fc20036740210ed99f6513abd16a678d18f/scripts/sync-repo-to-database.ts). Esa es la fuente usada.
- Cada JSON descargado se guarda tal cual en `data/raw/{slug}.json`; su SHA-256 está en `data/raw/manifest.json`.

| Roadmap | Tipo | updatedAt | Nodos | Aristas | HTTP API | HTTP página | HTTP .md antiguo | HTTP .json antiguo | HTTP roadmap-content antiguo | SHA-256 (12) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| linux | skill | 2026-05-12T11:02:34.052Z | 121 | 51 | 200 | 200 | 404 | 404 | 404 | `2af0427f3edb` |
| network-engineer | role | 2026-08-18T12:08:26.227Z | 248 | 78 | 200 | 200 | 404 | 404 | 404 | `0f915b09b4b0` |
| software-architect | role | 2026-01-06T16:31:52.878Z | 146 | 58 | 200 | 200 | 404 | 404 | 404 | `189a58ba00e3` |
| devops | role | 2026-07-29T09:51:43.464Z | 171 | 60 | 200 | 200 | 404 | 404 | 404 | `90ca7569703b` |
| docker | skill | 2026-02-26T08:41:07.276Z | 79 | 30 | 200 | 200 | 404 | 404 | 404 | `61ed3aa58d37` |
| java | skill | 2026-01-27T13:57:35.172Z | 125 | 29 | 200 | 200 | 404 | 404 | 404 | `8285ea306345` |
| spring-boot | skill | 2026-03-17T15:55:08.992Z | 57 | 37 | 200 | 200 | 404 | 404 | 404 | `727049a91365` |
| api-design | skill | 2026-05-18T13:59:39.252Z | 123 | 55 | 200 | 200 | 404 | 404 | 404 | `abafb348d614` |
| aws | skill | 2026-02-26T08:40:46.664Z | 131 | 52 | 200 | 200 | 404 | 404 | 404 | `e01e22f76908` |
| shell-bash | skill | 2026-05-12T10:59:14.861Z | 237 | 46 | 200 | 200 | 404 | 404 | 404 | `67f1d33112ae` |
| claude-code | skill | 2026-09-10T10:53:24.782Z | 145 | 46 | 200 | 200 | 404 | 404 | 404 | `378e5b492e05` |
| aws-best-practices | best-practice | 2025-12-02T08:55:07.437Z | 39 | 0 | 200 | 200 | 404 | 404 | 404 | `50d1da4e6af0` |
| frontend-performance-best-practices | best-practice | 2025-11-15T07:18:38.172Z | 23 | 1 | 200 | 200 | 404 | 404 | 404 | `c24c183f23eb` |
| api-security-best-practices | best-practice | 2025-11-19T10:04:22.877Z | 27 | 0 | 200 | 200 | 404 | 404 | 404 | `c250f213d456` |
| backend-performance-best-practices | best-practice | 2025-11-14T22:08:05.149Z | 28 | 0 | 200 | 200 | 404 | 404 | 404 | `7b10146a4041` |
| seo | role | 2026-09-24T10:56:35.877Z | 263 | 144 | 200 | 200 | 404 | 404 | 404 | `a4175474b66b` |
| cyber-security | role | 2026-06-15T11:47:47.372Z | 373 | 18 | 200 | 200 | 404 | 404 | 404 | `272c23dc68f3` |
| software-design-architecture | skill | 2025-09-12T12:38:05.654Z | 126 | 31 | 200 | 200 | 404 | 404 | 404 | `e92846913222` |

Cruce con el repo (clon local `/tmp/developer-roadmap`, HEAD `68253fc20036740210ed99f6513abd16a678d18f`): 1.834 de 1.837 nodos topic/subtopic (99,8 %) tienen su archivo `roadmaps/{slug}/content/*@{id}.md`.

| Roadmap | Nodos topic/subtopic | Con archivo de contenido | Archivos sin nodo en la API |
|---|---:|---:|---:|
| linux | 102 | 102 (100,0 %) | 0 |
| network-engineer | 196 | 195 (99,5 %) | 1 |
| software-architect | 113 | 112 (99,1 %) | 0 |
| devops | 139 | 139 (100,0 %) | 1 |
| docker | 57 | 56 (98,2 %) | 0 |
| java | 88 | 88 (100,0 %) | 0 |
| spring-boot | 46 | 46 (100,0 %) | 0 |
| api-design | 97 | 97 (100,0 %) | 0 |
| aws | 101 | 101 (100,0 %) | 0 |
| shell-bash | 174 | 174 (100,0 %) | 0 |
| claude-code | 113 | 113 (100,0 %) | 0 |
| aws-best-practices | 0 | sin directorio en el repo | — |
| frontend-performance-best-practices | 0 | sin directorio en el repo | — |
| api-security-best-practices | 0 | sin directorio en el repo | — |
| backend-performance-best-practices | 0 | sin directorio en el repo | — |
| seo | 216 | 216 (100,0 %) | 10 |
| cyber-security | 301 | 301 (100,0 %) | 0 |
| software-design-architecture | 94 | 94 (100,0 %) | 0 |

`aws-best-practices`, `frontend-performance-best-practices`, `api-security-best-practices`, `backend-performance-best-practices` no tienen `roadmaps/{slug}/content/` en ese commit del repo: su grafo solo existe en la API, y sus nodos checklist no tienen etiqueta ni contenido propio.

## Roadmaps excluidos

Ninguno: los 18 JSON se cargaron y pasaron la validación de origen (HTTP 200, `slug` correcto, arrays `nodes`/`edges`, ids únicos, aristas con extremos existentes y posiciones numéricas).

## Alcance de nodos

- Incluidos: `title`, `topic`, `subtopic`, `label`, `paragraph`, `button` y un nodo `checklist-item` por cada ítem de `data.checklists[]` (id y etiqueta reales).
- Excluidos (primitivas de dibujo sin contenido propio): `vertical`, `horizontal`, `section`, `linksgroup`, `legend`. Los contenedores `checklist` se sustituyen por sus ítems.

| Tipo | Nodos en origen | Tratamiento |
|---|---:|---|
| subtopic | 1.555 | incluido |
| topic | 282 | incluido |
| vertical | 126 | excluido |
| label | 126 | incluido |
| button | 88 | incluido |
| horizontal | 78 | excluido |
| section | 70 | excluido |
| paragraph | 63 | incluido |
| checklist | 41 | sustituido por sus ítems |
| title | 18 | incluido |
| linksgroup | 14 | excluido |
| legend | 1 | excluido |
| checklist-item (derivado de `data.checklists[]`) | 199 | incluido |

Aristas descartadas por tocar un tipo excluido: 12 (topic→section: 5, section→topic: 4, paragraph→section: 2, section→paragraph: 1).

## Regla de fusión

**A exacta, solo entre roadmaps** (confirmada por el usuario):

1. Solo participan nodos `topic` y `subtopic`.
2. Clave: etiqueta normalizada con NFKC, `casefold` y espacios colapsados y recortados. **La puntuación se conserva.**
3. Las claves vacías nunca se fusionan.
4. Una clave se fusiona solo si aparece en ≥2 roadmaps distintos y como máximo una vez en cada uno. Si se repite dentro de algún roadmap, esa clave no se fusiona en ningún sitio.
5. `title`, `label`, `paragraph`, `button` y `checklist-item` nunca se fusionan.

Alternativas descartadas antes de fusionar. **Opción B** (mismo `topicId`): `roadmap.sh/roadmap-content/{slug}.json` responde HTTP 200 con un cuerpo `not_found` en 18/18 roadmaps; además, 39 ids aparecen en más de un roadmap y 20 de ellos con etiquetas distintas (p. ej. `3hatcMVLDbMuz73uTx-9P`: «Bare Metal vs VMs vs Containers» en docker; «Public vs Private vs Hybrid Cloud» en aws), porque los roadmaps se crean copiando plantillas. **Opción A literal** (quitando la puntuación): 11 nodos topic/subtopic de shell-bash, claude-code quedaban con clave vacía y se habrían unido en uno solo (`!`, `$#`, `$*`, `$?`, `$@`, `*`, `?`, `@`, `[...]`, `\`, `{...}`).

Resultado: 106 nodos fusionados que agrupan 236 nodos de origen. Claves coincidentes entre roadmaps que no se fusionaron por repetirse dentro de un roadmap: 11 («architecture», «arp», «awk», «datadog», «dhcp», «dns», «nmap», «nslookup», «ping», «prometheus», «tools»; detalle en `skipped_merges.csv`). Algunas serían equivalencias reales, como herramientas o protocolos; la regla elegida las deja sin fusionar a propósito.

Nodos fusionados presentes en más roadmaps (la lista completa está en `merged_nodes.csv`):

| Etiqueta | Nº roadmaps | Roadmaps |
|---|---:|---|
| Introduction | 7 | network-engineer, docker, spring-boot, aws, shell-bash, claude-code, seo |
| SSH | 5 | linux, network-engineer, devops, shell-bash, cyber-security |
| Loops | 4 | linux, java, shell-bash, claude-code |
| AWS | 3 | network-engineer, devops, cyber-security |
| Azure | 3 | network-engineer, devops, cyber-security |
| Bash | 3 | devops, shell-bash, cyber-security |
| Conditionals | 3 | linux, java, shell-bash |
| Containers | 3 | software-architect, devops, docker |
| Go | 3 | software-architect, devops, cyber-security |
| grep | 3 | linux, shell-bash, cyber-security |
| Microservices | 3 | software-architect, spring-boot, software-design-architecture |
| netstat | 3 | linux, network-engineer, cyber-security |
| Networking | 3 | linux, docker, java |
| Observability | 3 | network-engineer, devops, api-design |
| Python | 3 | software-architect, devops, cyber-security |
| SSL / TLS | 3 | network-engineer, devops, cyber-security |
| Troubleshooting | 3 | linux, network-engineer, cyber-security |
| Abstraction | 2 | java, software-design-architecture |
| ACLs | 2 | network-engineer, cyber-security |
| Annotations | 2 | java, spring-boot |
| Ansible | 2 | network-engineer, devops |
| Application Architecture | 2 | software-architect, docker |
| apt | 2 | shell-bash, cyber-security |
| Arrays  | 2 | java, shell-bash |
| Bluetooth | 2 | network-engineer, cyber-security |

## Inferencia geométrica de contención (capa `derived_geometric`)

Solo se aplica a subtopics sin aristas en su roadmap. Usa `position` (absoluta, no hay `parentId`) y `measured`; se ignora `positionAbsolute` porque es un campo heredado que no coincide con `position` en parte de los nodos. Cada arista derivada lleva `rule`, `validated` y `evidence` (ids de la sección, la línea o los hermanos usados).

| Regla | Descripción | Subtopics conectados | Validación con aristas explícitas |
|---|---|---:|---|
| R1 | pila: el subtopic forma una cadena de subtopics adyacentes (hueco ≤ 4 px) con un único padre explícito | 175 | 197 pilas con padre explícito; 0 con padres distintos. 270/270 parejas adyacentes comparten padre. |
| R3 | sección enlazada: la sección mínima que contiene la pila tiene una arista explícita **discontinua** con exactamente un topic | 31 | No validable directamente; se apoya en la convención de estilos del origen (ver abajo). |
| R2 | encabezado de sección: la sección mínima que contiene la pila contiene exactamente un label y ningún topic | 195 | No validable: no hay aristas explícitas equivalentes que sirvan de referencia. |
| R5 | línea conectora: una línea vertical u horizontal toca la pila (≤ 6 px) y exactamente un topic | 115 | No validable: no hay aristas explícitas equivalentes que sirvan de referencia. |
| — | Regla descartada: topic más cercano a la pila | 0 | Acierta 148/197 (75,1 %) en pilas con padre conocido; no se usa. |

Subtopics huérfanos en origen: 1.062; conectados por inferencia: 516; sin regla aplicable: 546. Detalle en `derived_edges.csv`.

**Convención de estilos del origen**, en la que se apoya R3: aristas topic–subtopic 467 discontinuas y 0 sólidas; topic–topic 161 sólidas y 0 discontinuas; topic–section 5 discontinuas y 4 sólidas. Es decir, la discontinua asocia un topic con sus subtopics y la sólida marca el camino entre topics. Por eso R3 solo acepta aristas discontinuas; 18 subtopics estaban en secciones enlazadas solo por aristas sólidas y pasaron a las reglas siguientes.

**Revisión manual** (hecha por el asistente el 2026-09-27 sobre esta misma huella `fad90138d763`): se revisaron todos los grupos padre → hijos inferidos, comparando la etiqueta del padre con las de sus hijos. Resultado: R1 66/66 grupos coherentes, R2 38/38, R3 5/5 y R5 28/28. Antes de restringir R3 a aristas discontinuas, 4 de sus 9 grupos eran incorrectos, y los 4 usaban una arista sólida. Por ejemplo, en linux asignaba «Users and Groups» y «Managing Permissions» a «Service Management (systemd)», cuando la sección está pegada a «User Management». Es un juicio cualitativo sobre las etiquetas, no una validación formal.

## Cifras antes y después por roadmap

| Roadmap | Nodos origen | Aristas origen | Nodos en alcance | Aristas en alcance | Nodos fusionados | Aristas inferidas | Huérfanos finales* |
|---|---:|---:|---:|---:|---:|---:|---:|
| linux | 121 | 51 | 111 | 50 | 26 | 25 | 25 |
| network-engineer | 248 | 78 | 225 | 77 | 41 | 39 | 83 |
| software-architect | 146 | 58 | 135 | 58 | 24 | 52 | 19 |
| devops | 171 | 60 | 156 | 57 | 30 | 53 | 33 |
| docker | 79 | 30 | 68 | 30 | 9 | 14 | 16 |
| java | 125 | 29 | 105 | 28 | 16 | 39 | 22 |
| spring-boot | 57 | 37 | 54 | 37 | 7 | 4 | 11 |
| api-design | 123 | 55 | 110 | 55 | 7 | 9 | 40 |
| aws | 131 | 52 | 129 | 52 | 4 | 26 | 44 |
| shell-bash | 237 | 46 | 197 | 42 | 23 | 114 | 22 |
| claude-code | 145 | 46 | 133 | 46 | 2 | 2 | 78 |
| aws-best-practices | 39 | 0 | 56 | 0 | 0 | 0 | 55 |
| frontend-performance-best-practices | 23 | 1 | 53 | 1 | 0 | 0 | 50 |
| api-security-best-practices | 27 | 0 | 55 | 0 | 0 | 0 | 54 |
| backend-performance-best-practices | 28 | 0 | 51 | 0 | 0 | 0 | 50 |
| seo | 263 | 144 | 246 | 144 | 2 | 3 | 89 |
| cyber-security | 373 | 18 | 341 | 16 | 37 | 111 | 180 |
| software-design-architecture | 126 | 31 | 106 | 31 | 8 | 25 | 44 |
| **Total** | **2.462** | **736** | **2.331** | **724** | **236** | **516** | **925** |

\* Sin contar títulos. Se cuenta sobre el grafo final: un nodo fusionado deja de ser huérfano si tiene aristas en otro roadmap. Los nodos fusionados que siguen huérfanos (10) no figuran en ninguna fila, pero sí en el total.

## Validaciones

| Comprobación | Estado | Detalle |
|---|---|---|
| Fuentes cargadas | OK | 18/18 roadmaps válidos |
| Nodos: salida ≤ alcance | OK | 2.201 ≤ 2.331 (en origen: 2.462) |
| Aristas de fuente: salida ≤ alcance ≤ origen | OK | 724 ≤ 724 ≤ 736; las 516 inferidas se cuentan aparte |
| Etiquetas: todas existen en el origen | OK | 0 etiquetas ajenas |
| Nodos fusionados con miembros de origen | OK | 106 nodos fusionados, 0 sin miembros |
| Aristas de fuente trazables a una arista original | OK | 0 sin correspondencia |
| Aristas inferidas con regla y evidencia | OK | 516 inferidas, 0 incompletas |
| Nodos huérfanos (sin contar títulos) | ADVERTENCIA | 925 tras la inferencia: subtopic 499, checklist-item 199, button 78, label 73, paragraph 45, topic 30, subtopic\|topic 1; 10 en el grupo de fusionados. Lista en `orphans.csv` |
| Ida y vuelta node-link JSON y GraphML | OK | JSON 2201/1240, GraphML 2201/1240, grafo 2201/1240 (nodos/aristas) |
| Tamaño ≤ 2.000 nodos | ADVERTENCIA | 2.201 nodos: se genera además el resumen |
| Resumen dentro de los límites por defecto de Mermaid | OK | 229 aristas (≤ 500), 20.089 caracteres (≤ 50.000) |
| Completo dentro de los límites por defecto de Mermaid | ADVERTENCIA | 1.240 aristas, 110.777 caracteres: requiere `mermaid.config.json` |
| Render graphviz:merged_roadmaps_summary.svg | OK | 0,1 s |
| Render graphviz:merged_roadmaps.svg | OK | 2,7 s |
| Render graphviz:merged_roadmaps_hierarchical.svg | OK | 0,2 s |
| Render mermaid:summary (config por defecto) | OK | 3,7 s |
| Render mermaid:completo (mermaid.config.json) | OK | 16,4 s |

Renderizado:

| Salida | Resultado | Tiempo | Detalle |
|---|---|---:|---|
| graphviz:merged_roadmaps_summary.svg | OK | 0,1 s | motor dot, lienzo 5.161 × 11.719 pt, SVG de 312.211 bytes |
| graphviz:merged_roadmaps.svg | OK | 2,7 s | motor fdp, lienzo 9.285 × 8.072 pt, SVG de 1.939.520 bytes |
| graphviz:merged_roadmaps_hierarchical.svg | OK | 0,2 s | motor dot, lienzo 7.183 × 55.765 pt, SVG de 1.766.568 bytes |
| mermaid:summary (config por defecto) | OK | 3,7 s | SVG de 690.466 bytes |
| mermaid:completo (mermaid.config.json) | OK | 16,4 s | SVG de 8.631.901 bytes |

## Limitaciones

- **Etiquetas genéricas fusionadas.** La regla fusiona por texto, no por significado. Ejemplos comprobados: «Introduction» une introducciones de roadmaps distintos, y «Loops» en claude-code trata el comando `/loop`, no los bucles de Java o Bash. Revisa `merged_nodes.csv`.
- **Inferencia geométrica.** R2, R3 y R5 no se pueden validar con los datos; R1 solo se valida por la consistencia de las pilas con padre explícito. Las aristas inferidas no son datos del origen y están marcadas como tales.
- **Huérfanos restantes.** Parte de la jerarquía de roadmap.sh solo existe como disposición visual. Los subtopics sin regla aplicable, los ítems de checklist (agrupados en su checklist) y otros nodos quedan sin aristas y figuran en `orphans.csv`.
- **Tamaño.** Con más de 2.000 nodos, el diagrama completo no es legible sin zoom.
- **Límites de Mermaid.** Por defecto Mermaid limita a 500 aristas (`maxEdges`) y 50.000 caracteres (`maxTextSize`). Son claves `secure`: no se pueden cambiar desde el diagrama, así que el `.mmd` completo necesita `mermaid.config.json` (por ejemplo, `mmdc -c`).
- **Datos vivos.** La API cambia; las cifras corresponden a la copia de `data/raw/` y se reproducen sin `--refresh`.
- **Layout de `fdp` no determinista.** Con Graphviz 2.43, dos renders del mismo `.dot` dan disposiciones y tamaños de lienzo distintos, con los mismos nodos, aristas y clusters. El `.dot` sí es idéntico entre ejecuciones; `dot` es estable.
- **Muestra de procedencia.** El cruce API↔repo solo comprueba que existe un archivo de contenido para cada id; no compara su texto.

## Cómo regenerar

```bash
pip install -r requirements.txt
python scripts/merge_roadmaps.py            # con la copia de data/raw
python scripts/merge_roadmaps.py --refresh  # descargando de nuevo las 18 fuentes
fdp -Tsvg output/merged_roadmaps.dot -o output/merged_roadmaps.svg                # vista compacta
dot -Tsvg output/merged_roadmaps.dot -o output/merged_roadmaps_hierarchical.svg   # jerárquica (muy alta)
dot -Tsvg output/merged_roadmaps_summary.dot -o output/merged_roadmaps_summary.svg
mmdc -c output/mermaid.config.json -i output/merged_roadmaps.mmd -o merged_roadmaps.mmd.svg
```
