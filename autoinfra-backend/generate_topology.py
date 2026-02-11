import os
import json

class TopologyGenerator:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.bicep_dir = os.path.join(output_dir, "bicep")
        self.powershell_dir = os.path.join(output_dir, "powershell")
        os.makedirs(self.bicep_dir, exist_ok=True)
        os.makedirs(self.powershell_dir, exist_ok=True)

    def generate(self, topology):
        nodes = topology.get("nodes", [])
        edges = topology.get("edges", [])

        if not nodes:
            raise ValueError("No nodes provided in the topology.")
        if not edges:
            raise ValueError("No edges provided in the topology.")

        # Validate required fields for domainController nodes
        for node in nodes:
            if node["type"] == "domainController":
                if "adminUsername" not in node["data"] or "adminPassword" not in node["data"]:
                    raise ValueError(f"Node {node['id']} is missing 'adminUsername' or 'adminPassword'.")

        self.generate_bicep(topology)
        self.generate_powershell(topology)

    def generate_bicep(self, topology):
        main_bicep = {
            "targetScope": "subscription",
            "parameters": {},
            "resources": []
        }

        for node in topology["nodes"]:
            if node["type"] == "domainController":
                resource_name = f"{node['id']}-VM"
                main_bicep["parameters"][f"{node['id']}ImageReference"] = {
                    "type": "string",
                    "defaultValue": "/subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Compute/galleries/<gallery-name>/images/<image-name>/versions/1.0.0"
                }
                main_bicep["resources"].append({
                    "type": "Microsoft.Compute/virtualMachines",
                    "apiVersion": "2023-07-01",
                    "name": resource_name,
                    "location": "[parameters('location')]",
                    "properties": {
                        "hardwareProfile": {
                            "vmSize": "[parameters('vmSize')]"
                        },
                        "storageProfile": {
                            "imageReference": {
                                "id": f"[parameters('{node['id']}ImageReference')]"
                            }
                        },
                        "osProfile": {
                            "computerName": node["data"]["domainName"],
                            "adminUsername": node["data"]["adminUsername"],
                            "adminPassword": node["data"]["adminPassword"]
                        }
                    }
                })

        main_bicep_path = os.path.join(self.bicep_dir, "main.bicep")
        with open(main_bicep_path, "w") as f:
            json.dump(main_bicep, f, indent=2)

    def generate_powershell(self, topology):
        for node in topology["nodes"]:
            if node["type"] == "domainController":
                script_content = f"""
param(
    [string]$domainName = "{node['data']['domainName']}",
    [string]$adminUsername = "{node['data']['adminUsername']}",
    [string]$adminPassword = "{node['data']['adminPassword']}",
    [string]$parentDomainName = "{node['data'].get('parentDomainName', '')}"
)

if ($parentDomainName -ne "") {{
    Write-Host "Configuring subdomain $domainName under $parentDomainName"
}} else {{
    Write-Host "Configuring root domain $domainName"
}}
"""
                script_path = os.path.join(self.powershell_dir, f"{node['id']}.ps1")
                with open(script_path, "w") as f:
                    f.write(script_content)

    def _generate_bicep_content(self, nodes, edges):
        # Placeholder logic for generating Bicep content
        bicep_lines = ["targetScope = 'subscription'"]
        for node in nodes:
            bicep_lines.append(f"// Node: {node['id']} - {node['type']}")
        for edge in edges:
            bicep_lines.append(f"// Edge: {edge['source']} -> {edge['target']}")
        return "\n".join(bicep_lines)
