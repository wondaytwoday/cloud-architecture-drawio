# Behavioral scenarios

1. Recreate the supplied AWS visual style: two AZ columns, web/app/db tiers, ASG overlays, CSP icons and editable connections. Treat the input image as a stylistic reference; state missing network details rather than inventing an existing deployment.
2. Draw Azure VMs in two zones using a shared regional subnet, Application Gateway, and SQL via Private Endpoint. The endpoint and SQL service must be separate objects.
3. Draw GCP zonal compute in regional subnets in a global VPC, accessing Cloud SQL via PSC. Do not use an AWS-style AZ/subnet hierarchy.
4. Extend AWS application compute to three AZs while retaining a two-AZ primary/standby database. Keep existing IDs; do not invent a third DB standby.
5. Produce the AWS diagram in Korean. Preserve CSP product names, make role and boundary labels Korean, and inspect text wrapping at normal size.
6. Reject intentionally invalid models: missing icons, dangling edges, duplicate IDs, cycles, resource overlap, unreasonably long labels, incorrect regional/zonal subnet scope, managed SQL inside endpoint subnet, and a card covering a container title.

The implementation author executed these fixtures locally. This is not an independent-agent benchmark or a claim of universal cloud-design correctness.
