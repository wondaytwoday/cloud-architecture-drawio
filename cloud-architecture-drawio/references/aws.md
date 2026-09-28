# AWS placement and connections

- Scope account, Region, VPC, AZ, subnet separately. VPC is regional; every subnet belongs to one AZ. AZ boxes inside the VPC are a view of that VPC's zonal placement, not a claim that an AZ belongs exclusively to it.
- Route 53 and CloudFront are outside VPC subnets. An S3 bucket is not deployed into your subnet. Show a gateway/interface endpoint separately when private access is relevant.
- Specify ALB/NLB and public/internal intent. One logical load balancer may attach to multiple subnets; a central icon represents one service, not an extra AZ. Add subnet attachments in a detailed view.
- NAT is outbound connectivity, not the entry point for public client requests. A zonal NAT example is not a universal rule for every NAT deployment mode. Include IGW and routes in an egress view if requested.
- WAF Web ACL is associated with the protected supported service; do not route DNS or packets through a standalone WAF appliance unless documenting a different actual product.
- Show RDS primary/standby separately from read replicas. Do not send reads to a standby by default. The sample assumes a traditional Multi-AZ DB instance, not a Multi-AZ DB cluster.
- EFS is a regional service with zonal mount targets. If drawing network endpoints, show mount targets in subnets; do not equate the EFS service icon with a single zonal server.
- ASG is logical membership across AZs, not a subnet containing other subnets. Security groups are policies, not additional mandatory routing hops.

Sources checked 2026-09-24:
- https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html
- https://docs.aws.amazon.com/waf/latest/APIReference/API_AssociateWebACL.html
- https://aws.amazon.com/architecture/icons/

For service variants not covered here, verify current provider documentation before asserting placement or connectivity.
