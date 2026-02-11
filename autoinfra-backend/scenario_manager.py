import json
import os
import logging
import fs_manager
import helpers
logger = logging.getLogger(__name__)

class ScenarioManager:
    def __init__(self):
        self.base_dir = helpers.TEMPLATE_DIRECTORY

    def get_parameter(self, param_name, deployment_id=None):
        """Get a parameter by name, potentially from a build deployment"""
        if deployment_id:
            try:
                deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
                
                if "topologyFile" in deployment or "topology" in deployment:
                    try:
                        # Try to get from topology file or embedded topology
                        if "topology" in deployment:
                            topology = deployment.get("topology")
                        else:
                            topology_file = deployment.get("topologyFile")
                            topology = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, topology_file)
                        
                        # Extract parameters based on the parameter name
                        if isinstance(topology, dict) and "nodes" in topology:
                            if param_name == "enterpriseAdminUsername" or param_name == "enterpriseAdminPassword":
                                # First check if credentials are at topology level
                                if "credentials" in topology:
                                    creds = topology.get("credentials", {})
                                    if param_name == "enterpriseAdminUsername" and "enterpriseAdminUsername" in creds:
                                        logger.info(f"Using build parameter {param_name} from topology credentials for {deployment_id}")
                                        return creds.get("enterpriseAdminUsername")
                                    elif param_name == "enterpriseAdminPassword" and "enterpriseAdminPassword" in creds:
                                        logger.info(f"Using build parameter {param_name} from topology credentials for {deployment_id}")
                                        return creds.get("enterpriseAdminPassword")

                                # Fall back to finding root domain controller
                                for node in topology["nodes"]:
                                    if node["type"] == "domainController":
                                        data = node.get("data", {})
                                        is_root = data.get("isRoot", not data.get("isSub", False))
                                        if is_root:
                                            if param_name == "enterpriseAdminUsername":
                                                logger.info(f"Using build parameter {param_name} from topology node for {deployment_id}")
                                                return data.get("adminUsername")
                                            elif param_name == "enterpriseAdminPassword":
                                                logger.info(f"Using build parameter {param_name} from topology node for {deployment_id}")
                                                return data.get("adminPassword")
                            
                            elif param_name == "rootDomainName":
                                # Find root domain controller to get domain name
                                for node in topology["nodes"]:
                                    if node["type"] == "domainController":
                                        data = node.get("data", {})
                                        is_root = data.get("isRoot", not data.get("isSub", False))
                                        if is_root:
                                            logger.info(f"Using build parameter {param_name} from topology for {deployment_id}")
                                            return data.get("domainName")
                            
                            elif param_name == "rootDCName":
                                # Find root domain controller name
                                for node in topology["nodes"]:
                                    if node["type"] == "domainController":
                                        data = node.get("data", {})
                                        is_root = data.get("isRoot", not data.get("isSub", False))
                                        if is_root:
                                            logger.info(f"Using build parameter {param_name} from topology for {deployment_id}")
                                            return data.get("domainControllerName")
                    except Exception as e:
                        logger.error(f"Error loading topology data for {deployment_id}: {str(e)}")
                    
                    try:
                        if "resourceGroup" in deployment:
                            _ = deployment.get("resourceGroup")
                            build_params_path = helpers.SCENARIO_MANAGER_BUILD_PARAMS
                            if os.path.exists(build_params_path):
                                with open(build_params_path, 'r') as f:
                                    build_params = json.load(f)
                                    
                                    # Extract parameters based on the parameter name
                                    if param_name == "enterpriseAdminUsername":
                                        logger.info(f"Using {param_name} from build parameters file for {deployment_id}")
                                        return build_params['parameters']['enterpriseAdminUsername']['value']
                                    elif param_name == "enterpriseAdminPassword":
                                        logger.info(f"Using {param_name} from build parameters file for {deployment_id}")
                                        return build_params['parameters']['enterpriseAdminPassword']['value']
                                    elif param_name == "rootDomainName":
                                        # In build params, we have to look at rootDomainControllers array
                                        if 'rootDomainControllers' in build_params['parameters']:
                                            controllers = build_params['parameters']['rootDomainControllers']['value']
                                            if controllers and len(controllers) > 0:
                                                logger.info(f"Using {param_name} from build parameters file for {deployment_id}")
                                                return controllers[0]['domainName']
                                    elif param_name == "rootDCName":
                                        # In build params, we have to look at rootDomainControllers array
                                        if 'rootDomainControllers' in build_params['parameters']:
                                            controllers = build_params['parameters']['rootDomainControllers']['value']
                                            if controllers and len(controllers) > 0:
                                                logger.info(f"Using {param_name} from build parameters file for {deployment_id}")
                                                return controllers[0]['name']
                                    elif param_name == "rootDomainNetBIOSName":
                                        # In build params, we have to look at rootDomainControllers array
                                        if 'rootDomainControllers' in build_params['parameters']:
                                            controllers = build_params['parameters']['rootDomainControllers']['value']
                                            if controllers and len(controllers) > 0:
                                                logger.info(f"Using {param_name} from build parameters file for {deployment_id}")
                                                return controllers[0].get('netbios', controllers[0]['domainName'].split('.')[0].upper())
                    except Exception as e:
                        logger.error(f"Error loading build parameters for {deployment_id}: {str(e)}")
                
                # This handles deployed Build scenarios where topology is in the scenario file
                if "scenario" in deployment:
                    scenario_name = deployment.get("scenario")
                    try:
                        scenario_path = os.path.join(helpers.SCENARIO_DIRECTORY, f"{scenario_name}.json")
                        if os.path.exists(scenario_path):
                            with open(scenario_path, 'r') as f:
                                scenario_data = json.load(f)
                            
                            if "topology" in scenario_data:
                                topology = scenario_data.get("topology", {})
                                
                                # First check credentials at topology level
                                if "credentials" in topology:
                                    creds = topology.get("credentials", {})
                                    if param_name == "enterpriseAdminUsername" and "enterpriseAdminUsername" in creds:
                                        logger.info(f"Using {param_name} from scenario {scenario_name} topology credentials")
                                        return creds.get("enterpriseAdminUsername")
                                    elif param_name == "enterpriseAdminPassword" and "enterpriseAdminPassword" in creds:
                                        logger.info(f"Using {param_name} from scenario {scenario_name} topology credentials")
                                        return creds.get("enterpriseAdminPassword")
                                
                                # Extract from nodes if not in credentials
                                for node in topology.get("nodes", []):
                                    if node.get("type") == "domainController":
                                        data = node.get("data", {})
                                        is_root = data.get("isRoot", not data.get("isSub", False))
                                        if is_root:
                                            if param_name == "enterpriseAdminUsername":
                                                logger.info(f"Using {param_name} from scenario {scenario_name} topology node")
                                                return data.get("adminUsername")
                                            elif param_name == "enterpriseAdminPassword":
                                                logger.info(f"Using {param_name} from scenario {scenario_name} topology node")
                                                return data.get("adminPassword")
                                            elif param_name == "rootDomainName":
                                                logger.info(f"Using {param_name} from scenario {scenario_name} topology node")
                                                return data.get("domainName")
                                            elif param_name == "rootDCName":
                                                logger.info(f"Using {param_name} from scenario {scenario_name} topology node")
                                                return data.get("domainControllerName")
                    except Exception as e:
                        logger.error(f"Error loading scenario {scenario_name} for {deployment_id}: {str(e)}")
                    
            except Exception as e:
                logger.error(f"Error getting build parameter {param_name} for {deployment_id}: {str(e)}")
        
        params = fs_manager.load_file(helpers.TEMPLATE_DIRECTORY, "ScenarioManager.parameters.json")
        return params['parameters'][param_name]['value']

    def list_parameters(self):
        params = fs_manager.load_file(helpers.TEMPLATE_DIRECTORY, "ScenarioManager.parameters.json")
        return params['parameters']

    def build_image_reference(self, server, subscriptionID, vmGalleryResourceGroup='VMImages', galleryName='VMImages'):
        return f'/subscriptions/{subscriptionID}/resourceGroups/{vmGalleryResourceGroup}/providers/Microsoft.Compute/galleries/{galleryName}/images/{server}/versions/1.0.0'

    def set_scenario_manager_parameters(self, params):
        params_path = helpers.SCENARIO_MANAGER_PARAMS
        with open(params_path, 'r') as fd:
            scenarioManagerParameters = json.loads(fd.read())

            scenarioManagerParameters['parameters']['scenarioTagValue']['value'] = params.scenarioTag
            scenarioManagerParameters['parameters']['scenarioSelection']['value'] = params.scenarioSelection
            scenarioManagerParameters['parameters']['DC01ImageReferenceID']['value'] = self.build_image_reference(params.rootDCName, params.subscriptionID)
            scenarioManagerParameters['parameters']['CA01ImageReferenceID']['value'] = self.build_image_reference(params.caName, params.subscriptionID)
            scenarioManagerParameters['parameters']['SRV01ImageReferenceID']['value'] = self.build_image_reference(params.rootStandaloneName, params.subscriptionID)

            scenarioManagerParameters['parameters']['rootDCName']['value'] = params.rootDCName
            scenarioManagerParameters['parameters']['caName']['value'] = params.caName
            scenarioManagerParameters['parameters']['rootStandaloneServerName']['value'] = params.rootStandaloneName

            scenarioManagerParameters['parameters']['location']['value'] = params.region

            scenarioManagerParameters['parameters']['rootDomainName']['value'] = params.domainName
            #scenarioManagerParameters['parameters']['subDomainName']['value'] = params.subdomainName
            scenarioManagerParameters['parameters']['enterpriseAdminUsername']['value'] = params.enterpriseAdminUsername
            scenarioManagerParameters['parameters']['enterpriseAdminPassword']['value'] = params.enterpriseAdminPassword
            scenarioManagerParameters['parameters']['caAdminUsername']['value'] = params.caAdminUsername
            scenarioManagerParameters['parameters']['caAdminPassword']['value'] = params.caAdminPassword
            scenarioManagerParameters['parameters']['standaloneAdminUsername']['value'] = params.standaloneAdminUsername
            scenarioManagerParameters['parameters']['standaloneAdminPassword']['value'] = params.standaloneAdminPassword
            scenarioManagerParameters['parameters']['rootDomainNetBIOSName']['value'] = params.rootDomainNetBIOSName
            scenarioManagerParameters['parameters']['subscriptionID']['value'] = params.subscriptionID

        with open(params_path, 'w') as fd:
            fd.write(json.dumps(scenarioManagerParameters, indent=2))