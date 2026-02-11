from flask import Blueprint, request, jsonify
from azure_clients import AzureClients
from deployments import Deployments
import helpers
import fs_manager
import command_runner
import logging
from scenario_manager import ScenarioManager
from azure.mgmt.compute.models import RunCommandInput, RunCommandInputParameter
import os

deployment_config_apis_blueprint = Blueprint('deployment_config', __name__)
azure_clients = AzureClients()
deployment_handler = Deployments()
scenario_manager = ScenarioManager()
deployment_config_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)


@deployment_config_apis_blueprint.route("/getDeploymentDomains", methods=["POST"])
def get_deployment_domains():
    """
    Get list of domains from deployment topology.
    Returns domain names with their associated DC names for running commands.
    """
    data = request.get_json()
    deploymentID = data.get("deploymentID")
    
    if not deploymentID:
        return jsonify({"message": "deploymentID is required", "domains": []}), 400
    
    try:
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
        
        if "ERROR" in str(deployment):
            return jsonify({"message": "Deployment not found", "domains": []}), 404
        
        domains = []
        
        if "topology" in deployment:
            topology = deployment.get("topology", {})
            nodes = topology.get("nodes", [])
            
            # Extract unique domains from domain controller nodes
            for node in nodes:
                if node.get("type") == "domainController":
                    data_obj = node.get("data", {})
                    domain_name = data_obj.get("domainName")
                    dc_name = data_obj.get("domainControllerName")
                    is_sub = data_obj.get("isSub", False)
                    is_root = data_obj.get("isRoot", not is_sub)
                    
                    if domain_name and dc_name:
                        existing = next((d for d in domains if d["domainName"] == domain_name), None)
                        if not existing:
                            domains.append({
                                "domainName": domain_name,
                                "dcName": dc_name,
                                "isRoot": is_root
                            })
        else:
            # Fallback for non-topology deployments (scenario-based)
            root_domain = scenario_manager.get_parameter("rootDomainName", deploymentID)
            root_dc = scenario_manager.get_parameter("rootDCName", deploymentID)
            if root_domain and root_dc:
                domains.append({
                    "domainName": root_domain,
                    "dcName": root_dc,
                    "isRoot": True
                })
        
        # Sort domains: root domain first, then by name
        domains.sort(key=lambda x: (not x.get("isRoot", False), x.get("domainName", "")))
        
        deployment_config_apis_blueprint.logger.info(f"GET_DEPLOYMENT_DOMAINS: Found {len(domains)} domains for {deploymentID}")
        return jsonify({"message": "Success", "domains": domains}), 200
        
    except Exception as e:
        deployment_config_apis_blueprint.logger.error(f"GET_DEPLOYMENT_DOMAINS: Error: {str(e)}")
        return jsonify({"message": f"Error: {str(e)}", "domains": []}), 500


@deployment_config_apis_blueprint.route("/getDeploymentMachines", methods=["POST"])
def get_deployment_machines():
    """
    Get list of all machines from deployment topology.
    Returns machine names with their types (DC, workstation, standalone, CA) for attack targeting.
    """
    data = request.get_json()
    deploymentID = data.get("deploymentID")

    if not deploymentID:
        return jsonify({"message": "deploymentID is required", "machines": []}), 400

    try:
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)

        if "ERROR" in str(deployment):
            return jsonify({"message": "Deployment not found", "machines": []}), 404

        machines = []

        if "topology" in deployment:
            topology = deployment.get("topology", {})
            nodes = topology.get("nodes", [])

            # Extract machines from all node types
            for node in nodes:
                node_type = node.get("type")
                data_obj = node.get("data", {})

                if node_type == "domainController":
                    machine_name = data_obj.get("domainControllerName")
                    domain_name = data_obj.get("domainName")
                    is_sub = data_obj.get("isSub", False)
                    is_root = data_obj.get("isRoot", not is_sub)

                    if machine_name:
                        machines.append({
                            "machineName": machine_name,
                            "machineType": "DC",
                            "domainName": domain_name,
                            "isRoot": is_root,
                            "displayName": f"{machine_name} (DC - {domain_name})"
                        })

                elif node_type == "workstation":
                    machine_name = data_obj.get("workstationName")
                    domain_name = data_obj.get("domainName")

                    if machine_name:
                        machines.append({
                            "machineName": machine_name,
                            "machineType": "Workstation",
                            "domainName": domain_name,
                            "isRoot": False,
                            "displayName": f"{machine_name} (Workstation - {domain_name})"
                        })

                elif node_type == "standalone":
                    machine_name = data_obj.get("standaloneName")

                    if machine_name:
                        machines.append({
                            "machineName": machine_name,
                            "machineType": "Standalone",
                            "domainName": None,
                            "isRoot": False,
                            "displayName": f"{machine_name} (Standalone)"
                        })

                elif node_type == "certificateAuthority":
                    machine_name = data_obj.get("caName")
                    domain_name = data_obj.get("domainName")

                    if machine_name:
                        machines.append({
                            "machineName": machine_name,
                            "machineType": "CA",
                            "domainName": domain_name,
                            "isRoot": False,
                            "displayName": f"{machine_name} (CA - {domain_name})"
                        })
        else:
            # Fallback for non-topology deployments (scenario-based)
            root_dc = scenario_manager.get_parameter("rootDCName", deploymentID)
            root_domain = scenario_manager.get_parameter("rootDomainName", deploymentID)
            if root_dc:
                machines.append({
                    "machineName": root_dc,
                    "machineType": "DC",
                    "domainName": root_domain,
                    "isRoot": True,
                    "displayName": f"{root_dc} (DC - {root_domain})"
                })

        machines.sort(key=lambda x: (
            x.get("machineType") != "DC",  # DCs first
            not x.get("isRoot", False),    # Root DC first among DCs
            x.get("machineName", "")       # Then alphabetically
        ))

        deployment_config_apis_blueprint.logger.info(f"GET_DEPLOYMENT_MACHINES: Found {len(machines)} machines for {deploymentID}")
        return jsonify({"message": "Success", "machines": machines}), 200

    except Exception as e:
        deployment_config_apis_blueprint.logger.error(f"GET_DEPLOYMENT_MACHINES: Error: {str(e)}")
        return jsonify({"message": f"Error: {str(e)}", "machines": []}), 500


@deployment_config_apis_blueprint.route("/generateUsers", methods=["POST"])
def generate_users():
    data = request.get_json()
    deploymentID = data["deploymentID"]
    
    targetDomain = data.get("targetDomain")
    targetDC = data.get("targetDC")

    enterpriseAdminUsername = scenario_manager.get_parameter("enterpriseAdminUsername", deploymentID)
    domainAdminPassword = scenario_manager.get_parameter("enterpriseAdminPassword", deploymentID)
    rootDomainName = scenario_manager.get_parameter("rootDomainName", deploymentID)
    
    # Use target domain/DC if specified, otherwise use root domain
    domainName = targetDomain if targetDomain else rootDomainName
    dc = targetDC if targetDC else scenario_manager.get_parameter("rootDCName", deploymentID)

    # Construct username in UPN format (user@domain.fqdn) for AD authentication
    # UPN format is required for cross-domain operations as it uses DNS resolution
    # Always use root domain for the admin credentials
    domainAdminUsername = f"{enterpriseAdminUsername}@{rootDomainName}"

    deployment_config_apis_blueprint.logger.info(f"GENERATE_USERS: Constructed domainAdminUsername: '{domainAdminUsername}' (UPN format)")
    deployment_config_apis_blueprint.logger.info(f"GENERATE_USERS: Target domain: '{domainName}', Target DC: '{dc}'")

    try:
        compute_client = azure_clients.get_compute_client()

        script_dir = helpers.CONFIG_DIRECTORY
        execute_script_path = helpers.EXECUTE_MODULE_SCRIPT

        with open(execute_script_path, 'r') as f:
            execute_script = f.read()

        deployment_config_apis_blueprint.logger.info(f"GENERATE_USERS: Executing user generation on {dc}")
        execute_params = RunCommandInput(
            command_id='RunPowerShellScript',
            script=[execute_script],
            parameters=[
                RunCommandInputParameter(name='domainAdminUsername', value=domainAdminUsername),
                RunCommandInputParameter(name='domainAdminPassword', value=domainAdminPassword),
                RunCommandInputParameter(name='domainName', value=domainName),
                RunCommandInputParameter(name='attackSelection', value='generate-users')
            ]
        )

        poller = compute_client.virtual_machines.begin_run_command(
            resource_group_name=deploymentID,
            vm_name=dc,
            parameters=execute_params
        )
        result = poller.result()  # Wait for completion

        # Extract output from result
        output_messages = []
        if result.value:
            for item in result.value:
                if item.message:
                    output_messages.append(item.message)
        output = '\n'.join(output_messages)
        deployment_config_apis_blueprint.logger.info(f"GENERATE_USERS: Execution output: {output}")

        # Parse output to extract created usernames
        created_users = []
        for line in output.split('\n'):
            if 'Successfully created user:' in line:
                # Extract username from "GenerateUsers Function: Successfully created user: User1"
                username = line.split('Successfully created user:')[-1].strip()
                if username:
                    created_users.append(username)

        # Store created users in deployment metadata (with domain info)
        if created_users:
            try:
                deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)

                users_list = deployment.get('users', [])

                # Add new users with domain info (avoid duplicates)
                for username in created_users:
                    user_entry = {
                        'username': username,
                        'domain': domainName,
                        'dc': dc
                    }
                    
                    user_exists = False
                    for u in users_list:
                        if isinstance(u, dict):
                            if u.get('username') == username and u.get('domain') == domainName:
                                user_exists = True
                                break
                        elif u == username:
                            user_exists = True
                            break
                    
                    if not user_exists:
                        users_list.append(user_entry)

                deployment['users'] = users_list

                fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deploymentID)

                deployment_config_apis_blueprint.logger.info(f"GENERATE_USERS: Stored {len(created_users)} users in deployment metadata with domain info: {domainName}")
            except Exception as e:
                deployment_config_apis_blueprint.logger.error(f"GENERATE_USERS: Error storing users in metadata: {str(e)}")

        return jsonify({"message": "Users generation initiated successfully", "users": created_users, "domain": domainName}), 200
    except Exception as e:
        deployment_config_apis_blueprint.logger.error(f"GENERATE_USERS: Error generating users: {str(e)}")
        return jsonify({"message": f"Error generating users: {str(e)}"}), 500


@deployment_config_apis_blueprint.route("/generateRandomUsers", methods=["POST"])
def generate_random_users():
    data = request.get_json()
    deploymentID = data["deploymentID"]
    numberOfUsers = int(data['numberOfUsers'])
    usernameFormat = data.get('usernameFormat', 'firstname')  # New parameter: 'firstname', 'firstname.lastname', 'firstinitial.lastname'
    
    targetDomain = data.get("targetDomain")
    targetDC = data.get("targetDC")

    enterpriseAdminUsername = scenario_manager.get_parameter("enterpriseAdminUsername", deploymentID)
    domainAdminPassword = scenario_manager.get_parameter("enterpriseAdminPassword", deploymentID)
    rootDomainName = scenario_manager.get_parameter("rootDomainName", deploymentID)
    
    # Use target domain/DC if specified, otherwise use root domain
    domainName = targetDomain if targetDomain else rootDomainName
    dc = targetDC if targetDC else scenario_manager.get_parameter("rootDCName", deploymentID)

    # Construct username in UPN format (user@domain.fqdn) for AD authentication
    # Always use root domain for the admin credentials
    domainAdminUsername = f"{enterpriseAdminUsername}@{rootDomainName}"
    
    deployment_config_apis_blueprint.logger.info(f"GENERATE_RANDOM_USERS: Target domain: '{domainName}', Target DC: '{dc}', Format: '{usernameFormat}'")

    try:
        compute_client = azure_clients.get_compute_client()

        script_dir = helpers.CONFIG_DIRECTORY
        execute_script_path = helpers.EXECUTE_MODULE_SCRIPT
        module_script_path = helpers.ADVULN_MODULE_SCRIPT

        with open(execute_script_path, 'r') as f:
            execute_script = f.read()
        
        with open(module_script_path, 'r', encoding='utf-8') as f:
            module_script = f.read()

        wrapper_script = f"""param(
    [string]$domainAdminUsername,
    [string]$domainAdminPassword,
    [string]$domainName,
    [string]$numberOfUsers,
    [string]$usernameFormat,
    [string]$attackSelection
)

$modulePath = "C:\\Temp\\ADVulnEnvModule\\ADVulnEnvModule.psm1"
$moduleDir = "C:\\Temp\\ADVulnEnvModule"
$logFilePath = "C:\\Temp\\logfile.txt"

Add-Content -Path $logFilePath -Value "=== Updating ADVulnEnvModule.psm1 with latest version ==="

if (-not (Test-Path $moduleDir)) {{
    New-Item -ItemType Directory -Path $moduleDir -Force | Out-Null
}}

$moduleContent = @'
{module_script}
'@

Set-Content -Path $modulePath -Value $moduleContent -Force -Encoding UTF8
Add-Content -Path $logFilePath -Value "Module updated successfully at $modulePath"

$executeScriptPath = "C:\\Temp\\ExecuteModule.ps1"
$executeScriptContent = @'
{execute_script}
'@

Set-Content -Path $executeScriptPath -Value $executeScriptContent -Force -Encoding UTF8

& $executeScriptPath -domainAdminUsername $domainAdminUsername -domainAdminPassword $domainAdminPassword -domainName $domainName -numberOfUsers $numberOfUsers -usernameFormat $usernameFormat -attackSelection $attackSelection
"""

        deployment_config_apis_blueprint.logger.info(f"GENERATE_RANDOM_USERS: Executing random user generation on {dc}")
        execute_params = RunCommandInput(
            command_id='RunPowerShellScript',
            script=[wrapper_script],
            parameters=[
                RunCommandInputParameter(name='domainAdminUsername', value=domainAdminUsername),
                RunCommandInputParameter(name='domainAdminPassword', value=domainAdminPassword),
                RunCommandInputParameter(name='domainName', value=domainName),
                RunCommandInputParameter(name='numberOfUsers', value=str(numberOfUsers)),
                RunCommandInputParameter(name='usernameFormat', value=usernameFormat),
                RunCommandInputParameter(name='attackSelection', value='generate-random-users')
            ]
        )

        poller = compute_client.virtual_machines.begin_run_command(
            resource_group_name=deploymentID,
            vm_name=dc,
            parameters=execute_params
        )
        result = poller.result()

        # Extract output
        output_messages = []
        if result.value:
            for item in result.value:
                if item.message:
                    output_messages.append(item.message)
        output = '\n'.join(output_messages)
        deployment_config_apis_blueprint.logger.info(f"GENERATE_RANDOM_USERS: Execution output: {output}")

        # Parse output to extract created usernames (similar to generateUsers)
        created_users = []
        for line in output.split('\n'):
            if 'Successfully created user:' in line:
                username = line.split('Successfully created user:')[-1].strip()
                if username:
                    created_users.append(username)

        # Store created users in deployment metadata (with domain info)
        if created_users:
            try:
                deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
                users_list = deployment.get('users', [])

                for username in created_users:
                    user_entry = {
                        'username': username,
                        'domain': domainName,
                        'dc': dc
                    }
                    
                    user_exists = False
                    for u in users_list:
                        if isinstance(u, dict):
                            if u.get('username') == username and u.get('domain') == domainName:
                                user_exists = True
                                break
                        elif u == username:
                            user_exists = True
                            break
                    
                    if not user_exists:
                        users_list.append(user_entry)

                deployment['users'] = users_list
                fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deploymentID)
                deployment_config_apis_blueprint.logger.info(f"GENERATE_RANDOM_USERS: Stored {len(created_users)} users in deployment metadata with domain info: {domainName}")
            except Exception as e:
                deployment_config_apis_blueprint.logger.error(f"GENERATE_RANDOM_USERS: Error storing users in metadata: {str(e)}")

        return jsonify({"message": "Users generation initiated successfully", "users": created_users}), 200
    except Exception as e:
        deployment_config_apis_blueprint.logger.error(f"GENERATE_RANDOM_USERS: Error generating users: {str(e)}")
        return jsonify({"message": f"Error generating random users: {str(e)}"}), 500


@deployment_config_apis_blueprint.route("/createFixedCTF1", methods=["POST"])
def create_fixed_ctf1():
    data = request.get_json()
    deploymentID = data["deploymentID"]
    targetBox = data["targetBox"]

    enterpriseAdminUsername = scenario_manager.get_parameter("enterpriseAdminUsername", deploymentID)
    domainAdminPassword = scenario_manager.get_parameter("enterpriseAdminPassword", deploymentID)
    domainName = scenario_manager.get_parameter("rootDomainName", deploymentID)
    dc = scenario_manager.get_parameter("rootDCName", deploymentID)

    # Construct username in UPN format (user@domain.fqdn) for AD authentication
    domainAdminUsername = f"{enterpriseAdminUsername}@{domainName}"

    try:
        compute_client = azure_clients.get_compute_client()

        script_dir = helpers.CONFIG_DIRECTORY
        download_script_path = helpers.DOWNLOAD_FILES_SCRIPT
        execute_script_path = helpers.EXECUTE_MODULE_SCRIPT

        with open(download_script_path, 'r') as f:
            download_script = f.read()

        with open(execute_script_path, 'r') as f:
            execute_script = f.read()

        deployment_config_apis_blueprint.logger.info(f"create_fixed_ctf1: Running download tools command on {targetBox}")
        download_tools_params = RunCommandInput(
            command_id='RunPowerShellScript',
            script=[download_script],
            parameters=[
                RunCommandInputParameter(name='targetFiles', value='tools'),
                RunCommandInputParameter(name='targetBox', value=targetBox),
                RunCommandInputParameter(name='domainAdminUsername', value=domainAdminUsername),
                RunCommandInputParameter(name='domainAdminPassword', value=domainAdminPassword)
            ]
        )

        poller1 = compute_client.virtual_machines.begin_run_command(
            resource_group_name=deploymentID,
            vm_name=targetBox,
            parameters=download_tools_params
        )
        result1 = poller1.result()

        output1_messages = []
        if result1.value:
            for item in result1.value:
                if item.message:
                    output1_messages.append(item.message)
        output1 = '\n'.join(output1_messages)
        deployment_config_apis_blueprint.logger.info(f"create_fixed_ctf1: Download tools output: {output1}")

        deployment_config_apis_blueprint.logger.info(f"create_fixed_ctf1: Running execute command on {targetBox}")
        execute_params = RunCommandInput(
            command_id='RunPowerShellScript',
            script=[execute_script],
            parameters=[
                RunCommandInputParameter(name='domainAdminUsername', value=domainAdminUsername),
                RunCommandInputParameter(name='domainAdminPassword', value=domainAdminPassword),
                RunCommandInputParameter(name='domainName', value=domainName),
                RunCommandInputParameter(name='targetUser', value='EntryUser'),
                RunCommandInputParameter(name='computerForCDelegation', value=targetBox),
                RunCommandInputParameter(name='dcName', value=dc),
                RunCommandInputParameter(name='attackSelection', value='fixed-ctf1')
            ]
        )

        poller2 = compute_client.virtual_machines.begin_run_command(
            resource_group_name=deploymentID,
            vm_name=targetBox,
            parameters=execute_params
        )
        result2 = poller2.result()

        output2_messages = []
        if result2.value:
            for item in result2.value:
                if item.message:
                    output2_messages.append(item.message)
        output2 = '\n'.join(output2_messages)
        deployment_config_apis_blueprint.logger.info(f"create_fixed_ctf1: Execution output: {output2}")

        return jsonify({"message": "Created CTF1"}), 200
    except Exception as e:
        deployment_config_apis_blueprint.logger.error(f"create_fixed_ctf1: Error generating user: {str(e)}")
        return jsonify({"message": f"Error creating fixed ctf1: {str(e)}"}), 500


@deployment_config_apis_blueprint.route("/createRandomCTF", methods=["POST"])
def create_random_ctf():
    data = request.get_json()
    deploymentID = data["deploymentID"]
    targetBox = data["targetBox"]
    numberOfUsers = int(data['numberOfUsers'])
    difficulty = data["difficulty"]

    enterpriseAdminUsername = scenario_manager.get_parameter("enterpriseAdminUsername", deploymentID)
    domainAdminPassword = scenario_manager.get_parameter("enterpriseAdminPassword", deploymentID)
    domainName = scenario_manager.get_parameter("rootDomainName", deploymentID)
    dc = scenario_manager.get_parameter("rootDCName", deploymentID)

    # Construct username in UPN format (user@domain.fqdn) for AD authentication
    domainAdminUsername = f"{enterpriseAdminUsername}@{domainName}"

    try:
        compute_client = azure_clients.get_compute_client()

        script_dir = helpers.CONFIG_DIRECTORY
        download_script_path = helpers.DOWNLOAD_FILES_SCRIPT
        execute_script_path = helpers.EXECUTE_MODULE_SCRIPT

        with open(download_script_path, 'r') as f:
            download_script = f.read()

        with open(execute_script_path, 'r') as f:
            execute_script = f.read()

        deployment_config_apis_blueprint.logger.info(f"create_random_ctf: Running download tools command on {targetBox}")
        download_tools_params = RunCommandInput(
            command_id='RunPowerShellScript',
            script=[download_script],
            parameters=[
                RunCommandInputParameter(name='targetFiles', value='tools'),
                RunCommandInputParameter(name='targetBox', value=targetBox),
                RunCommandInputParameter(name='domainAdminUsername', value=domainAdminUsername),
                RunCommandInputParameter(name='domainAdminPassword', value=domainAdminPassword)
            ]
        )

        poller1 = compute_client.virtual_machines.begin_run_command(
            resource_group_name=deploymentID,
            vm_name=targetBox,
            parameters=download_tools_params
        )
        result1 = poller1.result()

        output1_messages = []
        if result1.value:
            for item in result1.value:
                if item.message:
                    output1_messages.append(item.message)
        output1 = '\n'.join(output1_messages)
        deployment_config_apis_blueprint.logger.info(f"create_random_ctf: Download tools output: {output1}")

        deployment_config_apis_blueprint.logger.info(f"create_random_ctf: Running execute command on {targetBox}")
        execute_params = RunCommandInput(
            command_id='RunPowerShellScript',
            script=[execute_script],
            parameters=[
                RunCommandInputParameter(name='domainAdminUsername', value=domainAdminUsername),
                RunCommandInputParameter(name='domainAdminPassword', value=domainAdminPassword),
                RunCommandInputParameter(name='domainName', value=domainName),
                RunCommandInputParameter(name='targetUser', value='EntryUser'),
                RunCommandInputParameter(name='computerForCDelegation', value=targetBox),
                RunCommandInputParameter(name='dcName', value=dc),
                RunCommandInputParameter(name='numberOfUsers', value=str(numberOfUsers)),
                RunCommandInputParameter(name='difficulty', value=difficulty),
                RunCommandInputParameter(name='attackSelection', value='random-ctf')
            ]
        )

        poller2 = compute_client.virtual_machines.begin_run_command(
            resource_group_name=deploymentID,
            vm_name=targetBox,
            parameters=execute_params
        )
        result2 = poller2.result()

        output2_messages = []
        if result2.value:
            for item in result2.value:
                if item.message:
                    output2_messages.append(item.message)
        output2 = '\n'.join(output2_messages)
        deployment_config_apis_blueprint.logger.info(f"create_random_ctf: Execution output: {output2}")

        return jsonify({"message": "Created random CTF"}), 200
    except Exception as e:
        deployment_config_apis_blueprint.logger.error(f"create_random_ctf: Error: {str(e)}")
        return jsonify({"message": f"Error create_random_ctf: {str(e)}"}), 500

@deployment_config_apis_blueprint.route("/createSingleUser", methods=["POST"])
def create_single_user():
    data = request.get_json()
    deploymentID = data["deploymentID"]
    singleUsername = data["singleUsername"]
    singleUserPassword = data["singleUserPassword"]
    
    targetDomain = data.get("targetDomain")
    targetDC = data.get("targetDC")

    enterpriseAdminUsername = scenario_manager.get_parameter("enterpriseAdminUsername", deploymentID)
    domainAdminPassword = scenario_manager.get_parameter("enterpriseAdminPassword", deploymentID)
    rootDomainName = scenario_manager.get_parameter("rootDomainName", deploymentID)
    
    # Use target domain/DC if specified, otherwise use root domain
    domainName = targetDomain if targetDomain else rootDomainName
    dc = targetDC if targetDC else scenario_manager.get_parameter("rootDCName", deploymentID)

    # Construct username in UPN format (user@domain.fqdn) for AD authentication
    # Always use root domain for the admin credentials
    domainAdminUsername = f"{enterpriseAdminUsername}@{rootDomainName}"
    
    deployment_config_apis_blueprint.logger.info(f"CREATE_SINGLE_USER: Target domain: '{domainName}', Target DC: '{dc}'")

    try:
        compute_client = azure_clients.get_compute_client()

        script_dir = helpers.CONFIG_DIRECTORY
        execute_script_path = helpers.EXECUTE_MODULE_SCRIPT

        with open(execute_script_path, 'r') as f:
            execute_script = f.read()

        deployment_config_apis_blueprint.logger.info(f"CREATE_SINGLE_USER: Running execute command on {dc}")
        execute_params = RunCommandInput(
            command_id='RunPowerShellScript',
            script=[execute_script],
            parameters=[
                RunCommandInputParameter(name='domainAdminUsername', value=domainAdminUsername),
                RunCommandInputParameter(name='domainAdminPassword', value=domainAdminPassword),
                RunCommandInputParameter(name='domainName', value=domainName),
                RunCommandInputParameter(name='singleUsername', value=singleUsername),
                RunCommandInputParameter(name='singleUserPassword', value=singleUserPassword),
                RunCommandInputParameter(name='attackSelection', value='create-single-user')
            ]
        )

        poller = compute_client.virtual_machines.begin_run_command(
            resource_group_name=deploymentID,
            vm_name=dc,
            parameters=execute_params
        )
        result = poller.result()

        # Extract output
        output_messages = []
        if result.value:
            for item in result.value:
                if item.message:
                    output_messages.append(item.message)
        output = '\n'.join(output_messages)
        deployment_config_apis_blueprint.logger.info(f"CREATE_SINGLE_USER: Execution output: {output}")

        if 'Successfully created user:' in output and singleUsername in output:
            try:
                deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)

                users_list = deployment.get('users', [])

                # Store user with domain info (new format: list of dicts)
                user_entry = {
                    'username': singleUsername,
                    'domain': domainName,
                    'dc': dc
                }
                
                user_exists = False
                for u in users_list:
                    if isinstance(u, dict):
                        if u.get('username') == singleUsername and u.get('domain') == domainName:
                            user_exists = True
                            break
                    elif u == singleUsername:
                        user_exists = True
                        break
                
                if not user_exists:
                    users_list.append(user_entry)

                deployment['users'] = users_list

                fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deploymentID)

                deployment_config_apis_blueprint.logger.info(f"CREATE_SINGLE_USER: Stored user '{singleUsername}@{domainName}' in deployment metadata")
            except Exception as e:
                deployment_config_apis_blueprint.logger.error(f"CREATE_SINGLE_USER: Error storing user in metadata: {str(e)}")

        return jsonify({"message": "Single user creation initiated successfully", "user": singleUsername, "domain": domainName}), 200
    except Exception as e:
        deployment_config_apis_blueprint.logger.error(f"CREATE_SINGLE_USER: Error creating single user: {str(e)}")
        return jsonify({"message": f"Error creating single user: {str(e)}"}), 500

