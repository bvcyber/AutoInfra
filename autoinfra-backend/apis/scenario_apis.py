from flask import Blueprint, request, jsonify
import os
from azure_clients import AzureClients
from deployments import Deployments
import helpers
import fs_manager
import command_runner
from scenario_manager import ScenarioManager
import json
import logging

scenario_apis_blueprint = Blueprint('scenario_apis', __name__)
azure_clients = AzureClients()
deployment_handler = Deployments()
scenario_manager = ScenarioManager()
scenario_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)

@scenario_apis_blueprint.route('/listScenarios', methods=['GET'])
def list_scenarios():
    config = helpers.load_config()
    scenarios = config["scenarios"] if config else []
    return jsonify({ "message":scenarios })

@scenario_apis_blueprint.route("/getScenario", methods=["POST"])
def get_scenario_info():
    try:
        if request.is_json:
            data = request.get_json()
            scenario = data.get('scenario')
        else:
            scenario = request.data.decode("utf-8")

        # Special case for Custom Topology (build deployments)
        if scenario == "Custom Topology":
            deployment_id = data.get('deploymentID') if request.is_json else None
            if deployment_id:
                try:
                    deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
                    if "topologyFile" in deployment:
                        info = {
                            "name": deployment_id,  # Use deploymentID as the name
                            "subtype": "NETWORK",
                            "description": "Custom network topology created with the topology builder",
                            "machines": []
                        }
                        return jsonify({"message": info})
                except Exception as e:
                    scenario_apis_blueprint.logger.error(f"GET_SCENARIO_INFO: Error checking build deployment {deployment_id}: {str(e)}")
            
            # Fallback for Custom Topology without deployment ID
            return jsonify({"message": {
                "name": "Custom Topology",
                "subtype": "NETWORK",
                "description": "Custom network topology",
                "machines": []
            }})

        scenarioInfo = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{scenario}.json")
        if "ERROR" not in scenarioInfo:
            scenario_apis_blueprint.logger.info(f"GET_SCENARIO_INFO: Scenario info for {scenario}: {scenarioInfo}")
            return jsonify({"message": scenarioInfo})
        else:
            scenario_apis_blueprint.logger.error(f"GET_SCENARIO_INFO: Scenario {scenario} not found")
            return jsonify({"message": "Scenario not found."}), 404
    except Exception as e:
        scenario_apis_blueprint.logger.error(f"GET_SCENARIO_INFO: Error: {str(e)}")
        return jsonify({"message": f"Error retrieving scenario info: {str(e)}"}), 500

@scenario_apis_blueprint.route('/getScenarioVersions', methods=['POST'])
def get_scenario_versions():
    """
    Get all available versions for a scenario by querying Azure gallery.
    Returns both legacy format (single versions array) and new format (per-machine versions).
    """
    try:
        data = request.get_json()
        scenario_name = data.get('scenario')
        
        if not scenario_name:
            return jsonify({"error": "Scenario name is required"}), 400
        
        scenario_apis_blueprint.logger.info(f"GET_SCENARIO_VERSIONS: Getting versions for {scenario_name}")
        
        scenario_obj = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
        if "ERROR" in scenario_obj:
            scenario_apis_blueprint.logger.error(f"GET_SCENARIO_VERSIONS: Scenario {scenario_name} not found")
            return jsonify({"error": f"Scenario {scenario_name} not found"}), 404
        
        image_refs = scenario_obj.get("imageReferences", {})
        if not image_refs:
            scenario_apis_blueprint.logger.warning(f"GET_SCENARIO_VERSIONS: No image references found for {scenario_name}")
            return jsonify({"versions": ["1.0.0"], "machineVersions": {}}), 200
        
        machine_versions = {}
        all_versions_set = set()
        
        for machine_name, image_ref in image_refs.items():
            try:
                # Parse the image reference to get gallery and image definition
                parts = image_ref.split("/")
                gallery_idx = parts.index("galleries") if "galleries" in parts else -1
                images_idx = parts.index("images") if "images" in parts else -1
                
                if gallery_idx == -1 or images_idx == -1:
                    scenario_apis_blueprint.logger.warning(f"GET_SCENARIO_VERSIONS: Invalid image ref for {machine_name}")
                    continue
                
                gallery_name = parts[gallery_idx + 1]
                image_definition = parts[images_idx + 1]
                
                default_version = "1.0.0"
                if "/versions/" in image_ref:
                    default_version = image_ref.split("/versions/")[-1]
                
                version_command = [
                    "/usr/bin/az", "sig", "image-version", "list",
                    "--resource-group", helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP,
                    "--gallery-name", gallery_name,
                    "--gallery-image-definition", image_definition,
                    "--query", "[].name",
                    "--output", "json"
                ]

                version_output = command_runner.run_command_and_read_output(version_command)
                versions = json.loads(version_output)

                if not versions:
                    versions = [default_version]
                else:
                    def version_key(v):
                        try:
                            p = v.split('.')
                            return (int(p[0]), int(p[1]), int(p[2]))
                        except:
                            return (0, 0, 0)
                    versions = sorted(versions, key=version_key, reverse=True)
                
                machine_versions[machine_name] = {
                    "versions": versions,
                    "default": default_version
                }
                all_versions_set.update(versions)
                
                scenario_apis_blueprint.logger.info(f"GET_SCENARIO_VERSIONS: {machine_name} has versions: {versions}, default: {default_version}")
                
            except Exception as e:
                scenario_apis_blueprint.logger.warning(f"GET_SCENARIO_VERSIONS: Error getting versions for {machine_name}: {e}")
                default_version = "1.0.0"
                if "/versions/" in image_ref:
                    default_version = image_ref.split("/versions/")[-1]
                machine_versions[machine_name] = {
                    "versions": [default_version],
                    "default": default_version
                }
        
        if machine_versions:
            version_sets = [set(mv["versions"]) for mv in machine_versions.values()]
            common_versions = version_sets[0]
            for vs in version_sets[1:]:
                common_versions = common_versions.intersection(vs)
            
            unified_versions = sorted(list(common_versions), key=lambda v: tuple(int(x) for x in v.split('.') if x.isdigit()), reverse=True)
        else:
            unified_versions = []
        
        if not unified_versions:
            unified_versions = ["1.0.0"]
        
        scenario_apis_blueprint.logger.info(f"GET_SCENARIO_VERSIONS: Found versions for {len(machine_versions)} machines, unified versions: {unified_versions}")
        
        return jsonify({
            "versions": unified_versions,  # Unified: only versions ALL machines share
            "machineVersions": machine_versions  # Per-machine versions with defaults
        }), 200
            
    except Exception as e:
        scenario_apis_blueprint.logger.error(f"GET_SCENARIO_VERSIONS: Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@scenario_apis_blueprint.route('/deployScenario', methods=['POST'])
def deploy():
    import requests as http_requests
    
    if request.is_json:
        data = request.get_json()
        scenario = data.get('scenario')
        version = data.get('version', None)  # Optional unified version parameter
        machine_versions = data.get('machineVersions', None)  # Optional per-machine versions
    else:
        scenario = request.data.decode('utf-8')
        version = None
        machine_versions = None
    
    caller_ip = None
    try:
        response = http_requests.get('https://api.ipify.org?format=json', timeout=helpers.IP_LOOKUP_TIMEOUT)
        caller_ip = response.json()['ip']
        scenario_apis_blueprint.logger.info(f"DEPLOY_SCENARIO: Detected public IP address: {caller_ip}")
    except Exception as e:
        scenario_apis_blueprint.logger.warning(f"DEPLOY_SCENARIO: Failed to detect public IP: {e}")
        caller_ip = request.remote_addr
        scenario_apis_blueprint.logger.info(f"DEPLOY_SCENARIO: Using fallback IP address: {caller_ip}")
    
    return jsonify(deployment_handler.deploy_scenario(scenario, caller_ip, version, machine_versions))


@scenario_apis_blueprint.route('/deleteScenario', methods=['DELETE'])
def delete_scenario():
    """
    Delete a BUILD scenario including its files and gallery images
    """
    try:
        data = request.get_json()
        scenario_name = data.get('scenario')
        
        if not scenario_name:
            return jsonify({"error": "Scenario name is required"}), 400
        
        if not scenario_name.startswith("Build-"):
            return jsonify({"error": "Only Build scenarios can be deleted"}), 403
        
        scenario_apis_blueprint.logger.info(f"DELETE_SCENARIO: Deleting scenario {scenario_name}")
        
        from apis.deployment_apis import cleanup_build_images
        
        scenario_json_path = os.path.join(helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
        if os.path.exists(scenario_json_path):
            os.remove(scenario_json_path)
            scenario_apis_blueprint.logger.info(f"DELETE_SCENARIO: Deleted {scenario_json_path}")
        
        bicep_path = os.path.join(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"Scenario{scenario_name}.bicep")
        if os.path.exists(bicep_path):
            os.remove(bicep_path)
            scenario_apis_blueprint.logger.info(f"DELETE_SCENARIO: Deleted {bicep_path}")
        
        json_path = os.path.join(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"Scenario{scenario_name}.json")
        if os.path.exists(json_path):
            os.remove(json_path)
            scenario_apis_blueprint.logger.info(f"DELETE_SCENARIO: Deleted {json_path}")
        
        params_path = os.path.join(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"{scenario_name}.parameters.json")
        if os.path.exists(params_path):
            os.remove(params_path)
            scenario_apis_blueprint.logger.info(f"DELETE_SCENARIO: Deleted {params_path}")
        
        # 5. Delete gallery images - extract build ID from scenario name (Build-XXXXX format)
        # The cleanup_build_images expects the full "BuildLab-XXXXX" format
        build_id = scenario_name.replace("Build-", helpers.BUILD_LAB_PREFIX)
        cleanup_build_images(helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP, build_id)
        scenario_apis_blueprint.logger.info(f"DELETE_SCENARIO: Cleaned up gallery images for {build_id}")
        
        config_path = helpers.CONFIG_FILE_PATH
        config = helpers.load_config()
        
        if "scenarios" in config and scenario_name in config["scenarios"]:
            config["scenarios"].remove(scenario_name)
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            scenario_apis_blueprint.logger.info(f"DELETE_SCENARIO: Removed {scenario_name} from config.json")
        
        return jsonify({
            "success": True,
            "message": f"Successfully deleted scenario {scenario_name}"
        }), 200
        
    except Exception as e:
        scenario_apis_blueprint.logger.error(f"DELETE_SCENARIO: Error deleting scenario: {str(e)}")
        return jsonify({"error": str(e)}), 500


@scenario_apis_blueprint.route("/createBuildScenario", methods=["POST"])
def create_build_scenario():
    try:
        data = json.loads(request.data.decode("utf-8"))
        deployment_id = data.get("deploymentId")
        
        scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Creating scenario from build deployment {deployment_id}")
        
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        if "ERROR" in deployment:
            scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: Could not load deployment {deployment_id}")
            return jsonify({"message": f"Error: Could not load deployment {deployment_id}"}), 404
        
        # Extract key information from the deployment
        resource_group = deployment.get("resourceGroup", deployment_id)
        
        topology = None
        if "topology" in deployment:
            # Topology is embedded in the deployment file (newer builds)
            topology = deployment.get("topology")
            scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Using embedded topology from deployment")
        elif "topologyFile" in deployment:
            # Topology is in a separate file (older builds)
            topology_file_name = deployment.get("topologyFile")
            topology = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, topology_file_name)
            if "ERROR" in topology:
                scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: Could not load topology file {topology_file_name}")
                return jsonify({"message": f"Error: Could not load topology file {topology_file_name}"}), 404
            scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Loaded topology from file {topology_file_name}")
        else:
            scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: No topology found in deployment {deployment_id}")
            return jsonify({"message": f"Error: No topology found in deployment {deployment_id}"}), 404
        
        scenario_name = f"Build-{deployment_id.split('-')[-1]}"  # Use the unique part of the ID
        
        # Extract machine information from topology
        machines = {}
        for node in topology.get("nodes", []):
            node_type = node.get("type")
            node_data = node.get("data", {})
            
            if node_type == "domainController":
                machine_name = node_data.get("domainControllerName")
                machines[machine_name] = {
                    "Name": machine_name,
                    "OSType": "Windows"
                }
            elif node_type == "workstation" or node_type == "standalone":
                machine_name = node_data.get("workstationName", node_data.get("standaloneName"))
                if machine_name:  # Only add if we have a valid name
                    machines[machine_name] = {
                        "Name": machine_name,
                        "OSType": "Windows"
                    }
            elif node_type == "certificateAuthority":
                machine_name = node_data.get("caName", "CA01")
                machines[machine_name] = {
                    "Name": machine_name,
                    "OSType": "Windows"
                }
            elif node_type == "jumpbox":
                machines["JUMPBOX"] = {
                    "Name": "JUMPBOX",
                    "OSType": "Linux"
                }
        
        scenario_description = deployment.get("scenarioInfo", "").strip()
        if not scenario_description:
            # Generate descriptive text from topology - simple list of components
            components = []
            
            # Count domain controllers
            root_dc_count = 0
            sub_dc_count = 0
            for node in topology.get("nodes", []):
                if node.get("type") == "domainController":
                    node_data = node.get("data", {})
                    if node_data.get("isSub", False):
                        sub_dc_count += 1
                    else:
                        root_dc_count += 1
            
            if root_dc_count > 0:
                components.append(f"{root_dc_count} Root DC{'s' if root_dc_count > 1 else ''}")
            
            if sub_dc_count > 0:
                components.append(f"{sub_dc_count} Sub DC{'s' if sub_dc_count > 1 else ''}")
            
            ca_count = sum(1 for node in topology.get("nodes", []) if node.get("type") == "certificateAuthority")
            if ca_count > 0:
                components.append(f"{ca_count} CA{'s' if ca_count > 1 else ''}")
            
            standalone_count = sum(1 for node in topology.get("nodes", []) if node.get("type") in ["workstation", "standalone"])
            if standalone_count > 0:
                components.append(f"{standalone_count} Standalone{'s' if standalone_count > 1 else ''}")
            
            has_jumpbox = any(node.get("type") == "jumpbox" for node in topology.get("nodes", []))
            if has_jumpbox:
                components.append("1 Jumpbox")
            
            if components:
                scenario_description = ", ".join(components)
            else:
                machine_count = len(machines)
                scenario_description = f"{machine_count} machine{'s' if machine_count != 1 else ''}"
        
        scenario_obj = {
            "machines": machines,
            "type": "BUILD",
            "subtype": "NETWORK",
            "info": scenario_description,  # Use the user-provided or generated description
            "description": scenario_description,  # Also set description field
            "attackCompatibility": ["ADCS", "Privilege Escalation", "Authentication", "UserAttacks"],
            "enabledAttacks": {},
            "topology": topology,  # Include the full topology for visualization
            "imageReferences": {},
            "kaliSku": helpers.get_latest_kali_sku()  # Save the current latest Kali SKU (matches what build used)
        }
        
        subscription_id = helpers.get_subscription_id()
        if not subscription_id:
            scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: Could not determine subscription ID - image references may be invalid")
        
        for machine_name in machines:
            if machines[machine_name]["OSType"] == "Windows":
                scenario_obj["imageReferences"][machine_name] = f"/subscriptions/{subscription_id}/resourceGroups/{helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP}/providers/Microsoft.Compute/galleries/{helpers.BUILD_GALLERY_NAME}/images/{deployment_id}-{machine_name}/versions/1.0.0"
            elif machines[machine_name]["OSType"] == "Linux":
                scenario_obj["imageReferences"][machine_name] = f"/subscriptions/{subscription_id}/resourceGroups/{helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP}/providers/Microsoft.Compute/galleries/{helpers.BUILD_GALLERY_NAME}/images/{deployment_id}-{machine_name}/versions/1.0.0"
        
        # NOTE: Frontend timer handles the wait period for AD initialization - no backend sleep needed
        scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Deploying BuildInfrastructure to create snapshots for {deployment_id}")
        
        try:
            server_objects = []
            for machine_name, machine_info in machines.items():
                if machine_info["OSType"] == "Windows":
                    # Determine serverType based on machine name or topology
                    server_type = "Standalone"  # Default
                    for node in topology.get("nodes", []):
                        node_data = node.get("data", {})
                        if node.get("type") == "domainController":
                            if node_data.get("domainControllerName") == machine_name:
                                server_type = "RootDC" if node_data.get("isRoot", True) else "SubDC"
                                break
                        elif node.get("type") == "certificateAuthority":
                            if node_data.get("caName", "CA01") == machine_name:
                                server_type = "CA"
                                break
                    
                    server_objects.append({
                        "name": machine_name,
                        "serverType": server_type
                    })
                elif machine_info["OSType"] == "Linux":
                    server_objects.append({
                        "name": "BuildJumpbox",  # The actual Azure VM resource name during build
                        "imageName": "JUMPBOX",  # The name to use in the gallery image path
                        "serverType": "Jumpbox"
                    })
            
            build_infra_template = fs_manager.load_file(helpers.TEMPLATE_DIRECTORY, "BuildInfrastructure.json")
            if "ERROR" in build_infra_template:
                raise Exception(f"Could not load BuildInfrastructure.json template")
            
            domain_name = ""
            for node in topology.get("nodes", []):
                if node.get("type") == "domainController":
                    domain_name = node.get("data", {}).get("domainName", "")
                    if domain_name:
                        break
            
            build_infra_params = {
                "location": {"value": deployment.get("location", helpers.LOCATION)},
                "resourceGroupName": {"value": helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP},
                "sourceResourceGroupName": {"value": resource_group},
                "scenarioTagValue": {"value": "BUILD"},
                "galleryName": {"value": helpers.BUILD_GALLERY_NAME},
                "domainNameTag": {"value": domain_name},
                "subscriptionID": {"value": subscription_id},
                "serverObjects": {"value": server_objects},
                "kaliSku": {"value": helpers.get_latest_kali_sku()}  # Use current latest Kali SKU
            }
            
            from azure_clients import AzureClients
            from azure.mgmt.resource.resources.models import Deployment, DeploymentProperties, DeploymentMode
            
            azure_clients = AzureClients()
            resource_client = azure_clients.get_resource_client()
            
            deployment_properties = DeploymentProperties(
                mode=DeploymentMode.INCREMENTAL,
                template=build_infra_template,
                parameters=build_infra_params
            )
            
            deployment_name = f"BuildInfra-{scenario_name}"
            deployment_obj = Deployment(
                location=deployment.get("location", helpers.LOCATION),
                properties=deployment_properties
            )
            
            scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Starting BuildInfrastructure deployment {deployment_name}")
            
            poller = resource_client.deployments.begin_create_or_update_at_subscription_scope(
                deployment_name=deployment_name,
                parameters=deployment_obj
            )
            
            scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Waiting for snapshot creation to complete...")
            result = poller.result()  # This blocks until deployment completes
            
            scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: BuildInfrastructure deployment completed successfully")
            
        except Exception as snapshot_error:
            import traceback
            error_trace = traceback.format_exc()
            scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: Error creating snapshots: {str(snapshot_error)}")
            scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: Snapshot error traceback:\n{error_trace}")
            return jsonify({"message": f"Error creating snapshots: {str(snapshot_error)}"}), 500
        
        users = deployment_handler.get_deployment_attribute(deployment_id, "users") or []
        enabled_attacks = deployment_handler.get_deployment_attribute(deployment_id, "enabledAttacks") or {}
        scenario_obj["users"] = users
        scenario_obj["enabledAttacks"] = enabled_attacks
        scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Caching {len(users)} users and {len(enabled_attacks)} enabled attacks in scenario {scenario_name}")
        
        fs_manager.save_file(scenario_obj, helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
        
        create_scenario_bicep(scenario_name, scenario_obj, topology)

        create_scenario_parameters(scenario_name, scenario_obj, topology)

        config = helpers.load_config()
        if scenario_name not in config["scenarios"]:
            config["scenarios"].append(scenario_name)
            fs_manager.save_file(config, helpers.CONFIG_DIRECTORY, "config.json")
            
        scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Successfully created scenario {scenario_name}")
        return jsonify({"message": f"Successfully created scenario {scenario_name}", "scenarioName": scenario_name}), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: Error creating scenario: {str(e)}")
        scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: Full traceback:\n{error_trace}")
        return jsonify({"message": f"Error creating scenario: {str(e)}"}), 500


@scenario_apis_blueprint.route("/updateScenario", methods=["POST"])
def update_scenario():
    """
    Update an existing scenario with new snapshots from a build or deployed environment.
    This is the 'Save' functionality that updates the linked scenario.
    """
    try:
        data = json.loads(request.data.decode("utf-8"))
        deployment_id = data.get("deploymentId")
        
        scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Updating scenario from deployment {deployment_id}")
        
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        if "ERROR" in deployment:
            scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Could not load deployment {deployment_id}")
            return jsonify({"message": f"Error: Could not load deployment {deployment_id}"}), 404
        
        scenario_name = None
        scenario_field = deployment.get("scenario", "")
        
        if scenario_field and scenario_field != "Custom Topology":
            scenario_name = scenario_field
            scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Updating deployed scenario {scenario_name}")
        elif helpers.BUILD_LAB_PREFIX in deployment_id:
            scenario_name = f"Build-{deployment_id.split('-')[-1]}"
            scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Updating build scenario {scenario_name}")
        else:
            scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Could not determine scenario name from deployment {deployment_id}")
            return jsonify({"message": "Error: Could not determine linked scenario"}), 400
        
        scenario_file_path = os.path.join(helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
        if not os.path.exists(scenario_file_path):
            scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Scenario {scenario_name} does not exist")
            return jsonify({"message": f"Error: Scenario {scenario_name} does not exist. Use 'Save as Scenario' first."}), 404
        
        scenario_obj = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
        if "ERROR" in scenario_obj:
            scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Could not load scenario {scenario_name}")
            return jsonify({"message": f"Error: Could not load scenario {scenario_name}"}), 404
        
        resource_group = deployment.get("resourceGroup", deployment_id)
        
        machines = scenario_obj.get("machines", {})
        
        topology = None
        if "topology" in deployment:
            topology = deployment.get("topology")
        elif "topology" in scenario_obj:
            topology = scenario_obj.get("topology")
        else:
            scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: No topology found")
            return jsonify({"message": "Error: No topology found"}), 404
        
        subscription_id = helpers.get_subscription_id()
        if not subscription_id:
            scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Could not determine subscription ID")
            return jsonify({"message": "Error: Could not determine subscription ID"}), 500
        
        scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Creating new snapshots for {deployment_id}")
        
        try:
            server_objects = []
            for machine_name, machine_info in machines.items():
                if machine_info["OSType"] == "Windows":
                    # Determine serverType from topology
                    server_type = "Standalone"  # Default
                    for node in topology.get("nodes", []):
                        node_data = node.get("data", {})
                        if node.get("type") == "domainController":
                            if node_data.get("domainControllerName") == machine_name:
                                server_type = "RootDC" if node_data.get("isRoot", True) else "SubDC"
                                break
                        elif node.get("type") == "certificateAuthority":
                            if node_data.get("caName", "CA01") == machine_name:
                                server_type = "CA"
                                break
                    
                    server_objects.append({
                        "name": machine_name,
                        "serverType": server_type
                    })
                elif machine_info["OSType"] == "Linux":
                    vm_name = "Jumpbox" if scenario_field and scenario_field != "Custom Topology" else "BuildJumpbox"
                    
                    server_objects.append({
                        "name": vm_name,  # The actual Azure VM resource name
                        "imageName": "JUMPBOX",  # The name to use in the gallery image path
                        "serverType": "Jumpbox"
                    })
            
            build_infra_template = fs_manager.load_file(helpers.TEMPLATE_DIRECTORY, "BuildInfrastructure.json")
            if "ERROR" in build_infra_template:
                raise Exception("Could not load BuildInfrastructure.json template")
            
            domain_name = ""
            for node in topology.get("nodes", []):
                if node.get("type") == "domainController":
                    domain_name = node.get("data", {}).get("domainName", "")
                    if domain_name:
                        break
            
            current_version = "1.0.0"  # Default starting version
            
            try:
                if scenario_obj.get("imageReferences"):
                    # Extract gallery and image definition info from first image reference
                    first_image_ref = next(iter(scenario_obj["imageReferences"].values()))
                    
                    # Parse the image reference to get gallery and image definition
                    parts = first_image_ref.split("/")
                    gallery_idx = parts.index("galleries") if "galleries" in parts else -1
                    images_idx = parts.index("images") if "images" in parts else -1
                    
                    if gallery_idx != -1 and images_idx != -1:
                        gallery_name = parts[gallery_idx + 1]
                        image_definition = parts[images_idx + 1]
                        
                        version_command = [
                            "/usr/bin/az", "sig", "image-version", "list",
                            "--resource-group", helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP,
                            "--gallery-name", gallery_name,
                            "--gallery-image-definition", image_definition,
                            "--query", "[].name",
                            "--output", "json"
                        ]
                        
                        version_output = command_runner.run_command_and_read_output(version_command)
                        versions = json.loads(version_output)
                        
                        if versions and len(versions) > 0:
                            def version_key(v):
                                try:
                                    parts = v.split('.')
                                    return (int(parts[0]), int(parts[1]), int(parts[2]))
                                except:
                                    return (0, 0, 0)
                            
                            versions_sorted = sorted(versions, key=version_key, reverse=True)
                            current_version = versions_sorted[0]  # Highest version in Azure
                            scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Found {len(versions)} versions in Azure, latest is {current_version}")
            except Exception as e:
                scenario_apis_blueprint.logger.warning(f"UPDATE_SCENARIO: Could not query Azure for versions, using scenario JSON: {e}")
                if scenario_obj.get("imageReferences"):
                    first_image_ref = next(iter(scenario_obj["imageReferences"].values()))
                    if "/versions/" in first_image_ref:
                        version_part = first_image_ref.split("/versions/")[1]
                        current_version = version_part.split("/")[0].split("?")[0].strip()
            
            # Parse version and increment patch number
            try:
                version_parts = current_version.split(".")
                if len(version_parts) != 3:
                    raise ValueError(f"Invalid version format: {current_version}")
                
                major = int(version_parts[0])
                minor = int(version_parts[1])
                patch = int(version_parts[2])
                new_patch = patch + 1
                new_version = f"{major}.{minor}.{new_patch}"
                
                scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Incrementing version from {current_version} to {new_version}")
            except (ValueError, IndexError) as e:
                scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Invalid version format '{current_version}': {e}")
                return jsonify({"message": f"Error: Invalid version format in existing scenario"}), 500
            
            # Extract the original build ID from the scenario name for image naming
            original_build_id = f"{helpers.BUILD_LAB_PREFIX}{scenario_name.split('-')[-1]}"
            
            build_infra_params = {
                "location": {"value": deployment.get("location", helpers.LOCATION)},
                "resourceGroupName": {"value": helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP},
                "sourceResourceGroupName": {"value": resource_group},  # Use current deployment RG where VMs exist
                "scenarioTagValue": {"value": "BUILD"},
                "galleryName": {"value": helpers.BUILD_GALLERY_NAME},
                "domainNameTag": {"value": domain_name},
                "subscriptionID": {"value": subscription_id},
                "serverObjects": {"value": server_objects},
                "kaliSku": {"value": helpers.get_latest_kali_sku()},
                "versionName": {"value": new_version},  # Use new version number
                "imageNamePrefix": {"value": original_build_id}  # Preserve original naming for gallery images
            }
            
            from azure.mgmt.resource.resources.models import Deployment, DeploymentProperties, DeploymentMode
            
            resource_client = azure_clients.get_resource_client()
            
            deployment_properties = DeploymentProperties(
                mode=DeploymentMode.INCREMENTAL,
                template=build_infra_template,
                parameters=build_infra_params
            )
            
            deployment_name = f"UpdateScenario-{scenario_name}-{new_patch}"
            deployment_obj_azure = Deployment(
                location=deployment.get("location", helpers.LOCATION),
                properties=deployment_properties
            )
            
            scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Starting BuildInfrastructure deployment {deployment_name}")
            
            try:
                existing = resource_client.deployments.get_at_subscription_scope(deployment_name)
                if existing.properties.provisioning_state in ["Failed", "Canceled"]:
                    scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Found stale deployment {deployment_name} in state {existing.properties.provisioning_state}, cleaning up...")
                    try:
                        resource_client.deployments.begin_delete_at_subscription_scope(deployment_name).wait()
                        scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Cleaned up stale deployment {deployment_name}")
                    except Exception as cleanup_error:
                        scenario_apis_blueprint.logger.warning(f"UPDATE_SCENARIO: Could not clean up stale deployment: {cleanup_error}")
            except Exception:
                pass
            
            poller = resource_client.deployments.begin_create_or_update_at_subscription_scope(
                deployment_name=deployment_name,
                parameters=deployment_obj_azure
            )
            
            scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Waiting for snapshot creation to complete...")
            result = poller.result()  # This blocks until deployment completes
            
            scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: BuildInfrastructure deployment completed successfully")
            
        except Exception as snapshot_error:
            import traceback
            error_trace = traceback.format_exc()
            scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Error creating snapshots: {str(snapshot_error)}")
            scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Snapshot error traceback:\n{error_trace}")
            return jsonify({"message": f"Error creating snapshots: {str(snapshot_error)}"}), 500
        
        for machine_name in machines:
            scenario_obj["imageReferences"][machine_name] = f"/subscriptions/{subscription_id}/resourceGroups/{helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP}/providers/Microsoft.Compute/galleries/{helpers.BUILD_GALLERY_NAME}/images/{original_build_id}-{machine_name}/versions/{new_version}"
        
        if "kaliSku" in scenario_obj:
            scenario_obj["kaliSku"] = helpers.get_latest_kali_sku()
        
        users = deployment_handler.get_deployment_attribute(deployment_id, "users") or []
        enabled_attacks = deployment_handler.get_deployment_attribute(deployment_id, "enabledAttacks") or {}
        scenario_obj["users"] = users
        scenario_obj["enabledAttacks"] = enabled_attacks
        scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Caching {len(users)} users and {len(enabled_attacks)} enabled attacks in scenario {scenario_name}")
        
        fs_manager.save_file(scenario_obj, helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
        
        scenario_apis_blueprint.logger.info(f"UPDATE_SCENARIO: Successfully updated scenario {scenario_name} to version {new_version}")
        return jsonify({"message": f"Successfully updated scenario {scenario_name} to version {new_version}", "scenarioName": scenario_name, "newVersion": new_version}), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Error updating scenario: {str(e)}")
        scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIO: Full traceback:\n{error_trace}")
        return jsonify({"message": f"Error updating scenario: {str(e)}"}), 500
    


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
param certificateAuthorities array = []
param callerIPAddress string = ''
param kaliSku string = 'kali-2025-2'

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
        has_public_ip = node_data.get("hasPublicIP", False)
        
        network_deps = []
        if private_ip.startswith("10.10."):
            network_deps.append("vnet10")
        elif private_ip.startswith("172.16."):
            network_deps.append("vnet172")
        elif private_ip.startswith("192.168."):
            network_deps.append("vnet192")
        
        network_depends = ", ".join(network_deps)
        
        connection_str = private_ip if private_ip in jumpbox_connections else ""
        
        has_public_ip_str = "true" if has_public_ip else "false"
        
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
    hasPublicIP: {has_public_ip_str}
    callerIPAddress: callerIPAddress
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
        has_public_ip = node_data.get("hasPublicIP", False)
        
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
        
        has_public_ip_str = "true" if has_public_ip else "false"
        
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
    hasPublicIP: {has_public_ip_str}
    callerIPAddress: callerIPAddress
  }}
  dependsOn: [
    {network_depends}
  ]
}}
"""

    for node in topology.get("nodes", []):
        if node.get("type") == "certificateAuthority":
            node_data = node.get("data", {})
            machine_name = node_data.get("caName", "CA01")
            private_ip = node_data.get("privateIPAddress", "10.10.0.20")
            has_public_ip = node_data.get("hasPublicIP", False)
            
            # Find connected domain controller (parent)
            dc_ip = ""
            domain_name = ""
            dc_node = None
            
            # Check edges to find connected DC
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
                dc_name = dc_data.get("domainControllerName", "DC01")
            else:
                if root_domain_controllers:
                    dc_data = root_domain_controllers[0].get("data", {})
                    dc_ip = dc_data.get("privateIPAddress", "10.10.0.5")
                    domain_name = dc_data.get("domainName", "domain.local")
                    dc_name = dc_data.get("domainControllerName", "DC01")
                else:
                    dc_ip = "10.10.0.5"
                    domain_name = "domain.local"
                    dc_name = "DC01"
            
            network_deps = []
            if private_ip.startswith("10.10."):
                network_deps.append("vnet10")
            elif private_ip.startswith("172.16."):
                network_deps.append("vnet172")
            elif private_ip.startswith("192.168."):
                network_deps.append("vnet192")
            
            if dc_name:
                network_deps.append(dc_name)
            
            network_depends = ", ".join(network_deps)
            
            connection_str = private_ip if private_ip in jumpbox_connections else ""
            
            has_public_ip_str = "true" if has_public_ip else "false"
            
            bicep_content += f"""
module {machine_name} '../base/CertificateAuthority.bicep' = {{
  scope: resourceGroup(resourceGroupName)
  name: '{machine_name}'
  params: {{
    location: location
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: '{machine_name}'
    resourceGroupName: resourceGroupName
    osDiskType: vmDiskType
    rootDomainControllerPrivateIp: '{dc_ip}'
    domainAndEnterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    domainName: '{domain_name}'
    deployOrBuild: 'deploy'
    imageReference: {machine_name}ImageReferenceID
    privateIPAddress: '{private_ip}'
    localAdminUsername: enterpriseAdminUsername
    localAdminPassword: enterpriseAdminPassword
    oldScenarios: oldScenarios
    jumpboxPrivateIPAddress: '{jumpbox_ip}'
    connectedPrivateIPAddress: '{connection_str}'
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
    hasPublicIP: {has_public_ip_str}
    callerIPAddress: callerIPAddress
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
        
        ca_processed = False
        for node in topology.get("nodes", []):
            if node.get("type") == "certificateAuthority":
                if node.get("data", {}).get("caName") == machine_name:
                    ca_processed = True
                    break
        if ca_processed:
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
            has_public_ip = node_data.get("hasPublicIP", False)
            
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
            
            has_public_ip_str = "true" if has_public_ip else "false"
            
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
    domainAndEnterpriseAdminUsername: enterpriseAdminUsername
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
    hasPublicIP: {has_public_ip_str}
    callerIPAddress: callerIPAddress
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
            
            bicep_content += f"""
module Jumpbox '../base/Jumpbox.bicep' = {{
  scope: resourceGroup(resourceGroupName)
  name: 'Jumpbox'
  params: {{
    location: location
    vmName: '{machine_name}'
    vmSize: jumpboxVmSize
    resourceGroupName: resourceGroupName
    jumpboxPrivateIPAddress: '{private_ip}'
    connectedPrivateIPAddress: '{connection_str}'
    oldScenarios: oldScenarios
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
    deployOrBuild: 'deploy'
    osDiskType: vmDiskType
    jumpboxAdminUsername: 'redteamer'
    jumpboxAdminPassword: 'Password#123'
    kaliSku: kaliSku
    callerIPAddress: callerIPAddress
    imageReference: {machine_name}ImageReferenceID
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
    
    scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Compiling Scenario{scenario_name}.bicep to JSON...")
    json_path = os.path.join(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"Scenario{scenario_name}.json")
    compile_command = ["az", "bicep", "build", "--file", bicep_path, "--outfile", json_path]
    compile_output = command_runner.run_command_and_read_output(compile_command)
    compile_exit_code = command_runner.run_command_and_get_exit_code(compile_command)
    
    if compile_exit_code != 0:
        scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: Bicep compilation failed with exit code {compile_exit_code}")
        scenario_apis_blueprint.logger.error(f"CREATE_BUILD_SCENARIO: Compilation output: {compile_output}")
        raise Exception(f"Failed to compile scenario template: {compile_output}")
    
    scenario_apis_blueprint.logger.info(f"CREATE_BUILD_SCENARIO: Scenario{scenario_name}.bicep compiled successfully to JSON")
    
    return bicep_path

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
        scenario_apis_blueprint.logger.error(f"UPDATE_SCENARIOS_LIST: Error updating scenarios list: {str(e)}")


def create_scenario_parameters(scenario_name, scenario_data, topology):
    """Generate a custom parameters file for a saved build scenario"""

    build_params_path = helpers.SCENARIO_MANAGER_BUILD_PARAMS

    with open(build_params_path, 'r') as f:
        build_params = json.load(f)

    build_params["parameters"]["scenarioSelection"]["value"] = scenario_name
    build_params["parameters"]["scenarioTagValue"]["value"] = scenario_name

    # Inject subscription ID dynamically (template file has empty value)
    build_params["parameters"]["subscriptionID"]["value"] = helpers.get_subscription_id()

    kali_sku = helpers.get_latest_kali_sku()
    build_params["parameters"]["kaliSku"] = {"value": kali_sku}

    for machine_name, image_ref in scenario_data.get("imageReferences", {}).items():
        build_params["parameters"][f"{machine_name}ImageReferenceID"] = {"value": image_ref}

    params_path = os.path.join(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"{scenario_name}.parameters.json")
    os.makedirs(os.path.dirname(params_path), exist_ok=True)

    with open(params_path, "w") as f:
        json.dump(build_params, f, indent=2)

    return params_path

