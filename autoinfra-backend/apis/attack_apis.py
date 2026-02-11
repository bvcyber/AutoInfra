from flask import Blueprint, request, jsonify
from azure_clients import AzureClients
import json
from azure_setup import AzureSetup
from deployments import Deployments
import helpers
import fs_manager
import command_runner
from scenario_manager import ScenarioManager
import logging
import os
from azure.mgmt.compute.models import RunCommandInput, RunCommandInputParameter

attack_apis_blueprint = Blueprint('attack_apis', __name__)
azure_clients = AzureClients()
deployment_handler = Deployments()
azure_setup = AzureSetup()
scenario_manager = ScenarioManager()
attack_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)


@attack_apis_blueprint.route("/listAttacks", methods=["GET","POST"])
def list_attacks():
    attacks = fs_manager.load_file(helpers.CONFIG_DIRECTORY, "attacks.json")
    if request.method == "POST":
        try:
            data = json.loads(request.data.decode("utf-8"))
            attack_apis_blueprint.logger.debug(f"LIST_ATTACKS: Data is {data}")
            deploymentID = data["deploymentId"]

            deploymentInfo = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
            if "ERROR" in deploymentInfo:
                attack_apis_blueprint.logger.error(f"LIST_ATTACKS: Could not load deployment {deploymentID}. File not found.")
                return jsonify({"message": {}})

            deployed_machine_types = helpers.get_deployed_machine_types(deploymentID)
            attack_apis_blueprint.logger.info(f"LIST_ATTACKS: Deployed machine types for {deploymentID}: {deployed_machine_types}")

            applicable_attacks = {}
            for _, attack_dict in attacks.items():
                for attack_key, attack_value in attack_dict.items():
                    required_types = attack_value.get("requiredMachineTypes", [])

                    if not required_types:
                        attack_apis_blueprint.logger.warning(f"LIST_ATTACKS: Attack {attack_key} has no requiredMachineTypes defined")
                        continue

                    if any(machine_type in deployed_machine_types for machine_type in required_types):
                        applicable_attacks[attack_key] = attack_value
                        attack_apis_blueprint.logger.debug(f"LIST_ATTACKS: Attack {attack_key} is applicable (requires {required_types}, found {deployed_machine_types & set(required_types)})")
                    else:
                        attack_apis_blueprint.logger.debug(f"LIST_ATTACKS: Attack {attack_key} not applicable (requires {required_types}, deployed: {deployed_machine_types})")

            attack_apis_blueprint.logger.info(f"LIST_ATTACKS: Returning {len(applicable_attacks)} applicable attacks for {deploymentID}")
            return jsonify({"message": applicable_attacks})

        except Exception as e:
            attack_apis_blueprint.logger.error(f"LIST_ATTACKS: Error processing request: {str(e)}")
            return jsonify({"message": f"Error: {str(e)}"}), 400
    elif request.method == "GET":
        return jsonify({"message": attacks})
    else:
        return jsonify({"message": "Method Not Allowed"}), 405
    

@attack_apis_blueprint.route("/listEnabledAttacks", methods=["POST"])
def list_enabled_attacks():
    deploymentID = request.data.decode("utf-8")

    try:
        deploymentInfo = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)

        enabledAttacks = deploymentInfo.get("enabledAttacks", {})
        attacksInProgress = deploymentInfo.get("attacksInProgress", {})
        attacks = fs_manager.load_file(helpers.CONFIG_DIRECTORY, "attacks.json")

        enabledAttacksInfo = {}
        for attack_type, instances in enabledAttacks.items():
            attack_def = None
            for _, attack_dict in attacks.items():
                if attack_type in attack_dict:
                    attack_def = attack_dict[attack_type]
                    break

            if attack_def:
                enabledAttacksInfo[attack_type] = {
                    **attack_def,
                    "instances": instances  # Include list of instances with targets
                }

        inProgressAttacksInfo = {}
        for attack_type, instances in attacksInProgress.items():
            attack_def = None
            for _, attack_dict in attacks.items():
                if attack_type in attack_dict:
                    attack_def = attack_dict[attack_type]
                    break

            if attack_def:
                inProgressAttacksInfo[attack_type] = {
                    **attack_def,
                    "instances": instances  # Include list of instances with targets
                }

        attack_apis_blueprint.logger.info(f"LIST_ENABLED_ATTACKS: Found {len(enabledAttacksInfo)} enabled and {len(inProgressAttacksInfo)} in-progress attacks for {deploymentID}")

        return jsonify({
            "enabled": enabledAttacksInfo,
            "inProgress": inProgressAttacksInfo
        })

    except Exception as e:
        attack_apis_blueprint.logger.error(f"LIST_ENABLED_ATTACKS: Error getting enabled attacks: {str(e)}")
        return jsonify({"enabled": {}, "inProgress": {}})  # Return empty objects instead of error

@attack_apis_blueprint.route("/enableAttacks", methods=["POST"])
def enable_attacks():
    data = json.loads(request.data.decode("utf-8"))
    deploymentID = data["deploymentid"]

    attack_inputs = data.get("attackInputs", {})
    target_box_inputs = attack_inputs.get("targetBox", {})
    target_user_inputs = attack_inputs.get("targetUser", {})
    single_user_password_inputs = attack_inputs.get("singleUserPassword", {})
    granting_user_inputs = attack_inputs.get("grantingUser", {})
    receiving_user_inputs = attack_inputs.get("receivingUser", {})

    enterpriseAdminUsername = scenario_manager.get_parameter("enterpriseAdminUsername", deploymentID)
    domainAdminPassword = scenario_manager.get_parameter("enterpriseAdminPassword", deploymentID)
    rootDomainName = scenario_manager.get_parameter("rootDomainName", deploymentID)
    rootDC = scenario_manager.get_parameter("rootDCName", deploymentID)

    # Construct username in UPN format (user@domain.fqdn) for AD authentication
    # Always use root domain for Enterprise Admin credentials
    domainAdminUsername = f"{enterpriseAdminUsername}@{rootDomainName}"

    deploymentInfo = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
    
    # Build domain-to-DC mapping from topology for multi-domain support
    domain_to_dc = {}
    topology = deploymentInfo.get("topology", {})
    for node in topology.get("nodes", []):
        if node.get("type") == "domainController":
            node_data = node.get("data", {})
            domain_name = node_data.get("domainName", "").lower()
            dc_name = node_data.get("domainControllerName", node_data.get("name", ""))
            if domain_name and dc_name:
                domain_to_dc[domain_name] = dc_name
    
    # Fallback to root domain if no mapping found
    if not domain_to_dc:
        domain_to_dc[rootDomainName.lower()] = rootDC
    
    attack_apis_blueprint.logger.info(f"ENABLE_ATTACKS: Domain-to-DC mapping: {domain_to_dc}")
    
    # Build username-to-domain mapping from users list
    user_to_domain = {}
    users_list = deploymentInfo.get("users", [])
    for user in users_list:
        if isinstance(user, dict):
            username = user.get("username", "").lower()
            domain = user.get("domain", "").lower()
            dc = user.get("dc", "")
            if username:
                user_to_domain[username] = {"domain": domain, "dc": dc}
    
    attack_apis_blueprint.logger.info(f"ENABLE_ATTACKS: User-to-domain mapping has {len(user_to_domain)} entries")

    if "enabledAttacks" not in deploymentInfo:
        deploymentInfo["enabledAttacks"] = {}
    if "attacksInProgress" not in deploymentInfo:
        deploymentInfo["attacksInProgress"] = {}

    attacksToEnable = [key for key, value in data["checkboxes"].items() if value]

    enabledAttacks = deploymentInfo.get("enabledAttacks", {})
    attacksInProgressCheck = deploymentInfo.get("attacksInProgress", {})

    for attack in attacksToEnable:
        targetUser = target_user_inputs.get(attack, "")
        targetBox = target_box_inputs.get(attack, "")
        singleUserPassword = single_user_password_inputs.get(attack, "")
        grantingUser = granting_user_inputs.get(attack, "")
        receivingUser = receiving_user_inputs.get(attack, "")
        
        # Parse UPN format for targetUser (username@domain)
        targetUserUsername = targetUser  # For passing to attack scripts
        targetUserDomain = ""
        if targetUser and "@" in targetUser:
            parts = targetUser.split("@", 1)
            targetUserUsername = parts[0]
            targetUserDomain = parts[1]
        
        # Parse UPN format for grantingUser
        grantingUserUsername = grantingUser
        grantingUserDomain = ""
        if grantingUser and "@" in grantingUser:
            parts = grantingUser.split("@", 1)
            grantingUserUsername = parts[0]
            grantingUserDomain = parts[1]
            
        # Parse UPN format for receivingUser
        receivingUserUsername = receivingUser
        receivingUserDomain = ""
        if receivingUser and "@" in receivingUser:
            parts = receivingUser.split("@", 1)
            receivingUserUsername = parts[0]
            receivingUserDomain = parts[1]

        if attack == "ACLs" and grantingUser and receivingUser:
            targetToCheck = f"{grantingUser} -> {receivingUser}"
        else:
            targetToCheck = targetUser or targetBox
        alreadyEnabled = False

        if attack in enabledAttacks:
            for instance in enabledAttacks[attack]:
                existingTarget = instance.get("targetUser") or instance.get("targetBox")
                if existingTarget == targetToCheck:
                    alreadyEnabled = True
                    attack_apis_blueprint.logger.info(f"ENABLE_ATTACKS: {attack} already enabled for {targetToCheck}, skipping")
                    break

        if not alreadyEnabled and attack in attacksInProgressCheck:
            for instance in attacksInProgressCheck[attack]:
                existingTarget = instance.get("targetUser") or instance.get("targetBox")
                if existingTarget == targetToCheck:
                    alreadyEnabled = True
                    attack_apis_blueprint.logger.info(f"ENABLE_ATTACKS: {attack} already in progress for {targetToCheck}, skipping")
                    break

        if alreadyEnabled:
            continue

        # Determine the correct domain and DC for this attack based on target user
        # Default to root domain/DC
        attackDomainName = rootDomainName
        attackDC = rootDC
        
        if targetUserDomain:
            attackDomainName = targetUserDomain
            # Look up DC for this domain
            if attackDomainName.lower() in domain_to_dc:
                attackDC = domain_to_dc[attackDomainName.lower()]
            attack_apis_blueprint.logger.info(
                f"ENABLE_ATTACKS: Using domain from UPN: '{targetUser}' -> domain='{attackDomainName}', dc='{attackDC}'"
            )
        # Fallback: Look up user's domain from user_to_domain mapping (legacy format)
        elif targetUserUsername:
            user_lower = targetUserUsername.lower()
            if user_lower in user_to_domain:
                user_info = user_to_domain[user_lower]
                attackDomainName = user_info.get("domain", rootDomainName)
                attackDC = user_info.get("dc", "")
                
                if not attackDC and attackDomainName.lower() in domain_to_dc:
                    attackDC = domain_to_dc[attackDomainName.lower()]
                
                attack_apis_blueprint.logger.info(
                    f"ENABLE_ATTACKS: User '{targetUserUsername}' found in domain '{attackDomainName}', using DC '{attackDC}'"
                )
            else:
                attack_apis_blueprint.logger.warning(
                    f"ENABLE_ATTACKS: User '{targetUserUsername}' not found in user mapping, using root domain"
                )
        
        if not attackDC:
            attackDC = rootDC

        attack_apis_blueprint.logger.info(f"ENABLE_ATTACKS: Starting attack {attack} on {deploymentID} for target {targetToCheck} (domain={attackDomainName}, dc={attackDC})")
        attack_resolver(attack, deploymentID, domainAdminUsername, domainAdminPassword, attackDomainName, attackDC, targetBox, targetUser, singleUserPassword, grantingUser, receivingUser)

    deploymentInfo = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)

    attack_operations = deploymentInfo.get("attackOperations", {})
    attacks_in_progress = deploymentInfo.get("attacksInProgress", {})

    for operation_id, op_info in attack_operations.items():
        if op_info.get("status") == "InProgress":
            attack_type = op_info.get("attackType")
            if attack_type:
                if attack_type not in attacks_in_progress:
                    attacks_in_progress[attack_type] = []

                instance_info = {
                    "operationId": operation_id,
                    "targetUser": op_info.get("targetUser"),
                    "targetBox": op_info.get("targetBox"),
                    "timestamp": op_info.get("timestamp")
                }

                if not any(inst.get("operationId") == operation_id for inst in attacks_in_progress[attack_type]):
                    attacks_in_progress[attack_type].append(instance_info)

    deploymentInfo["attacksInProgress"] = attacks_in_progress

    fs_manager.save_file(deploymentInfo, helpers.DEPLOYMENT_DIRECTORY, deploymentID)

    attack_apis_blueprint.logger.info(f"ENABLE_ATTACKS: All attacks started successfully (running in background)")

    return jsonify({"message": "Attack execution initiated successfully"}), 200

@attack_apis_blueprint.route("/checkAttackStatus", methods=["POST"])
def check_attack_status():
    """
    Check the status of running attack operations by polling Azure.
    When operations complete, moves them from attacksInProgress to enabledAttacks.
    Returns: {
        "attacksInProgress": [list of attack names],
        "enabledAttacks": [list of attack names],
        "operations": { attackName: { status, message } }
    }
    """
    try:
        data = json.loads(request.data.decode("utf-8"))
        deploymentID = data.get("deploymentId") or data.get("deploymentid")

        if not deploymentID:
            return jsonify({"error": "deploymentId is required"}), 400

        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
        if "ERROR" in deployment:
            return jsonify({"error": "Deployment not found"}), 404

        attack_operations = deployment.get("attackOperations", {})
        attacks_in_progress = deployment.get("attacksInProgress", {})
        enabled_attacks = deployment.get("enabledAttacks", {})

        if not attack_operations:
            return jsonify({
                "attacksInProgress": attacks_in_progress,
                "enabledAttacks": enabled_attacks,
                "operations": {}
            }), 200

        compute_client = azure_clients.get_compute_client()
        operations_status = {}
        needs_save = False

        for operation_id, op_info in list(attack_operations.items()):
            current_status = op_info.get("status", "Unknown")
            attack_type = op_info.get("attackType", "Unknown")

            if current_status in ["Succeeded", "Failed"]:
                operations_status[operation_id] = {
                    "status": current_status,
                    "message": op_info.get("message", ""),
                    "attackType": attack_type
                }
                continue

            try:
                vm_name = op_info.get("vmName")
                resource_group = op_info.get("resourceGroup")
                run_command_name = op_info.get("runCommandName")

                if not run_command_name:
                    attack_apis_blueprint.logger.error(f"CHECK_ATTACK_STATUS: No run command name found for {operation_id}")
                    operations_status[operation_id] = {
                        "status": "Unknown",
                        "message": "Missing run command name",
                        "attackType": attack_type
                    }
                    continue

                attack_apis_blueprint.logger.info(f"CHECK_ATTACK_STATUS: Querying run command '{run_command_name}' status for {attack_type}")

                run_command_info = compute_client.virtual_machine_run_commands.get_by_virtual_machine(
                    resource_group_name=resource_group,
                    vm_name=vm_name,
                    run_command_name=run_command_name,
                    expand="instanceView"  # Get execution details
                )

                provisioning_state = run_command_info.provisioning_state
                attack_apis_blueprint.logger.info(f"CHECK_ATTACK_STATUS: {attack_type} ({operation_id}) provisioning_state: {provisioning_state}")

                execution_state = None
                if run_command_info.instance_view:
                    execution_state = run_command_info.instance_view.execution_state
                    attack_apis_blueprint.logger.info(f"CHECK_ATTACK_STATUS: {attack_type} ({operation_id}) execution_state: {execution_state}")

                if provisioning_state == "Succeeded" and execution_state == "Succeeded":
                    attack_apis_blueprint.logger.info(f"CHECK_ATTACK_STATUS: {attack_type} ({operation_id}) completed successfully!")

                    attack_operations[operation_id]["status"] = "Succeeded"
                    attack_operations[operation_id]["message"] = "Attack enabled successfully"

                    instance_info = {
                        "operationId": operation_id,
                        "targetUser": op_info.get("targetUser"),
                        "targetBox": op_info.get("targetBox"),
                        "timestamp": op_info.get("timestamp")
                    }

                    if attack_type not in enabled_attacks:
                        enabled_attacks[attack_type] = []
                    enabled_attacks[attack_type].append(instance_info)

                    if attack_type in attacks_in_progress:
                        attacks_in_progress[attack_type] = [
                            inst for inst in attacks_in_progress[attack_type]
                            if inst.get("operationId") != operation_id
                        ]
                        if not attacks_in_progress[attack_type]:
                            del attacks_in_progress[attack_type]

                    needs_save = True

                    operations_status[operation_id] = {
                        "status": "Succeeded",
                        "message": "Attack enabled successfully",
                        "attackType": attack_type
                    }

                elif provisioning_state == "Failed" or execution_state == "Failed":
                    attack_apis_blueprint.logger.error(f"CHECK_ATTACK_STATUS: {attack_type} ({operation_id}) failed!")

                    attack_operations[operation_id]["status"] = "Failed"
                    error_msg = "Attack execution failed"
                    if run_command_info.instance_view and run_command_info.instance_view.error:
                        error_msg = run_command_info.instance_view.error

                    attack_operations[operation_id]["message"] = error_msg

                    if attack_type in attacks_in_progress:
                        attacks_in_progress[attack_type] = [
                            inst for inst in attacks_in_progress[attack_type]
                            if inst.get("operationId") != operation_id
                        ]
                        if not attacks_in_progress[attack_type]:
                            del attacks_in_progress[attack_type]

                    needs_save = True

                    operations_status[operation_id] = {
                        "status": "Failed",
                        "message": error_msg,
                        "attackType": attack_type
                    }

                else:
                    attack_apis_blueprint.logger.info(f"CHECK_ATTACK_STATUS: {attack_type} ({operation_id}) still in progress (prov: {provisioning_state}, exec: {execution_state})")
                    operations_status[operation_id] = {
                        "status": "InProgress",
                        "message": f"Attack running on {vm_name}",
                        "attackType": attack_type
                    }

            except Exception as e:
                attack_apis_blueprint.logger.error(f"CHECK_ATTACK_STATUS: Error checking {attack_type} ({operation_id}): {str(e)}")
                operations_status[operation_id] = {
                    "status": "InProgress",
                    "message": f"Still enabling on {op_info.get('vmName', 'VM')}",
                    "attackType": attack_type
                }

        if needs_save:
            deployment["attackOperations"] = attack_operations
            deployment["attacksInProgress"] = attacks_in_progress
            deployment["enabledAttacks"] = enabled_attacks
            fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deploymentID)
            attack_apis_blueprint.logger.info(f"CHECK_ATTACK_STATUS: Updated deployment {deploymentID} - moved completed attacks to enabled")

        return jsonify({
            "attacksInProgress": attacks_in_progress,
            "enabledAttacks": enabled_attacks,
            "operations": operations_status
        }), 200

    except Exception as e:
        attack_apis_blueprint.logger.error(f"CHECK_ATTACK_STATUS: Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def _execute_attack_on_vm(attack_name, vm_name, resource_group, script_params, deploymentID, target_user_display="", extra_fields=None):
    """
    Common logic for executing any attack on a VM via Azure run command.

    Args:
        attack_name: Name of the attack (e.g., "ESC1", "Kerberoasting")
        vm_name: Name of the VM to execute on
        resource_group: Azure resource group name
        script_params: List of script parameters for the attack
        deploymentID: Deployment ID
        target_user_display: Optional display string for targetUser field in attack operation
        extra_fields: Optional dict of additional fields to store in attackOperations

    Returns:
        run_command_name: The name of the run command operation
    """
    import time

    attack_apis_blueprint.logger.info(f"ATTACK_RESOLVER: Starting {attack_name} attack via SDK on {vm_name}")

    try:
        compute_client = azure_clients.get_compute_client()
        vm = compute_client.virtual_machines.get(resource_group, vm_name)

        script_dir = helpers.CONFIG_DIRECTORY
        execute_script_path = helpers.EXECUTE_MODULE_SCRIPT
        with open(execute_script_path, 'r') as f:
            execute_script = f.read()

        run_command_name = f"{attack_name}-{int(time.time())}"

        run_command = {
            "location": vm.location,
            "source": {"script": execute_script},
            "parameters": script_params,
            "async_execution": False,
            "timeout_in_seconds": helpers.RUN_COMMAND_TIMEOUT
        }

        compute_client.virtual_machine_run_commands.begin_create_or_update(
            resource_group_name=resource_group,
            vm_name=vm_name,
            run_command_name=run_command_name,
            run_command=run_command
        )

        attack_apis_blueprint.logger.info(f"ATTACK_RESOLVER: {attack_name} run command '{run_command_name}' created successfully")

        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
        if "attackOperations" not in deployment:
            deployment["attackOperations"] = {}

        operation_data = {
            "attackType": attack_name,
            "runCommandName": run_command_name,
            "status": "InProgress",
            "vmName": vm_name,
            "resourceGroup": resource_group,
            "targetUser": target_user_display,
            "timestamp": int(time.time())
        }

        if extra_fields:
            operation_data.update(extra_fields)

        deployment["attackOperations"][run_command_name] = operation_data
        fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deploymentID)

        return run_command_name

    except Exception as e:
        attack_apis_blueprint.logger.error(f"ATTACK_RESOLVER: Error executing {attack_name} via SDK: {str(e)}")
        raise

def attack_resolver(attack, deploymentID, domainAdminUsername, domainAdminPassword, domainName, dc, targetBox, targetUser, singleUserPassword, grantingUser="", receivingUser=""):
    attack_apis_blueprint.logger.debug(f"ATTACK_RESOLVER: Running attack resolver with parameters: attack={attack}, deploymentID={deploymentID}, domainAdminUsername={domainAdminUsername}, domainAdminPassword={domainAdminPassword}, domainName={domainName}, dc={dc}, targetUser={targetUser}, targetBox={targetBox}, singleUserPassword={singleUserPassword}, grantingUser={grantingUser}, receivingUser={receivingUser}")
    
    # Parse UPN format for users (username@domain) - extract just username for scripts
    targetUserForScript = targetUser
    if targetUser and "@" in targetUser:
        targetUserForScript = targetUser.split("@", 1)[0]
    
    grantingUserForScript = grantingUser
    if grantingUser and "@" in grantingUser:
        grantingUserForScript = grantingUser.split("@", 1)[0]
        
    receivingUserForScript = receivingUser
    if receivingUser and "@" in receivingUser:
        receivingUserForScript = receivingUser.split("@", 1)[0]
    
    try:
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deploymentID)
        resource_group = deployment.get("resourceGroup", deploymentID)
        attack_apis_blueprint.logger.debug(f"ATTACK_RESOLVER: Using resource group {resource_group} for deployment {deploymentID}")
    except Exception as e:
        resource_group = deploymentID
        attack_apis_blueprint.logger.error(f"ATTACK_RESOLVER: Error getting resource group for {deploymentID}, falling back to using deploymentID: {str(e)}")
    
    ca_name = scenario_manager.get_parameter("caName", deploymentID)  # e.g., "CA01"
    
    domain_admin_username = domainAdminUsername or scenario_manager.get_parameter("enterpriseAdminUsername", deploymentID)
    domain_admin_password = domainAdminPassword or scenario_manager.get_parameter("enterpriseAdminPassword", deploymentID)
    domain_name = domainName or scenario_manager.get_parameter("rootDomainName", deploymentID)

    if attack == "ESC1":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "attackSelection", "value": "esc1"}
        ]
        if targetUserForScript:
            script_params.append({"name": "targetUser", "value": targetUserForScript})

        _execute_attack_on_vm("ESC1", ca_name, resource_group, script_params, deploymentID, targetUser)

    elif attack == "ESC3":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "attackSelection", "value": "esc3"}
        ]
        if targetUser:
            script_params.append({"name": "targetUser", "value": targetUserForScript})

        _execute_attack_on_vm("ESC3", ca_name, resource_group, script_params, deploymentID, targetUser)

    elif attack == "ESC4":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "attackSelection", "value": "esc4"}
        ]
        if targetUser:
            script_params.append({"name": "targetUser", "value": targetUserForScript})

        _execute_attack_on_vm("ESC4", ca_name, resource_group, script_params, deploymentID, targetUser)

    elif attack == "Kerberoasting":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "attackSelection", "value": "kerberoast"}
        ]
        if targetUser:
            script_params.append({"name": "targetUser", "value": targetUserForScript})

        _execute_attack_on_vm("Kerberoasting", dc, resource_group, script_params, deploymentID, targetUser)

    elif attack == "ASREPRoasting":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "attackSelection", "value": "disable-preauth"}
        ]
        if targetUser:
            script_params.append({"name": "targetUser", "value": targetUserForScript})

        _execute_attack_on_vm("ASREPRoasting", dc, resource_group, script_params, deploymentID, targetUser)

    elif attack == "UserConstrainedDelegation":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "dcName", "value": dc},
            {"name": "attackSelection", "value": "update-user-for-constrained-delegation"}
        ]
        if targetUser:
            script_params.append({"name": "userForCDelegation", "value": targetUserForScript})

        _execute_attack_on_vm("UserConstrainedDelegation", dc, resource_group, script_params, deploymentID, targetUser)

    elif attack == "ComputerConstrainedDelegation":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "dcName", "value": dc},
            {"name": "attackSelection", "value": "update-computer-for-constrained-delegation"}
        ]
        if targetBox:
            script_params.append({"name": "computerForCDelegation", "value": targetBox})

        _execute_attack_on_vm("ComputerConstrainedDelegation", dc, resource_group, script_params, deploymentID, "", {"targetBox": targetBox})

    elif attack == "AddCredsForMimikatz":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "attackSelection", "value": "add-creds-for-mimikatz"}
        ]
        if targetBox:
            script_params.append({"name": "computerForMimikatz", "value": targetBox})
        if targetUser:
            script_params.append({"name": "userForMimikatz", "value": targetUserForScript})
        if singleUserPassword:
            script_params.append({"name": "singleUserPassword", "value": singleUserPassword})

        _execute_attack_on_vm("AddCredsForMimikatz", dc, resource_group, script_params, deploymentID, targetUser, {"targetBox": targetBox})

    elif attack == "LocalPrivesc1":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "attackSelection", "value": "local-privesc1"}
        ]
        if targetUser:
            script_params.append({"name": "targetUser", "value": targetUserForScript})

        _execute_attack_on_vm("LocalPrivesc1", dc, resource_group, script_params, deploymentID, targetUser)

    elif attack == "LocalPrivesc2":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "vulnerablePath", "value": "C:\\Program Files\\My Vulnerable App"},
            {"name": "attackSelection", "value": "local-privesc2"}
        ]
        if targetUser:
            script_params.append({"name": "targetUser", "value": targetUserForScript})

        _execute_attack_on_vm("LocalPrivesc2", dc, resource_group, script_params, deploymentID, targetUser)

    elif attack == "LocalPrivesc3":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "targetName", "value": "localhost"},
            {"name": "attackSelection", "value": "local-privesc3"}
        ]
        if targetUser:
            script_params.append({"name": "targetUser", "value": targetUserForScript})

        _execute_attack_on_vm("LocalPrivesc3", dc, resource_group, script_params, deploymentID, targetUser)

    elif attack == "ACLs":
        script_params = [
            {"name": "domainAdminUsername", "value": domain_admin_username},
            {"name": "domainAdminPassword", "value": domain_admin_password},
            {"name": "domainName", "value": domain_name},
            {"name": "attackSelection", "value": "acls"}
        ]
        if grantingUser:
            script_params.append({"name": "GrantingUser", "value": grantingUserForScript})
        if receivingUser:
            script_params.append({"name": "ReceivingUser", "value": receivingUserForScript})
        script_params.append({"name": "PermissionType", "value": "GenericAll"})

        target_user_display = f"{grantingUser} -> {receivingUser}" if grantingUser and receivingUser else "ACLs"
        _execute_attack_on_vm("ACLs", dc, resource_group, script_params, deploymentID, target_user_display)
    