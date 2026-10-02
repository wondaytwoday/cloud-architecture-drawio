# Model format, v3

The compiler accepts UTF-8 JSON, with or without a byte order mark, on any system locale. Coordinates are absolute canvas coordinates; output coordinates become relative to their actual draw.io parents. IDs are stable unique nonempty strings across containers, nodes, and edges; `0`, `1`, and the `__` prefix are reserved. Dimensions must be positive finite numbers. Every container and node must stay inside x 10..width-10 and y 80..height-90: the top 80 px hold the title and the bottom 90 px the legend and notes, and the validator rejects shapes that enter those bands. Fields the compiler writes (title, subtitle, notes, legend, and container, node and edge fields) must not contain control characters that XML cannot store; use `\n` for a line break. Metadata is not checked.

```json
{
  "provider": "aws",
  "title": "Production web application",
  "subtitle": "Proposed topology · assumptions recorded below",
  "width": 1440, "height": 1620,
  "locale": "en",
  "routing": {"clearance": 8, "stub": 16},
  "containers": [], "nodes": [], "edges": [],
  "notes": ["Illustrative ports; validate against deployment."]
}
```

`provider` is `aws`, `azure`, `gcp`, or `multi`. For `multi`, specify the provider on each provider boundary or resource; descendants inherit it. A VPC, VNet, AZ, or subnet without a provider takes the provider of the resources inside it (their explicit provider, else their product icon); region, account, and cloud boxes may frame several providers and are not inferred; a VPC, VNet, AZ, or subnet holding icons of several providers is an error, and an explicit provider that contradicts an ancestor's is an error. Page title/subtitle must each fit one line, notes two lines, and the legend one row. Widen the canvas or split a view when they do not fit. Routing settings are optional; `clearance` is nonnegative card padding in pixels, and `stub` is a positive outward lead-in length. Defaults are shown above.

`locale` (`en` default, or `ko`) selects the built-in legend captions. `legend` overrides captions per edge kind for any language, for example `{"dns": "DNS 질의"}`; each caption must fit one 160 px line at 11 px. Legend entries follow the routing order of their kinds, not the order of the edge array.

Unknown keys are checked. A near miss of a supported key (`parnet`, `labelalign`, `note`) or a common alias (`from`, `to`, `type`, `name`) is an error when the intended key is absent, so a typo cannot silently fall back to a default; otherwise it is a warning. Keep free-form metadata in `evidence`, `assumptions`, `members`, `meta`, or keys starting with `x-`.

Use bundled templates as complete starting models:

- `assets/templates/aws-three-tier.json`: 2 AZs, public/private tiers, cross-AZ logical groups.
- `assets/templates/azure-regional.json`: regional subnets, zonal compute, separate SQL private endpoint.
- `assets/templates/gcp-regional.json`: global VPC, regional subnets, zonal compute, separate PSC endpoint.

These templates use grid cells and fitted boxes (see Layout shorthands):

- `assets/templates/aws-serverless.json`: CloudFront, API Gateway, Lambda, DynamoDB, SQS events, Cognito; no VPC.
- `assets/templates/aws-egress.json`: two AZs, NAT gateways, internet gateway, S3 gateway endpoint.
- `assets/templates/aws-multi-region-dr.json`: Route 53 failover, two Regions, Aurora global database, S3 replication.
- `assets/templates/aws-eks.json`: ALB ingress, EKS node groups in two AZs, Aurora, ECR, SQS, CloudWatch.
- `assets/templates/aws-hybrid-vpn.json`: on-premises site, site-to-site VPN and Direct Connect, Transit Gateway attached to two VPCs.
- `assets/templates/azure-hub-spoke.json`: hub VNet with VPN gateway, Azure Firewall and Bastion, peered spokes, Private Endpoint to SQL.
- `assets/templates/gcp-cloud-run.json`: global external ALB with Cloud Armor, Cloud Run, Pub/Sub and Functions, PSC to Cloud SQL, Cloud NAT.

## Layout shorthands

Coordinates may be absolute numbers everywhere, as in the templates, or left to these shorthands, which `validate`, `build` and `check` resolve first. `cloud_drawio.py normalize model.json` prints the resolved absolute model.

- Node `w`/`h` may be omitted for the standard 156×124 card.
- A top-level `"grid": {"left": 60, "top": 140, "column": 236, "row": 204}` (defaults shown) lets nodes give `col`/`row` instead of `x`/`y`; fractions such as `1.5` are allowed. A node gives either `x` or `col`, not both.
- A container's `x`, `y`, `w` or `h` may be `"fit"`: it wraps its children with 24 px at the sides and bottom and 56 px for the title, enough for a card connected through its top side. A fitted width also grows to hold the one-line title. An overlay group fits its `members` (node or container IDs) instead of its children; its left edge then meets the first member's box, so its title is centred unless `labelAlign` says otherwise. `"match:ID"` copies that dimension from another container, for example equal-height AZ columns.
- `"width"`/`"height": "auto"` sizes the canvas to the content, the footer, the legend, and the one-line page title and subtitle.
- When shapes reach into the page margins (x below 10, y below 80), the whole layout shifts right and down to x 30 and y 90; a layout already inside the margins is not moved. An `auto` canvas always pulls the layout up and left to x 30 and y 90. Either way, a card connected through its top side keeps `routing.stub` px below the 80 px title band for its lead-in.
- A fitted box's title sits just above its first row of cards and covers the top centre of a standard card unless the title is very short (about eight characters). A connector that drops straight into the top of such a card has to detour around the title, so connect cards stacked in one fitted column from the side (`sourcePort`/`targetPort` `left` or `right`). Moving the card does not help: the fitted box and its title move with it.
- Two container titles may not overlap; give one `labelAlign` or `labelOffset`, or move it.

## Containers

Required: `id`, `kind`, `label`, `x`, `y`, `w`, `h`. Optional: `parent`, `provider`, `zone`, `public`, `overlay`, `labelAlign`, `labelOffset`.

Kinds: `cloud`, `account`, `project`, `region`, `vpc`, `vnet`, `az`, `subnet`, `group`. Children must fit and start at least 34 px below the parent's top. A card connected through its `top` side under the parent's title needs 36 px plus `routing.stub` (52 px by default) so its lead-in clears the title. Container titles fit one line. `labelAlign` is `left` (default), `center`, or `right`; use a nonnegative `labelOffset` to move a left-aligned title right into a clear gap. Nonzero offsets require left alignment. Only the title rectangle obstructs routes; the rest of the header and boundary are passable.

`public: true` changes subnet presentation; it does not prove internet reachability. `overlay: true` makes a `group` transparent and expresses membership, not network placement; other kinds reject it, because a subnet, AZ, VPC or VNet is placement. Put cross-AZ groups under the VPC and keep instances parented to their actual subnets. AWS subnets require an AZ and a VPC ancestor; Azure subnets require a VNet and GCP subnets a VPC, and neither has an AZ ancestor. A VPC or VNet cannot sit inside a subnet, AZ, or another VPC/VNet; draw peered networks side by side. A subnet or AZ cannot sit inside a subnet. Use `vnet` for Azure and `vpc` for AWS/GCP.

Geometry and hierarchy must agree, because draw.io nests each cell under its declared parent and the provider rules read that hierarchy. The innermost non-overlay container that encloses a shape must be its nearest non-overlay declared ancestor; non-overlay containers may not cross each other's borders, and a node may not straddle a container border. Overlay groups are exempt: they cross boundaries by design.

## Nodes

Required: `id`, `label`, `x`, `y`, `w`, `h`. Optional: `icon` (default `generic`), `detail`, `parent`, `provider`, `zone`.

Recommended size: 156×124 or wider for long labels; minimum 100×124. Title and detail each allow two lines. Use `\n` for intentional breaks. Positions are preserved on rebuild. Choose an icon from the catalog (`cloud_drawio.py icons`); `generic.*` glyphs (server, onprem, mobile, desktop, internet, firewall, router, storage) are provider-neutral and fit any diagram, `generic` is a plain system box, and `generic.user` is a person glyph. Label generic endpoints with their actual role. Do not substitute another CSP's product icon. The report lists nodes drawn as a plain `generic` box under `fallbackIcons`; disclose them.

Managed services and their private access endpoints are different nodes. The linter checks selected services against every subnet/AZ that is an ancestor or encloses the card on the page, so neither an intermediate group nor a missing `parent` makes invalid placement acceptable. It rejects these icons inside a subnet or AZ: managed or global services (S3, CloudFront, Route 53, Front Door, Azure SQL, Storage and DNS, Cloud SQL, Cloud Storage, Cloud DNS, Memorystore), policy associations (WAF, Shield, Cloud Armor), and network-level objects (Internet Gateway, VPC network, Cloud Router, Cloud NAT). Application Gateway and Private Endpoint must sit in a subnet; a subnet holding an Application Gateway is dedicated to it and cannot be named `GatewaySubnet`. It does not validate every deployment mode. Metadata such as `evidence`, `assumptions`, and `members` may be kept in the source JSON; the compiler does not interpret those fields.

## Edges

Required: `id`, `source`, `target` naming node IDs, or network boundaries (`vpc`, `vnet`, `subnet`, `region`, `cloud`, `account`, `project`) for peering, attachments and VPN links. A boundary cannot connect to anything inside itself; the route stays outside every boundary it ends on. Optional: `label`, `kind`, `sourcePort`, `targetPort`, `sourceOffset`, `targetOffset`, `priority`.

Kinds: `traffic` (default, solid), `dns`, `association`, `replication`, `egress`, `management` (each dashed with its own color, dash rhythm, and legend entry), `event` (an asynchronous message to a queue, topic or event bus: long dashes, open arrow), and `connectivity` (a network link such as peering, VPN, Direct Connect or a transit attachment: heavy solid line without arrows). Association has no arrowhead either. Arrows express the documented request/transfer direction, not every response packet. Keep each edge label to a short single line: about 228 px of text at 11 px, drawn in a box of up to 244 px.

Ports accept `top`, `bottom`, `left`, `right`, or `auto` (the default). Offsets are fractions from `0.1` through `0.9` along the selected side: left-to-right on top/bottom, top-to-bottom on left/right. For example:

```json
{
  "id": "gateway-app-a", "source": "gateway", "target": "app-a",
  "kind": "traffic", "label": "HTTPS",
  "sourcePort": "bottom", "sourceOffset": 0.35,
  "targetPort": "top", "priority": 0
}
```

Automatic allocation separates incoming and outgoing connections on each card side and respects explicit offsets. Explicit offsets on one side must be at least the automatic spacing apart (10 px on a standard card); offsets that coincide or nearly coincide, or an overcrowded side, fail with a remedy. Connections attach to the entire resource card. `priority` is a finite number; smaller values route earlier. Default categories are traffic 0, egress 1, replication 2, DNS 3, association 4, management 5, event 6, connectivity 7, followed by endpoint distance and stable edge ID. Changing the order of the edge array does not change routes. See [routing](routing.md) for algorithm limits and editing guidance.

The current compiler handles edges between nodes and network boundaries, not self-loops, edge-to-edge junctions, shared buses, or user-specified waypoint arrays. Preserve those relationships with native XML when necessary; do not approximate them by overlapping unrelated lines.

## Validation and output

`validate` checks structure, unknown keys, text budgets, reserved page bands, containment against the drawn geometry, icon consistency, and selected provider rules. `build` additionally allocates ports, routes every edge, and places every label; inability to do so is an error, as is a route that would double back on itself, for example between facing card sides closer than 2 × `stub`. This is not a reachability proof: route tables, SG/NSG/firewall policy, service configuration, and DNS may require a separate view.

Layout is template-driven; resources are not automatically rearranged. Add an AZ by widening the canvas/VPC and updating group spans, not shrinking all text. Routes can change when geometry, IDs, ports, or priorities change. The output stores explicit orthogonal waypoints and fixed connection fractions. Labels are editable relative child cells of their edge, so they retain their edge association through edits and save/reopen; inspect their placement after manual changes.

`bundle OUT MODEL...` validates every model, then writes one `.drawio` with a page per model (`page-1`, `page-2`, ...) and one report whose `pages` array holds each page's report; errors are prefixed with their page number.

`pull EDITED MODEL [--output OUT] [--page N]` reads a compiled page after manual draw.io edits, from a `.drawio` (also compressed or with cells wrapped for links and data) or from a `*.drawio.png`/`*.drawio.svg` with an embedded diagram. It returns the model with changed positions, sizes, parents, connector ends and texts. Coordinates are written in the model's own frame, before the page shift above. Shapes within 0.5 px of their planned box keep `col`/`row` and `"fit"`; a moved card loses `col`/`row` for absolute `x`/`y`, and a moved or resized fitted box gets absolute numbers. The pulled model is then resolved again: a fitted or matched box that would land elsewhere, or that lost its last child, gets its drawn numbers (`pinned`); if that cannot reproduce the drawing, for example after moving the top-most card of an `auto` canvas, every shape gets its drawn geometry and the canvas its size (`layout: "absolute"`). Edited text where the compiler wrapped lines keeps the original spaces. It never adds or removes model items: the summary lists `moved`, `resized`, `reparented`, `relabelled`, `reconnected`, `pinned`, `missing`, `unmodelled` and `ignored`, the `layout`, and validation `errors` of the result. A page that matches the model worse than another page of the file is refused with the page to use.

`build PATH` writes `PATH` and `PATH` with a `.report.json` suffix, each atomically. If `PATH` exists and its hash differs from `drawio_sha256` in that report (a manual draw.io edit), or the report is missing, `build` stops instead of discarding the edits; `--force` overwrites deliberately. Reports from version 2 carry no hash and do not block a rebuild.

`.report.json` version 3 includes `model_sha256`, `drawio_sha256`, `routing` (the routing mode that succeeded), `routes`, `labels`, `quality`, `warnings`, and `errors`. Label data records its rectangle, relative position, and offset. Quality records `crossingCount`, `overlapLength`, `bendCount`, `totalLength`, plus individual crossing/overlap locations. A route that would meet itself, or a connector whose port lies on another connector, is a build error instead of a metric. Crossings produce warnings for visual review. These metrics do not measure cloud correctness or guarantee the clearest possible layout.
