---
name: cloud-architecture-drawio
description: Create and revise editable AWS, Azure, and Google Cloud (GCP) architecture diagrams as draw.io / diagrams.net files with CSP icons, VPC/VNet/subnet/AZ boundaries, availability placement, and labeled communication paths, plus a verified PNG. Use for cloud architecture or network topology diagrams (구성도, 아키텍처 다이어그램) from requirements, Terraform/CloudFormation/Bicep, or reference images, including multi-cloud views. Not for sequence diagrams, ERDs, or Mermaid/PlantUML output.
---

# Cloud architecture in draw.io

Deliver an editable `.drawio`, a rendered PNG, the architecture model, and a short list of assumptions. Preserve the source even when exporting images. This skill bundles a Python compiler and curated draw.io vector assets; MCP is optional.

## Working procedure

1. Identify the requested view and evidence: existing deployment, proposed design, or visual reconstruction. Do not turn a reference picture into an asserted deployment. Preserve given resources and connections. Separate observed facts from proposed settings; never infer runtime traffic from an IaC dependency alone.
2. Read only the relevant [AWS](references/aws.md), [Azure](references/azure.md), or [GCP](references/gcp.md) guide, then [model format](references/model.md). Use the matching JSON in `assets/templates/` as an editable starting point. Templates contain illustrative resources and ports: remove or change anything unsupported by the user's input. They are examples, not mandatory architectures.
3. Model network containment, geographical scope, logical memberships, and edges separately. Use `overlay` groups for memberships crossing subnets/AZs. An icon inside a subnet asserts placement there; private access does not imply that a managed service itself lives in that subnet.
4. Apply [visual rules](references/visual-rules.md) and [routing rules](references/routing.md). Reuse row/column positions for repeated tiers; grid cells and `"fit"` containers in the [model](references/model.md) keep a new layout free of hand-computed boundary sizes. Reserve connector corridors before adding resources; distribute incoming and outgoing attachments on busy resources. Use `scripts/cloud_drawio.py icons` for actual icon keys. Do not guess shape IDs or substitute a different CSP's product icon. For a missing product, add it with `scripts/add_icon.py` as in [asset provenance](references/assets.md), or use a labeled `generic` box and disclose it (`fallbackIcons` in the verdict).
5. Run the compiler from the skill directory. `check` validates, builds, renders with draw.io, and prints one JSON verdict; `validate` and `build` run the first steps alone:
   ```sh
   python3 scripts/cloud_drawio.py check /path/to/model.json /path/to/architecture.drawio
   ```
   Exit 0 means every automated check passed, 1 a failure (`stage` says which), and 2 a successful build that could not be rendered here. Resolve errors and inspect warnings and quality metrics. The compiler rejects overlapping route segments and unplaceable labels; a failed build lists every caption that found no place, the caption size, and the shapes in the way. Enlarge a lane or change ports instead of omitting a relationship or label. `validate` checks structure, misspelled keys, reserved page bands, and whether every shape's drawn position matches its declared `parent`; `build` also checks route and label feasibility. `build` refuses to overwrite a `.drawio` that changed after it was built; see the editing section before using `--force`.
6. Render using actual draw.io: `check` does this, or run `scripts/render.cjs` as in [rendering](references/rendering.md). It fails on clipped text, missing icons, crossings without a jump arc, and drift from the planned geometry, but you still inspect the full PNG and dense areas at readable size: icon visibility, Korean text, route direction, line crossings, and box meanings. Confirm residual crossings cannot be mistaken for branches and labels remain attached to their edges. Fix the model and rebuild. Stop once acceptance criteria pass. If rendering is unavailable, deliver the editable source with a clear “visual verification not completed” status, never claim visual approval.
7. Deliver links to source, preview, model, and substantive assumptions. When the preview will be shared on its own, render it with `--embed` and name it `*.drawio.png`: draw.io then opens the image as the editable diagram. State which network paths were intentionally omitted. Do not call a diagram deployable or fully network-validated based on this linter alone.

## Editing an existing diagram

If a matching model exists and the drawing has not been manually edited, change only affected IDs and layout coordinates. `build` detects manual edits: the report records the hash of the file it wrote, and a rebuild over a changed file stops with an error. Never answer that error with `--force` unless the user wants their edits discarded.

If the `.drawio` was edited in draw.io and its model exists, pull the edits back first:
```sh
python3 scripts/cloud_drawio.py pull edited.drawio model.json --output model.pulled.json
```
It carries moved and resized shapes, cards dropped into another boundary, and edited titles, details, boundary titles and captions into the model; untouched shapes keep their grid cells and `"fit"` sizes. The summary on stderr lists `unmodelled` cells (hand-drawn shapes or connectors) and `missing` model items, which are not carried over, and `errors` if the edited positions break validation (exit 1). Connector paths are replanned on rebuild, so hand-bent routes are not kept. When both lists are empty and the pulled model validates, review the diff, replace the model, and rebuild with `--force`: the edits now live in the model. Otherwise model those cells, or keep the edited file authoritative: preserve its original, patch affected cells in its XML, and render it with `--no-report`, because its planned geometry no longer applies. Do not regenerate from a stale model.

Stable resource IDs are part of the interface. For unsupported topologies such as explicit branch junctions or self-loops, author native draw.io XML with these same domain and visual rules. Record that manual source is authoritative and rerender it. To keep several views in one file, `bundle out.drawio a.json b.json` compiles each model as a page and `render.cjs out.drawio page2.png --page 2` checks one page against the shared report.

When expanding AZs or changing service modes, update labels and attachments as well as boxes. A three-AZ application does not imply a third standby for a two-AZ DB deployment. Make geography/count annotations consistent with the updated topology.

## Acceptance criteria

- Every requested resource and relationship is present, or an omission is explicitly explained.
- Each provider's scopes and network boundaries are correct for the selected service mode.
- No resource overlap, clipped label, missing icon, connector through an unrelated resource, or ambiguous shared line segment.
- Labels avoid other labels, routes, resources, and boundary titles. Residual crossings are individually reviewed with visible jump arcs; fewer crossings must not change the intended topology.
- Request traffic, DNS, policy association, replication, and egress have distinct semantics and a legend in the diagram's language (`locale` or `legend` in the model).
- `.drawio` opens as individually editable shapes and connectors with attached labels; PNG is rendered from that source. Review route metrics alongside the image, not as a substitute for it.
- Preserve ambiguity as labeled assumptions. Ask only about missing facts that materially change topology; use reasonable presentation defaults without pausing.
