from flask import Blueprint, request, jsonify
from azure_clients import AzureClients
from deployments import Deployments
import helpers
import fs_manager
from scenario_manager import ScenarioManager
import logging
import re

user_sync_apis_blueprint = Blueprint('user_sync_apis', __name__)
azure_clients = AzureClients()
deployment_handler = Deployments()
scenario_manager = ScenarioManager()
user_sync_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)


def _parse_get_aduser_output(output: str, domain: str, dc: str) -> list:
    """
    Parse Get-ADUser PowerShell output to extract usernames.
    Filters out built-in accounts.
    """
    users = []
    
    builtin_accounts = {
        'administrator', 'guest', 'krbtgt', 'defaultaccount',
        'wdagutilityaccount', 'health mailbox', 'systemmailbox',
        'discovery search mailbox', 'migration', 'federatedemail'
    }
    
    # Extract usernames from output
    lines = output.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Try to extract from "SamAccountName : username" format
        match = re.search(r'SamAccountName\s*:\s*(\S+)', line, re.IGNORECASE)
        if match:
            username = match.group(1).strip()
        elif re.match(r'^[a-zA-Z0-9_\-\.]+$', line):
            username = line
        else:
            continue
        
        if username.lower() not in builtin_accounts:
            users.append({
                "username": username,
                "domain": domain,
                "dc": dc
            })
    
    return users


@user_sync_apis_blueprint.route("/syncUsers", methods=["POST"])
def sync_users():
    """
    Dynamically query all DCs in the deployment to fetch live user lists.
    Filters out built-in accounts and returns fresh user data.
    """
    try:
        data = request.get_json()
        deployment_id = data.get("deploymentID")
        
        if not deployment_id:
            return jsonify({"error": "Missing deploymentID"}), 400
        
        user_sync_apis_blueprint.logger.info(f"SYNC_USERS: Syncing users for deployment {deployment_id}")
        
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        if "ERROR" in deployment:
            return jsonify({"error": "Deployment not found"}), 404
        
        topology = deployment.get("topology", {})
        nodes = topology.get("nodes", [])
        
        # Find all domain controllers
        domain_controllers = []
        for node in nodes:
            if node.get("type") == "domainController":
                node_data = node.get("data", {})
                dc_name = node_data.get("domainControllerName", "")
                domain_name = node_data.get("domainName", "")
                if dc_name and domain_name:
                    domain_controllers.append({
                        "dc": dc_name,
                        "domain": domain_name
                    })
        
        if not domain_controllers:
            user_sync_apis_blueprint.logger.warning(f"SYNC_USERS: No domain controllers found in topology for {deployment_id}")
            return jsonify({"users": [], "message": "No domain controllers found"}), 200
        
        user_sync_apis_blueprint.logger.info(f"SYNC_USERS: Found {len(domain_controllers)} domain controllers")
        
        enterprise_admin_username = scenario_manager.get_parameter("enterpriseAdminUsername", deployment_id)
        enterprise_admin_password = scenario_manager.get_parameter("enterpriseAdminPassword", deployment_id)
        
        if not enterprise_admin_username or not enterprise_admin_password:
            return jsonify({"error": "Missing domain admin credentials"}), 400
        
        all_users = []
        compute_client = azure_clients.get_compute_client()
        
        for dc_info in domain_controllers:
            dc_name = dc_info["dc"]
            domain_name = dc_info["domain"]
            
            user_sync_apis_blueprint.logger.info(f"SYNC_USERS: Querying {dc_name} for users in domain {domain_name}")
            
            # Use enterprise admin credentials formatted as UPN for the root domain
            root_domain = scenario_manager.get_parameter("rootDomainName", deployment_id)
            admin_upn = f"{enterprise_admin_username}@{root_domain}" if root_domain else enterprise_admin_username
            
            script = f"""
$ErrorActionPreference = "Continue"

$password = ConvertTo-SecureString '{enterprise_admin_password}' -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential('{admin_upn}', $password)

try {{
    $users = Get-ADUser -Filter * -Credential $credential -Server {domain_name} -Properties SamAccountName | 
             Where-Object {{ 
                 $_.SamAccountName -notin @('Administrator', 'Guest', 'krbtgt', 'DefaultAccount', 'WDAGUtilityAccount') -and
                 $_.SamAccountName -notlike 'HealthMailbox*' -and
                 $_.SamAccountName -notlike 'SystemMailbox*'
             }} | 
             Select-Object -ExpandProperty SamAccountName
    
    Write-Output "=== USERS START ==="
    foreach ($user in $users) {{
        Write-Output $user
    }}
    Write-Output "=== USERS END ==="
}} catch {{
    Write-Output "ERROR: $_"
}}
"""
            
            try:
                from azure.mgmt.compute.models import RunCommandInput
                
                execute_params = RunCommandInput(
                    command_id='RunPowerShellScript',
                    script=[script]
                )
                
                poller = compute_client.virtual_machines.begin_run_command(
                    resource_group_name=deployment_id,
                    vm_name=dc_name,
                    parameters=execute_params
                )
                result = poller.result()
                
                # Parse output
                output_messages = []
                if result.value:
                    for item in result.value:
                        if item.message:
                            output_messages.append(item.message)
                
                full_output = "\n".join(output_messages)
                user_sync_apis_blueprint.logger.debug(f"SYNC_USERS: Raw output from {dc_name}:\n{full_output}")
                
                # Extract users from output (between markers)
                user_section = re.search(r'=== USERS START ===\s*\n(.*?)\n=== USERS END ===', full_output, re.DOTALL)
                if user_section:
                    user_lines = user_section.group(1).strip()
                    for line in user_lines.split('\n'):
                        line = line.strip()
                        if line and not line.startswith('ERROR'):
                            all_users.append({
                                "username": line,
                                "domain": domain_name,
                                "dc": dc_name
                            })
                
                user_sync_apis_blueprint.logger.info(f"SYNC_USERS: Found {len([u for u in all_users if u['dc'] == dc_name])} users on {dc_name}")
                
            except Exception as dc_error:
                user_sync_apis_blueprint.logger.error(f"SYNC_USERS: Error querying {dc_name}: {str(dc_error)}")
                continue
        
        user_sync_apis_blueprint.logger.info(f"SYNC_USERS: Total users found: {len(all_users)}")
        
        deployment["users"] = all_users
        fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        
        return jsonify({
            "users": all_users,
            "message": f"Successfully synced {len(all_users)} users from {len(domain_controllers)} domain controllers"
        }), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        user_sync_apis_blueprint.logger.error(f"SYNC_USERS: Error syncing users: {str(e)}")
        user_sync_apis_blueprint.logger.error(f"SYNC_USERS: Full traceback:\n{error_trace}")
        return jsonify({"error": f"Error syncing users: {str(e)}"}), 500
