# Render and inspect

Preferred: installed draw.io Desktop, export the generated file to PNG. Check `drawio --help` on the actual installed version. Typical export:

```sh
drawio --export --format png --output architecture.png architecture.drawio
```

On macOS the executable is normally `/Applications/draw.io.app/Contents/MacOS/draw.io`. Keep the editable `.drawio` source.

## Actual draw.io viewer fallback

`scripts/render.cjs` uses the actual draw.io `Graph`/`mxCodec`, with Playwright. It is not an independent mock renderer. Requires Node.js, Playwright, an installed compatible Chromium, and a locally downloaded viewer bundle.

```sh
npm install --prefix /tmp/cloud-diagram-runtime playwright
/tmp/cloud-diagram-runtime/node_modules/.bin/playwright install chromium
curl -L --fail https://viewer.diagrams.net/js/viewer-static.min.js -o /tmp/viewer-static.min.js
NODE_PATH=/tmp/cloud-diagram-runtime/node_modules node scripts/render.cjs architecture.drawio architecture.png /tmp/viewer-static.min.js
```

Use an existing available Playwright installation instead of installing again. `CHROME_PATH` can specify an existing browser executable. Follow host permission rules for installation/download. The renderer blocks all browser network requests after loading the local bundle; diagram content and embedded icons stay local. The viewer URL is mutable: record its SHA-256 in evaluation reports for reproducibility.

Outputs PNG, standalone SVG preview and `.render.json`. The `.drawio` is the editable master; the SVG is a preview, not an alternative source model. Inspect PNG with the environment's image-view tool, and open the `.drawio` in a compatible editor for an editability check when available. Missing icons and JavaScript errors fail rendering. Visual judgment is still required even when the render report is clean.

When the compiler's matching `.report.json` is next to the input, the renderer compares every rendered connector's vertices and attached caption rectangle with the planned geometry. It permits 0.51 px for caption anchors, which mxGraph rounds to screen pixels. Keep the report paired with the exact `.drawio`; a stale report will correctly fail this comparison.

The render report also records actual jump markers, broken embedded images, and an editability check: move and restore a connected resource, translate a labeled connector together with its endpoints/waypoints and confirm its caption follows, then serialize and reopen the model to check source/target references and relative caption parents. These are model-level tests in the real draw.io engine, not a claim that the desktop editor UI was manually tested. A fixture without captions reports `labelFollow: null` because that check does not apply.

For diagrams with reported crossings, inspect the PNG at the listed coordinates and verify an arc appears. Jump markers clarify independent crossing paths; they are not branch junctions. Shape/label collision checks and rendering do not prove network reachability.
