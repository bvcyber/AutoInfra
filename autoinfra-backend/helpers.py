import logging, string, random, subprocess, json, os
from datetime import datetime, timedelta
import command_runner
import fs_manager

LOGGER_NAME = "backend-logs"
logger = logging.getLogger(LOGGER_NAME)

DEPLOYMENT_DIRECTORY = "./deployments"
CONFIG_DIRECTORY = "./config"
SCENARIO_DIRECTORY = "./scenarios"
SAVED_DEPLOYMENTS_DIRECTORY = "./saved-deployments"
TEMPLATE_DIRECTORY = "./templates/"
SCENARIO_TEMPLATE_DIRECTORY = "./templates/scenarios/"
GENERATED_TEMPLATE_DIRECTORY = "./templates/generated/"
UPDATES_TEMPLATE_DIRECTORY = "./templates/updates/"
TOPOLOGY_TEMPLATE_DIRECTORY = "./config/topology-templates"
CONFIG_FILE_PATH = "./config/config.json"
SAVE_DEPLOYMENT_BICEP = "./templates/SaveDeployment.bicep"
SCENARIO_MANAGER_BICEP = "./templates/ScenarioManager.bicep"
SCENARIO_MANAGER_JSON = "./templates/ScenarioManager.json"
SCENARIO_MANAGER_PARAMS = "./templates/ScenarioManager.parameters.json"
SCENARIO_MANAGER_BUILD_PARAMS = "./templates/ScenarioManagerBuild.parameters.json"
EXECUTE_MODULE_SCRIPT = "./config/ExecuteModule.ps1"
ADVULN_MODULE_SCRIPT = "./config/ADVulnEnvModule.psm1"
DOWNLOAD_FILES_SCRIPT = "./config/DownloadFiles.ps1"
GENERATED_ROOT_DC_MODULES = "./templates/generated/GeneratedRootDCModules.bicep"
GENERATED_SUB_DC_MODULES = "./templates/generated/GeneratedSubDCModules.bicep"
GENERATED_STANDALONE_MODULES = "./templates/generated/GeneratedStandaloneModules.bicep"
GENERATED_JUMPBOX_MODULES = "./templates/generated/GeneratedJumpboxModules.bicep"
GENERATED_CA_MODULES = "./templates/generated/GeneratedCAModules.bicep"

BUILD_LAB_PREFIX = "BuildLab-"
SAVED_DEPLOYMENT_PREFIX = "SavedDeployment-"
RUN_COMMAND_TIMEOUT = 3600
IP_LOOKUP_TIMEOUT = 5
CORS_MAX_AGE = 3600
CLEANUP_CHECK_INTERVAL = 300
CLEANUP_ERROR_RETRY_DELAY = 60
DESTROY_DEPLOYMENT_RETRIES = 3
DELETION_VERIFICATION_MAX_RETRIES = 5
DELETION_VERIFICATION_BASE_WAIT = 180
IMAGE_CLEANUP_MAX_WORKERS = 10
RANDOM_PORT_MIN = 30000
RANDOM_PORT_MAX = 31000

def load_config():
    """Load config.json and return the parsed dict, or None on failure."""
    config = fs_manager.load_file(CONFIG_DIRECTORY, "config.json")
    if "ERROR" in config:
        logger.error("LOAD_CONFIG: Could not load config.json")
        return None
    return config

_config = load_config() or {}

LOCATION = _config.get("region", "eastus")
DEPLOYMENT_REGIONS = _config.get("deploymentRegions", [LOCATION])
VM_IMAGE_GALLERY_RESOURCE_GROUP = _config.get("vmImageGalleryResourceGroup", "VMImages")
VM_IMAGE_GALLERY_NAME = _config.get("vmImageGalleryName", "VMImages")
BUILD_GALLERY_NAME = _config.get("buildGalleryName", "TestBuilds")
DEPLOYMENT_TIMEOUT_HOURS = _config.get("deploymentTimeoutHours", 2)
SAVED_DEPLOYMENT_TIMEOUT_HOURS = _config.get("savedDeploymentTimeoutHours", 168)
MAX_DEPLOYMENT_EXTENSIONS = _config.get("maxDeploymentExtensions", 2)
BACKEND_PORT = _config.get("backendPort", 8100)

# Kali Linux marketplace configuration
KALI_PUBLISHER = "kali-linux"
KALI_OFFER = "kali"
KALI_FALLBACK_SKU = "kali-2025-2"  # Fallback version if query fails
_kali_version_cache = None
_kali_cache_timestamp = None
_kali_cache_ttl = timedelta(hours=24)  # Cache for 24 hours

_subscription_id_cache = None
_az_cli_logged_in = False


def _ensure_az_cli_auth():
    """Ensure Azure CLI is authenticated using environment variables."""
    global _az_cli_logged_in
    if _az_cli_logged_in or not all([os.getenv("AZURE_CLIENT_ID"), os.getenv("AZURE_CLIENT_SECRET"), os.getenv("AZURE_TENANT_ID")]):
        return
    try:
        subprocess.run(["az", "login", "--service-principal", "-u", os.environ["AZURE_CLIENT_ID"], "-p", os.environ["AZURE_CLIENT_SECRET"], "--tenant", os.environ["AZURE_TENANT_ID"]], capture_output=True, timeout=10)
        _az_cli_logged_in = True
    except: pass


def get_current_time_formatted():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def generate_random_id(size=5, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

def get_future_time(hours):
    futureTime = int(datetime.now().timestamp()) + (hours * 3600)
    logger.debug(f"GET_FUTURE_TIME: FutureTime: {futureTime}")
    return futureTime

def generate_random_port():
    return random.randint(RANDOM_PORT_MIN, RANDOM_PORT_MAX)

def get_subscription_id():
    global _subscription_id_cache

    if _subscription_id_cache:
        return _subscription_id_cache

    subscription_id = None
    source = None

    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    if subscription_id:
        source = "environment variable"

    if not subscription_id:
        try:
            result = command_runner.run_command_and_read_output(
                ["az", "account", "show", "--query", "id", "-o", "tsv"]
            )
            subscription_id = result.strip() if result else None
            if subscription_id:
                source = "Azure CLI"
        except Exception as e:
            logger.debug(f"GET_SUBSCRIPTION_ID: Could not get from Azure CLI: {e}")

    if subscription_id:
        _subscription_id_cache = subscription_id
        logger.info(f"GET_SUBSCRIPTION_ID: Using subscription ID from {source}")
    else:
        logger.error("GET_SUBSCRIPTION_ID: Could not determine subscription ID from any source")

    return subscription_id

def update_expiry_tag(newValue, deploymentID):
    subscription_id = get_subscription_id()
    resourceID = f"/subscriptions/{subscription_id}/resourceGroups/{deploymentID}"
    tag = f"expiryTimeout={newValue}"
    command = ["az", "tag", "update", "--resource-id", resourceID, "--operation", "Merge", "--tags", tag]
    command_runner.run_command_and_read_output(command)

def add_time(deploymentID, hours):
    deployment = fs_manager.load_file(DEPLOYMENT_DIRECTORY, deploymentID)
    if "ERROR" not in deployment:
        if deployment["remainingExtensions"] > 0:
            deployment_timeout = deployment["timeout"]
            newTimeout = deployment_timeout + (hours*3600)
            deployment["timeout"] = newTimeout
            deployment["remainingExtensions"] -= 1
            update_expiry_tag(newTimeout, deploymentID)
            logger.info(f"ADD_TIME: New timeout: {newTimeout}")
            fs_manager.save_file(deployment, DEPLOYMENT_DIRECTORY, deploymentID)
        else:
            logger.error("ADD_TIME: Failed. No extensions remaining.")
            return "NO MORE EXTENSIONS"
    else:
        logger.error("ADD_TIME: Failed. Could not load deployment file.")
        return "FILE NOT FOUND"

def update_config_value(key, value):
    config = load_config()
    if not config:
        logger.error("UPDATE_CONFIG_VALUE: Failed. Could not load config.")
        return {"message": "failed"}

    if key in config:
        config[key] = value
        fs_manager.save_file(config, CONFIG_DIRECTORY, "config.json")
        logger.info(f"UPDATE_CONFIG_VALUE: Updated {key} to {value}")
        return {"message": "success"}
    else:
        logger.error(f"UPDATE_CONFIG_VALUE: Failed. Key {key} not in config.")
        return {"message": "failed"}

def get_deployed_machine_types(deploymentID):
    """
    Query Azure for all VMs in a deployment and extract their machine types from tags.
    Returns a set of machine types (e.g., {"RootDC", "CA", "Workstation"})
    """
    try:
        from azure_clients import AzureClients
        from azure.mgmt.compute import ComputeManagementClient

        azure_clients = AzureClients()
        credential, subscription_id = azure_clients.get_auth_config()
        compute_client = ComputeManagementClient(credential, subscription_id)

        machine_types = set()

        vms = compute_client.virtual_machines.list(deploymentID)

        for vm in vms:
            tags = vm.tags or {}
            if "VM" in tags:
                # Tag format is "Type:ResourceGroup", extract the Type part
                vm_tag = tags["VM"]
                if ":" in vm_tag:
                    machine_type = vm_tag.split(":")[0]
                    machine_types.add(machine_type)
                    logger.debug(f"GET_DEPLOYED_MACHINE_TYPES: Found {machine_type} in {deploymentID}")
                else:
                    logger.warning(f"GET_DEPLOYED_MACHINE_TYPES: VM tag format incorrect: {vm_tag}")

        logger.info(f"GET_DEPLOYED_MACHINE_TYPES: Found {len(machine_types)} machine types in {deploymentID}")
        return machine_types

    except Exception as e:
        logger.error(f"GET_DEPLOYED_MACHINE_TYPES: Error: {str(e)}")
        return set()

def get_latest_kali_sku():
    """
    Query Azure Marketplace for the latest available Kali Linux SKU.
    Uses caching to avoid repeated API calls (24-hour TTL).
    Returns the SKU string (e.g., "kali-2025-2") or fallback version if query fails.
    """
    global _kali_version_cache, _kali_cache_timestamp
    _ensure_az_cli_auth()

    try:
        if _kali_version_cache and _kali_cache_timestamp:
            cache_age = datetime.now() - _kali_cache_timestamp
            if cache_age < _kali_cache_ttl:
                logger.info(f"GET_LATEST_KALI_SKU: Using cached version: {_kali_version_cache}")
                return _kali_version_cache

        logger.info("GET_LATEST_KALI_SKU: Querying Azure Marketplace for latest Kali version...")

        command = [
            "az", "vm", "image", "list-skus",
            "--location", LOCATION,
            "--publisher", KALI_PUBLISHER,
            "--offer", KALI_OFFER,
            "--output", "json"
        ]

        result = subprocess.run(command, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            skus = json.loads(result.stdout)

            if not skus:
                logger.warning("GET_LATEST_KALI_SKU: No SKUs returned from Azure")
                return KALI_FALLBACK_SKU

            kali_skus = [
                sku['name'] for sku in skus
                if (sku['name'].startswith('kali-')
                    and sku['name'] != 'latest'
                    and 'arm64' not in sku['name'].lower()
                    and 'gen2' not in sku['name'].lower())
            ]

            if not kali_skus:
                logger.warning("GET_LATEST_KALI_SKU: No versioned Kali SKUs found")
                return KALI_FALLBACK_SKU

            kali_skus.sort(reverse=True)
            latest_sku = kali_skus[0]

            _kali_version_cache = latest_sku
            _kali_cache_timestamp = datetime.now()

            logger.info(f"GET_LATEST_KALI_SKU: Found latest version: {latest_sku}")
            return latest_sku
        else:
            logger.error(f"GET_LATEST_KALI_SKU: Azure CLI error: {result.stderr}")
            return KALI_FALLBACK_SKU

    except subprocess.TimeoutExpired:
        logger.error("GET_LATEST_KALI_SKU: Timeout querying Azure Marketplace")
        return KALI_FALLBACK_SKU
    except Exception as e:
        logger.error(f"GET_LATEST_KALI_SKU: Error: {str(e)}")
        return KALI_FALLBACK_SKU

def accept_kali_marketplace_terms(subscription_id=None):
    """
    Accept Azure Marketplace terms for Kali Linux.
    This must be done before deploying Kali for the first time in a subscription.
    Returns True if successful, False otherwise.
    """
    _ensure_az_cli_auth()
    try:
        kali_sku = get_latest_kali_sku()
        logger.info(f"ACCEPT_KALI_TERMS: Accepting marketplace terms for {kali_sku}...")

        command = [
            "az", "vm", "image", "terms", "accept",
            "--offer", KALI_OFFER,
            "--plan", kali_sku,
            "--publisher", KALI_PUBLISHER
        ]

        if subscription_id:
            command.extend(["--subscription", subscription_id])

        result = subprocess.run(command, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            logger.info(f"ACCEPT_KALI_TERMS: Successfully accepted terms for {kali_sku}")
            return True
        else:
            logger.error(f"ACCEPT_KALI_TERMS: Failed to accept terms: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("ACCEPT_KALI_TERMS: Timeout accepting marketplace terms")
        return False
    except Exception as e:
        logger.error(f"ACCEPT_KALI_TERMS: Error: {str(e)}")
        return False

def check_kali_marketplace_terms(subscription_id=None):
    """
    Check if Azure Marketplace terms for Kali Linux are already accepted.
    Returns True if accepted, False if not accepted or unable to determine.
    """
    _ensure_az_cli_auth()
    try:
        kali_sku = get_latest_kali_sku()
        logger.info(f"CHECK_KALI_TERMS: Checking marketplace terms for {kali_sku}...")

        command = [
            "az", "vm", "image", "terms", "show",
            "--offer", KALI_OFFER,
            "--plan", kali_sku,
            "--publisher", KALI_PUBLISHER,
            "--output", "json"
        ]

        if subscription_id:
            command.extend(["--subscription", subscription_id])

        result = subprocess.run(command, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            terms_info = json.loads(result.stdout)
            accepted = terms_info.get('accepted', False)
            logger.info(f"CHECK_KALI_TERMS: Terms accepted: {accepted}")
            return accepted
        else:
            logger.warning(f"CHECK_KALI_TERMS: Could not check terms: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("CHECK_KALI_TERMS: Timeout checking marketplace terms")
        return False
    except Exception as e:
        logger.error(f"CHECK_KALI_TERMS: Error: {str(e)}")
        return False
