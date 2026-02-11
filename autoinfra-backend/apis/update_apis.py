"""
Update APIs - Endpoints for updating existing saved scenarios with new nodes.

This module handles the "Update Scenario" workflow:
1. Load scenario topology for editing
2. Deploy base scenario for update
3. Deploy new nodes to existing resource group
4. Save updated scenario with new images
"""

from flask import Blueprint, request, jsonify
import os
import json
import traceback
import requests as http_requests
from azure_clients import AzureClients
from deployments import Deployments
import helpers
import fs_manager
import command_runner
from azure.mgmt.resource.resources.models import Deployment, DeploymentProperties, DeploymentMode
import logging

update_apis_blueprint = Blueprint('update_apis', __name__)
azure_clients = AzureClients()
deployment_handler = Deployments()
update_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)


@update_apis_blueprint.route('/getScenarioTopology', methods=['POST'])
def get_scenario_topology():
    """
    Get the topology of a saved scenario for editing in the Build page.
    
    Returns:
    - topology: { nodes, edges } from the scenario
    - credentials: { enterpriseAdminUsername, enterpriseAdminPassword }
    - machines: dict of machine info
    - imageReferences: dict of machine image references
    
    This is used when a user wants to "Update Existing" scenario.
    The frontend will display existing nodes as locked/non-editable.
    """
    try:
        data = request.get_json()
        scenario_name = data.get('scenario')
        
        if not scenario_name:
            return jsonify({"error": "Scenario name is required"}), 400
        
        if not scenario_name.startswith("Build-"):
            return jsonify({"error": "Only Build scenarios can be updated"}), 400
        
        update_apis_blueprint.logger.info(f"GET_SCENARIO_TOPOLOGY: Loading topology for {scenario_name}")
        
        scenario = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
        if "ERROR" in scenario:
            update_apis_blueprint.logger.error(f"GET_SCENARIO_TOPOLOGY: Scenario {scenario_name} not found")
            return jsonify({"error": f"Scenario {scenario_name} not found"}), 404
        
        # Extract topology
        topology = scenario.get("topology", {})
        if not topology:
            return jsonify({"error": "Scenario has no topology data"}), 400
        
        # Extract credentials from topology
        credentials = topology.get("credentials", {})
        
        params_path = os.path.join(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"{scenario_name}.parameters.json")
        if os.path.exists(params_path):
            try:
                with open(params_path, 'r') as f:
                    params = json.load(f)
                    params_data = params.get("parameters", {})
                    
                    # Use params credentials if topology credentials are missing
                    if not credentials.get("enterpriseAdminUsername"):
                        credentials["enterpriseAdminUsername"] = params_data.get("enterpriseAdminUsername", {}).get("value", "")
                    if not credentials.get("enterpriseAdminPassword"):
                        credentials["enterpriseAdminPassword"] = params_data.get("enterpriseAdminPassword", {}).get("value", "")
            except Exception as e:
                update_apis_blueprint.logger.warning(f"GET_SCENARIO_TOPOLOGY: Could not load params file: {e}")
        
        # Mark all existing nodes with a status field
        nodes = topology.get("nodes", [])
        for node in nodes:
            node["status"] = "deployed"  # Mark as existing/locked
        
        # Resource groups are tagged with "Scenario: Build-XXXXX"
        existing_deployments = []
        try:
            resource_client = azure_clients.get_resource_client()
            resource_groups = resource_client.resource_groups.list()
            
            for rg in resource_groups:
                # Only consider resource groups tagged as lab deployments
                if not rg.tags or rg.tags.get("Scenario") != scenario_name:
                    continue

                deployment_info = {
                    "deploymentId": rg.name,
                    "location": rg.location,
                    "tags": rg.tags,
                    "hasActiveUpdateSession": False
                }

                try:
                    deployment_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, rg.name)
                    if "ERROR" not in deployment_file:
                        update_session = deployment_file.get("updateSession", {})
                        if update_session.get("active"):
                            deployment_info["hasActiveUpdateSession"] = True
                except:
                    pass

                existing_deployments.append(deployment_info)
                update_apis_blueprint.logger.info(f"GET_SCENARIO_TOPOLOGY: Found existing deployment {rg.name} with Scenario tag '{scenario_name}', activeUpdate={deployment_info['hasActiveUpdateSession']}")
        except Exception as e:
            update_apis_blueprint.logger.warning(f"GET_SCENARIO_TOPOLOGY: Could not check for existing deployments: {e}")
        
        existing_deployment_id = existing_deployments[0]["deploymentId"] if existing_deployments else None
        
        # instead of the saved scenario (to include nodes that were added but not yet saved)
        response_topology = {"nodes": nodes, "edges": topology.get("edges", [])}
        for dep in existing_deployments:
            if dep.get("hasActiveUpdateSession"):
                try:
                    deployment_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, dep["deploymentId"])
                    if "ERROR" not in deployment_file and "topology" in deployment_file:
                        dep_topology = deployment_file["topology"]
                        # Use deployment's topology which includes new nodes
                        dep_nodes = dep_topology.get("nodes", [])
                        dep_edges = dep_topology.get("edges", [])
                        
                        # Mark existing nodes as deployed/locked
                        for node in dep_nodes:
                            if node.get("status") != "deployed":
                                # New nodes from update session don't have status
                                node["status"] = "new"
                            node["data"] = node.get("data", {})
                            node["data"]["locked"] = node.get("status") == "deployed"
                        
                        response_topology = {"nodes": dep_nodes, "edges": dep_edges}
                        update_apis_blueprint.logger.info(f"GET_SCENARIO_TOPOLOGY: Using topology from active update session in {dep['deploymentId']} with {len(dep_nodes)} nodes")
                        break
                except Exception as e:
                    update_apis_blueprint.logger.warning(f"GET_SCENARIO_TOPOLOGY: Could not load deployment topology: {e}")
        
        response_data = {
            "scenario": scenario_name,
            "topology": response_topology,
            "credentials": credentials,
            "machines": scenario.get("machines", {}),
            "imageReferences": scenario.get("imageReferences", {}),
            "description": scenario.get("description", ""),
            "info": scenario.get("info", ""),
            "deploymentId": existing_deployment_id,  # Backwards compat: first match or None
            "existingDeployments": existing_deployments  # NEW: All matching deployments
        }
        
        update_apis_blueprint.logger.info(f"GET_SCENARIO_TOPOLOGY: Successfully loaded topology with {len(response_topology['nodes'])} nodes, {len(existing_deployments)} existing deployment(s)")
        return jsonify(response_data), 200
        
    except Exception as e:
        update_apis_blueprint.logger.error(f"GET_SCENARIO_TOPOLOGY: Error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@update_apis_blueprint.route('/listBuildScenarios', methods=['GET'])
def list_build_scenarios():
    """
    List all saved Build scenarios that can be updated.
    
    Returns only scenarios that start with "Build-" prefix.
    Query param: excludeStandalone=true to filter out standalone VM scenarios
    """
    try:
        exclude_standalone = request.args.get('excludeStandalone', 'false').lower() == 'true'
        
        config = helpers.load_config()
        all_scenarios = config.get("scenarios", [])
        
        build_scenarios = [s for s in all_scenarios if s.startswith("Build-")]
        
        scenarios_info = []
        for scenario_name in build_scenarios:
            try:
                scenario = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
                if "ERROR" not in scenario:
                    if exclude_standalone and scenario.get("type") == "STANDALONE":
                        update_apis_blueprint.logger.debug(f"LIST_BUILD_SCENARIOS: Excluding standalone scenario {scenario_name}")
                        continue
                    
                    scenarios_info.append({
                        "name": scenario_name,
                        "description": scenario.get("description", ""),
                        "machines": list(scenario.get("machines", {}).keys()),
                        "nodeCount": len(scenario.get("topology", {}).get("nodes", [])) if scenario.get("topology") else 0,
                        "type": scenario.get("type", "BUILD")
                    })
            except Exception as e:
                update_apis_blueprint.logger.warning(f"LIST_BUILD_SCENARIOS: Could not load {scenario_name}: {e}")
        
        update_apis_blueprint.logger.info(f"LIST_BUILD_SCENARIOS: Found {len(scenarios_info)} build scenarios (excludeStandalone={exclude_standalone})")
        return jsonify({"scenarios": scenarios_info}), 200
        
    except Exception as e:
        update_apis_blueprint.logger.error(f"LIST_BUILD_SCENARIOS: Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@update_apis_blueprint.route('/deployScenarioForUpdate', methods=['POST'])
def deploy_scenario_for_update():
    """
    Deploy a saved scenario in preparation for adding new nodes.
    
    This is similar to regular scenario deployment but:
    1. Tracks the update session in the deployment file
    2. Returns the resource group name for subsequent update deployments
    
    Body:
    - scenario: The scenario name (e.g., "Build-RX40Q")
    
    Returns:
    - deploymentID: The resource group name (5 chars)
    - scenario: The scenario being updated
    """
    try:
        data = request.get_json()
        scenario_name = data.get('scenario')
        
        if not scenario_name:
            return jsonify({"error": "Scenario name is required"}), 400
        
        if not scenario_name.startswith("Build-"):
            return jsonify({"error": "Only Build scenarios can be updated"}), 400
        
        update_apis_blueprint.logger.info(f"DEPLOY_FOR_UPDATE: Deploying {scenario_name} for update")
        
        app_config = helpers.load_config()
        if app_config.get("azureAuth") != "true":
            return jsonify({"error": "Not authorized to Azure"}), 401
        
        scenario = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
        if "ERROR" in scenario:
            return jsonify({"error": f"Scenario {scenario_name} not found"}), 404
        
        caller_ip = None
        try:
            response = http_requests.get('https://api.ipify.org?format=json', timeout=helpers.IP_LOOKUP_TIMEOUT)
            caller_ip = response.json()['ip']
            update_apis_blueprint.logger.info(f"DEPLOY_FOR_UPDATE: Detected public IP: {caller_ip}")
        except Exception as e:
            update_apis_blueprint.logger.warning(f"DEPLOY_FOR_UPDATE: Failed to detect public IP: {e}")
            caller_ip = request.remote_addr
        
        result = deployment_handler.deploy_scenario(scenario_name, caller_ip)
        
        if "deploymentID" not in result:
            return jsonify({"error": result.get("message", "Deployment failed")}), 500
        
        deployment_id = result["deploymentID"]
        
        import time
        time.sleep(1)
        
        try:
            deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
            if "ERROR" not in deployment:
                deployment["updateSession"] = {
                    "active": True,
                    "baseScenario": scenario_name,
                    "originalTopology": scenario.get("topology", {}),
                    "newNodes": [],
                    "newEdges": [],
                    "savedToScenario": False
                }
                fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deployment_id)
                update_apis_blueprint.logger.info(f"DEPLOY_FOR_UPDATE: Updated deployment {deployment_id} with update session")
        except Exception as e:
            update_apis_blueprint.logger.warning(f"DEPLOY_FOR_UPDATE: Could not update deployment file: {e}")
        
        update_apis_blueprint.logger.info(f"DEPLOY_FOR_UPDATE: Started deployment {deployment_id} for scenario {scenario_name}")
        
        return jsonify({
            "deploymentID": deployment_id,
            "scenario": scenario_name,
            "message": f"Deploying {scenario_name} to {deployment_id} for update"
        }), 200
        
    except Exception as e:
        update_apis_blueprint.logger.error(f"DEPLOY_FOR_UPDATE: Error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@update_apis_blueprint.route('/updateJumpboxConnection', methods=['POST'])
def update_jumpbox_connection():
    """
    Update the Jumpbox connection to a different node.
    
    This handles the NSG rule updates when the Jumpbox is repositioned:
    1. Remove Jumpbox NSG rules from the OLD connected node
    2. Add Jumpbox NSG rules to the NEW connected node (unless removeOnly=true)
    
    Body:
    - deploymentID: The resource group
    - oldConnectedIP: The IP of the previously connected node
    - newConnectedIP: The IP of the newly connected node
    - jumpboxIP: The Jumpbox's IP address
    - removeOnly: If true, only remove rules from old node (don't add to new)
    
    Returns:
    - message: Status message
    """
    try:
        data = request.get_json()
        deployment_id = data.get('deploymentID')
        old_connected_ip = data.get('oldConnectedIP')
        new_connected_ip = data.get('newConnectedIP')
        jumpbox_ip = data.get('jumpboxIP')
        remove_only = data.get('removeOnly', False)
        
        if not deployment_id:
            return jsonify({"error": "deploymentID is required"}), 400
        if not new_connected_ip and not remove_only:
            return jsonify({"error": "newConnectedIP is required"}), 400
        if not jumpbox_ip:
            return jsonify({"error": "jumpboxIP is required"}), 400
        
        update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Updating Jumpbox connection from {old_connected_ip} to {new_connected_ip} (removeOnly={remove_only})")
        
        app_config = helpers.load_config()
        if app_config.get("azureAuth") != "true":
            return jsonify({"error": "Not authorized to Azure"}), 401
        
        network_client = azure_clients.get_network_client()
        
        nsgs = list(network_client.network_security_groups.list(deployment_id))
        update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Found {len(nsgs)} NSGs in {deployment_id}")
        
        def find_nsg_for_ip(target_ip):
            """Find the NSG associated with a machine by its IP."""
            nics = list(network_client.network_interfaces.list(deployment_id))
            for nic in nics:
                for ip_config in nic.ip_configurations:
                    if ip_config.private_ip_address == target_ip:
                        if nic.network_security_group:
                            nsg_id = nic.network_security_group.id
                            nsg_name = nsg_id.split('/')[-1]
                            return nsg_name
                        if ip_config.subnet:
                            subnet_id = ip_config.subnet.id
                            # Parse subnet info
                            parts = subnet_id.split('/')
                            vnet_name = parts[parts.index('virtualNetworks') + 1]
                            subnet_name = parts[parts.index('subnets') + 1]
                            subnet = network_client.subnets.get(deployment_id, vnet_name, subnet_name)
                            if subnet.network_security_group:
                                return subnet.network_security_group.id.split('/')[-1]
            return None
        
        jumpbox_inbound_rule = {
            'name': 'Allow-Jumpbox-Communication-Inbound',
            'protocol': '*',
            'source_port_range': '*',
            'destination_port_range': '*',
            'source_address_prefix': jumpbox_ip,
            'destination_address_prefix': '*',
            'access': 'Allow',
            'priority': 150,
            'direction': 'Inbound',
            'description': 'Allows inbound traffic from jumpbox'
        }
        
        jumpbox_outbound_rule = {
            'name': 'Allow-Jumpbox-Communication-Outbound',
            'protocol': '*',
            'source_port_range': '*',
            'destination_port_range': '*',
            'source_address_prefix': '*',
            'destination_address_prefix': jumpbox_ip,
            'access': 'Allow',
            'priority': 150,
            'direction': 'Outbound',
            'description': 'Allows outbound traffic to jumpbox'
        }
        
        # Remove rules from OLD connected node's NSG (if provided)
        if old_connected_ip and old_connected_ip != new_connected_ip:
            old_nsg_name = find_nsg_for_ip(old_connected_ip)
            if old_nsg_name:
                update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Removing Jumpbox rules from {old_nsg_name}")
                try:
                    try:
                        network_client.security_rules.begin_delete(
                            deployment_id,
                            old_nsg_name,
                            'Allow-Jumpbox-Communication-Inbound'
                        ).result()
                        update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Removed inbound rule from {old_nsg_name}")
                    except Exception as e:
                        update_apis_blueprint.logger.warning(f"UPDATE_JUMPBOX_CONNECTION: Could not remove inbound rule: {e}")
                    
                    try:
                        network_client.security_rules.begin_delete(
                            deployment_id,
                            old_nsg_name,
                            'Allow-Jumpbox-Communication-Outbound'
                        ).result()
                        update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Removed outbound rule from {old_nsg_name}")
                    except Exception as e:
                        update_apis_blueprint.logger.warning(f"UPDATE_JUMPBOX_CONNECTION: Could not remove outbound rule: {e}")
                        
                except Exception as e:
                    update_apis_blueprint.logger.warning(f"UPDATE_JUMPBOX_CONNECTION: Error removing rules from old NSG: {e}")
            else:
                update_apis_blueprint.logger.warning(f"UPDATE_JUMPBOX_CONNECTION: Could not find NSG for old IP {old_connected_ip}")
        
        # Add rules to NEW connected node's NSG (skip if removeOnly=true)
        if not remove_only and new_connected_ip:
            new_nsg_name = find_nsg_for_ip(new_connected_ip)
            if new_nsg_name:
                update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Adding Jumpbox rules to {new_nsg_name}")
                try:
                    from azure.mgmt.network.models import SecurityRule
                    
                    inbound_rule = SecurityRule(
                        name='Allow-Jumpbox-Communication-Inbound',
                        protocol='*',
                        source_port_range='*',
                        destination_port_range='*',
                        source_address_prefix=jumpbox_ip,
                        destination_address_prefix=new_connected_ip,
                        access='Allow',
                        priority=150,
                        direction='Inbound',
                        description='Allows inbound traffic from jumpbox'
                    )
                    network_client.security_rules.begin_create_or_update(
                        deployment_id,
                        new_nsg_name,
                        'Allow-Jumpbox-Communication-Inbound',
                        inbound_rule
                    ).result()
                    update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Added inbound rule to {new_nsg_name}")
                    
                    outbound_rule = SecurityRule(
                        name='Allow-Jumpbox-Communication-Outbound',
                        protocol='*',
                        source_port_range='*',
                        destination_port_range='*',
                        source_address_prefix=new_connected_ip,
                        destination_address_prefix=jumpbox_ip,
                        access='Allow',
                        priority=150,
                        direction='Outbound',
                        description='Allows outbound traffic to jumpbox'
                    )
                    network_client.security_rules.begin_create_or_update(
                        deployment_id,
                        new_nsg_name,
                        'Allow-Jumpbox-Communication-Outbound',
                        outbound_rule
                    ).result()
                    update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Added outbound rule to {new_nsg_name}")
                    
                except Exception as e:
                    update_apis_blueprint.logger.error(f"UPDATE_JUMPBOX_CONNECTION: Error adding rules to new NSG: {e}")
                    return jsonify({"error": f"Failed to add NSG rules: {str(e)}"}), 500
            else:
                update_apis_blueprint.logger.warning(f"UPDATE_JUMPBOX_CONNECTION: Could not find NSG for new IP {new_connected_ip} - this is expected if connecting to a new node")
        
        if not remove_only and new_connected_ip:
            jumpbox_nsg_name = find_nsg_for_ip(jumpbox_ip)
            if jumpbox_nsg_name:
                update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Updating Jumpbox's own NSG {jumpbox_nsg_name}")
                try:
                    from azure.mgmt.network.models import SecurityRule
                    
                    inbound_rule = SecurityRule(
                        name='Allow-ConnectedIP-All-Inbound',
                        protocol='*',
                        source_port_range='*',
                        destination_port_range='*',
                        source_address_prefix=new_connected_ip,  # FROM the connected node
                        destination_address_prefix=jumpbox_ip,   # TO the Jumpbox
                        access='Allow',
                        priority=105,
                        direction='Inbound',
                        description='Allows all inbound traffic from connected private IP'
                    )
                    network_client.security_rules.begin_create_or_update(
                        deployment_id,
                        jumpbox_nsg_name,
                        'Allow-ConnectedIP-All-Inbound',
                        inbound_rule
                    ).result()
                    update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Updated Jumpbox inbound rule to allow from {new_connected_ip}")
                    
                    outbound_rule = SecurityRule(
                        name='Allow-ConnectedIP-All-Outbound',
                        protocol='*',
                        source_port_range='*',
                        destination_port_range='*',
                        source_address_prefix=jumpbox_ip,        # FROM the Jumpbox
                        destination_address_prefix=new_connected_ip,  # TO the connected node
                        access='Allow',
                        priority=105,
                        direction='Outbound',
                        description='Allows all outbound traffic to connected private IP'
                    )
                    network_client.security_rules.begin_create_or_update(
                        deployment_id,
                        jumpbox_nsg_name,
                        'Allow-ConnectedIP-All-Outbound',
                        outbound_rule
                    ).result()
                    update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Updated Jumpbox outbound rule to allow to {new_connected_ip}")
                    
                except Exception as e:
                    update_apis_blueprint.logger.error(f"UPDATE_JUMPBOX_CONNECTION: Error updating Jumpbox's NSG: {e}")
                    return jsonify({"error": f"Failed to update Jumpbox NSG rules: {str(e)}"}), 500
            else:
                update_apis_blueprint.logger.warning(f"UPDATE_JUMPBOX_CONNECTION: Could not find NSG for Jumpbox IP {jumpbox_ip}")
        
        if not remove_only and new_connected_ip:
            try:
                deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
                if "ERROR" not in deployment:
                    topology = deployment.get("topology", {})
                    for node in topology.get("nodes", []):
                        if node.get("type") == "jumpbox":
                            node["data"] = node.get("data", {})
                            node["data"]["connectedPrivateIPAddress"] = new_connected_ip
                        # Also update any edge connections
                        break
                
                edges = topology.get("edges", [])
                jumpbox_node_id = None
                for node in topology.get("nodes", []):
                    if node.get("type") == "jumpbox":
                        jumpbox_node_id = node.get("id")
                        break
                
                if jumpbox_node_id:
                    # Remove old Jumpbox edges
                    edges = [e for e in edges if e.get("source") != jumpbox_node_id and e.get("target") != jumpbox_node_id]
                    
                    # Find the new target node ID
                    new_target_id = None
                    for node in topology.get("nodes", []):
                        if node.get("data", {}).get("privateIPAddress") == new_connected_ip:
                            new_target_id = node.get("id")
                            break
                    
                    # Add new edge
                    if new_target_id:
                        edges.append({
                            "id": f"e-{jumpbox_node_id}-{new_target_id}",
                            "source": jumpbox_node_id,
                            "target": new_target_id,
                            "type": "default"
                        })
                
                topology["edges"] = edges
                deployment["topology"] = topology
                fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deployment_id)
                update_apis_blueprint.logger.info(f"UPDATE_JUMPBOX_CONNECTION: Updated deployment topology")
            except Exception as e:
                update_apis_blueprint.logger.warning(f"UPDATE_JUMPBOX_CONNECTION: Could not update deployment file: {e}")
        
        if remove_only:
            return jsonify({
                "message": f"Successfully removed Jumpbox rules from old connection {old_connected_ip or 'none'}",
                "deploymentID": deployment_id
            }), 200
        else:
            return jsonify({
                "message": f"Successfully updated Jumpbox connection from {old_connected_ip or 'none'} to {new_connected_ip}",
                "deploymentID": deployment_id,
                "newConnectedIP": new_connected_ip
            }), 200
        
    except Exception as e:
        update_apis_blueprint.logger.error(f"UPDATE_JUMPBOX_CONNECTION: Error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@update_apis_blueprint.route('/deployUpdate', methods=['POST'])
def deploy_update():
    """
    Deploy new nodes to an existing running scenario.
    
    This generates UPDATE-only bicep with:
    - New VNets if needed
    - VNet peerings for cross-subnet connectivity
    - New SubDC, Workstation, or CA modules
    
    Body:
    - deploymentID: The resource group to deploy to (5 chars)
    - baseScenario: The scenario being updated (e.g., "Build-RX40Q")
    - newNodes: Array of new nodes to add
    - newEdges: Array of edges (including connections to existing nodes)
    - existingNodes: Array of existing nodes (for dependency resolution)
    
    Returns:
    - message: Status message
    - deploymentID: The resource group name
    """
    try:
        data = request.get_json()
        deployment_id = data.get('deploymentID')
        base_scenario = data.get('scenario') or data.get('baseScenario')
        new_nodes = data.get('newNodes', [])
        new_edges = data.get('newEdges', [])
        existing_nodes = data.get('existingNodes', [])
        credentials = data.get('credentials', {})
        
        if not deployment_id:
            return jsonify({"error": "deploymentID is required"}), 400
        if not base_scenario:
            return jsonify({"error": "scenario is required"}), 400
        if not new_nodes:
            return jsonify({"error": "No new nodes to deploy"}), 400
        
        update_apis_blueprint.logger.info(f"DEPLOY_UPDATE: Deploying {len(new_nodes)} new nodes to {deployment_id}")
        
        app_config = helpers.load_config()
        if app_config.get("azureAuth") != "true":
            return jsonify({"error": "Not authorized to Azure"}), 401
        
        scenario = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{base_scenario}.json")
        if "ERROR" in scenario:
            return jsonify({"error": f"Scenario {base_scenario} not found"}), 404
        
        topology = scenario.get("topology", {})
        credentials = topology.get("credentials", {})
        enterprise_admin_username = credentials.get("enterpriseAdminUsername", "")
        enterprise_admin_password = credentials.get("enterpriseAdminPassword", "")
        
        if not enterprise_admin_username or not enterprise_admin_password:
            return jsonify({"error": "Missing credentials in scenario"}), 400
        
        caller_ip = None
        try:
            response = http_requests.get('https://api.ipify.org?format=json', timeout=helpers.IP_LOOKUP_TIMEOUT)
            caller_ip = response.json()['ip']
        except:
            caller_ip = request.remote_addr
        
        bicep_content = generate_update_bicep(
            deployment_id=deployment_id,
            base_scenario=base_scenario,
            new_nodes=new_nodes,
            new_edges=new_edges,
            existing_nodes=existing_nodes,
            enterprise_admin_username=enterprise_admin_username,
            enterprise_admin_password=enterprise_admin_password,
            caller_ip=caller_ip
        )
        
        update_bicep_dir = helpers.UPDATES_TEMPLATE_DIRECTORY
        os.makedirs(update_bicep_dir, exist_ok=True)
        
        update_bicep_path = os.path.join(update_bicep_dir, f"Update-{deployment_id}.bicep")
        with open(update_bicep_path, 'w') as f:
            f.write(bicep_content)
        
        update_apis_blueprint.logger.info(f"DEPLOY_UPDATE: Generated update bicep at {update_bicep_path}")
        
        update_json_path = os.path.join(update_bicep_dir, f"Update-{deployment_id}.json")
        compile_command = ["az", "bicep", "build", "--file", update_bicep_path, "--outfile", update_json_path]
        compile_output = command_runner.run_command_and_read_output(compile_command)
        compile_exit_code = command_runner.run_command_and_get_exit_code(compile_command)
        
        if compile_exit_code != 0:
            update_apis_blueprint.logger.error(f"DEPLOY_UPDATE: Bicep compilation failed: {compile_output}")
            return jsonify({"error": f"Failed to compile update template: {compile_output}"}), 500
        
        update_apis_blueprint.logger.info(f"DEPLOY_UPDATE: Compiled update bicep to JSON")
        
        with open(update_json_path, 'r') as f:
            template = json.load(f)
        
        parameters = {
            "enterpriseAdminUsername": {"value": enterprise_admin_username},
            "enterpriseAdminPassword": {"value": enterprise_admin_password},
            "callerIPAddress": {"value": caller_ip if caller_ip else ""}
        }
        
        deployment_properties = DeploymentProperties(
            mode=DeploymentMode.INCREMENTAL,
            template=template,
            parameters=parameters
        )
        
        deployment = Deployment(properties=deployment_properties)
        
        resource_client = azure_clients.get_resource_client()
        
        update_deployment_name = f"update-{deployment_id}-{helpers.generate_random_id(size=4)}"
        
        poller = resource_client.deployments.begin_create_or_update(
            resource_group_name=deployment_id,
            deployment_name=update_deployment_name,
            parameters=deployment
        )
        
        update_apis_blueprint.logger.info(f"DEPLOY_UPDATE: Started update deployment {update_deployment_name} to {deployment_id}")
        
        try:
            deployment_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
            if "ERROR" not in deployment_file:
                if "updateSession" not in deployment_file:
                    deployment_file["updateSession"] = {
                        "active": True,
                        "baseScenario": base_scenario,
                        "savedToScenario": False
                    }
                
                deployment_file["updateSession"]["newNodes"] = new_nodes
                deployment_file["updateSession"]["newEdges"] = new_edges
                deployment_file["updateSession"]["updateDeploymentName"] = update_deployment_name
                
                current_topology = deployment_file.get("topology", topology)
                current_topology["nodes"] = existing_nodes + new_nodes
                current_topology["edges"] = list(current_topology.get("edges", [])) + new_edges
                deployment_file["topology"] = current_topology
                
                fs_manager.save_file(deployment_file, helpers.DEPLOYMENT_DIRECTORY, deployment_id)
                update_apis_blueprint.logger.info(f"DEPLOY_UPDATE: Updated deployment file with new nodes")
        except Exception as e:
            update_apis_blueprint.logger.warning(f"DEPLOY_UPDATE: Could not update deployment file: {e}")
        
        return jsonify({
            "message": f"Deploying {len(new_nodes)} new nodes to {deployment_id}",
            "deploymentID": deployment_id,
            "updateDeploymentName": update_deployment_name
        }), 200
        
    except Exception as e:
        update_apis_blueprint.logger.error(f"DEPLOY_UPDATE: Error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def generate_update_bicep(deployment_id, base_scenario, new_nodes, new_edges, existing_nodes, 
                          enterprise_admin_username, enterprise_admin_password, caller_ip):
    """
    Generate a bicep file that deploys ONLY the new nodes to an existing resource group.
    
    This handles:
    - Creating new VNets if nodes are on new subnets
    - Creating VNet peerings between new and existing VNets
    - Deploying SubDCs that join existing domains
    - Deploying Workstations that join existing domains
    """
    
    update_apis_blueprint.logger.info(f"GENERATE_UPDATE_BICEP: Generating for {len(new_nodes)} nodes")
    
    all_nodes = existing_nodes + new_nodes
    node_map = {node["id"]: node for node in all_nodes}
    
    # Determine which VNets already exist (from existing nodes)
    existing_vnets = set()
    for node in existing_nodes:
        ip = node.get("data", {}).get("privateIPAddress", "")
        vnet = get_vnet_from_ip(ip)
        if vnet:
            existing_vnets.add(vnet)
    
    # Determine which VNets are needed (from new nodes)
    new_vnets_needed = set()
    for node in new_nodes:
        ip = node.get("data", {}).get("privateIPAddress", "")
        vnet = get_vnet_from_ip(ip)
        if vnet and vnet not in existing_vnets:
            new_vnets_needed.add(vnet)
    
    update_apis_blueprint.logger.info(f"GENERATE_UPDATE_BICEP: Existing VNets: {existing_vnets}, New VNets needed: {new_vnets_needed}")
    
    jumpbox_ip = ""
    jumpbox_connected_ip = ""  # The IP of the node the Jumpbox connects to
    jumpbox_node = None
    for node in all_nodes:
        if node.get("type") == "jumpbox":
            jumpbox_ip = node.get("data", {}).get("privateIPAddress", "")
            jumpbox_node = node
            break
    
    # Find which node the Jumpbox connects to (from edges)
    if jumpbox_node:
        jumpbox_id = jumpbox_node.get("id")
        # Check all edges (both new and existing)
        all_edges = new_edges + [e for e in existing_nodes if isinstance(e, dict) and "source" in e]
        for edge in new_edges:
            if edge.get("source") == jumpbox_id:
                target_id = edge.get("target")
                target_node = node_map.get(target_id)
                if target_node:
                    jumpbox_connected_ip = target_node.get("data", {}).get("privateIPAddress", "")
                    break
            elif edge.get("target") == jumpbox_id:
                source_id = edge.get("source")
                source_node = node_map.get(source_id)
                if source_node:
                    jumpbox_connected_ip = source_node.get("data", {}).get("privateIPAddress", "")
                    break
    
    update_apis_blueprint.logger.info(f"GENERATE_UPDATE_BICEP: Jumpbox IP: {jumpbox_ip}, Connected to: {jumpbox_connected_ip}")
    
    # Find root domain from existing nodes for UPN format
    root_domain_name = ""
    for node in existing_nodes:
        if node.get("type") == "domainController":
            node_data = node.get("data", {})
            if not node_data.get("isSub", False):
                root_domain_name = node_data.get("domainName", "")
                break
    
    # Fallback: use any DC's domain
    if not root_domain_name:
        for node in existing_nodes:
            if node.get("type") == "domainController":
                root_domain_name = node.get("data", {}).get("domainName", "")
                break
    
    if not root_domain_name:
        root_domain_name = "domain.local"  # Absolute fallback
    
    update_apis_blueprint.logger.info(f"GENERATE_UPDATE_BICEP: Root domain for UPN: {root_domain_name}")

    config = helpers.load_config()
    vm_sizes = config.get("vmSizes", {})
    windows_vm_size = vm_sizes.get("windowsVmSize", "Standard_B1ms")

    bicep_content = f"""// Auto-generated UPDATE bicep for {deployment_id}
// Adds new nodes to existing scenario {base_scenario}
targetScope = 'resourceGroup'

param enterpriseAdminUsername string
@secure()
param enterpriseAdminPassword string
param callerIPAddress string = ''
param location string = resourceGroup().location
param windowsVmSize string = '{windows_vm_size}'
param vmDiskType string = 'Standard_LRS'
param oldScenarios bool = false
param deployOrBuild string = 'build'

param kaliSku string = 'kali-2025-2'

// Construct UPN format for domain join (username@domain.tld)
var domainAndEnterpriseAdminUsername = '${{enterpriseAdminUsername}}@{root_domain_name}'

"""
    
    for vnet in new_vnets_needed:
        vnet_config = get_vnet_config(vnet)
        bicep_content += f"""
module {vnet_config['module_name']} '../base/VirtualNetwork.bicep' = {{
  name: '{vnet_config['name']}'
  params: {{
    location: location
    vnetName: '{vnet_config['name']}'
    virtualNetworkAddressPrefix: '{vnet_config['address_prefix']}'
    rootSubnetAddressPrefix: '{vnet_config['subnet_prefix']}'
    oldScenarios: oldScenarios
  }}
}}
"""
    
    # VNet peerings are now handled by the base templates (SubDomainController2.bicep, etc.)
    peerings_needed = set()
    for new_vnet in new_vnets_needed:
        for existing_vnet in existing_vnets:
            peering_key = tuple(sorted([new_vnet, existing_vnet]))
            peerings_needed.add(peering_key)
    
    update_apis_blueprint.logger.info(f"GENERATE_UPDATE_BICEP: Peerings needed: {peerings_needed} (will be created by base templates)")
    
    new_jumpbox_node = None
    for node in new_nodes:
        if node.get("type") == "jumpbox":
            new_jumpbox_node = node
            break
    
    if new_jumpbox_node:
        jb_data = new_jumpbox_node.get("data", {})
        jb_ip = jb_data.get("privateIPAddress", "")
        jb_vnet = get_vnet_from_ip(jb_ip)
        
        kali_sku = helpers.get_latest_kali_sku()
        update_apis_blueprint.logger.info(f"GENERATE_UPDATE_BICEP: Generating Jumpbox module with Kali SKU: {kali_sku}")
        
        jb_depends = []
        if jb_vnet in new_vnets_needed:
            jb_vnet_config = get_vnet_config(jb_vnet)
            jb_depends.append(jb_vnet_config['module_name'])
        
        jb_depends_str = ", ".join(jb_depends) if jb_depends else ""
        jb_depends_block = f"  dependsOn: [{jb_depends_str}]\n" if jb_depends else ""
        
        is_vnet_10 = "true" if "10" in existing_vnets or "10" in new_vnets_needed else "false"
        is_vnet_172 = "true" if "172" in existing_vnets or "172" in new_vnets_needed else "false"
        is_vnet_192 = "true" if "192" in existing_vnets or "192" in new_vnets_needed else "false"
        
        bicep_content += f"""
module Jumpbox '../base/Jumpbox.bicep' = {{
  name: 'Jumpbox'
  params: {{
    location: location
    vmName: 'UpdateJumpbox'
    vmSize: 'Standard_B2s'
    resourceGroupName: resourceGroup().name
    jumpboxPrivateIPAddress: '{jb_ip}'
    osDiskType: vmDiskType
    deployOrBuild: 'build'
    oldScenarios: oldScenarios
    connectedPrivateIPAddress: '{jumpbox_connected_ip}'
    isVNet10Required: {is_vnet_10}
    isVNet192Required: {is_vnet_192}
    isVNet172Required: {is_vnet_172}
    jumpboxAdminUsername: 'redteamer'
    jumpboxAdminPassword: 'Password#123'
    kaliSku: '{kali_sku}'
    callerIPAddress: '{caller_ip}'
  }}
{jb_depends_block}}}
"""
        update_apis_blueprint.logger.info(f"GENERATE_UPDATE_BICEP: Added Jumpbox module with IP {jb_ip}")
    
    # Build edge map for finding parent nodes
    edge_map = {}  # target -> source
    for edge in (new_edges + [e for e in node_map.get("edges", []) if isinstance(e, dict)]):
        if isinstance(edge, dict):
            source = edge.get("source", "")
            target = edge.get("target", "")
            if source and target:
                edge_map[target] = source
    
    # Also parse edges from existing topology
    for node in existing_nodes:
        pass  # existing_nodes don't contain edges
    
    # Build a mapping of domain name -> module name for Sub DC dependency resolution
    domain_to_module_name = {}
    new_subdc_nodes = []
    for node in new_nodes:
        if node.get("type") == "domainController":
            dc_name = node.get("data", {}).get("domainControllerName", "")
            domain_name = node.get("data", {}).get("domainName", "")
            if dc_name and domain_name:
                domain_to_module_name[domain_name] = dc_name
                new_subdc_nodes.append(node)
    
    new_subdc_names = list(domain_to_module_name.values())
    update_apis_blueprint.logger.info(f"GENERATE_UPDATE_BICEP: New Sub DCs: {new_subdc_names}, domain mapping: {domain_to_module_name}")
    
    peering_created_by = {}
    
    # Process each new node - DCs first with parent-based dependencies, then workstations/CAs
    # First pass: Domain Controllers only - each depends on its PARENT Sub DC, not all Sub DCs
    for node in new_subdc_nodes:
        node_data = node.get("data", {})
        domain_name = node_data.get("domainName", "")
        dc_name = node_data.get("domainControllerName", "")
        
        # Find the parent domain by removing the leftmost part (same logic as build_apis.py)
        domain_parts = domain_name.split('.') if domain_name else []
        parent_domain = '.'.join(domain_parts[1:]) if len(domain_parts) > 1 else None
        
        parent_dc_name = domain_to_module_name.get(parent_domain) if parent_domain else None
        
        update_apis_blueprint.logger.info(f"GENERATE_UPDATE_BICEP: Sub DC {dc_name} domain={domain_name} -> parent_domain={parent_domain} -> parent_dc={parent_dc_name}")
        
        # This is a Sub DC joining an existing domain
        bicep_content += generate_subdc_module(
            node=node,
            node_map=node_map,
            new_edges=new_edges,
            existing_nodes=existing_nodes,
            jumpbox_ip=jumpbox_ip,
            jumpbox_connected_ip=jumpbox_connected_ip,
            new_vnets_needed=new_vnets_needed,
            existing_vnets=existing_vnets,
            parent_dc_name=parent_dc_name,  # Only depend on parent Sub DC if it's new
            peering_created_by=peering_created_by
        )
    
    for node in new_nodes:
        node_type = node.get("type")
        
        if node_type == "workstation":
            bicep_content += generate_workstation_module(
                node=node,
                node_map=node_map,
                new_edges=new_edges,
                existing_nodes=existing_nodes,
                jumpbox_ip=jumpbox_ip,
                jumpbox_connected_ip=jumpbox_connected_ip,
                new_vnets_needed=new_vnets_needed,
                existing_vnets=existing_vnets,
                wait_for_dcs=new_subdc_names  # Wait for ALL new Sub DCs
            )
        
        elif node_type == "certificateAuthority":
            bicep_content += generate_ca_module(
                node=node,
                node_map=node_map,
                new_edges=new_edges,
                existing_nodes=existing_nodes,
                jumpbox_ip=jumpbox_ip,
                jumpbox_connected_ip=jumpbox_connected_ip,
                new_vnets_needed=new_vnets_needed,
                existing_vnets=existing_vnets,
                wait_for_dcs=new_subdc_names  # Wait for ALL new Sub DCs
            )
    
    return bicep_content


def get_vnet_from_ip(ip):
    """Extract VNet identifier from IP address."""
    if not ip:
        return None
    if ip.startswith("10.10.") or ip.startswith("10."):
        return "10"
    elif ip.startswith("172.16.") or ip.startswith("172."):
        return "172"
    elif ip.startswith("192.168.") or ip.startswith("192."):
        return "192"
    return None


def get_vnet_config(vnet_id):
    """Get VNet configuration based on identifier."""
    configs = {
        "10": {
            "name": "vnet-10",
            "module_name": "vnet10",
            "address_prefix": "10.10.0.0/16",
            "subnet_prefix": "10.10.0.0/24"
        },
        "172": {
            "name": "vnet-172",
            "module_name": "vnet172",
            "address_prefix": "172.16.0.0/16",
            "subnet_prefix": "172.16.0.0/24"
        },
        "192": {
            "name": "vnet-192",
            "module_name": "vnet192",
            "address_prefix": "192.168.0.0/16",
            "subnet_prefix": "192.168.0.0/24"
        }
    }
    return configs.get(vnet_id, configs["10"])


def find_parent_dc(node, node_map, new_edges, existing_nodes):
    """Find the parent DC for a node based on edges."""
    node_id = node.get("id")
    
    # Look through edges to find parent
    for edge in new_edges:
        if edge.get("target") == node_id:
            source_id = edge.get("source")
            source_node = node_map.get(source_id)
            if source_node and source_node.get("type") == "domainController":
                return source_node
        if edge.get("source") == node_id:
            target_id = edge.get("target")
            target_node = node_map.get(target_id)
            if target_node and target_node.get("type") == "domainController":
                return target_node
    
    return None


def generate_subdc_module(node, node_map, new_edges, existing_nodes, jumpbox_ip, jumpbox_connected_ip, new_vnets_needed, existing_vnets, parent_dc_name=None, peering_created_by=None):
    """Generate bicep module for a new Sub DC.
    
    Args:
        parent_dc_name: Name of parent Sub DC if it's a new Sub DC in this update (for dependency).
                       None if parent is an existing DC.
        peering_created_by: Dict to track which module creates which peering (to avoid duplicates).
    """
    if peering_created_by is None:
        peering_created_by = {}
    
    node_data = node.get("data", {})
    machine_name = node_data.get("domainControllerName", "SUBDC01")
    private_ip = node_data.get("privateIPAddress", "")
    domain_name = node_data.get("domainName", "sub.domain.local")
    netbios = domain_name.split('.')[0] if domain_name else "SUB"
    
    parent_dc = find_parent_dc(node, node_map, new_edges, existing_nodes)
    if parent_dc:
        parent_ip = parent_dc.get("data", {}).get("privateIPAddress", "")
        parent_name = parent_dc.get("data", {}).get("domainControllerName", "DC01")
    else:
        # Try to find root DC from existing nodes
        for existing_node in existing_nodes:
            if existing_node.get("type") == "domainController":
                parent_ip = existing_node.get("data", {}).get("privateIPAddress", "")
                parent_name = existing_node.get("data", {}).get("domainControllerName", "DC01")
                break
        else:
            parent_ip = "10.10.0.5"  # Default fallback
            parent_name = "DC01"
    
    node_vnet = get_vnet_from_ip(private_ip)
    parent_vnet = get_vnet_from_ip(parent_ip)
    vnet_config = get_vnet_config(node_vnet)
    
    skip_parent_peering = False
    skip_root_peering = False
    
    parent_peering_key = tuple(sorted([node_vnet, parent_vnet])) if node_vnet and parent_vnet and node_vnet != parent_vnet else None
    
    parent_peering_dependency = None
    root_peering_dependency = None
    
    if parent_peering_key:
        if node_vnet in existing_vnets and parent_vnet in existing_vnets:
            skip_parent_peering = True
        elif parent_peering_key in peering_created_by:
            skip_parent_peering = True
            parent_peering_dependency = peering_created_by[parent_peering_key]  # Must depend on module that creates it
            update_apis_blueprint.logger.debug(f"UPDATE: {machine_name} will skip parent peering {parent_peering_key} - created by {parent_peering_dependency}, adding dependency")
        else:
            peering_created_by[parent_peering_key] = machine_name
    
    root_ip = ""
    for existing_node in existing_nodes:
        if existing_node.get("type") == "domainController":
            node_data_check = existing_node.get("data", {})
            if not node_data_check.get("isSub", False):
                root_ip = node_data_check.get("privateIPAddress", "")
                break
    
    root_vnet = get_vnet_from_ip(root_ip) if root_ip else None
    root_peering_key = tuple(sorted([node_vnet, root_vnet])) if node_vnet and root_vnet and node_vnet != root_vnet and root_ip != parent_ip else None
    
    if root_peering_key:
        if node_vnet in existing_vnets and root_vnet in existing_vnets:
            skip_root_peering = True
        elif root_peering_key in peering_created_by:
            skip_root_peering = True
            root_peering_dependency = peering_created_by[root_peering_key]  # Must depend on module that creates it
            update_apis_blueprint.logger.debug(f"UPDATE: {machine_name} will skip root peering {root_peering_key} - created by {root_peering_dependency}, adding dependency")
        else:
            peering_created_by[root_peering_key] = machine_name
    
    depends = []
    if node_vnet in new_vnets_needed:
        depends.append(vnet_config['module_name'])
    
    if parent_dc_name:
        depends.append(parent_dc_name)
    
    if parent_peering_dependency and parent_peering_dependency != parent_dc_name:
        depends.append(parent_peering_dependency)
    if root_peering_dependency and root_peering_dependency not in depends:
        depends.append(root_peering_dependency)
    
    depends_str = ", ".join(depends) if depends else ""
    depends_block = f"  dependsOn: [{depends_str}]\n" if depends else ""
    
    # Determine if this node is where the Jumpbox connects to
    connection_str = jumpbox_connected_ip if jumpbox_connected_ip else ""
    
    is_vnet_10 = "true" if any(get_vnet_from_ip(n.get("data", {}).get("privateIPAddress", "")) == "10" for n in existing_nodes) or node_vnet == "10" else "false"
    is_vnet_172 = "true" if any(get_vnet_from_ip(n.get("data", {}).get("privateIPAddress", "")) == "172" for n in existing_nodes) or node_vnet == "172" else "false"
    is_vnet_192 = "true" if any(get_vnet_from_ip(n.get("data", {}).get("privateIPAddress", "")) == "192" for n in existing_nodes) or node_vnet == "192" else "false"
    
    return f"""
// Deploy Sub Domain Controller: {machine_name}
module {machine_name} '../base/SubDomainController2.bicep' = {{
  name: '{machine_name}'
  params: {{
    location: location
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: '{machine_name}'
    parentVirtualMachineHostname: '{parent_name}'
    resourceGroupName: resourceGroup().name
    osDiskType: vmDiskType
    domainName: '{domain_name}'
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    rootDomainNetBIOSName: '{netbios}'
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    deployOrBuild: deployOrBuild
    isRoot: false
    rootDomainControllerFQDN: '{parent_name}'
    parentDomainControllerPrivateIp: '{parent_ip}'
    rootDomainControllerPrivateIp: '{root_ip}'
    privateIPAddress: '{private_ip}'
    oldScenarios: oldScenarios
    jumpboxPrivateIPAddress: '{jumpbox_ip}'
    connectedPrivateIPAddress: '{connection_str}'
    isVNet10Required: {is_vnet_10}
    isVNet172Required: {is_vnet_172}
    isVNet192Required: {is_vnet_192}
    skipParentPeering: {'true' if skip_parent_peering else 'false'}
    skipRootPeering: {'true' if skip_root_peering else 'false'}
  }}
{depends_block}}}
"""


def generate_workstation_module(node, node_map, new_edges, existing_nodes, jumpbox_ip, jumpbox_connected_ip, new_vnets_needed, existing_vnets=None, wait_for_dcs=None):
    """Generate bicep module for a new Workstation."""
    if existing_vnets is None:
        existing_vnets = set()
    if wait_for_dcs is None:
        wait_for_dcs = []
    
    node_data = node.get("data", {})
    machine_name = node_data.get("workstationName", "WS01")
    private_ip = node_data.get("privateIPAddress", "")
    
    # Find parent DC for domain info
    parent_dc = find_parent_dc(node, node_map, new_edges, existing_nodes)
    if parent_dc:
        dc_ip = parent_dc.get("data", {}).get("privateIPAddress", "")
        domain_name = parent_dc.get("data", {}).get("domainName", "domain.local")
    else:
        for existing_node in existing_nodes:
            if existing_node.get("type") == "domainController":
                dc_ip = existing_node.get("data", {}).get("privateIPAddress", "")
                domain_name = existing_node.get("data", {}).get("domainName", "domain.local")
                break
        else:
            dc_ip = "10.10.0.5"
            domain_name = "domain.local"
    
    node_vnet = get_vnet_from_ip(private_ip)
    dc_vnet = get_vnet_from_ip(dc_ip)
    vnet_config = get_vnet_config(node_vnet)
    
    # Skip peering if BOTH the node's VNet AND the DC's VNet already exist
    skip_peering = (node_vnet in existing_vnets and dc_vnet in existing_vnets)
    
    depends = []
    if node_vnet in new_vnets_needed:
        depends.append(vnet_config['module_name'])
    
    for dc_name in wait_for_dcs:
        depends.append(dc_name)
    
    depends_str = ", ".join(depends) if depends else ""
    depends_block = f"  dependsOn: [{depends_str}]\n" if depends else ""
    
    # Determine if this node is where the Jumpbox connects to
    connection_str = jumpbox_connected_ip if jumpbox_connected_ip else ""
    
    is_vnet_10 = "true" if any(get_vnet_from_ip(n.get("data", {}).get("privateIPAddress", "")) == "10" for n in existing_nodes) or node_vnet == "10" else "false"
    is_vnet_172 = "true" if any(get_vnet_from_ip(n.get("data", {}).get("privateIPAddress", "")) == "172" for n in existing_nodes) or node_vnet == "172" else "false"
    is_vnet_192 = "true" if any(get_vnet_from_ip(n.get("data", {}).get("privateIPAddress", "")) == "192" for n in existing_nodes) or node_vnet == "192" else "false"
    
    skip_peering_str = "true" if skip_peering else "false"
    
    return f"""
module {machine_name} '../base/StandaloneServer.bicep' = {{
  name: '{machine_name}'
  params: {{
    location: location
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: '{machine_name}'
    resourceGroupName: resourceGroup().name
    osDiskType: vmDiskType
    domainName: '{domain_name}'
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    domainControllerPrivateIp: '{dc_ip}'
    standaloneServerPrivateIp: '{private_ip}'
    deployOrBuild: deployOrBuild
    rootOrSub: 'root'
    oldScenarios: oldScenarios
    jumpboxPrivateIPAddress: '{jumpbox_ip}'
    connectedPrivateIPAddress: '{connection_str}'
    isVNet10Required: {is_vnet_10}
    isVNet172Required: {is_vnet_172}
    isVNet192Required: {is_vnet_192}
    skipPeering: {skip_peering_str}
  }}
{depends_block}}}
"""


def generate_ca_module(node, node_map, new_edges, existing_nodes, jumpbox_ip, new_vnets_needed, jumpbox_connected_ip="", existing_vnets=None, wait_for_dcs=None):
    """Generate bicep module for a new Certificate Authority."""
    if existing_vnets is None:
        existing_vnets = set()
    if wait_for_dcs is None:
        wait_for_dcs = []
    
    node_data = node.get("data", {})
    machine_name = node_data.get("caName", "CA01")
    private_ip = node_data.get("privateIPAddress", "")
    
    parent_dc = find_parent_dc(node, node_map, new_edges, existing_nodes)
    if parent_dc:
        dc_ip = parent_dc.get("data", {}).get("privateIPAddress", "")
        domain_name = parent_dc.get("data", {}).get("domainName", "domain.local")
    else:
        for existing_node in existing_nodes:
            if existing_node.get("type") == "domainController" and not existing_node.get("data", {}).get("isSub"):
                dc_ip = existing_node.get("data", {}).get("privateIPAddress", "")
                domain_name = existing_node.get("data", {}).get("domainName", "domain.local")
                break
        else:
            dc_ip = "10.10.0.5"
            domain_name = "domain.local"
    
    node_vnet = get_vnet_from_ip(private_ip)
    dc_vnet = get_vnet_from_ip(dc_ip)
    vnet_config = get_vnet_config(node_vnet)
    
    # Skip peering if BOTH the node's VNet AND the DC's VNet already exist
    skip_peering = (node_vnet in existing_vnets and dc_vnet in existing_vnets)
    
    depends = []
    if node_vnet in new_vnets_needed:
        depends.append(vnet_config['module_name'])
    
    for dc_name in wait_for_dcs:
        depends.append(dc_name)
    
    depends_str = ", ".join(depends) if depends else ""
    depends_block = f"  dependsOn: [{depends_str}]\n" if depends else ""
    
    # Only set connection IP if this is the node the Jumpbox is connected to
    connection_str = private_ip if private_ip == jumpbox_connected_ip else ""
    
    is_vnet_10 = "true" if any(get_vnet_from_ip(n.get("data", {}).get("privateIPAddress", "")) == "10" for n in existing_nodes) or node_vnet == "10" else "false"
    is_vnet_172 = "true" if any(get_vnet_from_ip(n.get("data", {}).get("privateIPAddress", "")) == "172" for n in existing_nodes) or node_vnet == "172" else "false"
    is_vnet_192 = "true" if any(get_vnet_from_ip(n.get("data", {}).get("privateIPAddress", "")) == "192" for n in existing_nodes) or node_vnet == "192" else "false"
    
    skip_peering_str = "true" if skip_peering else "false"
    
    return f"""
module {machine_name} '../base/CertificateAuthority.bicep' = {{
  name: '{machine_name}'
  params: {{
    location: location
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: '{machine_name}'
    resourceGroupName: resourceGroup().name
    osDiskType: vmDiskType
    privateIPAddress: '{private_ip}'
    rootDomainControllerPrivateIp: '{dc_ip}'
    domainName: '{domain_name}'
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    localAdminUsername: enterpriseAdminUsername
    localAdminPassword: enterpriseAdminPassword
    deployOrBuild: deployOrBuild
    oldScenarios: oldScenarios
    jumpboxPrivateIPAddress: '{jumpbox_ip}'
    connectedPrivateIPAddress: '{connection_str}'
    isVNet10Required: {is_vnet_10}
    isVNet172Required: {is_vnet_172}
    isVNet192Required: {is_vnet_192}
    skipPeering: {skip_peering_str}
  }}
{depends_block}}}
"""


@update_apis_blueprint.route('/saveScenarioUpdate', methods=['POST'])
def save_scenario_update():
    """
    Save the updated scenario with new VM images.
    
    This:
    1. Captures VM images for all NEW nodes
    2. Updates the scenario bicep file with new modules
    3. Updates the parameters file with new image references
    
    Body:
    - deploymentID: The resource group with the deployed update
    - baseScenario: The scenario being updated (e.g., "Build-RX40Q")
    
    Returns:
    - message: Status message
    """
    try:
        data = request.get_json()
        deployment_id = data.get('deploymentID')
        base_scenario = data.get('scenario') or data.get('baseScenario')
        
        if not deployment_id:
            return jsonify({"error": "deploymentID is required"}), 400
        if not base_scenario:
            return jsonify({"error": "scenario is required"}), 400
        
        update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Saving update for {base_scenario} from {deployment_id}")
        
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        if "ERROR" in deployment:
            return jsonify({"error": f"Deployment {deployment_id} not found"}), 404
        
        update_session = deployment.get("updateSession", {})
        if not update_session.get("active"):
            return jsonify({"error": "No active update session for this deployment"}), 400
        
        new_nodes = update_session.get("newNodes", [])
        if not new_nodes:
            return jsonify({"error": "No new nodes to save"}), 400
        
        scenario = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{base_scenario}.json")
        if "ERROR" in scenario:
            return jsonify({"error": f"Scenario {base_scenario} not found"}), 404
        
        subscription_id = helpers.get_subscription_id()
        
        # Extract the scenario's build ID for image naming
        build_id = base_scenario.replace("Build-", helpers.BUILD_LAB_PREFIX)
        
        # Capture images for new nodes and update scenario
        new_image_refs = {}
        new_machines = {}
        
        for node in new_nodes:
            node_type = node.get("type")
            node_data = node.get("data", {})
            
            if node_type == "domainController":
                machine_name = node_data.get("domainControllerName", "")
            elif node_type == "workstation":
                machine_name = node_data.get("workstationName", "")
            elif node_type == "certificateAuthority":
                machine_name = node_data.get("caName", "")
            elif node_type == "jumpbox":
                machine_name = node_data.get("jumpboxName", "Jumpbox")  # Image name
                vm_name = "UpdateJumpbox"  # Actual Azure VM resource name
            else:
                continue
            
            if not machine_name:
                continue
            
            update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Processing machine {machine_name} (VM: {vm_name if node_type == 'jumpbox' else machine_name})")
            
            os_type = "Linux" if node_type == "jumpbox" else "Windows"
            new_machines[machine_name] = {"Name": machine_name, "OSType": os_type}
            
            image_ref = f"/subscriptions/{subscription_id}/resourceGroups/{helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP}/providers/Microsoft.Compute/galleries/{helpers.BUILD_GALLERY_NAME}/images/{build_id}-{machine_name}/versions/1.0.0"
            new_image_refs[machine_name] = image_ref
        
        update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Starting image capture for new machines")
        
        server_objects = []
        for node in new_nodes:
            node_type = node.get("type")
            node_data = node.get("data", {})
            
            if node_type == "domainController":
                machine_name = node_data.get("domainControllerName", "")
                server_type = "SubDC" if node_data.get("isSub", True) else "RootDC"
                if machine_name:
                    server_objects.append({
                        "name": machine_name,
                        "serverType": server_type
                    })
            elif node_type == "workstation":
                machine_name = node_data.get("workstationName", "")
                if machine_name:
                    server_objects.append({
                        "name": machine_name,
                        "serverType": "Standalone"
                    })
            elif node_type == "certificateAuthority":
                machine_name = node_data.get("caName", "")
                if machine_name:
                    server_objects.append({
                        "name": machine_name,
                        "serverType": "CA"
                    })
            elif node_type == "jumpbox":
                server_objects.append({
                    "name": "UpdateJumpbox",  # The actual Azure VM resource name
                    "imageName": "Jumpbox",  # The name to use in the gallery image path
                    "serverType": "Jumpbox"
                })
        
        if not server_objects:
            return jsonify({"error": "No valid machines to capture"}), 400
        
        update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Will capture {len(server_objects)} machines: {server_objects}")
        # NOTE: Frontend timer handles the wait period for AD initialization - no backend sleep needed
        
        domain_name = ""
        for node in scenario.get("topology", {}).get("nodes", []):
            if node.get("type") == "domainController":
                domain_name = node.get("data", {}).get("domainName", "")
                if domain_name:
                    break
        
        build_infra_template = fs_manager.load_file(helpers.TEMPLATE_DIRECTORY, "BuildInfrastructure.json")
        if "ERROR" in build_infra_template:
            return jsonify({"error": "Could not load BuildInfrastructure.json template"}), 500
        
        deployment_info = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        location = deployment_info.get("location", helpers.LOCATION) if "ERROR" not in deployment_info else helpers.LOCATION
        
        build_infra_params = {
            "location": {"value": location},
            "resourceGroupName": {"value": helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP},
            "sourceResourceGroupName": {"value": deployment_id},  # The RG where VMs currently exist
            "imageNamePrefix": {"value": build_id},  # Use BuildLab-XXXXX format for image names
            "scenarioTagValue": {"value": "BUILD"},
            "galleryName": {"value": helpers.BUILD_GALLERY_NAME},
            "domainNameTag": {"value": domain_name},
            "subscriptionID": {"value": subscription_id},
            "serverObjects": {"value": server_objects},
            "kaliSku": {"value": scenario.get("kaliSku", helpers.get_latest_kali_sku())}
        }
        
        from azure.mgmt.resource.resources.models import Deployment, DeploymentProperties, DeploymentMode
        
        resource_client = azure_clients.get_resource_client()
        
        deployment_properties = DeploymentProperties(
            mode=DeploymentMode.INCREMENTAL,
            template=build_infra_template,
            parameters=build_infra_params
        )
        
        deployment_name = f"UpdateSave-{deployment_id}"
        deployment_obj = Deployment(
            location=location,
            properties=deployment_properties
        )
        
        update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Starting BuildInfrastructure deployment {deployment_name} at subscription scope")
        
        try:
            poller = resource_client.deployments.begin_create_or_update_at_subscription_scope(
                deployment_name=deployment_name,
                parameters=deployment_obj
            )
            
            update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Waiting for snapshot creation to complete...")
            result = poller.result()  # This blocks until deployment completes
            
            update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: BuildInfrastructure deployment completed successfully")
            
        except Exception as snapshot_error:
            error_trace = traceback.format_exc()
            update_apis_blueprint.logger.error(f"SAVE_SCENARIO_UPDATE: Error creating snapshots: {str(snapshot_error)}")
            update_apis_blueprint.logger.error(f"SAVE_SCENARIO_UPDATE: Snapshot error traceback:\n{error_trace}")
            return jsonify({"error": f"Error creating snapshots: {str(snapshot_error)}"}), 500
        
        scenario["machines"].update(new_machines)
        scenario["imageReferences"].update(new_image_refs)
        
        users = deployment.get("users", [])
        enabled_attacks = deployment.get("enabledAttacks", {})
        if users:
            scenario["users"] = users
            update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Preserved {len(users)} users from deployment")
        if enabled_attacks:
            scenario["enabledAttacks"] = enabled_attacks
            update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Preserved {len(enabled_attacks)} enabled attacks from deployment")
        
        current_topology = scenario.get("topology", {})
        existing_nodes = current_topology.get("nodes", [])
        existing_edges = current_topology.get("edges", [])
        
        # Merge new nodes (mark them as deployed now)
        for node in new_nodes:
            node["status"] = "deployed"
        
        current_topology["nodes"] = existing_nodes + new_nodes
        
        # Find the Jumpbox node ID to handle edge updates correctly
        jumpbox_node_id = None
        for node in current_topology["nodes"]:
            if node.get("type") == "jumpbox":
                jumpbox_node_id = node.get("id")
                break
        
        new_edges = update_session.get("newEdges", [])
        
        if jumpbox_node_id:
            new_jumpbox_edges = [e for e in new_edges if e.get("source") == jumpbox_node_id or e.get("target") == jumpbox_node_id]
            if new_jumpbox_edges:
                # Remove old Jumpbox edges from existing edges
                existing_edges = [e for e in existing_edges if e.get("source") != jumpbox_node_id and e.get("target") != jumpbox_node_id]
                update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Removed old Jumpbox edges, adding {len(new_jumpbox_edges)} new Jumpbox edges")
        
        # Merge edges
        current_topology["edges"] = existing_edges + new_edges
        scenario["topology"] = current_topology
        
        fs_manager.save_file(scenario, helpers.SCENARIO_DIRECTORY, f"{base_scenario}.json")
        update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Updated scenario JSON")
        
        from apis.scenario_apis import create_scenario_bicep, create_scenario_parameters
        
        create_scenario_bicep(base_scenario, scenario, current_topology)
        create_scenario_parameters(base_scenario, scenario, current_topology)
        
        update_apis_blueprint.logger.info(f"SAVE_SCENARIO_UPDATE: Regenerated scenario bicep and parameters")
        
        deployment["updateSession"]["savedToScenario"] = True
        fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        
        return jsonify({
            "message": f"Successfully saved {len(new_nodes)} new nodes to {base_scenario}",
            "newMachines": list(new_machines.keys()),
            "scenario": base_scenario
        }), 200
        
    except Exception as e:
        update_apis_blueprint.logger.error(f"SAVE_SCENARIO_UPDATE: Error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
