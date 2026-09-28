# Google Cloud placement and connections

- Project is an ownership boundary. Shared VPC separates host-project network ownership and service-project workloads; don't collapse them if that relationship matters.
- VPC network is global. Subnets are regional, compute instances are zonal. A region inside a VPC is a visual slice of the network; it does not mean the network owns the geographical region.
- Do not give GCP subnets AWS's zonal scope or assume public/private labels alone determine reachability. External IPs, routes, firewall policies and access configuration matter.
- Distinguish regional/global load-balancer modes. Cloud Armor is a security policy association, not a separate packet-forwarding appliance.
- Name the chosen load-balancer variant in the diagram. The bundled example uses a global external Application Load Balancer; its edge placement must not be copied to a regional mode without reviewing that mode's scope and subnet requirements.
- Cloud NAT/Cloud Router are managed networking services; do not imply a Cloud Router VM is an inline data-plane hop.
- Private Service Connect endpoint and the managed service are different objects. Cloud SQL private connectivity modes differ; document whether using PSC or private services access, not an invented customer-subnet database instance.
- The regional template uses PSC for Cloud SQL and illustrative PostgreSQL ports; verify the real service mode and attachment before applying it to an existing deployment.

Sources checked 2026-09-24:
- https://docs.cloud.google.com/vpc/docs/subnets
- https://docs.cloud.google.com/compute/docs/regions-zones/global-regional-zonal-resources
- https://docs.cloud.google.com/architecture/network-application-delivery
- https://cloud.google.com/icons

Additional check 2026-09-28:
- https://docs.cloud.google.com/load-balancing/docs/https
