---
name: cloud-architecture-drawio
description: Create and revise editable AWS, Azure, and Google Cloud architecture diagrams in draw.io with CSP icons, network boundaries, availability placement, and communication paths. Use for cloud topology diagrams from requirements, IaC, or reference images.
---

# Cloud architecture in draw.io

Deliver an editable `.drawio`, a rendered PNG, the architecture model, and a short list of assumptions. Preserve the source even when exporting images. This skill bundles a Python compiler and curated draw.io vector assets; MCP is optional.

## Working procedure

1. Identify the requested view and evidence: existing deployment, proposed design, or visual reconstruction. Do not turn a reference picture into an asserted deployment. Preserve given resources and connections. Separate observed facts from proposed settings; never infer runtime traffic from an IaC dependency alone.
2. Read only the relevant [AWS](references/aws.md), [Azure](references/azure.md), or [GCP](references/gcp.md) guide, then [model format](references/model.md). Use the matching JSON in `assets/templates/` as an editable starting point. Templates contain illustrative resources and ports: remove or change anything unsupported by the user's input. They are examples, not mandatory architectures.
3. Model network containment, geographical scope, logical memberships, and edges separately. Use `overlay` groups for memberships crossing subnets/AZs. An icon inside a subnet asserts placement there; private access does not imply that a managed service itself lives in that subnet.
4. Apply [visual rules](references/visual-rules.md) and [routing rules](references/routing.md). Reuse row/column positions for repeated tiers. Reserve connector corridors before adding resources; distribute incoming and outgoing attachments on busy resources. Use `scripts/cloud_drawio.py icons` for actual icon keys. Do not guess shape IDs or substitute a different CSP's product icon. For missing products, see [asset provenance](references/assets.md).
5. Run the compiler from the skill directory:
   ```sh
   python3 scripts/cloud_drawio.py validate /path/to/model.json
   python3 scripts/cloud_drawio.py build /path/to/model.json /path/to/architecture.drawio
   ```
   Resolve errors and inspect `.report.json` warnings and quality metrics. The compiler rejects overlapping route segments and unplaceable labels; enlarge a lane or change ports instead of omitting a relationship or label. `validate` checks structure; `build` also checks route and label feasibility.
6. Render using actual draw.io, following [rendering](references/rendering.md). Inspect the full PNG and dense areas at readable size. Check icon visibility, Korean text, clipping, route direction, line crossings, and box meanings. Confirm residual crossings have visible jump arcs and cannot be mistaken for branches. Verify that labels remain attached to their edges. Fix the model and rebuild. Stop once acceptance criteria pass. If rendering is unavailable, deliver the editable source with a clear “visual verification not completed” status, never claim visual approval.
7. Deliver links to source, preview, model, and substantive assumptions. State which network paths were intentionally omitted. Do not call a diagram deployable or fully network-validated based on this linter alone.

## Editing an existing diagram

If a matching model exists and the drawing has not been manually edited, change only affected IDs and layout coordinates. If the `.drawio` has manual edits, preserve its original, read its XML and patch affected cells; do not regenerate from a stale model. Stable resource IDs are part of the interface. For unsupported topologies such as explicit branch junctions or self-loops, author native draw.io XML with these same domain and visual rules. Record that manual source is authoritative and rerender it.

When expanding AZs or changing service modes, update labels and attachments as well as boxes. A three-AZ application does not imply a third standby for a two-AZ DB deployment. Make geography/count annotations consistent with the updated topology.

## Acceptance criteria

- Every requested resource and relationship is present, or an omission is explicitly explained.
- Each provider's scopes and network boundaries are correct for the selected service mode.
- No resource overlap, clipped label, missing icon, connector through an unrelated resource, or ambiguous shared line segment.
- Labels avoid other labels, routes, resources, and boundary titles. Residual crossings are individually reviewed with visible jump arcs; fewer crossings must not change the intended topology.
- Request traffic, DNS, policy association, replication, and egress have distinct semantics and a legend.
- `.drawio` opens as individually editable shapes and connectors with attached labels; PNG is rendered from that source. Review route metrics alongside the image, not as a substitute for it.
- Preserve ambiguity as labeled assumptions. Ask only about missing facts that materially change topology; use reasonable presentation defaults without pausing.
