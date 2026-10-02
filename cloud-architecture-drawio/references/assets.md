# Asset provenance and extension

The bundled catalog is a **curated subset** (93 icons), not every CSP product and not a promise of the newest marketing icon family. AWS uses draw.io `aws4` vector stencils, GCP uses its established `gcp2` family, Azure uses `azure2` SVGs, and provider-neutral `generic.*` glyphs (server, on-premises site, mobile, desktop, internet, firewall, router, storage) come from draw.io's `networks` stencils. Every entry is shown in `evals/fixtures/icon-gallery.png`. Do not mix another icon generation into one diagram without intentionally migrating the diagram's catalog.

Source: `jgraph/drawio`, commit `82af434539c3449d99275b91a91b6b99998a7d58`, retrieved 2026-09-24. Every catalog entry records its source URL and local asset SHA-256. Original vector path data is retained; AWS stencil color is selected by the catalog. SVG colors are preserved. `assets/icons/LICENSE.drawio.txt` contains the upstream Apache 2.0 license. Provider marks remain subject to their respective icon/brand terms; this catalog does not grant additional trademark rights.

Official icon terms and downloads:
- https://aws.amazon.com/architecture/icons/
- https://learn.microsoft.com/en-us/azure/architecture/icons/
- https://cloud.google.com/icons

Each catalog entry may set `placement`, which drives the linter: `managed` (the service itself never sits in a subnet or AZ; draw its private endpoint separately), `policy` (associated with what it protects, hosts nothing), `network` (attached to a VPC/network, not one subnet), or `subnet` (takes an address in its subnet). Leave it out for services with both subnet-hosted and managed modes.

For an unsupported service, use `scripts/add_icon.py`. It downloads the libraries of the pinned commit once (cached under `$CLOUD_DRAWIO_CACHE` or `~/.cache/cloud-architecture-drawio`), so ask before the first download where that is required:

```sh
python3 scripts/add_icon.py search aws4 dynamodb
python3 scripts/add_icon.py add aws.dynamodb --from aws4:dynamodb --color '#C925D1' --placement managed
python3 scripts/add_icon.py search azure2 cosmos
python3 scripts/add_icon.py add azure.cosmosdb --from azure2:databases/Azure_Cosmos_DB.svg --placement managed
```

1. Search the library of the diagram's provider (`aws4`, `gcp2`, `azure2`, or `networks` for `generic.*`) and confirm the product against the official icon pages above; never invent a stencil name.
2. `add` writes the normalized stencil or the unmodified SVG to `assets/icons/` and a catalog entry with a commit-pinned `source`, its `sha256`, and for stencils the `color` you give (use the provider's category colour; AWS: compute/containers `#ED7100`, database `#C925D1`, networking/analytics `#8C4FFF`, security `#DD344C`, integration/management `#E7157B`, storage `#7AA116`; GCP `#4285F4`). It parses every icon before writing it and refuses DOCTYPE or entity declarations, script, foreignObject and other active elements, `on*` event attributes, `@import`, and any `href`, `src` or `url()` that leaves the file; only `#fragment` references and inline PNG, JPEG, GIF or WebP data are allowed. The built-in keys `generic` and `generic.user` cannot be replaced.
3. Render `evals/gallery.py` output or the diagram and inspect the new icon. In the source repository, regenerate the gallery, run the tests, and rebuild the release with `python3 tools/build_dist.py`.
4. If no exact icon exists, use a clearly labeled `generic` system box and disclose the fallback; builds list such nodes under `fallbackIcons`. Use `generic.user` only for people/clients, not network endpoints.

Embedded stencils use draw.io's native compressed stencil format. SVGs become embedded data images. Both remain independent editable objects, although an SVG's internal vector paths are not separate draw.io cells.
