from flask import Blueprint, request, jsonify
import json
from azure_clients import AzureClients
from azure_setup import AzureSetup
from deployments import Deployments
import helpers
import fs_manager
import command_runner
import logging

auth_apis_blueprint = Blueprint('auth_apis', __name__)
azure_clients = AzureClients()
deployment_handler = Deployments()
azure_setup = AzureSetup()
auth_apis_blueprint.logger = logging.getLogger(helpers.LOGGER_NAME)

@auth_apis_blueprint.route('/checkAuth', methods=['GET'])
def check_auth():
    return jsonify(azure_setup.check_auth())

@auth_apis_blueprint.route('/azureAuth', methods=['POST'])
def azure_auth():
    data = json.loads(request.data.decode('utf-8'))
    client_id = data["azServicePrincipalID"]
    client_secret = data["azServicePrincipalPassword"]
    tenant_id = data["azTenant"]
    subscription_id = data["azSubscriptionID"]
    result = azure_setup.azure_auth(client_id, client_secret, tenant_id, subscription_id)

    if result.get("message") == "success":
        auth_apis_blueprint.logger.info("AZURE_AUTH: Running health check after successful authentication...")
        deployment_handler.check_health_of_deployments()

    return jsonify(result)

@auth_apis_blueprint.route("/getJumpboxCreds",methods=["GET"])
def get_jumpbox_creds():
    config = helpers.load_config()
    user = config["jumpboxUser"]
    passwd = config["jumpboxPassword"]
    return jsonify({"message":f"{user}:{passwd}"})