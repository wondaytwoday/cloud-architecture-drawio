# Render and inspect

Verify with `scripts/render.cjs`. It renders the actual mxGraph model with draw.io's own `Graph`/`mxCodec` in Playwright, writes the PNG, and checks the result; it is not an independent mock renderer. draw.io Desktop export produces a PNG but performs none of these checks, so use it only for a final image when the verifying renderer has already passed:

```sh
drawio --export --format png --output architecture.png architecture.drawio
```

On macOS the Desktop executable is normally `/Applications/draw.io.app/Contents/MacOS/draw.io`. Keep the editable `.drawio` source.

## Verifying renderer

Requires Node.js, Playwright, an installed compatible Chromium, and a locally downloaded viewer bundle.

```sh
npm install --prefix /tmp/cloud-diagram-runtime playwright
/tmp/cloud-diagram-runtime/node_modules/.bin/playwright install chromium
curl -L --fail https://viewer.diagrams.net/js/viewer-static.min.js -o /tmp/viewer-static.min.js
NODE_PATH=/tmp/cloud-diagram-runtime/node_modules node scripts/render.cjs architecture.drawio architecture.png /tmp/viewer-static.min.js
```

Use an existing available Playwright installation instead of installing again. The viewer path may also come from `$DRAWIO_VIEWER`, and `CHROME_PATH` can specify an existing browser executable. Follow host permission rules for installation/download. The renderer blocks all browser network requests after loading the local bundle; diagram content and embedded icons stay local. The viewer URL is mutable: `.render.json` records the viewer's SHA-256, the Playwright version, and the input's SHA-256 for reproducibility.

```
node scripts/render.cjs INPUT.drawio OUTPUT.png [VIEWER.js] [--report REPORT.json | --no-report] [--page N]
```

The output must end in `.png`; the SVG preview and `.render.json` are written beside it with the same base name. The SVG has an opaque white page background so it stays readable in dark viewers. The `.drawio` is the editable master; the SVG is a preview, not an alternative source model. `--page N` renders one page of a multi-page file (default 1); each page is decoded on its own. A compiler report describes one built single-page file, so a combined multi-page file needs `--no-report`. The page background follows the model's `background` (white when none), and a missing page size falls back to draw.io's 850 × 1100 page grown to the content. Any `.render.json` from an earlier run is deleted first, so the three outputs always come from the same run.

## What fails a render

The process exits 1 when any of these holds:

- the compiler report is missing, or it is stale: its `drawio_sha256` differs from the input file, which means the `.drawio` changed after `build`;
- a rendered connector's vertices or caption rectangle differ from the planned geometry, or the report covers fewer connectors than the page has;
- a crossing listed in the report has no draw.io jump arc at that point;
- text is clipped: a card title or detail, the page title, subtitle, notes or a legend caption overflow their box, or a connector caption, legend caption or boundary title wraps beyond its explicit lines;
- a shape or connector lies outside the page, where the PNG and SVG would cut it off;
- an icon does not resolve offline: compiler icons and embedded `stencil(...)` shapes must draw, and draw.io library shapes such as `shape=mxgraph.aws4.*` or `resIcon=` fail because their libraries are not loaded (embed the stencil instead);
- an embedded image fails to load, the page throws a JavaScript error, or the editability round trip fails.

The report is found next to the input with the compiler's naming (`a.drawio` → `a.report.json`); `--report PATH` points elsewhere. For a manually patched `.drawio`, pass `--no-report`: the planned geometry no longer applies, so routes, labels and jump arcs are not compared, but icons, page bounds, images, text clipping and JavaScript errors are still checked. Editability is checked when the page has compiler-built resources; otherwise `.render.json` records a warning that it was skipped. Caption anchors may differ by 0.51 px, which mxGraph rounds to screen pixels.

The render report also records actual jump markers and an editability check: move and restore a connected resource, translate a labeled connector together with its endpoints/waypoints and confirm its caption follows, then serialize and reopen the model to check that every connected edge keeps its source and target and every caption its relative parent. Free annotation arrows without terminals are allowed. These are model-level tests in the real draw.io engine, not a claim that the desktop editor UI was manually tested. A fixture without captions reports `labelFollow: null` because that check does not apply.

## Visual inspection

Visual judgment is still required even when the render report is clean. Inspect the PNG with the environment's image-view tool, both the whole page and dense crops, and open the `.drawio` in a compatible editor for an editability check when available. Jump markers clarify independent crossing paths; they are not branch junctions. Shape/label collision checks and rendering do not prove network reachability.
