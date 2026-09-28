# Cloud architecture visual rules

These are project presentation conventions, not CSP-mandated dimensions.

- White canvas; muted container backgrounds; saturated provider icons. Minimum icon box 48×48; preserve SVG/stencil aspect ratio. Text defaults to 13 px titles, 11 px detail, 14 px boundary titles.
- Match tier rows across AZ columns. Keep at least 40 px clear lanes between cards; more for several labeled connections. Reserve 34 px for container headers. Subnet labels should say purpose and public/private access model, not only a CIDR.
- Main request path top-to-bottom or left-to-right. Shared services outside the main columns. DNS is resolution, not an inline HTTP hop. Draw protection/policy as associations. Draw replication separately from client reads/writes.
- Keep connectors orthogonal with clear space between parallel paths. Distribute incoming and outgoing ports on the same card side; use fixed offsets when a fan-out needs deliberate ordering. See [routing](routing.md) for controls and failure remedies.
- A crossing means two independent paths; show a visible jump arc. A branch means a shared relationship and needs an explicit junction with documented meaning. Do not disguise separate relationships as one bus to reduce line count.
- Distinguish actual containment (solid boundary) from geography or logical membership (dashed, labeled). A logical group can overlap AZ columns without owning their nodes.
- Draw transparent membership overlays above opaque container backgrounds so a newly added AZ/subnet cannot hide part of a cross-column group boundary. Keep resources and connector captions visible above the overlay.
- Keep overlay titles in an empty gap between resource columns. Use `labelAlign` or a left-aligned `labelOffset` instead of routing through the title. Network boundaries remain traversable by connectors; a boundary crossing alone does not prove permitted traffic.
- Ports/protocols come from input or an explicit assumption. Do not invent numerical ports just to fill labels. Do not imply that two private subnets cannot communicate merely because a box separates them.
- Avoid huge multi-purpose sheets. Split overview, egress/administration, and detailed security policy if routes overwhelm the primary view. Label deliberately omitted paths.
- If long text fails the linter, widen the card and its subnet or shorten the label while keeping full meaning in details/notes. Never silently truncate it or shrink it to unreadable size.
- Edge labels belong to their connectors and occupy a clear lane beside them. Place them after all routes exist; do not mask a crossing or subnet border with a white caption box.
- Compare render to the reference by boundary hierarchy, alignment, icon consistency, main flow clarity and legibility—not pixel copying.

After rendering, inspect both the whole page and dense crops. XML validity is not visual validity. Check crossing locations from `.report.json` against the actual jump arcs. A route can be collision-free and still confusing due to detours or repeated parallel paths; change ports, widen lanes, or split the view. Prefer a small number of clear crossings over a topology change or an unreadable maze of bends.
