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
curl -L --fail https://raw.githubusercontent.com/jgraph/drawio/82af434539c3449d99275b91a91b6b99998a7d58/src/main/webapp/js/viewer-static.min.js -o /tmp/viewer-static.min.js
NODE_PATH=/tmp/cloud-diagram-runtime/node_modules node scripts/render.cjs architecture.drawio architecture.png /tmp/viewer-static.min.js
```

For repeated use, install once into the cache that `cloud_drawio.py check` searches (`~/.cache/cloud-architecture-drawio`, or `$CLOUD_DRAWIO_CACHE`), with the Playwright version the examples were verified with:

```sh
npm install --prefix ~/.cache/cloud-architecture-drawio playwright@1.61.1
~/.cache/cloud-architecture-drawio/node_modules/.bin/playwright install chromium
curl -L --fail https://raw.githubusercontent.com/jgraph/drawio/82af434539c3449d99275b91a91b6b99998a7d58/src/main/webapp/js/viewer-static.min.js -o ~/.cache/cloud-architecture-drawio/viewer-static.min.js
```

`check` also honours `NODE_PATH` and `$DRAWIO_VIEWER`, and writes the PNG next to the `.drawio`. Use an existing available Playwright installation instead of installing again. The viewer path may also come from `$DRAWIO_VIEWER`, and `CHROME_PATH` can specify an existing browser executable. Follow host permission rules for installation/download. The renderer blocks all browser network requests after loading the local bundle; diagram content and embedded icons stay local. The setup helper pins the official viewer commit and verifies its SHA-256. `.render.json` records the viewer's SHA-256, the Playwright version, and the input's SHA-256 for reproducibility.

```
node scripts/render.cjs INPUT.drawio OUTPUT.png [VIEWER.js] [--report REPORT.json | --no-report] [--page N] [--embed]
```

The output must end in `.png`; the SVG preview and `.render.json` are written beside it with the same base name. The SVG has an opaque white page background so it stays readable in dark viewers. The `.drawio` is the editable master; the SVG is a preview, not an alternative source model. `--page N` renders one page of a multi-page file (default 1); each page is decoded on its own. A report written by `bundle` covers every page, and the renderer compares page N against its entry; any other multi-page file needs `--no-report`.

`--embed` stores the `.drawio` XML inside both previews: a `tEXt` chunk named `mxfile` in the PNG and the `content` attribute of the SVG, the forms draw.io reads when such a file is opened or imported. Name the output `*.drawio.png` so draw.io and file browsers recognise it. The renderer reads both files back with draw.io's own PNG decoder and fails unless each yields the exact source; `.render.json` records the result as `embedded`. An embedded preview carries the full diagram text, so share it only where the source may go. The page background follows the model's `background` (white when none), and a missing page size falls back to draw.io's 850 × 1100 page grown to the content. Any `.render.json` from an earlier run is deleted first, so the three outputs always come from the same run.

## What fails a render

The process exits 1 when any of these holds:

- the compiler report is missing, or it is stale: its `drawio_sha256` differs from the input file, which means the `.drawio` changed after `build`;
- a rendered connector's vertices or caption rectangle differ from the planned geometry, or the report covers fewer connectors than the page has;
- a crossing listed in the report has no draw.io jump arc at that point;
- text is clipped: a card title or detail, the page title, subtitle, notes or a legend caption overflow their box, or a connector caption, legend caption or boundary title wraps beyond its explicit lines;
- a shape or connector lies outside the page, where the PNG and SVG would cut it off;
- an icon does not resolve offline: compiler icons and embedded `stencil(...)` shapes must draw, and draw.io library shapes such as `shape=mxgraph.aws4.*` or `resIcon=` fail because their libraries are not loaded (embed the stencil instead);
- an embedded image fails to load, the page throws a JavaScript error, or the editability round trip fails;
- with `--embed`, either preview does not give back the exact `.drawio` source.

The report is found next to the input with the compiler's naming (`a.drawio` → `a.report.json`); `--report PATH` points elsewhere. For a manually patched `.drawio`, pass `--no-report`: the planned geometry no longer applies, so routes, labels and jump arcs are not compared, but icons, page bounds, images, text clipping and JavaScript errors are still checked. Editability is checked when the page has compiler-built resources; otherwise `.render.json` records a warning that it was skipped. Caption anchors may differ by 0.51 px, which mxGraph rounds to screen pixels.

The render report also records actual jump markers and an editability check: move and restore a connected resource, translate a labeled connector together with its endpoints/waypoints and confirm its caption follows, then serialize and reopen the model to check that every connected edge keeps its source and target and every caption its relative parent. Free annotation arrows without terminals are allowed. These are model-level tests in the real draw.io engine, not a claim that the desktop editor UI was manually tested. A fixture without captions reports `labelFollow: null` because that check does not apply.

## Visual inspection

Visual judgment is still required even when the render report is clean. Inspect the PNG with the environment's image-view tool, both the whole page and dense crops, and open the `.drawio` in a compatible editor for an editability check when available. Jump markers clarify independent crossing paths; they are not branch junctions. Shape/label collision checks and rendering do not prove network reachability.

## Environment diagnosis and bounded rendering

`python3 scripts/doctor.py` prints JSON for Python, Node, Playwright/browser availability and the viewer hash. `--smoke` renders the Azure template in a temporary directory. `--setup` downloads Playwright 1.61.1, Chromium and the draw.io viewer to the user cache (no repository icon bundle expansion); Node/npm must already exist. Linux may need `playwright install-deps chromium` through the system package manager. Windows users can use WSL or the manual setup above. The setup helper pins official draw.io commit `82af434539c3449d99275b91a91b6b99998a7d58` and verifies SHA-256 `ee0c444be46c95dc1842999f133c92598fe43e7cdf279f7095d0f057c48771b1` before writing the cache. `renderer-provenance.json` records the source and digest. This avoids a 403 response observed from the hosted viewer CDN in GitHub CI. The [official self-hosted viewer guide](https://www.drawio.com/docs/integrations/atlassian/confluence/customise/configure-javascript-viewer-drawio-confluence-server/) documents using the repository bundle.

`check --timeout 120` limits the renderer subprocess. Standalone `render.cjs --timeout 120` also has a watchdog. `check` failures, including malformed model JSON, I/O failures and timeouts, produce a JSON verdict. A completed build with unavailable rendering remains exit 2 and is not visual approval.
