"""
BloodHound Import API Endpoints for AutoInfra

Flow:
1. POST /bloodhound/upload - Upload and parse BloodHound zip
2. POST /bloodhound/generate-topology - Generate topology from parsed data  
3. POST /bloodhound/deploy - Start build deployment (returns deploymentID)
   - Frontend polls /getDeploymentStatus for completion
4. POST /bloodhound/configure-users - Create users after deployment is ready
5. POST /bloodhound/configure-attacks - Enable detected attacks
"""

import os
import json
import tempfile
import logging
import uuid
import re
import time
from datetime import datetime
from flask import Blueprint, request, jsonify

from bloodhound.parser import BloodHoundParser
from bloodhound.mapper import TopologyConfig, map_bloodhound_to_autoinfra
import helpers
import fs_manager
from scenario_manager import ScenarioManager
from azure_clients import AzureClients
from azure.mgmt.compute.models import RunCommandInput

bloodhound_apis_blueprint = Blueprint('bloodhound_apis', __name__)
bloodhound_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)

scenario_manager = ScenarioManager()
azure_clients = AzureClients()

ALLOWED_EXTENSIONS = {'zip'}


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def secure_filename(filename: str) -> str:
    """Simple filename sanitization."""
    filename = os.path.basename(filename)
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    return filename or 'upload.zip'


def _generate_batch_user_creation_script(users: list, domain_admin_upn: str, domain_admin_password: str, domain_name: str) -> str:
    """
    Generate a PowerShell script that creates multiple users in parallel within a single domain.
    
    This is much faster than running individual RunCommand calls for each user,
    as each RunCommand has significant overhead (~30s+ per call).
    
    Args:
        users: List of dicts with 'username' and 'password' keys
        domain_admin_upn: The UPN of the domain admin (e.g., 'adadmin@contoso.local')
        domain_admin_password: Password for domain admin
        domain_name: Target domain for user creation (e.g., 'contoso.local')
    
    Returns:
        PowerShell script string that creates all users
    """
    escaped_password = domain_admin_password.replace("'", "''").replace('"', '`"')
    escaped_admin_upn = domain_admin_upn.replace("'", "''")
    escaped_domain = domain_name.replace("'", "''")
    
    user_entries = []
    for user in users:
        username = user["username"].replace("'", "''")
        user_password = user.get("password", "Password#123").replace("'", "''")
        user_entries.append(f"@{{Username='{username}'; Password='{user_password}'}}")
    
    users_array = ",\n    ".join(user_entries)
    
    script = f'''
$ErrorActionPreference = "Continue"
$logFilePath = "C:\\Temp\\logfile.txt"

$adminPassword = ConvertTo-SecureString '{escaped_password}' -AsPlainText -Force
$domainAdminCreds = New-Object System.Management.Automation.PSCredential('{escaped_admin_upn}', $adminPassword)

# Target domain
$domainName = '{escaped_domain}'

$usersToCreate = @(
    {users_array}
)

Write-Output "Starting batch user creation for $($usersToCreate.Count) users on domain $domainName"
Add-Content -Path $logFilePath -Value "BatchUserCreation: Starting creation of $($usersToCreate.Count) users on $domainName"

$jobs = @()
foreach ($userInfo in $usersToCreate) {{
    $username = $userInfo.Username
    $userPassword = $userInfo.Password
    $upn = "$username@$domainName"
    $description = 'BloodHound Import User'
    
    try {{
        $existingUser = Get-ADUser -Filter "SamAccountName -eq '$username'" -Credential $domainAdminCreds -ErrorAction SilentlyContinue
        if ($existingUser) {{
            $msg = "User $username already exists in $domainName"
            Write-Output $msg
            Add-Content -Path $logFilePath -Value $msg
            continue
        }}
        
        $secureUserPassword = ConvertTo-SecureString $userPassword -AsPlainText -Force
        New-ADUser -Name $username `
                   -SamAccountName $username `
                   -Surname $username `
                   -Enabled $true `
                   -AccountPassword $secureUserPassword `
                   -UserPrincipalName $upn `
                   -Description $description `
                   -Credential $domainAdminCreds `
                   -ErrorAction Stop
        
        $successMsg = "Successfully created user: $username"
        Write-Output $successMsg
        Add-Content -Path $logFilePath -Value "BatchUserCreation: $successMsg"
    }}
    catch {{
        $errorMsg = "Error creating user $username : $_"
        Write-Output $errorMsg
        Add-Content -Path $logFilePath -Value "BatchUserCreation: $errorMsg"
    }}
}}

Write-Output "Batch user creation complete"
Add-Content -Path $logFilePath -Value "BatchUserCreation: Complete"
'''
    return script


@bloodhound_apis_blueprint.route("/bloodhound/upload", methods=["POST"])
def upload_bloodhound():
    """
    Upload and parse a BloodHound zip file.
    
    Request: multipart/form-data with 'file' field containing zip
    Response: Parsed BloodHound summary and attack paths
    """
    bloodhound_apis_blueprint.logger.info("BLOODHOUND_UPLOAD: Received upload request")
    
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "File must be a .zip file"}), 400
    
    try:
        filename = secure_filename(file.filename)
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, filename)
        file.save(temp_path)
        
        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_UPLOAD: Saved file to {temp_path}")
        
        # Parse the BloodHound data
        parser = BloodHoundParser()
        bh_data = parser.parse_zip(temp_path)
        
        attack_summary = parser.get_attack_summary()
        domain_info = parser.get_domain_info()
        
        upload_id = str(uuid.uuid4())[:8]
        
        parsed_data = {
            "upload_id": upload_id,
            "domain": domain_info,
            "computers": [
                {
                    "name": c.name,
                    "is_dc": c.is_domain_controller,
                    "os": c.os,
                    "unconstrained_delegation": c.unconstraineddelegation
                }
                for c in bh_data.computers
            ],
            "users": [
                {
                    "username": u.samaccountname,
                    "name": u.name,
                    "enabled": u.enabled,
                    "dontreqpreauth": u.dontreqpreauth,
                    "hasspn": u.hasspn,
                    "admincount": u.admincount
                }
                for u in bh_data.users
            ],
            "attack_summary": attack_summary,
            "temp_path": temp_path
        }
        
        fs_manager.save_file(parsed_data, helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        response = {
            "success": True,
            "upload_id": upload_id,
            "domain": domain_info,
            "summary": {
                "total_computers": len(bh_data.computers),
                "domain_controllers": sum(1 for c in bh_data.computers if c.is_domain_controller),
                "workstations": sum(1 for c in bh_data.computers if not c.is_domain_controller),
                "total_users": len(bh_data.users),
                "enabled_users": sum(1 for u in bh_data.users if u.enabled)
            },
            "attack_paths": {
                "asrep_roastable": attack_summary.get('asrep_roastable', []),
                "kerberoastable": attack_summary.get('kerberoastable', []),
                "unconstrained_delegation": attack_summary.get('unconstrained_delegation', []),
                "constrained_delegation_count": len(attack_summary.get('constrained_delegation', [])),
                "acl_attack_paths_count": len(attack_summary.get('acl_attack_paths', []))
            }
        }
        
        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_UPLOAD: Successfully parsed, upload_id={upload_id}")
        return jsonify(response), 200
        
    except Exception as e:
        bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_UPLOAD: Error: {str(e)}")
        return jsonify({"error": f"Error processing file: {str(e)}"}), 500


@bloodhound_apis_blueprint.route("/bloodhound/generate-topology", methods=["POST"])
def generate_topology_from_bloodhound():
    """
    Generate AutoInfra topology from previously uploaded BloodHound data.
    
    Request Body:
        {
            "upload_id": "abc12345",
            "options": {
                "admin_username": "labadmin",
                "admin_password": "P@ssw0rd123!",
                "include_all_machines": true,
                "include_jumpbox": true,
                "max_workstations": 10
            }
        }
    """
    try:
        data = request.get_json()
        upload_id = data.get("upload_id")
        options = data.get("options", {})
        
        if not upload_id:
            return jsonify({"error": "upload_id is required"}), 400
        
        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_GENERATE: Generating for upload_id={upload_id}")
        
        bh_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        if "ERROR" in str(bh_file):
            return jsonify({"error": f"Upload not found: {upload_id}"}), 404
        
        temp_path = bh_file.get("temp_path")
        if not temp_path or not os.path.exists(temp_path):
            return jsonify({"error": "BloodHound data expired, please re-upload"}), 404
        
        # Re-parse the BloodHound data
        parser = BloodHoundParser()
        bh_data = parser.parse_zip(temp_path)
        
        # Configure topology
        config = TopologyConfig(
            admin_username=options.get("admin_username", "labadmin"),
            admin_password=options.get("admin_password", "P@ssw0rd123!"),
            include_all_machines=options.get("include_all_machines", True),
            include_jumpbox=options.get("include_jumpbox", True),
            max_workstations=options.get("max_workstations", 10)
        )
        
        autoinfra_config = map_bloodhound_to_autoinfra(bh_data, config)
        
        bh_file["autoinfra_config"] = autoinfra_config
        bh_file["options"] = options
        fs_manager.save_file(bh_file, helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        response = {
            "success": True,
            "upload_id": upload_id,
            "topology": autoinfra_config["topology"],
            "users": autoinfra_config["users"],
            "attacks": autoinfra_config["attacks"],
            "summary": autoinfra_config["summary"]
        }
        
        bloodhound_apis_blueprint.logger.info(
            f"BLOODHOUND_GENERATE: Generated topology with {len(autoinfra_config['topology']['nodes'])} nodes"
        )
        
        return jsonify(response), 200
        
    except Exception as e:
        bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_GENERATE: Error: {str(e)}")
        return jsonify({"error": f"Error generating topology: {str(e)}"}), 500


@bloodhound_apis_blueprint.route("/bloodhound/deploy", methods=["POST"])
def deploy_bloodhound_topology():
    """
    Deploy the BloodHound-generated topology using the build infrastructure.
    
    This calls the /build endpoint internally to start deployment.
    Frontend should then poll /getDeploymentStatus for completion.
    
    Request Body:
        {
            "upload_id": "abc12345"
        }
    
    Response:
        {
            "success": true,
            "deploymentID": "BuildLab-XXXXX",
            "message": "Deployment started. Poll /getDeploymentStatus for status."
        }
    """
    try:
        data = request.get_json()
        upload_id = data.get("upload_id")
        topology = data.get("topology")  # Get topology from request (includes manually added nodes)
        scenario_name = data.get("scenario_name")
        
        if not upload_id:
            return jsonify({"error": "upload_id is required"}), 400
        
        if not topology:
            return jsonify({"error": "topology is required"}), 400
        
        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_DEPLOY: Starting deploy for upload_id={upload_id}")
        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_DEPLOY: Received topology with {len(topology.get('nodes', []))} nodes and {len(topology.get('edges', []))} edges")
        
        bh_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        if "ERROR" in str(bh_file):
            return jsonify({"error": f"Upload not found: {upload_id}"}), 404
        
        autoinfra_config = bh_file.get("autoinfra_config")
        if not autoinfra_config:
            return jsonify({"error": "Topology not generated. Call /bloodhound/generate-topology first."}), 400
        
        # Use the topology from the request (which includes any manually added nodes)
        # NOT the stored topology from autoinfra_config
        
        domain_name = bh_file.get('domain', {}).get('name', 'Unknown')
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
        
        user_count = len(autoinfra_config.get("users", []))
        if user_count > 0:
            components.append(f"{user_count} User{'s' if user_count > 1 else ''}")
        
        attack_count = sum(len(targets) for targets in autoinfra_config.get("attacks", {}).values())
        if attack_count > 0:
            components.append(f"{attack_count} Attack{'s' if attack_count > 1 else ''}")
        
        if components:
            scenario_info = f"BloodHound Import - {domain_name}: {', '.join(components)}"
        else:
            scenario_info = f"BloodHound Import - {domain_name}"
        
        options = bh_file.get("options", {})
        admin_username = options.get("admin_username", "buildadmin")
        admin_password = options.get("admin_password", "Password#123")
        
        # Add credentials to topology (build endpoint expects topology.credentials)
        if "credentials" not in topology:
            topology["credentials"] = {}
        topology["credentials"]["enterpriseAdminUsername"] = admin_username
        topology["credentials"]["enterpriseAdminPassword"] = admin_password
        
        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_DEPLOY: Using admin credentials - username={admin_username}")
        
        import flask
        
        with flask.current_app.test_request_context(
            '/build',
            method='POST',
            json={
                "topology": topology,
                "scenarioInfo": scenario_info
            }
        ):
            from apis.build_apis import build
            response = build()
            
            if isinstance(response, tuple):
                result, status_code = response
            else:
                result = response
                status_code = 200
            
            if status_code != 200:
                return result, status_code
            
            result_data = result.get_json()
            deployment_id = result_data.get("deploymentID")
            
            bh_file["deploymentID"] = deployment_id
            bh_file["deploy_status"] = "deploying"
            fs_manager.save_file(bh_file, helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
            
            bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_DEPLOY: Started deployment {deployment_id}")
            
            return jsonify({
                "success": True,
                "deploymentID": deployment_id,
                "upload_id": upload_id,
                "message": "Deployment started. Poll /getDeploymentStatus for status, then call /bloodhound/configure-users"
            }), 200
        
    except Exception as e:
        bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_DEPLOY: Error: {str(e)}")
        return jsonify({"error": f"Error starting deployment: {str(e)}"}), 500


@bloodhound_apis_blueprint.route("/bloodhound/configure-users", methods=["POST"])
def configure_bloodhound_users():
    """
    Create users from BloodHound data on the deployed environment.
    
    Call this after deployment is complete (status = 'Succeeded').
    Creates each user using the createSingleUser mechanism.
    
    For multi-domain environments, this determines the correct DC to create
    each user on based on the user's domain.
    
    Request Body:
        {
            "upload_id": "abc12345",
            "deploymentID": "BuildLab-XXXXX"
        }
    
    Response:
        {
            "success": true,
            "users_created": ["User1", "User2", ...],
            "users_failed": []
        }
    """
    try:
        data = request.get_json()
        upload_id = data.get("upload_id")
        deployment_id = data.get("deploymentID")
        
        if not upload_id or not deployment_id:
            return jsonify({"error": "upload_id and deploymentID are required"}), 400
        
        bloodhound_apis_blueprint.logger.info(
            f"BLOODHOUND_USERS: Creating users for upload_id={upload_id}, deployment={deployment_id}"
        )
        
        bh_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        if "ERROR" in str(bh_file):
            return jsonify({"error": f"Upload not found: {upload_id}"}), 404
        
        autoinfra_config = bh_file.get("autoinfra_config")
        if not autoinfra_config:
            return jsonify({"error": "Topology not generated"}), 400
        
        users_to_create = autoinfra_config.get("users", [])
        
        if not users_to_create:
            return jsonify({
                "success": True,
                "users_created": [],
                "users_failed": [],
                "message": "No users to create"
            }), 200
        
        enterprise_admin_username = scenario_manager.get_parameter("enterpriseAdminUsername", deployment_id)
        enterprise_admin_password = scenario_manager.get_parameter("enterpriseAdminPassword", deployment_id)
        root_domain_name = scenario_manager.get_parameter("rootDomainName", deployment_id)
        root_dc = scenario_manager.get_parameter("rootDCName", deployment_id)
        
        # Debug: Log retrieved parameters
        bloodhound_apis_blueprint.logger.info(
            f"BLOODHOUND_USERS: Retrieved params - username='{enterprise_admin_username}', "
            f"domain='{root_domain_name}', dc='{root_dc}', password_set={bool(enterprise_admin_password)}"
        )
        
        # Build domain-to-DC mapping from topology (for multi-domain support)
        topology = autoinfra_config.get("topology", {})
        domain_to_dc = {}
        
        for node in topology.get("nodes", []):
            if node.get("type") == "domainController":
                node_data = node.get("data", {})
                domain_name = node_data.get("domainName", "").lower()
                dc_name = node_data.get("domainControllerName", "")
                if domain_name and dc_name:
                    domain_to_dc[domain_name] = dc_name
        
        if not domain_to_dc:
            domain_to_dc[root_domain_name.lower()] = root_dc
        
        bloodhound_apis_blueprint.logger.info(
            f"BLOODHOUND_USERS: Domain-to-DC mapping: {domain_to_dc}"
        )
        bloodhound_apis_blueprint.logger.info(
            f"BLOODHOUND_USERS: Creating {len(users_to_create)} users"
        )
        
        compute_client = azure_clients.get_compute_client()
        
        users_created = []
        users_failed = []
        
        # Group users by their target domain for batch creation
        users_by_domain = {}
        default_password = "Password#123"
        
        for user_info in users_to_create:
            username = user_info.get("username", user_info.get("samaccountname", ""))
            password = user_info.get("password", default_password)
            user_domain = user_info.get("domain", "")
            
            if not username:
                continue
            
            # Try to extract domain from username if in UPN format (user@domain.local)
            if "@" in username and not user_domain:
                parts = username.split("@")
                username = parts[0]  # Just the username
                user_domain = parts[1].lower()
            
            # Find the correct DC for this user's domain
            dc_to_use = root_dc
            domain_to_use = root_domain_name
            
            if user_domain:
                user_domain_lower = user_domain.lower()
                if user_domain_lower in domain_to_dc:
                    dc_to_use = domain_to_dc[user_domain_lower]
                    domain_to_use = user_domain_lower
                else:
                    for domain, dc in domain_to_dc.items():
                        if user_domain_lower in domain or domain in user_domain_lower:
                            dc_to_use = dc
                            domain_to_use = domain
                            break
            
            # Group by domain
            if domain_to_use not in users_by_domain:
                users_by_domain[domain_to_use] = {
                    "dc": dc_to_use,
                    "users": []
                }
            users_by_domain[domain_to_use]["users"].append({
                "username": username,
                "password": password
            })
        
        bloodhound_apis_blueprint.logger.info(
            f"BLOODHOUND_USERS: Grouped users by domain: {[(d, len(info['users'])) for d, info in users_by_domain.items()]}"
        )
        
        # Sort domains: root domain first, then children (alphabetically)
        sorted_domains = sorted(users_by_domain.keys(), 
                               key=lambda d: (0 if d.lower() == root_domain_name.lower() else 1, d))
        
        # Always use root domain admin for authentication (Enterprise Admin has rights to all child domains)
        domain_admin_username = f"{enterprise_admin_username}@{root_domain_name}"
        
        # Process each domain sequentially, but create all users in that domain in parallel (batch)
        for domain_name in sorted_domains:
            domain_info = users_by_domain[domain_name]
            dc_to_use = domain_info["dc"]
            domain_users = domain_info["users"]
            
            bloodhound_apis_blueprint.logger.info(
                f"BLOODHOUND_USERS: Creating {len(domain_users)} users on domain '{domain_name}' via DC '{dc_to_use}'"
            )
            
            # Build a batch PowerShell script that creates all users for this domain
            batch_script = _generate_batch_user_creation_script(
                domain_users, 
                domain_admin_username, 
                enterprise_admin_password, 
                domain_name
            )
            
            try:
                execute_params = RunCommandInput(
                    command_id='RunPowerShellScript',
                    script=[batch_script]
                )
                
                poller = compute_client.virtual_machines.begin_run_command(
                    resource_group_name=deployment_id,
                    vm_name=dc_to_use,
                    parameters=execute_params
                )
                result = poller.result()
                
                output_messages = []
                if result.value:
                    for item in result.value:
                        if item.message:
                            output_messages.append(item.message)
                output = '\n'.join(output_messages)
                
                bloodhound_apis_blueprint.logger.info(
                    f"BLOODHOUND_USERS: Batch result for {domain_name}: {output[:500]}"
                )
                
                # Parse output to determine success/failure for each user
                for user_info in domain_users:
                    username = user_info["username"]
                    if f"Successfully created user: {username}" in output:
                        users_created.append(username)
                        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_USERS: Created {username}")
                    elif f"already exists" in output and username in output:
                        users_created.append(username)
                        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_USERS: User {username} already exists")
                    elif f"Error creating user {username}" in output:
                        error_line = [line for line in output.split('\n') if f"Error creating user {username}" in line]
                        error_msg = error_line[0][:200] if error_line else "Unknown error"
                        users_failed.append({"username": username, "domain": domain_name, "error": error_msg})
                        bloodhound_apis_blueprint.logger.warning(f"BLOODHOUND_USERS: Failed to create {username}")
                    else:
                        users_created.append(username)
                        
            except Exception as e:
                bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_USERS: Error on domain {domain_name}: {e}")
                for user_info in domain_users:
                    users_failed.append({"username": user_info["username"], "domain": domain_name, "error": str(e)})
        
        try:
            deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
            # Format users as objects with domain info for frontend compatibility
            formatted_users = []
            for username in users_created:
                # Try to find which domain this user belongs to
                user_domain = root_domain_name  # default
                for domain_name, info in users_by_domain.items():
                    if username in [u["username"] for u in info["users"]]:
                        user_domain = domain_name
                        break
                
                formatted_users.append({
                    "username": username,
                    "domain": user_domain
                })
            
            deployment['users'] = deployment.get('users', []) + formatted_users
            fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        except Exception as e:
            bloodhound_apis_blueprint.logger.warning(f"BLOODHOUND_USERS: Could not update deployment: {e}")
        
        bh_file["users_created"] = users_created
        bh_file["users_failed"] = users_failed
        fs_manager.save_file(bh_file, helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        return jsonify({
            "success": True,
            "users_created": users_created,
            "users_failed": users_failed,
            "message": f"Created {len(users_created)} users, {len(users_failed)} failed"
        }), 200
        
    except Exception as e:
        bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_USERS: Error: {str(e)}")
        return jsonify({"error": f"Error creating users: {str(e)}"}), 500


@bloodhound_apis_blueprint.route("/bloodhound/configure-attacks", methods=["POST"])
def configure_bloodhound_attacks():
    """
    Enable attacks detected from BloodHound data on the deployed environment.
    
    Call this after users are created.
    Maps BloodHound attack paths to AutoInfra attack types.
    
    For multi-domain environments, this determines the correct DC to run
    each attack on based on the user's domain.
    
    Request Body:
        {
            "upload_id": "abc12345",
            "deploymentID": "BuildLab-XXXXX"
        }
    
    Response:
        {
            "success": true,
            "attacks_enabled": {"ASREPRoasting": ["User1"], ...}
        }
    """
    try:
        data = request.get_json()
        upload_id = data.get("upload_id")
        deployment_id = data.get("deploymentID")
        
        if not upload_id or not deployment_id:
            return jsonify({"error": "upload_id and deploymentID are required"}), 400
        
        bloodhound_apis_blueprint.logger.info(
            f"BLOODHOUND_ATTACKS: Enabling attacks for upload_id={upload_id}, deployment={deployment_id}"
        )
        
        bh_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        if "ERROR" in str(bh_file):
            return jsonify({"error": f"Upload not found: {upload_id}"}), 404
        
        autoinfra_config = bh_file.get("autoinfra_config")
        if not autoinfra_config:
            return jsonify({"error": "Topology not generated"}), 400
        
        attacks = autoinfra_config.get("attacks", {})
        unsupported_attacks_count = autoinfra_config.get("unsupported_attacks_count", 0)
        unsupported_attack_types = autoinfra_config.get("unsupported_attack_types", [])
        
        if not attacks:
            return jsonify({
                "success": True,
                "attacks_enabled": {},
                "unsupported_attacks_count": unsupported_attacks_count,
                "unsupported_attack_types": unsupported_attack_types,
                "message": "No attacks to enable"
            }), 200
        
        enterprise_admin_username = scenario_manager.get_parameter("enterpriseAdminUsername", deployment_id)
        enterprise_admin_password = scenario_manager.get_parameter("enterpriseAdminPassword", deployment_id)
        root_domain_name = scenario_manager.get_parameter("rootDomainName", deployment_id)
        root_dc = scenario_manager.get_parameter("rootDCName", deployment_id)
        
        # Build domain-to-DC mapping from topology
        # This allows attacks to be routed to the correct DC for multi-domain scenarios
        topology = autoinfra_config.get("topology", {})
        domain_to_dc = {}
        
        for node in topology.get("nodes", []):
            if node.get("type") == "domainController":
                node_data = node.get("data", {})
                domain_name = node_data.get("domainName", "").lower()
                dc_name = node_data.get("domainControllerName", "")
                if domain_name and dc_name:
                    domain_to_dc[domain_name] = dc_name
                    bloodhound_apis_blueprint.logger.debug(
                        f"BLOODHOUND_ATTACKS: Mapped domain '{domain_name}' -> DC '{dc_name}'"
                    )
        
        if not domain_to_dc:
            domain_to_dc[root_domain_name.lower()] = root_dc
        
        bloodhound_apis_blueprint.logger.info(
            f"BLOODHOUND_ATTACKS: Domain-to-DC mapping: {domain_to_dc}"
        )
        
        attacks_enabled = {}
        attacks_failed = []
        
        from apis.attack_apis import attack_resolver
        
        # NOTE: attacks dict already uses AutoInfra attack names (ASREPRoasting, Kerberoasting, etc.)
        for attack_type, targets in attacks.items():
            if not targets:
                continue
            
            if attack_type not in ["ASREPRoasting", "Kerberoasting", "UserConstrainedDelegation", 
                                   "ComputerConstrainedDelegation", "ACLs"]:
                bloodhound_apis_blueprint.logger.warning(
                    f"BLOODHOUND_ATTACKS: Unsupported attack type '{attack_type}', skipping"
                )
                continue
            
            if attack_type not in attacks_enabled:
                attacks_enabled[attack_type] = []
            
            for target in targets:
                # Extract target user and domain info
                if isinstance(target, dict):
                    target_user = target.get("targetUser", target.get("username", ""))
                    target_domain = target.get("domain", "")
                    granting_user = target.get("grantingUser", "")
                    receiving_user = target.get("receivingUser", "")
                else:
                    target_user = str(target)
                    target_domain = ""
                    granting_user = ""
                    receiving_user = ""
                
                if not target_user and attack_type != "ACLs":
                    continue
                
                # Try to extract domain from user if in UPN format (user@domain.local)
                if "@" in target_user and not target_domain:
                    parts = target_user.split("@")
                    target_user = parts[0]  # Just the username
                    target_domain = parts[1].lower()
                
                # Find the correct DC for this user's domain
                dc_to_use = root_dc
                domain_to_use = root_domain_name
                
                if target_domain:
                    if target_domain in domain_to_dc:
                        dc_to_use = domain_to_dc[target_domain]
                        domain_to_use = target_domain
                    else:
                        for domain, dc in domain_to_dc.items():
                            if target_domain in domain or domain in target_domain:
                                dc_to_use = dc
                                domain_to_use = domain
                                break
                
                # Always use root domain for admin credentials (Enterprise Admin)
                domain_admin_username = f"{enterprise_admin_username}@{root_domain_name}"
                
                bloodhound_apis_blueprint.logger.info(
                    f"BLOODHOUND_ATTACKS: Enabling {attack_type} for user '{target_user}' "
                    f"on domain '{domain_to_use}' via DC '{dc_to_use}'"
                )
                
                try:
                    attack_resolver(
                        attack=attack_type,
                        deploymentID=deployment_id,
                        domainAdminUsername=domain_admin_username,
                        domainAdminPassword=enterprise_admin_password,
                        domainName=domain_to_use,
                        dc=dc_to_use,
                        targetBox="",
                        targetUser=target_user,
                        singleUserPassword="",
                        grantingUser=granting_user,
                        receivingUser=receiving_user
                    )
                    attacks_enabled[attack_type].append(target_user)
                except Exception as e:
                    bloodhound_apis_blueprint.logger.error(
                        f"BLOODHOUND_ATTACKS: Error enabling {attack_type} for {target_user}: {e}"
                    )
                    attacks_failed.append({"attack": attack_type, "user": target_user, "error": str(e)})
        
        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        attack_operations = deployment.get("attackOperations", {})
        attacks_in_progress = deployment.get("attacksInProgress", {})
        
        for operation_id, op_info in attack_operations.items():
            if op_info.get("status") == "InProgress":
                op_attack_type = op_info.get("attackType")
                if op_attack_type:
                    if op_attack_type not in attacks_in_progress:
                        attacks_in_progress[op_attack_type] = []
                    
                    instance_info = {
                        "operationId": operation_id,
                        "targetUser": op_info.get("targetUser"),
                        "targetBox": op_info.get("targetBox"),
                        "timestamp": op_info.get("timestamp")
                    }
                    
                    if not any(inst.get("operationId") == operation_id for inst in attacks_in_progress[op_attack_type]):
                        attacks_in_progress[op_attack_type].append(instance_info)
        
        deployment["attacksInProgress"] = attacks_in_progress
        fs_manager.save_file(deployment, helpers.DEPLOYMENT_DIRECTORY, deployment_id)
        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_ATTACKS: Updated attacksInProgress with {len(attack_operations)} operations")
        
        bh_file["attacks_enabled"] = attacks_enabled
        bh_file["attacks_failed"] = attacks_failed
        fs_manager.save_file(bh_file, helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        total_enabled = sum(len(users) for users in attacks_enabled.values())
        
        message = f"Enabled {total_enabled} attacks across {len(attacks_enabled)} attack types"
        if unsupported_attacks_count > 0:
            message += f". {unsupported_attacks_count} unsupported attack(s) found in BloodHound data."
        
        return jsonify({
            "success": True,
            "attacks_enabled": attacks_enabled,
            "attacks_failed": attacks_failed,
            "unsupported_attacks_count": unsupported_attacks_count,
            "unsupported_attack_types": unsupported_attack_types,
            "message": message
        }), 200
        
    except Exception as e:
        bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_ATTACKS: Error: {str(e)}")
        return jsonify({"error": f"Error enabling attacks: {str(e)}"}), 500


@bloodhound_apis_blueprint.route("/bloodhound/preview/<upload_id>", methods=["GET"])
def preview_bloodhound_import(upload_id: str):
    """Get a preview of what would be created from the BloodHound import."""
    try:
        bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_PREVIEW: Getting preview for upload_id={upload_id}")
        
        bh_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        if "ERROR" in str(bh_file):
            return jsonify({"error": f"Upload not found: {upload_id}"}), 404
        
        response = {
            "success": True,
            "upload_id": upload_id,
            "domain": bh_file.get("domain"),
            "computers": bh_file.get("computers", []),
            "users": bh_file.get("users", []),
            "attack_summary": bh_file.get("attack_summary", {}),
            "autoinfra_config": bh_file.get("autoinfra_config"),
            "deploymentID": bh_file.get("deploymentID"),
            "deploy_status": bh_file.get("deploy_status"),
            "users_created": bh_file.get("users_created", []),
            "attacks_enabled": bh_file.get("attacks_enabled", {})
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_PREVIEW: Error: {str(e)}")
        return jsonify({"error": f"Error getting preview: {str(e)}"}), 500


@bloodhound_apis_blueprint.route("/bloodhound/active-session", methods=["GET"])
def get_active_bloodhound_session():
    """
    Get the most recent active BloodHound import session.
    
    This allows the frontend to restore state when the user navigates back to the page.
    An active session is one that:
    - Has been uploaded
    - Has NOT completed (deployment succeeded + users created + attacks enabled)
    
    Returns the session data needed to restore the frontend state.
    """
    try:
        import glob
        
        deployment_dir = helpers.DEPLOYMENT_DIRECTORY
        bh_files = []
        
        if os.path.exists(deployment_dir):
            for filename in os.listdir(deployment_dir):
                if filename.startswith("bh-") and filename.endswith(".json"):
                    upload_id = filename[3:-5]  # Remove "bh-" prefix and ".json" suffix
                    try:
                        bh_file = fs_manager.load_file(deployment_dir, f"bh-{upload_id}")
                        if "ERROR" not in str(bh_file):
                            bh_files.append((upload_id, bh_file))
                    except:
                        pass
        
        if not bh_files:
            return jsonify({"success": True, "active_session": None}), 200
        
        for upload_id, bh_file in reversed(bh_files):  # Most recent first
            deployment_id = bh_file.get("deploymentID")
            autoinfra_config = bh_file.get("autoinfra_config")
            users_created = bh_file.get("users_created", [])
            attacks_enabled = bh_file.get("attacks_enabled", {})
            
            current_step = "upload"  # Default - file exists but nothing done
            deploy_status = None
            
            if autoinfra_config:
                current_step = "topology"
                
                if deployment_id:
                    try:
                        deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
                        deploy_status = deployment.get("status", "unknown")
                    except:
                        deploy_status = "unknown"
                    
                    if deploy_status in ["Deploying", "Running", "Pending"]:
                        current_step = "deploying"
                    elif deploy_status == "Succeeded":
                        if not users_created:
                            current_step = "configuring-users"
                        elif not attacks_enabled:
                            current_step = "configuring-attacks"
                        else:
                            current_step = "complete"
                    elif deploy_status == "Failed":
                        current_step = "deploy-failed"
            
            if current_step == "complete":
                continue
            
            session_data = {
                "upload_id": upload_id,
                "step": current_step,
                "deploymentID": deployment_id,
                "deploy_status": deploy_status,
                "domain": bh_file.get("domain"),
                "summary": {
                    "total_computers": len(bh_file.get("computers", [])),
                    "domain_controllers": sum(1 for c in bh_file.get("computers", []) if c.get("is_dc")),
                    "workstations": sum(1 for c in bh_file.get("computers", []) if not c.get("is_dc")),
                    "total_users": len(bh_file.get("users", [])),
                    "enabled_users": sum(1 for u in bh_file.get("users", []) if u.get("enabled"))
                },
                "attack_paths": bh_file.get("attack_summary", {}),
                "topology": autoinfra_config.get("topology") if autoinfra_config else None,
                "users": autoinfra_config.get("users") if autoinfra_config else None,
                "attacks": autoinfra_config.get("attacks") if autoinfra_config else None
            }
            
            bloodhound_apis_blueprint.logger.info(
                f"BLOODHOUND_ACTIVE_SESSION: Found active session {upload_id} at step '{current_step}'"
            )
            
            return jsonify({"success": True, "active_session": session_data}), 200
        
        return jsonify({"success": True, "active_session": None}), 200
        
    except Exception as e:
        bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_ACTIVE_SESSION: Error: {str(e)}")
        return jsonify({"error": f"Error getting active session: {str(e)}"}), 500


@bloodhound_apis_blueprint.route("/bloodhound/clear-session/<upload_id>", methods=["DELETE"])
def clear_bloodhound_session(upload_id: str):
    """
    Clear/delete a BloodHound import session.
    
    Allows user to start fresh by removing an existing session.
    """
    try:
        bh_file_path = os.path.join(helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}.json")
        
        if os.path.exists(bh_file_path):
            os.remove(bh_file_path)
            bloodhound_apis_blueprint.logger.info(f"BLOODHOUND_CLEAR: Cleared session {upload_id}")
            return jsonify({"success": True, "message": f"Session {upload_id} cleared"}), 200
        else:
            return jsonify({"error": f"Session not found: {upload_id}"}), 404
        
    except Exception as e:
        bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_CLEAR: Error: {str(e)}")
        return jsonify({"error": f"Error clearing session: {str(e)}"}), 500


@bloodhound_apis_blueprint.route("/bloodhound/status/<upload_id>", methods=["GET"])
def get_bloodhound_status(upload_id: str):
    """Get the current status of a BloodHound import workflow."""
    try:
        bh_file = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, f"bh-{upload_id}")
        
        if "ERROR" in str(bh_file):
            return jsonify({"error": f"Upload not found: {upload_id}"}), 404
        
        deployment_id = bh_file.get("deploymentID")
        deploy_status = "not_started"
        
        if deployment_id:
            try:
                deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
                deploy_status = deployment.get("status", "unknown")
            except:
                deploy_status = "unknown"
        
        response = {
            "success": True,
            "upload_id": upload_id,
            "steps": {
                "uploaded": True,
                "topology_generated": bh_file.get("autoinfra_config") is not None,
                "deployment_started": deployment_id is not None,
                "deployment_status": deploy_status,
                "users_created": len(bh_file.get("users_created", [])),
                "attacks_enabled": len(bh_file.get("attacks_enabled", {}))
            },
            "deploymentID": deployment_id
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        bloodhound_apis_blueprint.logger.error(f"BLOODHOUND_STATUS: Error: {str(e)}")
        return jsonify({"error": f"Error getting status: {str(e)}"}), 500
