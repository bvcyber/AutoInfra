from flask import Blueprint, request, jsonify
import os
import json
import uuid
import datetime
import requests
from azure_clients import AzureClients
from deployments import Deployments
import helpers
import fs_manager
import command_runner
from azure.mgmt.resource.resources.models import Deployment, DeploymentProperties, DeploymentMode
import logging

build_apis_blueprint = Blueprint('build_apis', __name__)
azure_clients = AzureClients()
deployment_handler = Deployments()
build_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)

@build_apis_blueprint.route("/templates", methods=["GET"])
def get_templates():
    """Get all available infrastructure templates"""
    try:
        templates_dir = helpers.TOPOLOGY_TEMPLATE_DIRECTORY
        if not os.path.exists(templates_dir):
            os.makedirs(templates_dir)
            
        template_files = [f for f in os.listdir(templates_dir) if f.endswith('.json')]
        templates = []
        
        for file in template_files:
            try:
                with open(os.path.join(templates_dir, file), 'r') as f:
                    template = json.load(f)
                    templates.append(template)
            except Exception as e:
                build_apis_blueprint.logger.error(f"Error reading template {file}: {str(e)}")
        
        templates.sort(key=lambda x: x.get('created', ''), reverse=True)
        
        return jsonify({"templates": templates}), 200
    except Exception as e:
        build_apis_blueprint.logger.error(f"Error getting templates: {str(e)}")
        return jsonify({"message": f"Error getting templates: {str(e)}"}), 500

@build_apis_blueprint.route("/templates", methods=["POST"])
def save_template():
    """Save a new infrastructure template"""
    try:
        data = request.get_json()
        
        if not data.get('name'):
            return jsonify({"message": "Template name is required"}), 400
            
        if not data.get('parameters'):
            return jsonify({"message": "Template parameters are required"}), 400
            
        if not data.get('id'):
            data['id'] = str(uuid.uuid4())
            
        if not data.get('created'):
            data['created'] = datetime.datetime.now().isoformat()
        
        templates_dir = helpers.TOPOLOGY_TEMPLATE_DIRECTORY
        if not os.path.exists(templates_dir):
            os.makedirs(templates_dir)
            
        filename = f"{data['id']}.json"
        with open(os.path.join(templates_dir, filename), 'w') as f:
            json.dump(data, f, indent=2)
            
        return jsonify({"message": "Template saved successfully", "template": data}), 200
    except Exception as e:
        build_apis_blueprint.logger.error(f"Error saving template: {str(e)}")
        return jsonify({"message": f"Error saving template: {str(e)}"}), 500


@build_apis_blueprint.route("/templates/<template_id>", methods=["DELETE"])
def delete_template(template_id):
    """Delete an infrastructure template by ID"""
    try:
        templates_dir = helpers.TOPOLOGY_TEMPLATE_DIRECTORY
        
        template_file = os.path.join(templates_dir, f"{template_id}.json")
        
        if not os.path.exists(template_file):
            return jsonify({"message": f"Template not found: {template_id}"}), 404
            
        try:
            with open(template_file, 'r') as f:
                template_data = json.load(f)
                template_name = template_data.get('name', template_id)
        except:
            template_name = template_id
            
        os.remove(template_file)
        
        build_apis_blueprint.logger.info(f"Deleted template: {template_name} ({template_id})")
        return jsonify({"message": f"Template '{template_name}' deleted successfully"}), 200
        
    except Exception as e:
        build_apis_blueprint.logger.error(f"Error deleting template: {str(e)}")
        return jsonify({"message": f"Error deleting template: {str(e)}"}), 500


@build_apis_blueprint.route('/generateBuildID', methods=["POST"])
def generate_build_id():
    """Generate a unique deployment ID for a build before starting deployment"""
    deployment_id = f"{helpers.BUILD_LAB_PREFIX}{helpers.generate_random_id(size=5)}"
    return jsonify({"deploymentID": deployment_id}), 200


@build_apis_blueprint.route('/build', methods=["POST"])
def build():
    data = request.get_json()
    topology = data.get("topology", {})
    scenario_info = data.get("scenarioInfo", "")
    resource_group_name = data.get("deploymentID") or f"{helpers.BUILD_LAB_PREFIX}{helpers.generate_random_id(size=5)}"
    
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=helpers.IP_LOOKUP_TIMEOUT)
        caller_ip = response.json()['ip']
        build_apis_blueprint.logger.info(f"BUILD: Detected public IP address: {caller_ip}")
    except Exception as e:
        build_apis_blueprint.logger.warning(f"BUILD: Failed to detect public IP, using request.remote_addr: {e}")
        caller_ip = request.remote_addr
        build_apis_blueprint.logger.info(f"BUILD: Using fallback IP address: {caller_ip}")
    
    try:
        nodes = topology.get("nodes", [])
        has_jumpbox = any(node.get("type") == "jumpbox" for node in nodes)
        
        if has_jumpbox:
            build_apis_blueprint.logger.info("BUILD: Jumpbox detected, checking Kali marketplace terms...")
            
            kali_sku = helpers.get_latest_kali_sku()
            build_apis_blueprint.logger.info(f"BUILD: Using Kali SKU: {kali_sku}")
            
            terms_accepted = helpers.check_kali_marketplace_terms()
            
            if not terms_accepted:
                build_apis_blueprint.logger.info("BUILD: Kali marketplace terms not accepted, accepting now...")
                acceptance_result = helpers.accept_kali_marketplace_terms()
                
                if not acceptance_result:
                    build_apis_blueprint.logger.warning("BUILD: Failed to auto-accept Kali terms, deployment may fail")
                else:
                    build_apis_blueprint.logger.info("BUILD: Successfully accepted Kali marketplace terms")
            else:
                build_apis_blueprint.logger.info("BUILD: Kali marketplace terms already accepted")
    except Exception as e:
        build_apis_blueprint.logger.warning(f"BUILD: Error checking/accepting Kali terms: {e}")

    build_apis_blueprint.logger.info(f"BUILD: Received topology: {topology}")

    try:
        nodes = topology.get("nodes", [])
        edges = topology.get("edges", [])
        jumpbox_node = next((node for node in nodes if node["type"] == "jumpbox"), None)
        
        has_public_ip_node = any(
            node.get("data", {}).get("hasPublicIP", False) 
            for node in nodes 
            if node["type"] != "jumpbox"
        )
        
        if not jumpbox_node and not has_public_ip_node:
            return jsonify({"message": "Topology must include either a Jumpbox or at least one node with a Public IP"}), 400
        
        top_level_credentials = topology.get("credentials", {})
        enterprise_admin_username = top_level_credentials.get("enterpriseAdminUsername")
        enterprise_admin_password = top_level_credentials.get("enterpriseAdminPassword")
        
        if not enterprise_admin_username or not enterprise_admin_password:
            return jsonify({"message": "Error: Missing admin credentials"}), 400
            
        jumpbox_connections = []
        if jumpbox_node:
            for edge in edges:
                if edge["source"] == jumpbox_node["id"]:
                    connected_node = next(node for node in nodes if node["id"] == edge["target"])
                    jumpbox_connections.append({
                        "jumpboxPrivateIPAddress": jumpbox_node["data"]["privateIPAddress"],
                        "connectedPrivateIPAddress": connected_node["data"]["privateIPAddress"]
                    })
                elif edge["target"] == jumpbox_node["id"]:
                    connected_node = next(node for node in nodes if node["id"] == edge["source"])
                    jumpbox_connections.append({
                        "jumpboxPrivateIPAddress": jumpbox_node["data"]["privateIPAddress"],
                        "connectedPrivateIPAddress": connected_node["data"]["privateIPAddress"]
                    })

        kali_sku = helpers.get_latest_kali_sku() if jumpbox_node else ""
        if jumpbox_node:
            build_apis_blueprint.logger.info(f"BUILD: Will use Kali SKU: {kali_sku} in parameters")

        parameters = {
            "$schema": "https://schema.management.azure.com/schemas/2015-01-01/deploymentParameters.json#",
            "contentVersion": "1.0.0.0",
            "parameters": {
                "deployResourceGroupName": {"value": resource_group_name},
                "scenarioSelection": {"value": "BUILD"},
                "location": {"value": helpers.LOCATION},
                "scenarioTagValue": {"value": "BUILD"},
                "expiryTimestamp": {"value": str(helpers.get_future_time(helpers.DEPLOYMENT_TIMEOUT_HOURS))},
                "enterpriseAdminUsername": {"value": enterprise_admin_username},
                "enterpriseAdminPassword": {"value": enterprise_admin_password},
                "subscriptionID": {"value": helpers.get_subscription_id()},
                "rootDomainControllers": {"value": []},
                "subDomainControllers": {"value": []},
                "standaloneServers": {"value": []},
                "jumpboxConfig": {
                    "value": jumpbox_connections
                },
                "callerIPAddress": {"value": caller_ip},
                "kaliSku": {"value": kali_sku}
            }
        }

        node_map = {node["id"]: node for node in topology.get("nodes", [])}
        child_to_parent = {edge["target"]: edge["source"] for edge in topology.get("edges", [])}

        for node in topology["nodes"]:
            node_type = node.get("type")
            data = node.get("data", {})
            domain_name = data.get("domainName")
            netbios = domain_name.split('.')[0] if domain_name else None
            parent_id = child_to_parent.get(node["id"])
            parent_node = node_map.get(parent_id)
            parent_domain = parent_node.get("data", {}).get("domainName") if parent_node else None
            parent_ip = parent_node.get("data", {}).get("privateIPAddress") if parent_node else None

            if node_type == "domainController":
                is_root = parent_node is None or parent_node["type"] != "domainController"
                is_locked = data.get("locked", False) or node.get("status") == "deployed"
                dc_entry = {
                    "name": data.get("domainControllerName"),
                    "domainName": domain_name,
                    "netbios": netbios,
                    "isRoot": is_root,
                    "privateIPAddress": data.get("privateIPAddress"),
                    "hasPublicIP": data.get("hasPublicIP", False),
                    "locked": is_locked
                }
                if is_root:
                    parameters["parameters"]["rootDomainControllers"]["value"].append(dc_entry)
                else:
                    parameters["parameters"]["subDomainControllers"]["value"].append(dc_entry)

            elif node_type == "workstation":
                is_locked = data.get("locked", False) or node.get("status") == "deployed"
                server_entry = {
                    "name": data.get("workstationName"),
                    "domainName": parent_domain,
                    "rootOrSub": "sub" if parent_domain else "root",
                    "adminUsername": enterprise_admin_username,
                    "adminPassword": enterprise_admin_password,
                    "privateIPAddress": data.get("privateIPAddress"),
                    "dcIp": parent_ip,
                    "hasPublicIP": data.get("hasPublicIP", False),
                    "locked": is_locked
                }
                parameters["parameters"]["standaloneServers"]["value"].append(server_entry)

            elif node_type == "certificateAuthority":
                parent_id = child_to_parent.get(node["id"])
                parent_node = node_map.get(parent_id)
                
                if not parent_node or parent_node.get("type") != "domainController":
                    return jsonify({"message": "Certificate Authority must be connected to a Domain Controller"}), 400
                
                is_root_dc = parent_node.get("id") not in child_to_parent or \
                             node_map.get(child_to_parent.get(parent_node.get("id")), {}).get("type") != "domainController"
                
                if not is_root_dc:
                    return jsonify({"message": "Certificate Authority must be connected to a Root Domain Controller only"}), 400
                
                parent_domain = parent_node.get("data", {}).get("domainName")
                parent_ip = parent_node.get("data", {}).get("privateIPAddress")
                
                is_locked = data.get("locked", False) or node.get("status") == "deployed"
                
                ca_entry = {
                    "name": data.get("caName"),
                    "domainName": parent_domain,
                    "privateIPAddress": data.get("privateIPAddress"),
                    "rootDomainControllerPrivateIp": parent_ip,
                    "hasPublicIP": data.get("hasPublicIP", False),
                    "locked": is_locked
                }
                
                if "certificateAuthorities" not in parameters["parameters"]:
                    parameters["parameters"]["certificateAuthorities"] = {"value": []}
                
                parameters["parameters"]["certificateAuthorities"]["value"].append(ca_entry)

        if not parameters["parameters"]["enterpriseAdminUsername"]["value"]:
            raise ValueError("Missing enterpriseAdminUsername")
        if not parameters["parameters"]["enterpriseAdminPassword"]["value"]:
            raise ValueError("Missing enterpriseAdminPassword")

        base_dir = helpers.GENERATED_TEMPLATE_DIRECTORY
        os.makedirs(base_dir, exist_ok=True)

        param_block = """
param location string = ''
param windowsVmSize string = ''
param vmDiskType string = ''
param resourceGroupName string = ''
param domainAndEnterpriseAdminUsername string = ''
param enterpriseAdminUsername string = ''
@secure()
param enterpriseAdminPassword string = ''
param deployOrBuild string = ''
param rootDomainNetBIOSName string = ''
param rootDomainControllerFQDN string = ''
param rootDomainControllers array = []
param subDomainControllers array = []
param standaloneServers array = []
param standaloneServerPrivateIp string = ''
param callerIPAddress string = ''
param domainControllerPrivateIp string = ''
param oldScenarios bool = false
param jumpboxPrivateIPAddress string = ''
param connectedPrivateIPAddress string = ''
param isVNet10Required bool = false
param isVNet192Required bool = false
param isVNet172Required bool = false
param osDiskType string = ''
param jumpboxAdminUsername string = ''
@secure()
param jumpboxAdminPassword string = ''
param kaliSku string = 'kali-2025-2'
param hasPublicIP bool = false

"""

        def get_vnet_prefix(ip):
            if not ip:
                return None
            if ip.startswith("10."):
                return "10"
            elif ip.startswith("192.168."):
                return "192"
            elif ip.startswith("172."):
                return "172"
            return None
        
        # Compute which VNet peerings already exist from LOCKED (deployed) nodes
        existing_peerings = set()
        peering_created_by = {}  # Track which module creates each peering
        
        root_dc_ip = parameters["parameters"]["rootDomainControllers"]["value"][0]["privateIPAddress"] if parameters["parameters"]["rootDomainControllers"]["value"] else ""
        root_vnet = get_vnet_prefix(root_dc_ip)
        root_dc_locked = parameters["parameters"]["rootDomainControllers"]["value"][0].get("locked", False) if parameters["parameters"]["rootDomainControllers"]["value"] else False
        
        # Check all locked nodes and compute their peerings
        sub_dcs = parameters["parameters"]["subDomainControllers"]["value"]
        for dc in sub_dcs:
            if dc.get("locked", False):
                dc_vnet = get_vnet_prefix(dc["privateIPAddress"])
                
                dc_domain = dc["domainName"]
                domain_parts = dc_domain.split('.')
                if len(domain_parts) > 1:
                    parent_domain = '.'.join(domain_parts[1:])
                    parent_dc = next((d for d in sub_dcs if d["domainName"] == parent_domain), None)
                    if parent_dc:
                        parent_vnet = get_vnet_prefix(parent_dc["privateIPAddress"])
                    else:
                        parent_vnet = root_vnet
                    
                    if dc_vnet and parent_vnet and dc_vnet != parent_vnet:
                        peering_key = tuple(sorted([dc_vnet, parent_vnet]))
                        existing_peerings.add(peering_key)
                        build_apis_blueprint.logger.debug(f"BUILD: Found existing peering from locked SubDC: {peering_key}")
                
                if dc_vnet and root_vnet and dc_vnet != root_vnet:
                    peering_key = tuple(sorted([dc_vnet, root_vnet]))
                    existing_peerings.add(peering_key)
        
        for srv in parameters["parameters"]["standaloneServers"]["value"]:
            if srv.get("locked", False):
                srv_vnet = get_vnet_prefix(srv["privateIPAddress"])
                dc_vnet = get_vnet_prefix(srv["dcIp"])
                if srv_vnet and dc_vnet and srv_vnet != dc_vnet:
                    peering_key = tuple(sorted([srv_vnet, dc_vnet]))
                    existing_peerings.add(peering_key)
                    build_apis_blueprint.logger.debug(f"BUILD: Found existing peering from locked Standalone: {peering_key}")
        
        if "certificateAuthorities" in parameters["parameters"]:
            for ca in parameters["parameters"]["certificateAuthorities"]["value"]:
                if ca.get("locked", False):
                    ca_vnet = get_vnet_prefix(ca["privateIPAddress"])
                    dc_vnet = get_vnet_prefix(ca["rootDomainControllerPrivateIp"])
                    if ca_vnet and dc_vnet and ca_vnet != dc_vnet:
                        peering_key = tuple(sorted([ca_vnet, dc_vnet]))
                        existing_peerings.add(peering_key)
                        build_apis_blueprint.logger.debug(f"BUILD: Found existing peering from locked CA: {peering_key}")
        
        build_apis_blueprint.logger.info(f"BUILD: Existing peerings from locked nodes: {existing_peerings}")

        root_file = helpers.GENERATED_ROOT_DC_MODULES
        with open(root_file, "w") as f:
            f.write(param_block)
            for i, dc in enumerate(parameters["parameters"]["rootDomainControllers"]["value"]):
                f.write(f"""
module RootDC_{i} '../base/RootDomainController.bicep' = {{
  name: 'RootDC_{i}'
  scope: resourceGroup(resourceGroupName)
  params: {{
    location: location
    privateIPAddress: '{dc["privateIPAddress"]}'
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: '{dc["name"]}'
    resourceGroupName: resourceGroupName
    osDiskType: vmDiskType
    domainName: '{dc["domainName"]}'
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    rootDomainNetBIOSName: '{dc["netbios"]}'
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    deployOrBuild: deployOrBuild
    isRoot: true
    parentDomainControllerPrivateIp: ''
    oldScenarios: oldScenarios
    jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
    connectedPrivateIPAddress: connectedPrivateIPAddress
    isVNet10Required: isVNet10Required
    isVNet192Required: isVNet192Required
    isVNet172Required: isVNet172Required
    hasPublicIP: {'true' if dc.get("hasPublicIP", False) else 'false'}
    callerIPAddress: callerIPAddress
  }}
}}
""")

        sub_file = helpers.GENERATED_SUB_DC_MODULES
        with open(sub_file, "w") as f:
            f.write(param_block)
            
            root_dc_domain = parameters["parameters"]["rootDomainControllers"]["value"][0]["domainName"]
            
            # Build a mapping of domain name -> module index for dependency resolution
            domain_to_module_index = {}
            for idx, dc in enumerate(sub_dcs):
                domain_to_module_index[dc["domainName"]] = idx
            
            for i, dc in enumerate(sub_dcs):
                current_domain = dc["domainName"]
                current_ip = dc["privateIPAddress"]
                current_vnet = get_vnet_prefix(current_ip)
                
                # Find the parent domain by removing the leftmost part
                domain_parts = current_domain.split('.')
                if len(domain_parts) > 1:
                    parent_domain = '.'.join(domain_parts[1:])
                else:
                    parent_domain = None
                
                parent_found = False
                parent_hostname = None
                parent_ip = None
                parent_module_index = None
                
                for other_dc in sub_dcs:
                    if other_dc["domainName"] == parent_domain:
                        parent_hostname = other_dc["name"]
                        parent_ip = other_dc["privateIPAddress"]
                        parent_module_index = domain_to_module_index[parent_domain]
                        parent_found = True
                        break
                
                if not parent_found:
                    parent_hostname = parameters["parameters"]["rootDomainControllers"]["value"][0]["name"]
                    parent_ip = parameters["parameters"]["rootDomainControllers"]["value"][0]["privateIPAddress"]
                    parent_module_index = None
                
                parent_vnet = get_vnet_prefix(parent_ip)
                parent_peering_key = tuple(sorted([current_vnet, parent_vnet])) if current_vnet != parent_vnet else None
                
                root_peering_key = tuple(sorted([current_vnet, root_vnet])) if current_vnet != root_vnet and parent_ip != root_dc_ip else None
                
                skip_parent_peering = False
                skip_root_peering = False
                
                if parent_peering_key and parent_peering_key in existing_peerings:
                    skip_parent_peering = True
                    build_apis_blueprint.logger.debug(f"BUILD: SubDC_{i} will skip parent peering {parent_peering_key} - already exists")
                
                if root_peering_key and root_peering_key in existing_peerings:
                    skip_root_peering = True
                    build_apis_blueprint.logger.debug(f"BUILD: SubDC_{i} will skip root peering {root_peering_key} - already exists")
                
                peering_dependency_index = None
                if parent_peering_key and not skip_parent_peering:
                    if parent_peering_key in peering_created_by:
                        peering_dependency_index = peering_created_by[parent_peering_key]
                        skip_parent_peering = True  # Another module creates it, so skip
                    else:
                        peering_created_by[parent_peering_key] = i
                
                dependencies = []
                
                if parent_module_index is not None:
                    dependencies.append(f"SubDC_{parent_module_index}")
                
                if peering_dependency_index is not None and peering_dependency_index not in [parent_module_index]:
                    dependencies.append(f"SubDC_{peering_dependency_index}")
                
                if dependencies:
                    depends_block = f"  dependsOn: [{', '.join(dependencies)}]\n"
                else:
                    depends_block = ""
                
                root_dc_ip_param = root_dc_ip if parent_ip != root_dc_ip else ''
                    
                f.write(f"""
        module SubDC_{i} '../base/SubDomainController2.bicep' = {{
        name: 'SubDC_{i}'
        scope: resourceGroup(resourceGroupName)
        params: {{
            location: location
            privateIPAddress: '{dc["privateIPAddress"]}'
            virtualMachineSize: windowsVmSize
            virtualMachineHostname: '{dc["name"]}'
            parentVirtualMachineHostname: '{parent_hostname}'
            resourceGroupName: resourceGroupName
            osDiskType: vmDiskType
            domainName: '{dc["domainName"]}'
            domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
            rootDomainNetBIOSName: '{dc["netbios"]}'
            enterpriseAdminUsername: enterpriseAdminUsername
            enterpriseAdminPassword: enterpriseAdminPassword
            deployOrBuild: deployOrBuild
            isRoot: false
            rootDomainControllerFQDN: rootDomainControllerFQDN
            parentDomainControllerPrivateIp: '{parent_ip}'
            rootDomainControllerPrivateIp: '{root_dc_ip_param}'
            oldScenarios: oldScenarios
            jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
            connectedPrivateIPAddress: connectedPrivateIPAddress
            isVNet10Required: isVNet10Required
            isVNet192Required: isVNet192Required
            isVNet172Required: isVNet172Required
            hasPublicIP: {'true' if dc.get("hasPublicIP", False) else 'false'}
            callerIPAddress: callerIPAddress
            skipParentPeering: {'true' if skip_parent_peering else 'false'}
            skipRootPeering: {'true' if skip_root_peering else 'false'}
        }}
        {depends_block}}}
        """)


        standalone_file = helpers.GENERATED_STANDALONE_MODULES
        with open(standalone_file, "w") as f:
            f.write(param_block)
            for i, srv in enumerate(parameters["parameters"]["standaloneServers"]["value"]):
                srv_vnet = get_vnet_prefix(srv["privateIPAddress"])
                dc_vnet = get_vnet_prefix(srv["dcIp"])
                srv_peering_key = tuple(sorted([srv_vnet, dc_vnet])) if srv_vnet != dc_vnet else None
                
                # Skip if peering already exists from locked nodes OR will be created by another module
                skip_srv_peering = False
                if srv_peering_key and srv_peering_key in existing_peerings:
                    skip_srv_peering = True
                    build_apis_blueprint.logger.debug(f"BUILD: Standalone_{i} will skip peering {srv_peering_key} - already exists")
                elif srv_peering_key and srv_peering_key in peering_created_by:
                    skip_srv_peering = True
                    build_apis_blueprint.logger.debug(f"BUILD: Standalone_{i} will skip peering {srv_peering_key} - created by another module")
                elif srv_peering_key:
                    peering_created_by[srv_peering_key] = f"Standalone_{i}"
                
                f.write(f"""
        module Standalone_{i} '../base/StandaloneServer.bicep' = {{
        name: 'Standalone_{i}'
        scope: resourceGroup(resourceGroupName)
        params: {{
            location: location
            virtualMachineSize: windowsVmSize
            virtualMachineHostname: '{srv["name"]}'
            resourceGroupName: resourceGroupName
            osDiskType: 'Standard_LRS'
            domainName: '{srv["domainName"]}'
            domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
            enterpriseAdminPassword: enterpriseAdminPassword
            domainControllerPrivateIp: '{srv["dcIp"]}'
            standaloneServerPrivateIp: '{srv["privateIPAddress"]}'
            deployOrBuild: deployOrBuild
            rootOrSub: '{srv["rootOrSub"]}'
            oldScenarios: oldScenarios
            jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
            connectedPrivateIPAddress: connectedPrivateIPAddress
            isVNet10Required: isVNet10Required
            isVNet192Required: isVNet192Required
            isVNet172Required: isVNet172Required
            hasPublicIP: {'true' if srv.get("hasPublicIP", False) else 'false'}
            callerIPAddress: callerIPAddress
            skipPeering: {'true' if skip_srv_peering else 'false'}
        }}
        dependsOn: []
        }}
        """)
                
        jumpbox_file = helpers.GENERATED_JUMPBOX_MODULES
        
        if jumpbox_node:
            kali_sku = helpers.get_latest_kali_sku()
            build_apis_blueprint.logger.info(f"BUILD: Generating Jumpbox module with Kali SKU: {kali_sku}")
            
            with open(jumpbox_file, "w") as f:
                f.write(param_block)
                jb = jumpbox_node["data"]
                f.write(f"""
module Jumpbox '../base/Jumpbox.bicep' = {{
name: 'Jumpbox'
scope: resourceGroup(resourceGroupName)
params: {{
    location: location
    vmName: 'BuildJumpbox'
    vmSize: 'Standard_B2s'
    resourceGroupName: resourceGroupName
    jumpboxPrivateIPAddress: '{jb["privateIPAddress"]}'
    osDiskType: vmDiskType
    deployOrBuild: 'build'
    oldScenarios: oldScenarios
    connectedPrivateIPAddress: connectedPrivateIPAddress
    isVNet10Required: isVNet10Required
    isVNet192Required: isVNet192Required
    isVNet172Required: isVNet172Required
    jumpboxAdminUsername: 'redteamer'
    jumpboxAdminPassword: 'Password#123'
    kaliSku: '{kali_sku}'
    callerIPAddress: '{caller_ip}'
}}
}}
""")
        else:
            with open(jumpbox_file, "w") as f:
                f.write(param_block)
                f.write("// No Jumpbox in this deployment\n")

        if "certificateAuthorities" in parameters["parameters"] and \
           len(parameters["parameters"]["certificateAuthorities"]["value"]) > 0:
            
            ca_file = helpers.GENERATED_CA_MODULES
            with open(ca_file, "w") as f:
                f.write(param_block)
                for i, ca in enumerate(parameters["parameters"]["certificateAuthorities"]["value"]):
                    ca_vnet = get_vnet_prefix(ca["privateIPAddress"])
                    ca_dc_vnet = get_vnet_prefix(ca["rootDomainControllerPrivateIp"])
                    ca_peering_key = tuple(sorted([ca_vnet, ca_dc_vnet])) if ca_vnet != ca_dc_vnet else None
                    
                    skip_ca_peering = False
                    if ca_peering_key and ca_peering_key in existing_peerings:
                        skip_ca_peering = True
                        build_apis_blueprint.logger.debug(f"BUILD: CA_{i} will skip peering {ca_peering_key} - already exists")
                    elif ca_peering_key and ca_peering_key in peering_created_by:
                        skip_ca_peering = True
                        build_apis_blueprint.logger.debug(f"BUILD: CA_{i} will skip peering {ca_peering_key} - created by another module")
                    elif ca_peering_key:
                        peering_created_by[ca_peering_key] = f"CA_{i}"
                    
                    f.write(f"""
module CA_{i} '../base/CertificateAuthority.bicep' = {{
  name: 'CA_{i}'
  scope: resourceGroup(resourceGroupName)
  params: {{
    location: location
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: '{ca["name"]}'
    resourceGroupName: resourceGroupName
    osDiskType: vmDiskType
    privateIPAddress: '{ca["privateIPAddress"]}'
    rootDomainControllerPrivateIp: '{ca["rootDomainControllerPrivateIp"]}'
    domainName: '{ca["domainName"]}'
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    localAdminUsername: enterpriseAdminUsername
    localAdminPassword: enterpriseAdminPassword
    deployOrBuild: deployOrBuild
    oldScenarios: oldScenarios
    jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
    connectedPrivateIPAddress: connectedPrivateIPAddress
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
    hasPublicIP: {'true' if ca.get("hasPublicIP", False) else 'false'}
    callerIPAddress: '{caller_ip}'
    skipPeering: {'true' if skip_ca_peering else 'false'}
  }}
  dependsOn: []
}}
""")


        # Note: We don't write the parameters to ScenarioManagerBuild.parameters.json anymore
        # That file is kept as a clean template with empty subscription ID for version control
        # The subscription ID is injected at runtime below

        build_apis_blueprint.logger.info(f"BUILD: Using dynamically generated parameters (not writing to file)")
        build_apis_blueprint.logger.debug(f"BUILD: Parameters content: {json.dumps(parameters, indent=2)}")
        expiryTimestamp = 0

        topology_file = f"{resource_group_name}_topology.json"
        build_apis_blueprint.logger.info(f"BUILD: Saving topology to file: {topology_file}")
        build_apis_blueprint.logger.debug(f"BUILD: Topology data being saved: {topology}")
        fs_manager.save_file(topology, helpers.DEPLOYMENT_DIRECTORY, topology_file)

        deployment_id = resource_group_name

        deployment_handler.set_deployment_configs(
            action="build",
            deploymentID=deployment_id,
            scenario="Custom Topology",
            expiryTimestamp=expiryTimestamp,
            machines=[]
        )

        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        deployment["topology"] = topology
        deployment["resourceGroup"] = resource_group_name
        deployment["scenarioInfo"] = scenario_info
        fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deployment_id)

        build_apis_blueprint.logger.info("BUILD: Compiling ScenarioManager.bicep with generated modules...")
        bicep_path = helpers.SCENARIO_MANAGER_BICEP
        json_path = helpers.SCENARIO_MANAGER_JSON
        compile_command = ["az", "bicep", "build", "--file", bicep_path, "--outfile", json_path]
        compile_output = command_runner.run_command_and_read_output(compile_command)
        build_apis_blueprint.logger.info(f"BUILD: Bicep compilation output: {compile_output}")
        compile_exit_code = command_runner.run_command_and_get_exit_code(compile_command)
        if compile_exit_code != 0:
            build_apis_blueprint.logger.error(f"BUILD: Bicep compilation failed with exit code {compile_exit_code}")
            build_apis_blueprint.logger.error(f"BUILD: Compilation output: {compile_output}")
            return jsonify({"message": f"Failed to compile infrastructure template: {compile_output}"}), 500
        build_apis_blueprint.logger.info("BUILD: ScenarioManager.bicep compiled successfully")

        template = fs_manager.load_file(helpers.TEMPLATE_DIRECTORY, "ScenarioManager.json")

        # Use the dynamically created parameters instead of loading from file
        # This way the file can remain clean (with empty subscription ID) for version control
        params = parameters

        deployment_properties = DeploymentProperties(
            mode=DeploymentMode.incremental,
            template=template,
            parameters=params["parameters"]
        )

        deployment = Deployment(
            location=parameters["parameters"]["location"]["value"],
            properties=deployment_properties
        )

        
        resource_client = azure_clients.get_resource_client()
        resource_client.deployments.begin_create_or_update_at_subscription_scope(
            deployment_name=deployment_id,
            parameters=deployment
        )

        return jsonify({
            "message": "Deployment started",
            "deploymentID": deployment_id
        }), 200

    except Exception as e:
        build_apis_blueprint.logger.error(f"BUILD: Error processing topology: {str(e)}")
        return jsonify({"message": f"Error processing topology: {str(e)}"}), 500
    
    
def create_scenario_parameters(scenario_name, scenario_data, topology):
    """Generate a custom parameters file for a saved build scenario"""

    build_params_path = helpers.SCENARIO_MANAGER_BUILD_PARAMS

    with open(build_params_path, 'r') as f:
        build_params = json.load(f)

    build_params["parameters"]["scenarioSelection"]["value"] = scenario_name
    build_params["parameters"]["scenarioTagValue"]["value"] = scenario_name

    # Inject subscription ID dynamically (template file has empty value)
    build_params["parameters"]["subscriptionID"]["value"] = helpers.get_subscription_id()

    for machine_name, image_ref in scenario_data.get("imageReferences", {}).items():
        build_params["parameters"][f"{machine_name}ImageReferenceID"] = {"value": image_ref}

    params_path = os.path.join(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"{scenario_name}.parameters.json")
    os.makedirs(os.path.dirname(params_path), exist_ok=True)

    with open(params_path, "w") as f:
        json.dump(build_params, f, indent=2)

    return params_path



def create_scenario_bicep(scenario_name, scenario_data, topology):
    """Generate a custom bicep file for a saved build scenario"""

    machines = scenario_data.get("machines", {})

    config = helpers.load_config()
    vm_sizes = config.get("vmSizes", {})
    windows_vm_size = vm_sizes.get("windowsVmSize", "Standard_B1ms")
    jumpbox_vm_size = vm_sizes.get("jumpboxVmSize", "Standard_B2s")

    bicep_content = f"""
targetScope = 'subscription'

param location string = ''
param resourceGroupName string = ''
param scenarioTagValue string = ''
param expiryTimeout string = ''
param subscriptionID string = ''
param oldScenarios bool = false
param rootDomainControllers array = []
param subDomainControllers array = []
param standaloneServers array = []
param jumpboxConfig array = []

param enterpriseAdminUsername string = ''
param enterpriseAdminPassword string = ''
param domainAndEnterpriseAdminUsername string = ''

// Domain parameters
param rootDomainNetBIOSName string = ''
param rootDomainControllerFQDN string = ''
param rootDomainName string = ''
param parentDomainName string = ''
param parentDomainControllerFQDN string = ''
param parentDomainControllerPrivateIp string = ''

param windowsVmSize string = '{windows_vm_size}'
param jumpboxVmSize string = '{jumpbox_vm_size}'
param vmDiskType string = 'Standard_LRS'
param vmName string = ''
param virtualMachineSize string = ''
param virtualMachineHostname string = ''

param privateIPAddress string = ''
param jumpboxPrivateIPAddress string = ''
param connectedPrivateIPAddress string = ''
param domainControllerPrivateIp string = ''
param standaloneServerPrivateIp string = ''
param rootOrSub string = 'root'
param isRoot bool = true
param vnetName string = ''
param virtualNetworkAddressPrefix string = ''
param rootSubnetAddressPrefix string = ''
param deployOrBuild string = 'deploy'
param scenarioSelection string = ''
param expiryTimestamp string = ''
param deployResourceGroupName string = ''

// Domain-joined configuration
param domainName string = ''

param caName string = ''

"""
    
    for machine_name in scenario_data["machines"]:
        bicep_content += f"""
param {machine_name}ImageReferenceID string
"""
    
    bicep_content += f"""
resource CreateResourceGroup 'Microsoft.Resources/resourceGroups@2023-07-01' = {{
  name: resourceGroupName
  location: location
  tags: {{
    Scenario: scenarioTagValue
    expiryTimeout: expiryTimeout
  }}
}}
"""

    # Collect all IPs from nodes
    all_ips = []
    
    # Extract IPs from topology nodes
    for node in topology.get("nodes", []):
        node_data = node.get("data", {})
        ip = node_data.get("privateIPAddress", "")
        if ip:
            all_ips.append(ip)
    
    
    fixed_json = json.dumps(all_ips).replace('"', "'")
    bicep_content += f"""
    var allIPs = {fixed_json}

var all10IPs = [for ip in allIPs: contains(string(ip), '10.10.') ? ip : null]
var all10IPsFiltered = filter(all10IPs, ip => ip != null)
var isVNet10Required = length(all10IPsFiltered) > 0

var all192IPs = [for ip in allIPs: contains(string(ip), '192.168.') ? ip : null]
var all192IPsFiltered = filter(all192IPs, ip => ip != null)
var isVNet192Required = length(all192IPsFiltered) > 0

var all172IPs = [for ip in allIPs: contains(string(ip), '172.16.') ? ip : null]
var all172IPsFiltered = filter(all172IPs, ip => ip != null)
var isVNet172Required = length(all172IPsFiltered) > 0
"""

    bicep_content += f"""
module vnet10 '../base/VirtualNetwork.bicep' = if (isVNet10Required) {{
  name: 'vnet-10'
  scope: resourceGroup(resourceGroupName)
  params: {{
    location: location
    vnetName: 'vnet-10'
    virtualNetworkAddressPrefix: '10.10.0.0/16'
    rootSubnetAddressPrefix: '10.10.0.0/24'
    oldScenarios: oldScenarios
  }}
  dependsOn: [CreateResourceGroup]
}}

module vnet192 '../base/VirtualNetwork.bicep' = if (isVNet192Required) {{
  name: 'vnet-192'
  scope: resourceGroup(resourceGroupName)
  params: {{
    location: location
    vnetName: 'vnet-192'
    virtualNetworkAddressPrefix: '192.168.0.0/16'
    rootSubnetAddressPrefix: '192.168.0.0/24'
    oldScenarios: oldScenarios
  }}
  dependsOn: [CreateResourceGroup]
}}

module vnet172 '../base/VirtualNetwork.bicep' = if (isVNet172Required) {{
  name: 'vnet-172'
  scope: resourceGroup(resourceGroupName)
  params: {{
    location: location
    vnetName: 'vnet-172'
    virtualNetworkAddressPrefix: '172.16.0.0/16'
    rootSubnetAddressPrefix: '172.16.0.0/24'
    oldScenarios: oldScenarios
  }}
  dependsOn: [CreateResourceGroup]
}}
"""

    # First, process domain controllers to identify root vs sub
    root_domain_controllers = []
    sub_domain_controllers = []
    
    node_map = {node["id"]: node for node in topology.get("nodes", [])}
    
    jumpbox_ip = ""
    jumpbox_connections = {}  # Map of connected IPs to jumpbox
    for jb_node in topology.get("nodes", []):
        if jb_node.get("type") == "jumpbox":
            jumpbox_ip = jb_node.get("data", {}).get("privateIPAddress", "")
            
            for edge in topology.get("edges", []):
                if edge["source"] == jb_node["id"]:
                    connected_node = node_map.get(edge["target"])
                    if connected_node and "data" in connected_node:
                        connected_ip = connected_node.get("data", {}).get("privateIPAddress", "")
                        if connected_ip:
                            jumpbox_connections[connected_ip] = True
                elif edge["target"] == jb_node["id"]:
                    connected_node = node_map.get(edge["source"])
                    if connected_node and "data" in connected_node:
                        connected_ip = connected_node.get("data", {}).get("privateIPAddress", "")
                        if connected_ip:
                            jumpbox_connections[connected_ip] = True
            break
            
    # Map child nodes to parent nodes using edges
    parent_map = {}
    for edge in topology.get("edges", []):
        source_node = node_map.get(edge["source"])
        target_node = node_map.get(edge["target"])
        
        if source_node and source_node.get("type") == "domainController" and target_node:
            if target_node.get("type") == "domainController":
                source_ip = source_node.get("data", {}).get("privateIPAddress", "")
                target_ip = target_node.get("data", {}).get("privateIPAddress", "")
                
                if source_ip < target_ip:
                    parent_map[target_node["id"]] = source_node["id"]
                else:
                    parent_map[source_node["id"]] = target_node["id"]
            else:
                parent_map[target_node["id"]] = source_node["id"]
        
        elif target_node and target_node.get("type") == "domainController" and source_node:
            if source_node.get("type") != "domainController":
                parent_map[source_node["id"]] = target_node["id"]
    
    for node in topology.get("nodes", []):
        if node.get("type") == "domainController":
            if node["id"] not in parent_map:
                root_domain_controllers.append(node)
            else:
                parent_id = parent_map[node["id"]]
                parent_node = node_map.get(parent_id)
                if parent_node and parent_node.get("type") == "domainController":
                    sub_domain_controllers.append((node, parent_node))
                else:
                    root_domain_controllers.append(node)

    
    # First add root domain controllers
    for node in root_domain_controllers:
        node_data = node.get("data", {})
        machine_name = node_data.get("domainControllerName", "DC01")
        private_ip = node_data.get("privateIPAddress", "10.10.0.5")
        domain_name = node_data.get("domainName", "domain.local")
        netbios = node_data.get("netbios", domain_name.split('.')[0] if domain_name else "DOMAIN")
        
        network_deps = []
        if private_ip.startswith("10.10."):
            network_deps.append("vnet10")
        elif private_ip.startswith("172.16."):
            network_deps.append("vnet172")
        elif private_ip.startswith("192.168."):
            network_deps.append("vnet192")
        
        network_depends = ", ".join(network_deps)
        
        connection_str = private_ip if private_ip in jumpbox_connections else ""
        
        bicep_content += f"""
// Deploy Root Domain Controller: {machine_name}
module {machine_name} '../base/RootDomainController.bicep' = {{
  scope: resourceGroup(resourceGroupName)
  name: '{machine_name}'
  params: {{
    location: location
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: '{machine_name}'
    resourceGroupName: resourceGroupName
    osDiskType: vmDiskType
    domainName: '{domain_name}'
    rootDomainNetBIOSName: '{netbios}'
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    isRoot: true
    privateIPAddress: '{private_ip}'
    deployOrBuild: 'deploy'
    imageReference: {machine_name}ImageReferenceID
    oldScenarios: oldScenarios
    jumpboxPrivateIPAddress: '{jumpbox_ip}'
    connectedPrivateIPAddress: '{connection_str}'
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
  }}
  dependsOn: [
    {network_depends}
  ]
}}
"""
    
    # Add sub domain controllers with their parents
    for node, parent_node in sub_domain_controllers:
        node_data = node.get("data", {})
        parent_data = parent_node.get("data", {})
        
        machine_name = node_data.get("domainControllerName", "SUBDC01")
        private_ip = node_data.get("privateIPAddress", "10.10.0.6")
        domain_name = node_data.get("domainName", "sub.domain.local")
        netbios = node_data.get("netbios", domain_name.split('.')[0] if domain_name else "SUB")
        
        parent_name = parent_data.get("domainControllerName", "DC01")
        parent_ip = parent_data.get("privateIPAddress", "10.10.0.5")
        
        network_deps = []
        if private_ip.startswith("10.10."):
            network_deps.append("vnet10")
        elif private_ip.startswith("172.16."):
            network_deps.append("vnet172")
        elif private_ip.startswith("192.168."):
            network_deps.append("vnet192")
        
        network_deps.append(parent_name)
        
        network_depends = ", ".join(network_deps)
        
        connection_str = private_ip if private_ip in jumpbox_connections else ""
        
        bicep_content += f"""
// Deploy Sub Domain Controller: {machine_name}
module {machine_name} '../base/RootDomainController.bicep' = {{
  scope: resourceGroup(resourceGroupName)
  name: '{machine_name}'
  params: {{
    location: location
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: '{machine_name}'
    resourceGroupName: resourceGroupName
    osDiskType: vmDiskType
    domainName: '{domain_name}'
    rootDomainNetBIOSName: '{netbios}'
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    isRoot: false
    parentDomainControllerPrivateIp: '{parent_ip}'
    privateIPAddress: '{private_ip}'
    deployOrBuild: 'deploy'
    imageReference: {machine_name}ImageReferenceID
    jumpboxPrivateIPAddress: '{jumpbox_ip}'
    connectedPrivateIPAddress: '{connection_str}'
    oldScenarios: oldScenarios
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
  }}
  dependsOn: [
    {network_depends}
  ]
}}
"""

    for machine_name, machine_info in machines.items():
        # Skip if already processed as a domain controller
        if any(dc.get("data", {}).get("domainControllerName") == machine_name for dc in root_domain_controllers) or \
           any(dc[0].get("data", {}).get("domainControllerName") == machine_name for dc in sub_domain_controllers):
            continue
        
        machine_type = None
        node = None
        
        if machine_name.upper() == "JUMPBOX":
            for n in topology.get("nodes", []):
                if n.get("type") == "jumpbox":
                    node = n
                    machine_type = "jumpbox"
                    break
                    
        if not node:
            for n in topology.get("nodes", []):
                node_data = n.get("data", {})
                if machine_name in [node_data.get("workstationName", ""), 
                                node_data.get("privateIPAddress", "")]:
                    node = n
                    machine_type = n.get("type")
                    break
        
        if not node:
            continue
        
        if machine_type in ["workstation", "standaloneServer"]:
            node_data = node.get("data", {})
            private_ip = node_data.get("privateIPAddress", "10.10.0.50")
            
            # Find connected domain controller (parent)
            dc_ip = ""
            domain_name = ""
            dc_node = None
            
            if node["id"] in parent_map:
                parent_id = parent_map[node["id"]]
                dc_node = node_map.get(parent_id)
                
            if not dc_node:
                for edge in topology.get("edges", []):
                    if edge["source"] == node["id"]:
                        target_node = node_map.get(edge["target"])
                        if target_node and target_node.get("type") == "domainController":
                            dc_node = target_node
                            break
                    elif edge["target"] == node["id"]:
                        source_node = node_map.get(edge["source"])
                        if source_node and source_node.get("type") == "domainController":
                            dc_node = source_node
                            break
            
            # Extract DC details if found
            if dc_node:
                dc_data = dc_node.get("data", {})
                dc_ip = dc_data.get("privateIPAddress", "10.10.0.5")
                domain_name = dc_data.get("domainName", "domain.local")
            else:
                dc_ip = "10.10.0.5"
                domain_name = "domain.local"
            
            network_deps = []
            if private_ip.startswith("10.10."):
                network_deps.append("vnet10")
            elif private_ip.startswith("172.16."):
                network_deps.append("vnet172")
            elif private_ip.startswith("192.168."):
                network_deps.append("vnet192")
            
            if dc_node:
                dc_name = dc_node.get("data", {}).get("domainControllerName", "")
                if dc_name:
                    network_deps.append(dc_name)
            
            network_depends = ", ".join(network_deps)
            
            connection_str = private_ip if private_ip in jumpbox_connections else ""
            
            bicep_content += f"""
module {machine_name} '../base/StandaloneServer.bicep' = {{
  scope: resourceGroup(resourceGroupName)
  name: '{machine_name}'
  params: {{
    location: location
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: '{machine_name}'
    resourceGroupName: resourceGroupName
    domainControllerPrivateIp: '{dc_ip}'
    domainName: '{domain_name}'
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    standaloneServerPrivateIp: '{private_ip}'
    deployOrBuild: 'deploy'
    imageReference: {machine_name}ImageReferenceID
    jumpboxPrivateIPAddress: '{jumpbox_ip}'
    connectedPrivateIPAddress: '{connection_str}'
    oldScenarios: oldScenarios
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
  }}
  dependsOn: [
    {network_depends}
  ]
}}
"""
                
        elif machine_type == "jumpbox":
            node_data = node.get("data", {})
            private_ip = node_data.get("privateIPAddress", "10.10.0.100")
            
            connections = []
            
            for edge in topology.get("edges", []):
                if edge["source"] == node["id"]:
                    target_node = node_map.get(edge["target"])
                    if target_node:
                        target_ip = target_node.get("data", {}).get("privateIPAddress", "")
                        if target_ip:
                            connections.append(target_ip)
                elif edge["target"] == node["id"]:
                    source_node = node_map.get(edge["source"])
                    if source_node:
                        source_ip = source_node.get("data", {}).get("privateIPAddress", "")
                        if source_ip:
                            connections.append(source_ip)
            
            connection_str = ""
            if connections:
                connection_str = connections[0]
            else:
                # Find any domain controller to connect to
                for n in topology.get("nodes", []):
                    if n.get("type") == "domainController":
                        connection_str = n.get("data", {}).get("privateIPAddress", "")
                        if connection_str:
                            break
            
            network_deps = []
            if private_ip.startswith("10.10."):
                network_deps.append("vnet10")
            elif private_ip.startswith("172.16."):
                network_deps.append("vnet172")
            elif private_ip.startswith("192.168."):
                network_deps.append("vnet192")
            
            network_depends = ", ".join(network_deps)
            
            kali_sku = helpers.get_latest_kali_sku()
            
            bicep_content += f"""
module Jumpbox '../base/Jumpbox.bicep' = {{
  scope: resourceGroup(resourceGroupName)
  name: 'Jumpbox'
  params: {{
    location: location
    vmName: '{machine_name}'
    vmSize: jumpboxVmSize
    resourceGroupName: resourceGroupName
    referenceID: {machine_name}ImageReferenceID
    jumpboxPrivateIPAddress: '{private_ip}'
    connectedPrivateIPAddress: '{connection_str}'
    kaliSku: '{kali_sku}'
    oldScenarios: oldScenarios
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
  }}
  dependsOn: [
    {network_depends}
  ]
}}
"""
    
    bicep_path = os.path.join(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"Scenario{scenario_name}.bicep")
    os.makedirs(os.path.dirname(bicep_path), exist_ok=True)
    
    with open(bicep_path, "w") as f:
        f.write(bicep_content)
    
    return bicep_path

@build_apis_blueprint.route("/updateBuildIP", methods=["POST"])
def update_build_ip():
    """Update the entry IP for a completed build deployment"""
    try:
        data = request.get_json()
        deployment_id = data.get("deploymentID")

        if not deployment_id:
            return jsonify({"message": "deploymentID is required"}), 400

        build_apis_blueprint.logger.info(f"UPDATE_BUILD_IP: Updating IP for deployment {deployment_id}")

        if not deployment_id.startswith(helpers.BUILD_LAB_PREFIX):
            return jsonify({"message": "This endpoint is only for build deployments"}), 400

        deployment_handler.get_deployment_ip(deployment_id)

        return jsonify({"message": f"Successfully updated IP for {deployment_id}"}), 200

    except Exception as e:
        build_apis_blueprint.logger.error(f"UPDATE_BUILD_IP: Error updating IP: {str(e)}")
        return jsonify({"message": f"Error updating IP: {str(e)}"}), 500


def update_scenarios_list(new_scenario_name):
    """Add a new scenario to the scenarios list"""
    try:
        config = helpers.load_config()

        if "scenarios" not in config:
            config["scenarios"] = []

        if new_scenario_name not in config["scenarios"]:
            config["scenarios"].append(new_scenario_name)

        fs_manager.save_file(config, helpers.CONFIG_DIRECTORY, "config.json")

        global scenarios
        if new_scenario_name not in scenarios:
            scenarios.append(new_scenario_name)

    except Exception as e:
        build_apis_blueprint.logger.error(f"UPDATE_SCENARIOS_LIST: Error updating scenarios list: {str(e)}")