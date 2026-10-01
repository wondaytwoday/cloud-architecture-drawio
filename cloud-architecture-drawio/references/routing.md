# Connector routing and verification

Treat topology and presentation separately. A prettier line must not change which service calls which service, turn DNS resolution into request traffic, or imply a new network hop. Use stable resource/edge IDs and preserve each edge's semantic kind.

## Prepare space and ports

Align repeated tiers before routing. Reserve corridors between cards and alongside subnet columns; 40 px is a starting point, not enough for every labeled fan-out. Put shared services outside the main columns. Place logical-group titles in empty gaps with `labelAlign` or a left-aligned `labelOffset`.

An edge leaves and enters a chosen card side through fixed connection fractions. The compiler distributes all incoming and outgoing endpoints together, with roughly 20 px preferred spacing. Explicit `sourceOffset`/`targetOffset` values reserve their positions; other attachments avoid them. Explicit offsets on one side must keep the same minimum spacing as automatic ones (10 px on a standard card), because two lines a pixel or two apart read as a single branching line. Use explicit sides and offsets to keep a fan-out ordered. If a side is crowded, enlarge the card or move some connections to another side.

`routing.clearance` (default 8 px) pads unrelated resource cards. `routing.stub` (default 16 px) creates a short outward segment before the first bend and after the last bend. A blocked stub means the lane or port choice needs changing. When two connected sides face each other on the same line, they need at least 2 × `stub` (32 px by default) between them; otherwise the two lead-ins overlap and the build fails. A route never touches its own lead-ins except where it joins them, and a connector whose port lies on another connector fails the build because the arrowhead would read as a junction. A stub may not enter the 10 px side margin, the 80 px title band, or the 90 px footer, so cards connected through a side facing one of these bands need `stub` px of clearance from it. Do not set clearance to zero simply to squeeze a line against a label.

## What the bundled router does

`cloud_routes.py` implements sequential orthogonal A* routing on a sparse grid derived from obstacles and existing paths. It preserves resource positions. Primary traffic routes first by default; distance and ID break ties. Numeric edge `priority` can change this order. It penalizes bends, crossings, and tightly spaced parallel paths, and rejects shared collinear segments. This is deterministic routing with heuristics, not a global optimum or a libavoid integration.

Ports are chosen before routing, so every connector's lead-ins are known in advance. Lead-ins of connectors not yet routed are reserved: an earlier connector may not overlap them or end on them, which removes most blocked lead-ins and the crossings next to cards. Lines also pay extra for running within 8 px of a container border, so they do not read as part of the boundary. When captions do not fit, the router retries with parallel runs spread apart (horizontal neighbours within 40 px, vertical within 60 px), which opens caption lanes in fan-outs. Each of these adds constraints, so the build tries 12 modes in turn: with reservation, then without; within each, without spreading, then with it; within those, with border clearance, then without. Reserved modes first try without extra grid lanes beside the reserved lead-ins, then with them. `.report.json` records the mode that succeeded under `routing`. When every mode fails, the error comes from the attempt that got furthest: one that routed everything and missed the fewest captions. All modes share a budget of 1.5 million search steps, counted rather than timed so results do not depend on the machine; a very large diagram that exhausts it stops early with a note to split the view.

Resource cards and boundary-title rectangles are obstacles. Enclosing VPC/VNet/subnet boxes remain traversable, because a network boundary is not a solid visual wall. The router does not check whether crossing that boundary is permitted by network policy. Failure to find a separated route raises an error instead of silently drawing through an obstacle.

Only after every path exists does the compiler place labels. Candidate positions lie about every 6 px along each qualifying segment, plus its midpoint and fixed fractions, ranked by closeness to the middle of the route. A caption first looks for a spot that stays within its own segment and keeps 8 px from other connectors, so it cannot read as their label; failing that, it relaxes those wishes one at a time. Candidate captions must avoid all routes, resource cards, title rectangles, previously placed labels, and container borders. If none fits, the build fails and lists every such edge with the caption size, its longest segment, and the shapes that block the best positions. A caption is drawn in a box of its text width + 16 px by 22 px, placed above or below a horizontal segment or beside a vertical one; only segments of at least 24 px qualify. The box, padded about 4 px, must clear cards, routes, other captions, titles, and container borders. A straight horizontal connector between side-by-side cards therefore needs a gap of more than its text width + 24 px, while a vertical connector between stacked cards needs only the 2 × `stub` gap plus caption-width room beside the line. Labels become relative children of their edge, with a measured offset, rather than independent canvas text.

Explicit route vertices are written to native draw.io XML with fixed entry/exit fractions and `jumpStyle=arc`. The file remains editable, but arbitrary manual moves may require rerouting and renewed label checks.

## Crossings and junctions

A crossing joins nothing. Keep perpendicular crossings away from labels and bends; inspect the actual draw.io render to confirm that its arc is visible. The style declaration alone is insufficient evidence. Use jump arcs for a small number of clear residual crossings after reasonable lane/port adjustments.

A junction intentionally joins relationships. draw.io supports waypoint **shapes** that serve as connector terminals; these are different from bend waypoints on an edge. The bundled model does not currently represent junctions or shared buses. For a topology that needs them, author native XML with explicit junction cells and attachments, explain what the junction means, and preserve that manual source. Do not simulate a bus by placing independent edges on the same coordinates. A shared visual branch must not invent a load balancer, router, queue, or other resource.

## Review and repair

Read `.report.json` together with the rendered image:

| Measure | Interpretation and action |
| --- | --- |
| `overlapLength` | Shared collinear path length in pixels. Expect zero for separate model edges. |
| `crossingCount` | Perpendicular intersections between edge pairs, excluding a common terminal shared by both paths. Review every reported location; the metric includes T contacts. |
| `bendCount` | Total direction changes. Long detours or many short bends may justify different ports. |
| `totalLength` | Total Manhattan path length. Compare revisions of the same topology; shorter alone is not better. |

Repair in this order: choose a better card side; reorder explicit port offsets; widen the corridor or move a shared service; relocate an overlay title; adjust edge priority; split overview and detailed traffic into separate diagrams. The compiler writes one page per file. If one file is required, first render each built file with its own report, then combine the pages in draw.io and render each page of the combined file with `--page N --no-report`; the combined file matches no compiler report. Rebuild and render after meaningful changes. Never remove requested edges just to reach zero crossings, and never claim that zero crossings proves architectural correctness.

The reported geometry uses underlying polylines. Rendered arrowheads, jump arcs, font metrics, and edit behavior still need actual draw.io inspection. The bundled renderer compares actual route/label positions with the report, checks relative-label parents, and temporarily translates a labeled edge with its endpoints/waypoints to verify label movement before restoring it. Keep source/target and label associations intact through save/reopen. See [rendering](rendering.md) for verification details and limitations.

## Primary references

- [Connector waypoints](https://www.drawio.com/docs/manual/connectors/waypoints-connectors/) explains changing paths with bends and distinguishes crossing from joining.
- [Waypoint shapes](https://www.drawio.com/docs/manual/shapes/waypoint-shape/) and [aligned connectors](https://www.drawio.com/blog/aligned-connectors/) describe explicit branch attachment points.
- [Connector styles](https://www.drawio.com/docs/manual/styles/connector-styles/) documents orthogonal paths, arrowheads, and line jumps.
- [Diagram style reference](https://www.drawio.com/docs/reference/diagram-generation/style-reference/) is the native XML style reference for manual extensions.
- [draw.io routing implementation notes](https://raw.githubusercontent.com/jgraph/drawio/dev/docs/claude/libavoid-routing.md) informed fixed-port constraints, outward stubs, obstacle buffers, and treatment of enclosing containers. The bundled Python router uses its own implementation; upstream libavoid features are not automatically available here.
