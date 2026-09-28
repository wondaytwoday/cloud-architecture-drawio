# Model format, v2

The compiler accepts UTF-8 JSON. Coordinates are absolute canvas coordinates; output coordinates become relative to their actual draw.io parents. IDs are stable unique nonempty strings across containers, nodes, and edges; `0`, `1`, and the `__` prefix are reserved. Dimensions must be positive finite numbers. Reserve the top 80 px for the title and the bottom 90 px for the legend and notes.

```json
{
  "provider": "aws",
  "title": "Production web application",
  "subtitle": "Proposed topology · assumptions recorded below",
  "width": 1440, "height": 1620,
  "routing": {"clearance": 8, "stub": 16},
  "containers": [], "nodes": [], "edges": [],
  "notes": ["Illustrative ports; validate against deployment."]
}
```

`provider` is `aws`, `azure`, `gcp`, or `multi`. For `multi`, specify the provider on each provider boundary or resource; descendants inherit it. Page title/subtitle must each fit one line, notes two lines, and the legend one row. Widen the canvas or split a view when they do not fit. Routing settings are optional; `clearance` is nonnegative card padding in pixels, and `stub` is a positive outward lead-in length. Defaults are shown above.

Use bundled templates as complete starting models:

- `assets/templates/aws-three-tier.json`: 2 AZs, public/private tiers, cross-AZ logical groups.
- `assets/templates/azure-regional.json`: regional subnets, zonal compute, separate SQL private endpoint.
- `assets/templates/gcp-regional.json`: global VPC, regional subnets, zonal compute, separate PSC endpoint.

## Containers

Required: `id`, `kind`, `label`, `x`, `y`, `w`, `h`. Optional: `parent`, `provider`, `zone`, `public`, `overlay`, `labelAlign`, `labelOffset`.

Kinds: `cloud`, `account`, `project`, `region`, `vpc`, `vnet`, `az`, `subnet`, `group`. Children must fit and start at least 34 px below the parent's top. Container titles fit one line. `labelAlign` is `left` (default), `center`, or `right`; use a nonnegative `labelOffset` to move a left-aligned title right into a clear gap. Nonzero offsets require left alignment. Only the title rectangle obstructs routes; the rest of the header and boundary are passable.

`public: true` changes subnet presentation; it does not prove internet reachability. `overlay: true` makes a group transparent and expresses membership, not network placement. Put cross-AZ groups under the VPC and keep instances parented to their actual subnets. AWS subnets require an AZ ancestor; Azure/GCP subnets must not have one. Use `vnet` for Azure and `vpc` for AWS/GCP.

## Nodes

Required: `id`, `label`, `x`, `y`, `w`, `h`. Optional: `icon` (default `generic`), `detail`, `parent`, `provider`, `zone`.

Recommended size: 156×124 or wider for long labels; minimum 100×124. Title and detail each allow two lines. Use `\n` for intentional breaks. Positions are preserved on rebuild. Choose an icon from the catalog; `generic` is a neutral system box, and `generic.user` is a person glyph. Label generic endpoints with their actual role. Do not substitute another CSP's product icon.

Managed services and their private access endpoints are different nodes. The linter checks selected services against all subnet/AZ ancestors, so adding an intermediate group does not make invalid placement acceptable. It does not validate every deployment mode. Metadata such as `evidence`, `assumptions`, and `members` may be kept in the source JSON; the compiler does not interpret those fields.

## Edges

Required: `id`, `source`, `target` naming node IDs. Optional: `label`, `kind`, `sourcePort`, `targetPort`, `sourceOffset`, `targetOffset`, `priority`.

Kinds: `traffic` (default, solid), `dns`, `association`, `replication`, `egress`, and `management` (dashed with distinct colors and a legend). Association has no arrowhead. Arrows express the documented request/transfer direction, not every response packet. Keep each edge label to a short single line; the linter uses a 240 px caption budget.

Ports accept `top`, `bottom`, `left`, `right`, or `auto` (the default). Offsets are fractions from `0.1` through `0.9` along the selected side: left-to-right on top/bottom, top-to-bottom on left/right. For example:

```json
{
  "id": "gateway-app-a", "source": "gateway", "target": "app-a",
  "kind": "traffic", "label": "HTTPS",
  "sourcePort": "bottom", "sourceOffset": 0.35,
  "targetPort": "top", "priority": 0
}
```

Automatic allocation separates incoming and outgoing connections on each card side and respects explicit offsets. Coincident explicit offsets or an overcrowded side fail with a remedy. Connections attach to the entire resource card. `priority` is a finite number; smaller values route earlier. Default categories are traffic 0, egress 1, replication 2, DNS 3, association 4, management 5, followed by endpoint distance and stable edge ID. Changing the order of the edge array does not change routes. See [routing](routing.md) for algorithm limits and editing guidance.

The current compiler handles node-to-node edges, not self-loops, edge-to-edge junctions, shared buses, or user-specified waypoint arrays. Preserve those relationships with native XML when necessary; do not approximate them by overlapping unrelated lines.

## Validation and output

`validate` checks structure, text budgets, containment, icon consistency, and selected provider rules. `build` additionally allocates ports, routes every edge, and places every label; inability to do so is an error. This is not a reachability proof: route tables, SG/NSG/firewall policy, service configuration, and DNS may require a separate view.

Layout is template-driven; resources are not automatically rearranged. Add an AZ by widening the canvas/VPC and updating group spans, not shrinking all text. Routes can change when geometry, IDs, ports, or priorities change. The output stores explicit orthogonal waypoints and fixed connection fractions. Labels are editable relative child cells of their edge, so they retain their edge association through edits and save/reopen; inspect their placement after manual changes.

`.report.json` version 2 includes `model_sha256`, `routes`, `labels`, `quality`, `warnings`, and `errors`. Label data records its rectangle, relative position, and offset. Quality records `crossingCount`, `overlapLength`, `bendCount`, `totalLength`, plus individual crossing/overlap locations. Crossings produce warnings for visual review. These metrics do not measure cloud correctness or guarantee the clearest possible layout.
