# Layout, views, changes and evidence

Commands run from the skill directory. They operate on supplied models and never fetch cloud inventory.

## Layout repair proposals

```sh
python3 scripts/cloud_drawio.py repair crowded.json
python3 scripts/cloud_drawio.py repair crowded.json --apply best --output spaced.json
```

Tests up to six horizontal/vertical spacing expansions, with a bounded search budget per proposal. It keeps node sizes, relationships and labels; scales container extents and positions. Results include candidate IDs, scale factors, failures and quality metrics. `--apply expand-2` selects a successful candidate. The source cannot be overwritten. Render and inspect the result: spacing is a heuristic, not an optimal layout solver. No candidate is applied automatically on failure. Models with locked routes require an explicit decision about which locks to remove before requesting proposals. Fixed port problems may require manual port changes even after expansion.

## Explicit junctions and buses

A node with `icon: "generic.junction"`, a descriptive `label`, and `w:12,h:12` becomes an editable filled dot. The label records meaning in the model and is not printed on the dot. Use a nearby meaningful edge caption or diagram note. Give each incident edge a distinct cardinal side. A trunk is one actual edge between junctions; branches are separate edges attached to those dots. For example: producer → junction A → junction B, with consumers branching from A and B. Never overlap separate edges to fake a shared bus. The dot is a logical connection, not an invented deployed router. Self-loops and edge-to-edge terminals remain unsupported.

## Purpose views

```sh
python3 scripts/cloud_drawio.py views model.json new-view-directory
```

Writes overview plus nonempty network (DNS, egress, connectivity), application (traffic, event), and operations (management, replication, association) model files; combines them into `views.drawio`; records included and omitted edge IDs in `manifest.json`. Overview retains all nodes and relationships. Detail views keep selected endpoints and ancestors at their existing positions and filter unrelated resources; they are not automatically compacted or semantically summarized. The destination must be empty. Render every page with `render.cjs --page N`; disclose omissions from the manifest when presenting a page alone.

## Change reports

```sh
python3 scripts/cloud_drawio.py diff before.json after.json --output changes.json --highlight highlighted.json
python3 scripts/cloud_drawio.py check highlighted.json highlighted.drawio
```

Stable IDs identify added, removed and modified items. Field-level before/after values show placement, topology, labels and metadata changes; page-level differences include presentation and locked paths. Green borders mark additions, orange marks modifications. Removals stay in the report, not as apparently live resources in the new architecture. Highlight output is a derived model; preserve the original model's colors separately. Renaming an ID appears as removal plus addition.

## Evidence and assumptions

Top-level model and each container/node/edge may carry:

```json
"evidence": [{"kind":"iac", "source":"main.tf:42", "detail":"resource declaration"}],
"assumptions": ["Application traffic port requires operator confirmation"]
```

Kinds: `user`, `iac`, `observed`, `inferred`. `source` is required. Inference can carry `confirmed:true` once the user confirms it. Keep source excerpts concise and avoid storing credentials. Evidence is an author-supplied claim, not proof; IaC dependency alone does not establish runtime traffic.

```sh
python3 scripts/cloud_drawio.py evidence model.json --output evidence.json
python3 scripts/cloud_drawio.py evidence model.json --strict
```

The report lists missing evidence and unconfirmed inferences by ID, and retains assumptions. `--strict` fails on either; without it only schema errors fail. Existing free-form metadata remains readable by the compiler, but the evidence command reports malformed records for migration. Build reports include the inventory under `provenance`. Evidence stays in model/report JSON, not automatically in visible resource captions.
