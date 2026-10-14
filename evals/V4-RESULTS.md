# v4 verification

## Implemented scope

All twelve requested improvements are implemented: unsupported edit reporting, routing/render budgets, structured check errors, supported style/orthogonal route import, incremental reuse, bounded layout proposals, explicit junctions, purpose views, environment doctor/setup, CI/release workflow, semantic diff/highlighting, and provenance inventories.

## Verification

- 159 regression tests passed with no skips on Python 3.14.6, including 15 v4 behavioral tests and actual draw.io rendering (21.886 seconds).
- Existing AWS, Azure and GCP examples and the icon gallery were rebuilt and rendered. Text widths now use integer hundredths to eliminate Python-version-dependent floating-point summation; reports advance to v4 with normalized snapshots and evidence inventories.
- Manual bend/color import → build → pull preserves supported values. Invalid locked routes fail instead of being silently rerouted.
- A one-step routing budget stops inside the first search. Renderer timeout returns a structured failure. Malformed JSON produces a structured `check` failure.
- Incremental tests cover unchanged routes, moved endpoints and newly introduced obstacles.
- Layout repair resolves a fixture with overlapping connector lead-ins without dropping relationships. Source input remains unchanged.
- Explicit junction render: visible filled dot, three editable attached paths, no route overlap/crossing. Intentional attachment is excluded from ambiguous-continuation warnings.
- Purpose views preserve all relationships in overview, list detail omissions, produce an editable bundle, and refuse to overwrite a nonempty destination.
- Diff/evidence tests verify real changes, highlights, missing sources, unconfirmed inference and schema failures.

- `doctor.py --smoke` passed using the existing renderer. Viewer SHA-256: `ee0c444be46c95dc1842999f133c92598fe43e7cdf279f7095d0f057c48771b1`.
- Official skill validation passed. Release ZIP matches tracked skill files; extracted ZIP independently passed icon listing, Azure build and GCP page generation. Final archive remains about 238 KiB.

## Independent forward test

A separate agent used the skill instructions with a synthetic Azure model. It imported a manually colored and bent request connector, added Azure Storage and an upload edge, compared changes, and generated overview/network/application pages.

- Manual color `#AB147F` and bend coordinates remained equal in revised, highlighted and applicable bundled pages.
- Diff identified only the added resource and added edge.
- Unchanged DNS route was retained; new upload route was planned; manual request route remained locked.
- Highlight and all three pages passed actual draw.io rendering and visual inspection.
- Rebuilding over a manually edited source was refused.
- Findings corrected: stale v3 report documentation, obsolete manual page-combination instructions, and missing warning for per-edge color/legend mismatch.

## Practical limits

- Arbitrary draw.io constructs are not fully round-tripped. Unsupported edits are disclosed; keep original XML authoritative when unresolved.
- Manual caption positions, curves, wrapper links and newly hand-drawn resources need explicit handling.
- Repair tries six spacing expansions, not a global layout solver. Locked paths require a deliberate unlock before repair.
- Detail views retain original coordinates; they are not compacted automatically.
- Evidence is author-provided, not verified cloud inventory. No runtime reachability claims follow from the diagram.
- Setup downloads external renderer dependencies only on `--setup`; the official repository viewer is pinned by commit and checked against its SHA-256 before cache replacement. No full CSP icon library is added to the release.
- GitHub workflow execution and an actual tagged release are separate from local verification; no release tag is created by this change.

## Fresh CI environment

The first GitHub run exposed HTTP 403 from the hosted viewer CDN. Setup now downloads the identical viewer bytes from the official repository at a fixed commit and checks the digest. A regression verifies that a wrong digest cannot replace a working cached viewer.

Linux/Python 3.11 CI also exposed float-summation differences in label widths versus Python 3.14. Width estimates now sum integer hundredths; all fixtures and previews were regenerated. The non-Unicode stdout test now forces ASCII output directly, retaining the OS filename encoding rather than selecting a locale unavailable on the runner. Ubuntu 24.04 is pinned for the CI matrix.
