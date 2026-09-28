# Asset provenance and extension

The bundled catalog is a **curated subset**, not every CSP product and not a promise of the newest marketing icon family. AWS uses draw.io `aws4` vector stencils, GCP uses its established `gcp2` family, and Azure uses `azure2` SVGs. Do not mix another icon generation into one diagram without intentionally migrating the diagram's catalog.

Source: `jgraph/drawio`, commit `82af434539c3449d99275b91a91b6b99998a7d58`, retrieved 2026-09-24. Every catalog entry records its source URL and local asset SHA-256. Original vector path data is retained; AWS stencil color is selected by the catalog. SVG colors are preserved. `assets/icons/LICENSE.drawio.txt` contains the upstream Apache 2.0 license. Provider marks remain subject to their respective icon/brand terms; this catalog does not grant additional trademark rights.

Official icon terms and downloads:
- https://aws.amazon.com/architecture/icons/
- https://learn.microsoft.com/en-us/azure/architecture/icons/
- https://cloud.google.com/icons

For an unsupported service:
1. Prefer the exact official SVG or a verified matching draw.io stencil. Search official draw.io MCP `search_shapes` if available; never invent a stencil ID.
2. Save the vector in `assets/icons/`. Add a provider-prefixed key to `assets/icon-catalog.json` with `file`, `kind` (`svg` or `stencil`), `name`, `source`, `sha256`, and optional stencil `color`.
3. Do not introduce remote image URLs, external SVG fonts/images, scripts, or an arbitrary PNG masquerading as a vector. Inspect and render new assets before use.
4. If an exact icon cannot be obtained, use a clearly labeled `generic` system box and disclose the fallback. Use `generic.user` only for people/clients, not network endpoints.

Embedded stencils use draw.io's native compressed stencil format. SVGs become embedded data images. Both remain independent editable objects, although an SVG's internal vector paths are not separate draw.io cells.
