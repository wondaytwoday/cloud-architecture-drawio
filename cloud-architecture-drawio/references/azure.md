# Azure placement and connections

- Subscription/resource group are management scopes, not network boundaries. A resource group's location does not force every resource into that location.
- VNet and subnets are regional and span availability zones. Do not copy the AWS subnet-per-AZ hierarchy. Keep VM zone labels on resources or use an availability overlay.
- Private Endpoint has an IP in a subnet; the target SQL/Storage service does not thereby move into that subnet. Draw endpoint and target separately.
- Distinguish inbound Private Endpoint from outbound VNet integration. App Service integration is not evidence of a whole App Service instance living in that subnet.
- Front Door is an edge service outside VNet. Application Gateway uses its subnet. Show WAF policy association at the actual enforcement service.
- Application Gateway requires a dedicated subnet. Label it `App Gateway subnet`; avoid the reserved VPN gateway name `GatewaySubnet`. Do not put application VMs in its subnet.
- NSGs and UDRs are controls/route configuration, not generic inline appliances. Make actual Azure Firewall/NVA inspection paths explicit when relevant.

Sources checked 2026-09-24:
- https://learn.microsoft.com/en-us/azure/networking/design-guide/vnets-subnets
- https://learn.microsoft.com/en-us/azure/well-architected/architect-role/design-diagrams
- https://learn.microsoft.com/en-us/azure/architecture/icons/

Additional check 2026-09-28:
- https://learn.microsoft.com/en-us/azure/application-gateway/configuration-infrastructure
