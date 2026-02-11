from flask import Blueprint, request, jsonify
from azure_clients import AzureClients
import os
from azure_setup import AzureSetup
from deployments import Deployments
import helpers
import fs_manager
import command_runner
import logging
from generate_topology import TopologyGenerator

topology_apis_blueprint = Blueprint('topology_apis', __name__)
azure_clients = AzureClients()
deployment_handler = Deployments()
azure_setup = AzureSetup()
topology_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)

@topology_apis_blueprint.route('/getTopology', methods=["POST"])
def get_topology():
    try:
        data = request.get_json()
        deployment_id = data.get("deploymentID", "")
        scenario_name = data.get("scenarioName", "")
        
        topology_apis_blueprint.logger.debug(f"GET_TOPOLOGY: deploymentID={deployment_id}, scenarioName={scenario_name}")
        
        topology = None
        if deployment_id and deployment_id.strip():
            try:
                deployment = fs_manager.load_file(helpers.DEPLOYMENT_DIRECTORY, deployment_id)
                topology_apis_blueprint.logger.debug(f"GET_TOPOLOGY: Loaded deployment config: {deployment}")
                #    topology_apis_blueprint.logger.debug(f"GET_TOPOLOGY: Loading topology from file: {topology_file}")
                #    topology_apis_blueprint.logger.debug(f"GET_TOPOLOGY: Loaded topology from deployment file {topology_file}: {topology}")
                #    topology_apis_blueprint.logger.warning(f"GET_TOPOLOGY: No topologyFile found in deployment config")
                topology = deployment.get("topology")
            except Exception as e:
                topology_apis_blueprint.logger.error(f"GET_TOPOLOGY: Error loading deployment topology: {str(e)}")
        
        if not topology and scenario_name and scenario_name.strip():
            try:
                scenario_path = scenario_name
                if not scenario_path.endswith('.json'):
                    scenario_path += '.json'
                
                topology_apis_blueprint.logger.debug(f"GET_TOPOLOGY: Trying to load scenario: {scenario_path}")
                scenario = fs_manager.load_file(helpers.SCENARIO_DIRECTORY, scenario_path)
                
                if scenario and "topology" in scenario:
                    topology = scenario.get("topology")
                    topology_apis_blueprint.logger.debug(f"GET_TOPOLOGY: Found topology in scenario {scenario_name}")
                else:
                    topology_apis_blueprint.logger.debug(f"GET_TOPOLOGY: No topology found in scenario {scenario_name}")
            except Exception as e:
                topology_apis_blueprint.logger.error(f"GET_TOPOLOGY: Error loading scenario topology: {str(e)}")
        
        if not topology:
            topology_apis_blueprint.logger.warning(f"GET_TOPOLOGY: No topology found for deployment={deployment_id}, scenario={scenario_name}")
            return jsonify({"message": "No topology available"}), 404
        
        topology_apis_blueprint.logger.debug(f"GET_TOPOLOGY: Successfully returning topology data")
        return jsonify({"topology": topology}), 200
        
    except Exception as e:
        topology_apis_blueprint.logger.error(f"GET_TOPOLOGY: Error getting topology: {str(e)}")
        return jsonify({"message": f"Error getting topology: {str(e)}"}), 500
    

@topology_apis_blueprint.route("/generateTopology", methods=["POST"])
def generate_topology():
    data = request.get_json()
    topology = data["topology"]

    output_dir = helpers.GENERATED_TEMPLATE_DIRECTORY
    generator = TopologyGenerator(output_dir)

    # Generate the topology
    try:
        generator.generate(topology)
        return jsonify({"message": "Topology generated successfully"}), 200
    except Exception as e:
        topology_apis_blueprint.logger.error(f"Error generating topology: {str(e)}")
        return jsonify({"message": f"Error: {str(e)}"}), 500