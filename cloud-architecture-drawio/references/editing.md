# Manual edits and incremental revisions

Keep the edited drawing and its matching model together. Work into new files until the pull summary and render have been reviewed.

```sh
python3 scripts/cloud_drawio.py pull edited.drawio original.json --output pulled.json
python3 scripts/cloud_drawio.py check pulled.json revised.drawio --timeout 120
```

`pull` also reads embedded `.drawio.png` and `.drawio.svg`; use `--page N` for a bundle. The summary is JSON on stderr. `safeToRebuild` is false when validation fails or `ignored`, `missing`, or `unmodelled` is nonempty. Never treat exit 0 alone as proof of lossless import. Keep unsupported edits in the authoritative XML or explicitly resolve them before replacing the drawing. The tool recognizes compiler-owned IDs; arbitrary imported diagrams require native XML editing or a separately reviewed reconstruction.

Supported edits: resource/boundary position, size, parent, text, modelled connector terminals, page text, notes and legend; allowed style properties; explicit orthogonal connector bends with fixed cardinal attachments. Generated icon or caption moves, curved/automatic paths, loose terminals, new/deleted model resources, wrapper links/tooltips, custom cell attributes and unknown styles are reported rather than silently presumed safe. Deleting a connector caption is supported. Reconnecting a terminal without changing bend geometry requests automatic rerouting and is listed under `rerouted`.

## Presentation overrides

Top-level `presentation` maps actual cell IDs to style properties. Resource IDs address their card group; `__icon_ID`, `__name_ID`, `__detail_ID`, and `__label_EDGE_ID` address generated children. Avoid changing icon geometry. Properties allowed:

- Colors: `fillColor`, `strokeColor`, `fontColor`, `labelBackgroundColor`, `labelBorderColor` (hex, `none`, `default`).
- Numbers: `fontSize`, `fontStyle`, `strokeWidth`, `opacity`, `fillOpacity`, `strokeOpacity`, `dashed`, `rounded`, `arcSize`.
- Text: `fontFamily`, `dashPattern`.

Styles remain editable in draw.io. A per-edge color override does not change the global kind legend; the build warns about this. Use a caption, an explicit legend override, or a note so readers can still identify the relationship. Larger fonts can overflow existing cards; actual rendering remains required. Unsupported style changes stay in `ignored`. Property removal is reported because removing an override is different from removing the compiler default.

## Explicit paths

```json
"lockedRoutes": {
  "request": {
    "source": "client", "target": "gateway", "mode": "manual",
    "points": [[256,212],[300,212],[300,350],[600,350],[600,212],[650,212]]
  }
}
```

Points include both endpoints in absolute page coordinates. All segments must be nonzero and orthogonal; endpoints must lie on the resource side between 10% and 90%. Pull pins shape positions to the drawing's absolute frame. Locked routes are reserved before automatic routing. A moved endpoint or new obstacle that makes a manual path invalid fails the build; remove that edge's lock only when rerouting it is intended. Captions are automatically placed on the preserved path; manually moved captions are reported as unsupported.

## Incremental routing

```sh
python3 scripts/cloud_drawio.py build revised.json revised.drawio --reuse original.report.json
```

Version 4 reports store a normalized model snapshot. An unchanged edge with unchanged endpoints and a clear old path can reuse that route. New/moved obstacles invalidate affected paths. The report lists `incremental.retained`, `rerouted` and, if retaining paths prevented a successful layout, `fallbackReason`. A fallback replans automatically retained paths, never manual locks. Legacy reports without snapshots reroute all edges. The same route can still receive a newly placed caption. Incremental routing minimizes avoidable movement; it does not promise globally minimal changes.

For multiple pages, pull each page against its own model, then `bundle` the revised models. Do not replace a bundle with a single-page `build`.
