from flask import Blueprint, request, jsonify
from azure_clients import AzureClients
from deployments import Deployments
import helpers
import fs_manager
import command_runner
import logging
import threading
import os
import json

deployment_apis_blueprint = Blueprint('deployment_apis', __name__)
azure_clients = AzureClients()
deployment_handler = Deployments()
deployment_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)


def cleanup_update_files(deployment_id):
    """
    Clean up Update-*.bicep and Update-*.json files after deployment completes.
    These are temporary files generated for update deployments.
    """
    try:
        updates_dir = helpers.UPDATES_TEMPLATE_DIRECTORY
        if not os.path.exists(updates_dir):
            return
        
        bicep_file = os.path.join(updates_dir, f"Update-{deployment_id}.bicep")
        json_file = os.path.join(updates_dir, f"Update-{deployment_id}.json")
        
        if os.path.exists(bicep_file):
            os.remove(bicep_file)
            deployment_apis_blueprint.logger.info(f"CLEANUP: Removed {bicep_file}")
        
        if os.path.exists(json_file):
            os.remove(json_file)
            deployment_apis_blueprint.logger.info(f"CLEANUP: Removed {json_file}")
            
    except Exception as e:
        deployment_apis_blueprint.logger.warning(f"CLEANUP: Error cleaning up update files for {deployment_id}: {e}")

@deployment_apis_blueprint.route('/getDeploymentState', methods=['POST'])
def get_deployment_state():
    try:
        data = request.get_json()
        deploymentID = data.get('deploymentID')
        
        if not deploymentID or deploymentID in ["undefined", "false", "null"]:
            return jsonify({"message": "No deployment"}), 404
        
        resource_client = azure_clients.get_resource_client()
        
        subscription_deployment_running = False
        subscription_deployment_failed = False
        
        if deploymentID.startswith(helpers.BUILD_LAB_PREFIX):
            try:
                sub_deployment = resource_client.deployments.get_at_subscription_scope(deploymentID)
                sub_state = sub_deployment.properties.provisioning_state
                
                deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT_STATE: Subscription-scope deployment {deploymentID} state: {sub_state}")
                
                if sub_state in ["Running", "Accepted"]:
                    subscription_deployment_running = True
                elif sub_state == "Failed":
                    subscription_deployment_failed = True
                
            except Exception as sub_e:
                deployment_apis_blueprint.logger.debug(f"GET_DEPLOYMENT_STATE: No subscription-scope deployment for {deploymentID}: {sub_e}")
        
        try:
            resource_group = resource_client.resource_groups.get(deploymentID)
            rg_state = resource_group.properties.provisioning_state

            if rg_state == "Deleting":
                deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT_STATE: Resource group {deploymentID} is being deleted")

                try:
                    deployments = list(resource_client.deployments.list_by_resource_group(deploymentID))
                    failed_deployments = [d.name for d in deployments if d.properties.provisioning_state == "Failed"]

                    if failed_deployments and deploymentID.startswith(helpers.BUILD_LAB_PREFIX):
                        error_message = "Build failed and is being deleted"
                        try:
                            failed_deployment = resource_client.deployments.get(deploymentID, failed_deployments[0])
                            if failed_deployment.properties.error:
                                error_details = failed_deployment.properties.error
                                error_message = error_details.message if hasattr(error_details, 'message') else str(error_details)
                        except:
                            pass

                        return jsonify({
                            "message": "shutting down",
                            "error": error_message,
                            "details": {"failed": failed_deployments}
                        }), 200
                except:
                    pass

                return jsonify({"message": "shutting down"}), 200

        except Exception as e:
            deployment_apis_blueprint.logger.debug(f"GET_DEPLOYMENT_STATE: Resource group {deploymentID} not found or inaccessible: {str(e)}")
            if subscription_deployment_running:
                return jsonify({
                    "message": "deploying", 
                    "details": {"running": ["Creating resource group..."], "succeeded": []}
                }), 200
            return jsonify({"message": "Resource group not found"}), 404
        
        deployments = list(resource_client.deployments.list_by_resource_group(deploymentID))
        
        if not deployments:
            if deploymentID.startswith(helpers.BUILD_LAB_PREFIX):
                if subscription_deployment_running:
                    return jsonify({
                        "message": "deploying", 
                        "details": {"running": ["Initializing modules..."], "succeeded": []}
                    }), 200
                elif subscription_deployment_failed:
                    return jsonify({
                        "message": "failed", 
                        "details": {"failed": [deploymentID], "succeeded": [], "running": []}
                    }), 200
            return jsonify({"message": "No deployments found for that resource group."}), 404
        
        failed_deployments = []
        succeeded_deployments = []
        running_deployments = []
        
        for deployment in deployments:
            state = deployment.properties.provisioning_state
            if state == "Failed":
                failed_deployments.append(deployment.name)
            elif state == "Succeeded":
                succeeded_deployments.append(deployment.name)
            elif state in ["Running", "Accepted"]:
                running_deployments.append(deployment.name)
        
        if failed_deployments:
            deployment_apis_blueprint.logger.error(f"GET_DEPLOYMENT_STATE: Failed deployments in {deploymentID}: {failed_deployments}")

            error_message = "Deployment failed"
            try:
                failed_deployment = resource_client.deployments.get(deploymentID, failed_deployments[0])
                if failed_deployment.properties.error:
                    error_details = failed_deployment.properties.error
                    error_message = error_details.message if hasattr(error_details, 'message') else str(error_details)
                    deployment_apis_blueprint.logger.error(f"GET_DEPLOYMENT_STATE: Error details: {error_message}")
            except Exception as e:
                deployment_apis_blueprint.logger.warning(f"GET_DEPLOYMENT_STATE: Could not get error details: {e}")

            if deploymentID.startswith(helpers.BUILD_LAB_PREFIX):
                deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT_STATE: Build failed, triggering automatic deletion of {deploymentID}")
                try:
                    deployment_handler.destroy_deployment(deploymentID)
                except Exception as delete_error:
                    deployment_apis_blueprint.logger.error(f"GET_DEPLOYMENT_STATE: Error triggering deletion: {delete_error}")

            cleanup_update_files(deploymentID)
            return jsonify({
                "message": "failed",
                "error": error_message,
                "details": {
                    "failed": failed_deployments,
                    "succeeded": succeeded_deployments,
                    "running": running_deployments
                }
            }), 200
        elif running_deployments:
            deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT_STATE:Deployments still running in {deploymentID}: {running_deployments}")
            return jsonify({"message": "deploying", "details": {"running": running_deployments, "succeeded": succeeded_deployments}}), 200
        elif subscription_deployment_running:
            deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT_STATE: RG deployments done but subscription deployment still running for {deploymentID}")
            return jsonify({"message": "deploying", "details": {"running": ["Finalizing..."], "succeeded": succeeded_deployments}}), 200
        else:
            # This ensures newly deployed nodes with public IPs are captured
            try:
                deployment_handler.get_deployment_ip(deploymentID)
            except Exception as ip_error:
                deployment_apis_blueprint.logger.warning(f"GET_DEPLOYMENT_STATE: Could not refresh entry IPs: {ip_error}")

            cleanup_update_files(deploymentID)

            try:
                deployment_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
                current_timeout = deployment_file.get("timeout", 0)

                if current_timeout == 0:
                    new_timeout = helpers.get_future_time(helpers.DEPLOYMENT_TIMEOUT_HOURS)
                    deployment_handler.set_deployment_attribute(deploymentID, "timeout", new_timeout)
                    helpers.update_expiry_tag(new_timeout, deploymentID)
                    deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT_STATE: Set timeout to 2 hours from completion for {deploymentID}")
            except Exception as timeout_error:
                deployment_apis_blueprint.logger.warning(f"GET_DEPLOYMENT_STATE: Could not set timeout: {timeout_error}")

            deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT_STATE: All deployments succeeded in {deploymentID}")
            return jsonify({"message": "deployed", "details": {"succeeded": succeeded_deployments}}), 200
            
    except Exception as e:
        deployment_apis_blueprint.logger.error(f"GET_DEPLOYMENT_STATE: Error checking state for {deploymentID}: {str(e)}")
        return jsonify({"message": str(e)}), 500
    

@deployment_apis_blueprint.route('/extend', methods=['POST'])
def extend():
    deploymentID = request.data.decode('utf-8')
    addTimeOutput = helpers.add_time(deploymentID,1)
    if addTimeOutput == "FILE NOT FOUND":
        return jsonify({"message":"File not found"})
    elif addTimeOutput == "NO MORE EXTENSIONS":
        return jsonify({"message":"No More Extensions"})
    else:
        deployment_apis_blueprint.logger.info(f"EXTEND: Added one hour")
        return jsonify({"message":"Added one hour"})
    

@deployment_apis_blueprint.route("/deleteSavedDeployment",methods=["POST"])
def delete_saved_deployment():
    savedDeploymentID = request.data.decode('utf-8')
    deployment_apis_blueprint.logger.info(f"DELETE_SAVED_DEPLOYMENT: Incoming ID: {savedDeploymentID}")
    deployment_handler.delete_saved_deployment(savedDeploymentID)
    return jsonify({"message":"Deleting the saved deployment"})

@deployment_apis_blueprint.route("/saveDeployment",methods=["POST"])
def save_deployment():
    deploymentID = request.data.decode('utf-8')
    output = deployment_handler.save_deployment(deploymentID)
    return jsonify({"message":output})

@deployment_apis_blueprint.route("/getDeploymentTimeout",methods=["POST"])
def get_deployment_timeout():
    deploymentID = request.data.decode('utf-8')
    if deploymentID != "false":
        try:
            timeout = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)["timeout"]
            deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT_TIMEOUT: Got timeout for {deploymentID}: {timeout}")
            return jsonify({"message":timeout})
        except:
            deployment_apis_blueprint.logger.error(f"GET_DEPLOYMENT_TIMEOUT: Could not load deployment {deploymentID}. File not found.")
            return jsonify({"message":"File not found"})
    else:
        deployment_apis_blueprint.logger.info("GET_DEPLOYMENT_TIMEOUT: No deployment.")
        return jsonify({"message":"No deployment"})
    

@deployment_apis_blueprint.route("/listDeployments",methods=["GET"])
def list_deployments():
    return jsonify({"message":deployment_handler.list_azure_deployments()})

@deployment_apis_blueprint.route('/getDeployment', methods=['POST'])
def get_deployment():
    deploymentID = request.data.decode('utf-8')
    deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
    if "ERROR" not in deployment:
        # Normalize users: convert legacy string users to objects with domain info
        deployment = _normalize_deployment_users(deployment)
        deployment_apis_blueprint.logger.debug(f"GET_DEPLOYMENT: Got deployment for ID {deploymentID}: {deployment}")
        return jsonify({"message":deployment})
    else:
        deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT: No active deployment")
        return jsonify({"message":"No active deployment"})


def _normalize_deployment_users(deployment):
    """
    Convert legacy string users to objects with domain info.
    For backwards compatibility with old deployments that stored users as plain strings.
    """
    users = deployment.get('users', [])
    if not users:
        return deployment
    
    needs_normalization = any(isinstance(u, str) for u in users)
    if not needs_normalization:
        return deployment
    
    topology = deployment.get('topology', {})
    nodes = topology.get('nodes', [])
    edges = topology.get('edges', [])
    
    # Find all domains and their DCs
    domains = []
    for node in nodes:
        if node.get('type') == 'domainController':
            domain_name = node.get('data', {}).get('domainName', '')
            dc_name = node.get('data', {}).get('domainControllerName', '')
            if domain_name and dc_name:
                domains.append({
                    'domain': domain_name,
                    'dc': dc_name,
                    'node_id': node.get('id')
                })
    
    if not domains:
        root_domain = deployment.get('rootDomainName', '')
        root_dc = deployment.get('rootDomainControllerName', '')
        if root_domain and root_dc:
            domains.append({
                'domain': root_domain,
                'dc': root_dc,
                'node_id': None
            })
    
    # Default to first domain if we have one
    default_domain = domains[0] if domains else {'domain': 'unknown', 'dc': 'DC01', 'node_id': None}
    
    # Normalize each user
    normalized_users = []
    for user in users:
        if isinstance(user, str):
            # Convert string to object with default domain
            normalized_users.append({
                'username': user,
                'domain': default_domain['domain'],
                'dc': default_domain['dc']
            })
        else:
            normalized_users.append(user)
    
    deployment['users'] = normalized_users
    deployment_apis_blueprint.logger.info(f"GET_DEPLOYMENT: Normalized {len(normalized_users)} users with domain info")
    
    return deployment


@deployment_apis_blueprint.route("/getSavedDeployment", methods=["POST"])
def get_saved_deployment():
    savedDeploymentID = request.data.decode('utf-8')
    savedDeployment = deployment_handler.get_saved_deployment(savedDeploymentID)
    return jsonify({"message":savedDeployment}) 

@deployment_apis_blueprint.route("/listSavedDeployments", methods=["GET"])
def list_saved_deployments():
    return jsonify({ "message":deployment_handler.list_saved_deployments()})
    
@deployment_apis_blueprint.route('/deploySavedDeployment', methods=['POST'])
def deploy_saved_deployment():
    import os
    appConfig = helpers.load_config()
    region = appConfig['region']
    savedDeploymentID = request.data.decode("utf-8")
    deploymentConfigs = deployment_handler.get_saved_deployment(savedDeploymentID)
    deploymentID = savedDeploymentID
    randomPort = deploymentConfigs["dockerfilePort"]
    scenario = deploymentConfigs["scenario"]
    machines = deploymentConfigs["machines"]
    enabledAttacks = deploymentConfigs["enabledAttacks"]
    users = deploymentConfigs.get("users", [])  # Get users from saved deployment
    expiryTimestamp = 0
    machineImageReferences = {}
    for machine in machines:
        machineImageReferences[machine] = f"/subscriptions/{helpers.get_subscription_id()}/resourceGroups/{helpers.SAVED_DEPLOYMENT_PREFIX}{savedDeploymentID}/providers/Microsoft.Compute/galleries/{savedDeploymentID}Gallery/images/{machine}/versions/1.0.0"

    if appConfig["azureAuth"] != "true":
        deployment_apis_blueprint.logger.error(f"DEPLOY: Not authorized to Azure")
        return jsonify({"message":"Error: Not authorized to Azure"}), 401

    # Regenerate dynamic modules from saved topology if it's a custom build
    if "topology" in deploymentConfigs:
        deployment_apis_blueprint.logger.info(f"DEPLOY_SAVED: Regenerating dynamic modules from saved topology")
        topology = deploymentConfigs["topology"]
        
        # Extract CA nodes from topology
        ca_nodes = [node for node in topology.get("nodes", []) if node.get("type") == "certificateAuthority"]
        
        if ca_nodes:
            deployment_apis_blueprint.logger.info(f"DEPLOY_SAVED: Found {len(ca_nodes)} CA nodes, regenerating GeneratedCAModules.bicep")
            
            ca_entries = []
            for ca_node in ca_nodes:
                ca_data = ca_node.get("data", {})
                
                # Find connected Root DC from edges
                ca_id = ca_node.get("id")
                edges = topology.get("edges", [])
                parent_edge = next((e for e in edges if e.get("source") == ca_id or e.get("target") == ca_id), None)
                
                if parent_edge:
                    parent_id = parent_edge.get("target") if parent_edge.get("source") == ca_id else parent_edge.get("source")
                    parent_node = next((n for n in topology.get("nodes", []) if n.get("id") == parent_id), None)
                    
                    if parent_node:
                        parent_data = parent_node.get("data", {})
                        ca_entry = {
                            "name": ca_data.get("caName"),
                            "domainName": parent_data.get("domainName"),
                            "privateIPAddress": ca_data.get("privateIPAddress"),
                            "rootDomainControllerPrivateIp": parent_data.get("privateIPAddress")
                        }
                        ca_entries.append(ca_entry)
            
            if ca_entries:
                base_dir = helpers.GENERATED_TEMPLATE_DIRECTORY
                os.makedirs(base_dir, exist_ok=True)
                
                param_block = """param location string
param windowsVmSize string
param vmDiskType string
param resourceGroupName string
param domainAndEnterpriseAdminUsername string
param enterpriseAdminUsername string
param enterpriseAdminPassword string
param deployOrBuild string
param oldScenarios bool
param jumpboxPrivateIPAddress string
param connectedPrivateIPAddress string
param isVNet10Required bool
param isVNet172Required bool
param isVNet192Required bool

"""
                
                ca_file = helpers.GENERATED_CA_MODULES
                with open(ca_file, "w") as f:
                    f.write(param_block)
                    for i, ca in enumerate(ca_entries):
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
  }}
  dependsOn: []
}}
""")
                deployment_apis_blueprint.logger.info(f"DEPLOY_SAVED: Successfully regenerated GeneratedCAModules.bicep with {len(ca_entries)} CAs")

    scenarioInfo = fs_manager.load_file(helpers.SCENARIO_DIRECTORY,f"{scenario}.json")
    scenarioSubtype = ''
    if "ERROR" not in scenarioInfo:
        scenarioSubtype = scenarioInfo["subtype"]
    
    if scenarioSubtype == "NETWORK":
        command = [
            "/usr/bin/az", "deployment", "sub", "create", "--name", deploymentID, "--location", region,
            "--template-file", helpers.SCENARIO_MANAGER_BICEP,
            "--parameters", helpers.SCENARIO_MANAGER_PARAMS,
            "--parameters", f"deployResourceGroupName={deploymentID}", f"scenarioTagValue={scenario}", f"scenarioSelection={scenario}", f"expiryTimestamp={expiryTimestamp}", f"subscriptionID={helpers.get_subscription_id()}"
        ]
        for machine, reference in machineImageReferences.items():
            command.append(f"{machine}ImageReferenceID={reference}")
        deployment_apis_blueprint.logger.info(f"DEPLOY: Deploying {scenario} to {deploymentID}")
        deployment_apis_blueprint.logger.debug(f"DEPLOY: Command used for deployment: {command}")
        # Include topology from saved deployment so domains can be extracted
        topology = deploymentConfigs.get("topology")
        deployment_handler.set_deployment_configs("deploy",deploymentID,scenario,expiryTimestamp,"deploying",machines=machines,enabledAttacks=enabledAttacks,topology=topology,users=users)
        deployment_apis_blueprint.logger.info(f"DEPLOY_SAVED: Restored {len(users)} users and {len(enabledAttacks)} enabled attacks to deployment {deploymentID}")
        return jsonify({"deploymentID":deploymentID, "message":f"{scenario} deploying to {deploymentID}"})

    else:
        return jsonify({"message":f"Failed"})
    

def schedule_deletion_verification(resource_group_name, retry_count=0):
    """
    Schedule a verification task to make sure the resource group is truly deleted.
    Uses exponential backoff for retries.
    
    Parameters:
    - resource_group_name: The name of the resource group to verify deletion
    - retry_count: Current retry attempt (incremented with each retry)
    """
    max_retries = helpers.DELETION_VERIFICATION_MAX_RETRIES
    if retry_count >= max_retries:
        deployment_apis_blueprint.logger.error(f"VERIFY_DELETION: Giving up on {resource_group_name} after {retry_count} attempts")
        return
    
    wait_time = helpers.DELETION_VERIFICATION_BASE_WAIT * (2 ** retry_count)
    
    def verify_deletion():
        try:
            deployment_apis_blueprint.logger.debug(f"VERIFY_DELETION: Checking if {resource_group_name} is fully deleted (attempt {retry_count+1})")
            
            
            exists = deployment_handler.does_deployment_exist(resource_group_name)
            if exists:
                deployment_apis_blueprint.logger.warning(f"VERIFY_DELETION: Resource group {resource_group_name} still exists after deletion attempt")
                
                try:
                    deployment_apis_blueprint.logger.info(f"VERIFY_DELETION: Forcefully re-attempting resource group deletion for {resource_group_name}")
                    deployment_handler.destroy_deployment(resource_group_name)
                except Exception as e:
                    deployment_apis_blueprint.logger.error(f"VERIFY_DELETION: Error in resource group deletion attempt: {str(e)}")
                
                schedule_deletion_verification(resource_group_name, retry_count + 1)
            else:
                deployment_apis_blueprint.logger.info(f"VERIFY_DELETION: Resource group {resource_group_name} successfully deleted")
                try:
                    fs_manager.delete_file(helpers.DEPLOYMENT_DIRECTORY, resource_group_name)
                    deployment_apis_blueprint.logger.info(f"VERIFY_DELETION: Deleted deployment file for {resource_group_name}")
                except Exception as del_error:
                    deployment_apis_blueprint.logger.error(f"VERIFY_DELETION: Error deleting deployment file: {del_error}")

                # Also clean up topology file if it exists
                try:
                    topology_file = f"{resource_group_name}_topology"
                    fs_manager.delete_file(helpers.DEPLOYMENT_DIRECTORY, topology_file)
                    deployment_apis_blueprint.logger.info(f"VERIFY_DELETION: Deleted topology file for {resource_group_name}")
                except Exception as del_error:
                    # It's okay if topology file doesn't exist (older deployments might not have separate topology files)
                    deployment_apis_blueprint.logger.debug(f"VERIFY_DELETION: Topology file not found or error deleting: {del_error}")

                # Note: We do NOT clean up gallery images here.
        except Exception as e:
            deployment_apis_blueprint.logger.error(f"VERIFY_DELETION: Error during verification: {str(e)}")
            schedule_deletion_verification(resource_group_name, retry_count + 1)
    
    deployment_apis_blueprint.logger.info(f"VERIFY_DELETION: Scheduling verification for {resource_group_name} in {wait_time} seconds (attempt {retry_count+1})")
    threading.Timer(wait_time, verify_deletion).start()


@deployment_apis_blueprint.route('/shutdown', methods=['POST'])
def shutdown():
    deploymentID = request.data.decode('utf-8')
    deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)

    if "ERROR" in deployment:
        return jsonify({"message": f"Deployment {deploymentID} not found"}), 404

    resource_group = deployment.get("resourceGroup", deploymentID)

    deployment_apis_blueprint.logger.info(f"Shutting down {deploymentID} (resource group: {resource_group})")

    try:
        # Note: We do NOT clean up gallery images during shutdown.
                
        
        deployment_apis_blueprint.logger.info(f"SHUTDOWN: Deleting resource group {resource_group}")
        deployment_handler.destroy_deployment(deploymentID)
        
        schedule_deletion_verification(resource_group)
        
        return jsonify({"message": f"Successfully shut down {deploymentID}"}), 200
        
    except Exception as e:
        deployment_apis_blueprint.logger.error(f"SHUTDOWN: Error shutting down {deploymentID}: {str(e)}")
        return jsonify({"message": f"Error shutting down {deploymentID}: {str(e)}"}), 500


def cleanup_build_images(resource_group_name, build_id):
    """
    Clean up specific VM image definitions and versions for an unsaved build (PARALLELIZED)
    
    Parameters:
    - resource_group_name: Usually 'VMImages' where the gallery lives
    - build_id: The unique build ID (e.g., 'BuildLab-RX40Q')
    """
    import concurrent.futures
    import threading
    
    try:
        deployment_apis_blueprint.logger.info(f"CLEANUP_BUILD_IMAGES: Cleaning up images for build {build_id} (parallel mode)")
        
        gallery_resource_group = helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP
        gallery_name = helpers.BUILD_GALLERY_NAME
        
        image_def_command = [
            "/usr/bin/az", "sig", "image-definition", "list",
            "--resource-group", gallery_resource_group,
            "--gallery-name", gallery_name,
            "--query", "[].name",
            "--output", "json"
        ]
        
        try:
            image_def_output = command_runner.run_command_and_read_output(image_def_command)
            image_defs = json.loads(image_def_output)
            
            if not image_defs:
                deployment_apis_blueprint.logger.debug(f"CLEANUP_BUILD_IMAGES: No image definitions found in gallery {gallery_name}")
                return
                
            build_image_defs = [img_def for img_def in image_defs if build_id in img_def]
            
            deployment_apis_blueprint.logger.info(f"CLEANUP_BUILD_IMAGES: Found {len(build_image_defs)} image definitions for build {build_id}")
            
            if not build_image_defs:
                deployment_apis_blueprint.logger.debug(f"CLEANUP_BUILD_IMAGES: No matching image definitions for build {build_id}")
                return
            
            def delete_version(image_def, version):
                try:
                    delete_version_command = [
                        "/usr/bin/az", "sig", "image-version", "delete",
                        "--resource-group", gallery_resource_group,
                        "--gallery-name", gallery_name,
                        "--gallery-image-definition", image_def,
                        "--gallery-image-version", version
                    ]
                    deployment_apis_blueprint.logger.info(f"CLEANUP_BUILD_IMAGES: Deleting version {version} for {image_def}")
                    command_runner.run_command_and_read_output(delete_version_command)
                    return f"Deleted {image_def}/{version}"
                except Exception as e:
                    deployment_apis_blueprint.logger.error(f"CLEANUP_BUILD_IMAGES: Error deleting version {version}: {str(e)}")
                    return f"Error deleting {image_def}/{version}: {str(e)}"
            
            def delete_image_definition(image_def):
                try:
                    delete_image_def_command = [
                        "/usr/bin/az", "sig", "image-definition", "delete",
                        "--resource-group", gallery_resource_group,
                        "--gallery-name", gallery_name,
                        "--gallery-image-definition", image_def
                    ]
                    deployment_apis_blueprint.logger.info(f"CLEANUP_BUILD_IMAGES: Deleting image definition {image_def}")
                    command_runner.run_command_and_read_output(delete_image_def_command)
                    return f"Deleted definition {image_def}"
                except Exception as e:
                    deployment_apis_blueprint.logger.error(f"CLEANUP_BUILD_IMAGES: Error deleting definition {image_def}: {str(e)}")
                    return f"Error deleting definition {image_def}: {str(e)}"
            
            version_tasks = []
            for image_def in build_image_defs:
                deployment_apis_blueprint.logger.info(f"CLEANUP_BUILD_IMAGES: Processing image definition {image_def}")
                
                version_command = [
                    "/usr/bin/az", "sig", "image-version", "list",
                    "--resource-group", gallery_resource_group,
                    "--gallery-name", gallery_name,
                    "--gallery-image-definition", image_def,
                    "--query", "[].name",
                    "--output", "json"
                ]
                
                try:
                    version_output = command_runner.run_command_and_read_output(version_command)
                    versions = json.loads(version_output)
                    
                    if not versions:
                        deployment_apis_blueprint.logger.debug(f"CLEANUP_BUILD_IMAGES: No versions found for image {image_def}")
                    else:
                        deployment_apis_blueprint.logger.info(f"CLEANUP_BUILD_IMAGES: Found {len(versions)} versions for {image_def}")
                        for version in versions:
                            version_tasks.append((image_def, version))
                    
                except Exception as e:
                    deployment_apis_blueprint.logger.error(f"CLEANUP_BUILD_IMAGES: Error listing versions for {image_def}: {str(e)}")
            
            if version_tasks:
                deployment_apis_blueprint.logger.info(f"CLEANUP_BUILD_IMAGES: Deleting {len(version_tasks)} versions in parallel")
                with concurrent.futures.ThreadPoolExecutor(max_workers=helpers.IMAGE_CLEANUP_MAX_WORKERS) as executor:
                    futures = [executor.submit(delete_version, img_def, ver) for img_def, ver in version_tasks]
                    for future in concurrent.futures.as_completed(futures):
                        result = future.result()
                        deployment_apis_blueprint.logger.debug(f"CLEANUP_BUILD_IMAGES: {result}")
            
            import time
            time.sleep(2)
            
            deployment_apis_blueprint.logger.info(f"CLEANUP_BUILD_IMAGES: Deleting {len(build_image_defs)} image definitions in parallel")
            with concurrent.futures.ThreadPoolExecutor(max_workers=helpers.IMAGE_CLEANUP_MAX_WORKERS) as executor:
                futures = [executor.submit(delete_image_definition, img_def) for img_def in build_image_defs]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    deployment_apis_blueprint.logger.debug(f"CLEANUP_BUILD_IMAGES: {result}")
            
            deployment_apis_blueprint.logger.info(f"CLEANUP_BUILD_IMAGES: Completed parallel cleanup for build {build_id}")
            
        except Exception as e:
            deployment_apis_blueprint.logger.error(f"CLEANUP_BUILD_IMAGES: Error listing image definitions: {str(e)}")
            
    except Exception as e:
        deployment_apis_blueprint.logger.error(f"CLEANUP_BUILD_IMAGES: Error during cleanup: {str(e)}")


@deployment_apis_blueprint.route("/getResourceIPs", methods=["POST"])
def get_resource_ips():
    deploymentID = request.json.get('deploymentID')
    if not deploymentID:
        return jsonify({"message": "Deployment ID not provided"}), 400

    if deploymentID != "false":
        try:
            deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
            
            if "topologyFile" in deployment:
                try:
                    topology_file = deployment.get("topologyFile")
                    topology = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, topology_file)
                    
                    if isinstance(topology, dict) and "nodes" in topology:
                        vm_data = []
                        for node in topology["nodes"]:
                            if "data" in node and "privateIPAddress" in node["data"]:
                                name = None
                                if node["type"] == "domainController":
                                    name = node["data"].get("domainControllerName", "DC")
                                elif node["type"] == "workstation":
                                    name = node["data"].get("workstationName", "Workstation")
                                elif node["type"] == "jumpbox":
                                    name = "Jumpbox"

                                if name:
                                    vm_data.append({
                                        "name": name,
                                        "privateIP": node["data"]["privateIPAddress"],
                                        "publicIP": deployment.get("entryIP", "N/A") if node["type"] == "jumpbox" else "N/A"
                                    })
                        
                        topology_data = vm_data if vm_data else None
                except Exception as e:
                    deployment_apis_blueprint.logger.error(f"GET_RESOURCE_IPS: Error loading topology: {str(e)}")
                    topology_data = None
            
            resource_group = deployment.get("resourceGroup", deploymentID)
            
            try:
                vm_command = [
                    "/usr/bin/az", "vm", "list-ip-addresses",
                    "--resource-group", resource_group,
                    "--query", "[].{name:virtualMachine.name, privateIP:virtualMachine.network.privateIpAddresses[0], publicIP:virtualMachine.network.publicIpAddresses[0].ipAddress}",
                    "--output", "json"
                ]

                deployment_apis_blueprint.logger.info(f"GET_RESOURCE_IPS: Getting resource IPs for {deploymentID} using resource group {resource_group}")
                vm_output = command_runner.run_command_and_read_output(vm_command)
                vm_data = json.loads(vm_output)
                
                if vm_data:
                    return jsonify({"message": vm_data})
            except Exception as e:
                deployment_apis_blueprint.logger.error(f"GET_RESOURCE_IPS: Error from Azure CLI: {str(e)}")
                # Fall through to topology data if available
            
            if topology_data:
                deployment_apis_blueprint.logger.info(f"GET_RESOURCE_IPS: Using topology fallback data for {deploymentID}")
                return jsonify({"message": topology_data})
                
            return jsonify({"message": []})
            
        except Exception as e:
            deployment_apis_blueprint.logger.error(f"GET_RESOURCE_IPS: Error fetching resource IPs: {str(e)}")
            return jsonify({"message": []})  # Return empty array instead of error
    else:
        deployment_apis_blueprint.logger.error("GET_RESOURCE_IPS: No Deployment")
        return jsonify({"message": []})  # Return empty array for consistency

@deployment_apis_blueprint.route("/getRemoteDesktopUsers", methods=["POST"])
def get_remote_desktop_users():
    deploymentID = request.json.get('deploymentID')
    
    if not deploymentID:
        return jsonify({"message": "Deployment ID not provided"}), 400
        
    try:
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
        resource_group = deployment.get("resourceGroup", deploymentID)
        
        combinedTag = "Workstation:" + resource_group

        vm_list_command = [
            "/usr/bin/az", "resource", "list",
            "--resource-group", resource_group,
            "--query", "[?type=='Microsoft.Compute/virtualMachines' && tags.VM=='" + combinedTag + "'].{name:name}",
            "--output", "json"
        ]
        vm_list_output = command_runner.run_command_and_read_output(vm_list_command)
        vm_list = json.loads(vm_list_output)
        
        if not vm_list:
            return jsonify({"message": "No workstation VMs found with the specified tag"}), 400
        
        target_box = vm_list[0]['name']

        vm_command = [
            "/usr/bin/az", "vm", "run-command", "invoke",
            "--command-id", "RunPowerShellScript",
            "--name", target_box,
            "--resource-group", resource_group,
            "--scripts", "Get-LocalGroupMember -Group 'Remote Desktop Users' | Select-Object -ExpandProperty Name"
        ]

        deployment_apis_blueprint.logger.info(f"GET_REMOTE_DESKTOP_USERS: Getting Remote Desktop Users for {target_box} in resource group {resource_group}")
        vm_output = command_runner.run_command_and_read_output(vm_command)
        
        # Parse the stdout message to extract the user list
        vm_output_json = json.loads(vm_output)
        message = next((item['message'] for item in vm_output_json['value'] if item['code'] == 'ComponentStatus/StdOut/succeeded'), "")
        
        users = [line.strip() for line in message.splitlines() if line.strip()]

        return jsonify({"message": users})
    except Exception as e:
        deployment_apis_blueprint.logger.error(f"GET_REMOTE_DESKTOP_USERS: Error fetching Remote Desktop Users: {str(e)}")
        return jsonify({"message": f"Error fetching Remote Desktop Users: {str(e)}"}), 500