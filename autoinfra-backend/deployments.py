from datetime import datetime
import logging
import re
import os
import command_runner
import fs_manager
import helpers
from azure_clients import AzureClients
from azure_setup import AzureSetup
from azure.mgmt.resource.resources.models import Deployment, DeploymentProperties, DeploymentMode
import threading
logger = logging.getLogger(helpers.LOGGER_NAME)
azure_setup = AzureSetup()
azure_clients = AzureClients()
deploymentRegions = helpers.DEPLOYMENT_REGIONS

class Deployments:
    def __init__(self):
        self.expiryTimeoutTag = "timeout"
        self.ipv4_pattern = re.compile(r'\b((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')

    def deployment_resolver(self, poller, deploymentID, scenario):
        logger.debug(f"DEPLOYMENT_RESOLVER: Waiting for deployment {deploymentID} to complete...")

        try:
            result = poller.result()  # waits for completion
            logger.debug(f"DEPLOYMENT_RESOLVER: Deployment {deploymentID} complete.")
        except Exception as e:
            logger.error(f"DEPLOYMENT_RESOLVER: Error during deployment: {e}")
            return

        self.get_deployment_ip(deploymentID)

    def deploy_scenario(self, scenario, caller_ip=None, version=None, machine_versions=None):
        appConfig = helpers.load_config()
        region = appConfig['region']
        scenarios = appConfig["scenarios"]
        deploymentID = helpers.generate_random_id()
        expiryTimestamp = 0
        
        if region not in deploymentRegions:
            logger.error(f"DEPLOY: No region selected")
            return {"message":"Error: Please select a region before deploying."}

        if scenario not in scenarios:
            logger.error(f"DEPLOY: No scenario selected")
            return {"message":"Error: Please select a scenario before deploying."}
        
        if appConfig["azureAuth"] != "true":
            logger.error(f"DEPLOY: Not authorized to Azure")
            return {"message":"Error: Not authorized to Azure"}

        scenarioInfo = fs_manager.load_file(helpers.SCENARIO_DIRECTORY,f"{scenario}.json")

        if scenario.startswith("Build-"):
            scenarioInfo = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, f"{scenario}.json")
            if "ERROR" not in scenarioInfo:
                template = fs_manager.load_file(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"Scenario{scenario}.json")
                base_params = fs_manager.load_file(helpers.SCENARIO_TEMPLATE_DIRECTORY, f"{scenario}.parameters.json")

                if machine_versions:
                    logger.info(f"DEPLOY: Using per-machine versions for scenario {scenario}: {machine_versions}")
                    updated_image_refs = {}
                    for machine_name, image_ref in scenarioInfo["imageReferences"].items():
                        machine_version = machine_versions.get(machine_name)
                        if machine_version:
                            # Replace the version in the image reference
                            if "/versions/" in image_ref:
                                base_ref = image_ref.split("/versions/")[0]
                                updated_image_refs[machine_name] = f"{base_ref}/versions/{machine_version}"
                            else:
                                updated_image_refs[machine_name] = f"{image_ref}/versions/{machine_version}"
                            logger.info(f"DEPLOY: {machine_name} -> version {machine_version}")
                        else:
                            updated_image_refs[machine_name] = image_ref
                            logger.info(f"DEPLOY: {machine_name} -> default version")
                    image_references = updated_image_refs
                elif version:
                    logger.info(f"DEPLOY: Using unified version {version} for all machines in scenario {scenario}")
                    updated_image_refs = {}
                    for machine_name, image_ref in scenarioInfo["imageReferences"].items():
                        # Replace the version in the image reference
                        if "/versions/" in image_ref:
                            base_ref = image_ref.split("/versions/")[0]
                            updated_image_refs[machine_name] = f"{base_ref}/versions/{version}"
                        else:
                            updated_image_refs[machine_name] = f"{image_ref}/versions/{version}"
                    
                    image_references = updated_image_refs
                    logger.info(f"DEPLOY: Updated all image references to version {version}")
                else:
                    image_references = scenarioInfo["imageReferences"]
                    logger.info(f"DEPLOY: Using default image references from scenario")

                dynamic_params = {
                    "resourceGroupName": {"value": deploymentID},
                    "scenarioTagValue": {"value": scenario},
                    "expiryTimeout": {"value": str(expiryTimestamp)},
                    "kaliSku": {"value": scenarioInfo.get("kaliSku", helpers.get_latest_kali_sku())},  # Use saved SKU or fallback to latest
                    "callerIPAddress": {"value": caller_ip if caller_ip else ""},
                }

                for machine_name, image_ref in image_references.items():
                    dynamic_params[f"{machine_name}ImageReferenceID"] = {"value": image_ref}

                parameters = base_params.get("parameters", {})
                parameters.update(dynamic_params)

                deployment_properties = DeploymentProperties(
                    mode=DeploymentMode.INCREMENTAL,
                    template=template,
                    parameters=parameters
                )

                deployment = Deployment(location=region,properties=deployment_properties)

                resource_client = azure_clients.get_resource_client()
                poller = resource_client.deployments.begin_create_or_update_at_subscription_scope(
                    deployment_name=deploymentID,
                    parameters=deployment
                )

                threading.Thread(
                    target=self.deployment_resolver,
                    args=(poller, deploymentID, scenario)
                ).start()

                logger.info(f"DEPLOY: Deploying {scenario} to {deploymentID}.")
                # Include topology from scenario for multi-domain support
                topology = scenarioInfo.get("topology")
                users = scenarioInfo.get("users", [])
                enabled_attacks = scenarioInfo.get("enabledAttacks", {})
                logger.info(f"DEPLOY: Loading {len(users)} cached users and {len(enabled_attacks)} enabled attacks from scenario {scenario}")
                self.set_deployment_configs("deploy", deploymentID, scenario, expiryTimestamp, scenarioInfo["machines"], topology=topology, users=users, enabledAttacks=enabled_attacks)
                return {"deploymentID": deploymentID, "message": f"{scenario} deploying to {deploymentID}"} 

    def list_azure_deployments(self):
        logger.debug("LIST_AZURE_DEPLOYMENTS: Listing Azure deployments...")
        try:
            resource_client = azure_clients.get_resource_client()
            deployments = resource_client.resource_groups.list()

            result = {}

            for deployment in deployments:
                rg_name = deployment.name
                # Only consider resource groups tagged as lab deployments
                if not deployment.tags or "Scenario" not in deployment.tags:
                    continue

                deployment_data = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, rg_name)
                if "ERROR" in deployment_data:
                    continue

                result[rg_name] = {
                    "deploymentID": rg_name,
                    "scenario": deployment_data.get("scenario", "Unknown"),
                }

            return result

        except Exception as e:
            logger.error(f"LIST_AZURE_DEPLOYMENTS: Error listing Azure deployments: {e}")
            return {}


    def list_local_deployments(self):
        logger.debug("LIST_LOCAL_DEPLOYMENTS: Listing local deployments...")
        deployments = os.listdir(helpers.DEPLOYMENT_DIRECTORY)
        deploymentList = []
        for deployment in deployments:
            if deployment != ".gitkeep":
                deploymentList.append(fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment))
        logger.debug(f"LIST_DEPLOYMENTS: Found {len(deploymentList)} deployment(s)")
        return(deploymentList)

    def set_deployment_attribute(self, deploymentID, attribute, value):
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
        if "ERROR" not in deployment:
            deployment[attribute] = value
            logger.debug(f"SET_DEPLOYMENT_ATTRIBUTE: Set {attribute} to {value}")
            fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deploymentID)
        else:
            logger.error("SET_DEPLOYMENT_ATTRIBUTE: Failed. Could not load deployment file.")

    def get_deployment_attribute(self, deploymentID, attribute, directory=''):
        if directory == 'SAVED':
            deployment = fs_manager.load_file(helpers.SAVED_DEPLOYMENTS_DIRECTORY,deploymentID)
        else:
            deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)

        if "ERROR" not in deployment:
            attribute_value = deployment.get(attribute, '' if attribute != 'users' else [])
            logger.debug(f"GET_DEPLOYMENT_ATTRIBUTE: Got {attribute}: {attribute_value}")
            return attribute_value
        else:
            logger.error("GET_DEPLOYMENT_ATTRIBUTE: Failed. Could not load deployment file.")
            return '' if attribute != 'users' else []
    
    def list_deployment_attributes(self, deploymentID, directory=''):
        if directory == '':
            deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
            return deployment
        elif directory == "SAVED":
            deployment = fs_manager.load_file(helpers.SAVED_DEPLOYMENTS_DIRECTORY,deploymentID)
            logger.debug(f"LIST_DEPLOYMENT_ATTRIBUTES: Got deployment attributes: {deployment}")
            return deployment

    def get_deployment_ip(self, deploymentID):
        try:
            deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
            resource_group = deployment.get("resourceGroup", deploymentID)

            network_client = azure_clients.get_network_client()
            public_ips = network_client.public_ip_addresses.list(resource_group)

            # Collect all public IPs with their associated node names
            entry_ips = {}
            first_ip = None
            for public_ip in public_ips:
                if public_ip.ip_address:
                    # Extract node name from public IP name
                    ip_name = public_ip.name
                    if ip_name == "jumpbox-public-ip":
                        node_name = "JUMPBOX"
                    elif ip_name.endswith("-pip"):
                        node_name = ip_name[:-4]  # Remove "-pip" suffix
                    elif ip_name.endswith("-public-ip"):
                        node_name = ip_name[:-10]  # Remove "-public-ip" suffix
                    else:
                        node_name = ip_name
                    entry_ips[node_name] = public_ip.ip_address
                    if first_ip is None:
                        first_ip = public_ip.ip_address
                    logger.info(f"GET_DEPLOYMENT_IP: Found public IP for {node_name}: {public_ip.ip_address}")

            if entry_ips:
                # Store the dictionary of node -> IP mappings
                self.set_deployment_attribute(deploymentID, "entryIPs", entry_ips)
                self.set_deployment_attribute(deploymentID, "entryIP", first_ip)
                logger.info(f"GET_DEPLOYMENT_IP: Set entry IPs for deployment {deploymentID}: {entry_ips}")
            else:
                logger.error(f"GET_DEPLOYMENT_IP: Error Resolving Deployment IP: No IP address. Deployment {deploymentID} (resource group: {resource_group}) is either stale or currently deploying")
        except Exception as e:
            logger.error(f"GET_DEPLOYMENT_IP: Error getting IP for {deploymentID}: {str(e)}")
    
    def destroy_deployment(self, deploymentID, resource_group=None, retries=helpers.DESTROY_DEPLOYMENT_RETRIES):
        try:
            rg_name = resource_group if resource_group else deploymentID

            logger.info(f"DESTROY_DEPLOYMENT: Deleting resource group {rg_name} for deployment {deploymentID}")
            resource_client = azure_clients.get_resource_client()

            for attempt in range(retries):
                try:
                    delete_operation = resource_client.resource_groups.begin_delete(rg_name)
                    logger.info(f"DESTROY_DEPLOYMENT: Started async deletion of resource group {rg_name} for deployment {deploymentID}")

                    # logger.debug(f"DESTROY_DEPLOYMENT: Deleted files for deployment {deploymentID}")

                    return
                except Exception as e:
                    logger.error(f"DESTROY_DEPLOYMENT: Error deleting deployment {deploymentID} (resource group: {rg_name}): {e}")
                    if attempt < retries - 1:
                        logger.info(f"DESTROY_DEPLOYMENT: Retrying deletion for deployment {deploymentID} (attempt {attempt + 2}/{retries})")
                    else:
                        logger.error(f"DESTROY_DEPLOYMENT: Failed to delete deployment {deploymentID} after {retries} attempts")
        except Exception as e:
            logger.error(f"DESTROY_DEPLOYMENT: Error in destroy_deployment for deployment {deploymentID}: {e}")
    
    def does_deployment_exist(self, deploymentID) -> bool:
        resource_client = azure_clients.get_resource_client()
        return resource_client.resource_groups.check_existence(deploymentID)
    
    def destroy_saved_deployment(self, deploymentID, retries=helpers.DESTROY_DEPLOYMENT_RETRIES):
        try:
            command = [
                "az", "group", "delete",
                "--name", deploymentID, "-y"
            ]
            for attempt in range(retries):
                output = command_runner.run_command_and_read_output(command)
                logger.debug(f"DESTROY_DEPLOYMENT: Attempt {attempt + 1} - Destroy output for {deploymentID}: {output}")
                if "error" not in output.lower():  
                    try:
                        fs_manager.delete_file(helpers.SAVED_DEPLOYMENTS_DIRECTORY, deploymentID)
                        logger.debug(f"DESTROY_DEPLOYMENT: Deleted files for deployment {deploymentID}")
                        return
                    except Exception as e:
                        logger.error(f"DESTROY_DEPLOYMENT: Error deleting files for deployment {deploymentID}: {e}")
                        break
                else:
                    logger.error(f"DESTROY_DEPLOYMENT: Error deleting deployment {deploymentID}: {output}")
                    if attempt < retries - 1:
                        logger.info(f"DESTROY_DEPLOYMENT: Retrying deletion for deployment {deploymentID} (attempt {attempt + 2}/{retries})")
                    else:
                        logger.error(f"DESTROY_DEPLOYMENT: Failed to delete deployment {deploymentID} after {retries} attempts")
        except Exception as e:
            logger.error(f"DESTROY_DEPLOYMENT: Error in destroy_deployment for deployment {deploymentID}: {e}")

    def expired_saved_deployments_handler(self):
        currentTime = int(datetime.now().timestamp())
        deployments = self.list_saved_deployments()
        for deployment in deployments:
            resource_group_name = self.get_deployment_attribute(deploymentID=deployment,attribute='deploymentID',directory="SAVED");
            expiryTimestamp = self.get_deployment_attribute(deploymentID=deployment,attribute='expiryTimestamp',directory="SAVED");
            if expiryTimestamp:
                logger.info(f"EXPIRED_DEPLOYMENTS_HANDLER: Current timestamp: {currentTime}")
                logger.info(f"EXPIRED_DEPLOYMENTS_HANDLER: Expiry timestamp: {expiryTimestamp}")
                if int(expiryTimestamp) < currentTime:
                    logger.info(f"Found expired deployment: {resource_group_name}. Destroying.")
                    saved_resource_group_name = helpers.SAVED_DEPLOYMENT_PREFIX + resource_group_name
                    self.destroy_deployment(deploymentID=saved_resource_group_name)
                    logger.info(f"EXPIRED_DEPLOYMENTS_HANDLER: Finished deleting expired deployment {resource_group_name}")
                else:
                    logger.info(f"EXPIRED_DEPLOYMENTS_HANDLER: Deployment {resource_group_name} is not expired.")
            else:
                pass
    
    def expired_deployments_handler(self):
        """
        Check all deployments for expiry and delete expired ones.
        Called by background cleanup thread and manual cleanup.
        """
        currentTime = int(datetime.now().timestamp())
        deployments = self.list_local_deployments()

        for deployment in deployments:
            expiryTimestamp = deployment.get('timeout')
            deploymentID = deployment.get('deploymentID', 'unknown')
            if expiryTimestamp:
                logger.info(f"EXPIRED_DEPLOYMENTS_HANDLER: Current timestamp: {currentTime}")
                logger.info(f"EXPIRED_DEPLOYMENTS_HANDLER: Expiry timestamp: {expiryTimestamp}")
                if int(expiryTimestamp) < currentTime:
                    logger.info(f"Found expired deployment: {deploymentID}. Destroying.")
                    self.destroy_deployment(deploymentID=deploymentID)
                else:
                    logger.info(f"EXPIRED_DEPLOYMENTS_HANDLER: Deployment {deploymentID} is not expired.")
            else:
                pass


    def check_health_of_deployments(self):
        """
        On startup, check all local deployment files for:
        1. Stale files (resource group doesn't exist in Azure)
        2. Expired deployments (timeout has passed)
        This catches any cleanup missed if backend was offline.
        """
        logger.info("CHECK_HEALTH_OF_DEPLOYMENTS: Starting health check...")
        deployments = os.listdir(helpers.DEPLOYMENT_DIRECTORY)
        current_time = int(datetime.now().timestamp())

        try:
            resource_client = azure_clients.get_resource_client()
        except RuntimeError as e:
            logger.warning(f"CHECK_HEALTH: Skipping health check - Azure credentials not available")
            logger.info("CHECK_HEALTH: Health check will run after Azure authentication")
            return

        for deployment_file in deployments:
            if deployment_file == ".gitkeep":
                continue

            try:
                deployment_data = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_file)
                if "ERROR" in deployment_data:
                    logger.warning(f"CHECK_HEALTH: {deployment_file} - error loading, skipping")
                    continue

                deployment_id = deployment_data.get("deploymentID", deployment_file)
                resource_group = deployment_data.get("resourceGroup", deployment_id)

                exists = resource_client.resource_groups.check_existence(resource_group)

                if not exists:
                    logger.warning(f"CHECK_HEALTH: {deployment_id} (RG: {resource_group}) - stale file, deleting local copy")
                    fs_manager.delete_file(helpers.DEPLOYMENT_DIRECTORY, deployment_file)

                    # Also clean up topology file if it exists
                    try:
                        topology_file = f"{deployment_id}_topology"
                        fs_manager.delete_file(helpers.DEPLOYMENT_DIRECTORY, topology_file)
                        logger.info(f"CHECK_HEALTH: Deleted topology file for {deployment_id}")
                    except Exception:
                        # It's okay if topology file doesn't exist
                        pass

                    continue

                timeout = deployment_data.get("timeout", 0)
                if timeout and int(timeout) < current_time:
                    time_expired = current_time - int(timeout)
                    logger.warning(f"CHECK_HEALTH: {deployment_id} - expired {time_expired}s ago, destroying")
                    self.destroy_deployment(deployment_id, resource_group)
                else:
                    logger.info(f"CHECK_HEALTH: {deployment_id} - healthy")

            except Exception as e:
                logger.error(f"CHECK_HEALTH: Error checking {deployment_file}: {e}")

        logger.info("CHECK_HEALTH_OF_DEPLOYMENTS: Health check complete")

    def set_deployment_configs(self,action,deploymentID,scenario,expiryTimestamp,machines,enabledAttacks=None,dockerPort='',savedInfo='',deployable='',topology=None,users=None):
        if enabledAttacks is None:
            enabledAttacks = {}
        deployConfigs = {
            "deploymentID":deploymentID,
            "timeout": expiryTimestamp,
            "remainingExtensions": helpers.MAX_DEPLOYMENT_EXTENSIONS,
            "scenario": scenario,
            "entryIP": "Deploying",
            "enabledAttacks": enabledAttacks, 
            "dockerfilePort":  dockerPort,
            "currentlyEnablingAttacks": "false",
            "machines": machines,
            "savedInfo": savedInfo,
            "deployable": deployable
        }
        # Include topology if provided (for builds and saved deployments)
        if topology:
            deployConfigs["topology"] = topology
        if users is not None:
            deployConfigs["users"] = users
        logger.debug(f"SET_DEPLOYMENT_CONFIGS: Deployment configs: {deployConfigs}")
        directoryToSave = helpers.SAVED_DEPLOYMENTS_DIRECTORY if action == "save" else helpers.DEPLOYMENT_DIRECTORY
        fs_manager.save_file(deployConfigs, directoryToSave, deploymentID)

    ### Saved Deployments
    def list_saved_deployments(self):
        saved_deployments = os.listdir(helpers.SAVED_DEPLOYMENTS_DIRECTORY)

        azureCommand = [
            "az", "group", "list", "--query", f"[?starts_with(name, '{helpers.SAVED_DEPLOYMENT_PREFIX}')].{{Name:name}}"
        ]
        azureGroups = command_runner.run_command_and_read_output(azureCommand)
        logger.debug(f"LISTING SAVED DEPLOYMENTS: {azureGroups}")
        return azureGroups


    def get_saved_deployment(self,savedDeploymentID):
        azureCommand = [
            "az", "group", "list", "--query", f"[?starts_with(name, '{helpers.SAVED_DEPLOYMENT_PREFIX}')].{{Name:name}}"
        ]
        azureGroups = command_runner.run_command_and_read_output(azureCommand)
        deploymentConfigs = fs_manager.load_file(helpers.SAVED_DEPLOYMENTS_DIRECTORY, savedDeploymentID)
        logger.debug(f"GET_SAVED_DEPLOYMENTS: Environment Configs: {deploymentConfigs}")
        if savedDeploymentID in azureGroups and deploymentConfigs != "File not found":
            logger.info(f"GET_SAVED_DEPLOYMENTS: Found saved deployment {savedDeploymentID}")
            return deploymentConfigs
        else:
            return False
        
    def delete_saved_deployment(self,savedDeploymentID):
        savedEnvironment = self.get_saved_deployment(savedDeploymentID)
        if savedEnvironment:
            logger.info(f"DELETE_SAVED_ENVIRONMENT: Found saved environment {savedDeploymentID}. Deleting.")
            command_runner.run_async_command(self.delete_saved_environment_resolver,savedDeploymentID)

    def delete_saved_environment_resolver(self,deploymentID):
        savedDeploymentID = f"{helpers.SAVED_DEPLOYMENT_PREFIX}{deploymentID}"
        command = ["az", "group", "delete","--name", savedDeploymentID, "-y"]
        fs_manager.delete_file(helpers.SAVED_DEPLOYMENTS_DIRECTORY, deploymentID)
        logger.debug(f"DELETE_SAVED_ENVIRONMENT_RESOLVER: Finished deleting the cache data for {savedDeploymentID}.")
        command_runner.run_command_and_read_output(command)
        logger.debug(f"DELETE_SAVED_ENVIRONMENT_RESOLVER: Finished deleting {savedDeploymentID} from Azure.")


    def save_deployment(self,deploymentID):
        appConfig = helpers.load_config()
        region = appConfig["region"]
        subscriptionID = helpers.get_subscription_id()
        scenario = self.get_deployment_attribute(deploymentID,"scenario")
        enabledAttacks = self.get_deployment_attribute(deploymentID, "enabledAttacks")
        dockerPort = self.get_deployment_attribute(deploymentID, "dockerfilePort")
        scenMachines = self.get_deployment_attribute(deploymentID, "machines")
        users = self.get_deployment_attribute(deploymentID, "users") or []
        logger.info(f"SAVE_DEPLOYMENT: Saving deployment {deploymentID} with {len(users)} users and {len(enabledAttacks)} enabled attacks")
        expiryTimestamp = helpers.get_future_time(helpers.SAVED_DEPLOYMENT_TIMEOUT_HOURS)
        expiryDate = datetime.fromtimestamp(expiryTimestamp)
        savedInfo = f"This is a saved {scenario} deployment. It will expire and be deleted on {expiryDate}"
        if deploymentID != "false":
            command = [
                "az", "deployment", "sub", "create", "--name", deploymentID, "--location", region,
                "--template-file", helpers.SAVE_DEPLOYMENT_BICEP,
                "--parameters", f"resourceGroupName={helpers.SAVED_DEPLOYMENT_PREFIX}{deploymentID}", f"galleryName={deploymentID}Gallery", f"subscriptionID={subscriptionID}", f"machineObjects={scenMachines}", f"timeout={expiryTimestamp}", f"resourceGroupID={deploymentID}"
            ]
            command_runner.run_async_command(self.save_deployment_resolver, command, deploymentID)
            self.set_deployment_configs(action="save",deploymentID=deploymentID,scenario=scenario,expiryTimestamp=expiryTimestamp,machines=scenMachines,enabledAttacks=enabledAttacks,dockerPort=dockerPort,savedInfo=savedInfo,users=users)
            return f"Saving deployment {deploymentID} to {helpers.SAVED_DEPLOYMENT_PREFIX}{deploymentID}"
        

    def save_deployment_resolver(self, command, deploymentID):
        logger.debug(f"SAVE_DEPLOYMENT_RESOLVER: Deleting previous save of {deploymentID} if it exists...")
        self.delete_saved_deployment(deploymentID)
        logger.debug(f"SAVE_DEPLOYMENT_RESOLVER: Saving {deploymentID} to {helpers.SAVED_DEPLOYMENT_PREFIX}{deploymentID}...")
        command_runner.run_command_and_read_output(command)#run_command_and_read_output(command)
        logger.debug(f"SAVE_DEPLOYMENT_RESOLVER: Destroying deployment...")
        self.destroy_deployment(deploymentID)
        logger.debug(f"SAVE_DEPLOYMENT_RESOLVER: Finished destroying")

    def get_deployment_state(self, deploymentID):
        try:
            if not deploymentID or deploymentID in ["undefined", "false", "null"]:
                return {"message": "No deployment", "status": 404}

            resource_client = azure_clients.get_resource_client()

            if not resource_client.resource_groups.check_existence(deploymentID):
                return {"message": "Resource group not found", "status": 404}

            deployments = list(resource_client.deployments.list_by_resource_group(deploymentID))

            if not deployments:
                return {"message": "No deployments found", "status": 404}

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
                logger.error(f"GET_DEPLOYMENT_STATE: Failed deployments in {deploymentID}: {failed_deployments}")
                return {"message": "failed", "details": {"failed": failed_deployments, "succeeded": succeeded_deployments, "running": running_deployments}, "status": 200}
            elif running_deployments:
                logger.info(f"GET_DEPLOYMENT_STATE: Deployments still running in {deploymentID}: {running_deployments}")
                return {"message": "deploying", "details": {"running": running_deployments, "succeeded": succeeded_deployments}, "status": 200}
            else:
                logger.info(f"GET_DEPLOYMENT_STATE: All deployments succeeded in {deploymentID}")
                return {"message": "deployed", "details": {"succeeded": succeeded_deployments}, "status": 200}

        except Exception as e:
            logger.error(f"GET_DEPLOYMENT_STATE: Error checking state for {deploymentID}: {str(e)}")
            return {"message": str(e), "status": 500}


    def cleanup_deployments_on_exit(self):
        """
        Clean up all active deployments on shutdown.
        Called by signal handler on Ctrl+C or termination.
        """
        deployment_files = os.listdir(helpers.DEPLOYMENT_DIRECTORY)
        deployment_ids = [f for f in deployment_files if f != ".gitkeep" and not f.endswith("_topology")]

        if not deployment_ids:
            logger.info("CLEANUP_DEPLOYMENTS_ON_EXIT: No active deployments to clean up")
            return

        logger.info(f"CLEANUP_DEPLOYMENTS_ON_EXIT: Found {len(deployment_ids)} deployment(s) to clean up")

        for deployment_id in deployment_ids:
            try:
                logger.info(f"CLEANUP_DEPLOYMENTS_ON_EXIT: Destroying deployment {deployment_id}")
                self.destroy_deployment(deployment_id)
            except Exception as e:
                logger.error(f"CLEANUP_DEPLOYMENTS_ON_EXIT: Error destroying {deployment_id}: {e}")
