import os
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.network import NetworkManagementClient
import logging
import helpers


class AzureClients:
    def __init__(self):
        self.credential = None
        self.subscription_id = None
        self.resource_client = None
        self.compute_client = None
        self.storage_client = None
        self.network_client = None
        self.logger = logging.getLogger(helpers.LOGGER_NAME)

    def get_credential(self):
        required_env = ["AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_SECRET"]
        missing = [key for key in required_env if not os.getenv(key)]
        if missing:
            self.logger.warning(f"Azure credentials not set. Missing: {', '.join(missing)}")
            return None 

        self.credential = ClientSecretCredential(
            tenant_id=os.environ["AZURE_TENANT_ID"],
            client_id=os.environ["AZURE_CLIENT_ID"],
            client_secret=os.environ["AZURE_CLIENT_SECRET"]
        )
        self.logger.info("Azure credential initialized.")

        return self.credential

    def get_subscription_id(self):
        if self.subscription_id is None:
            self.subscription_id =  os.getenv("AZURE_SUBSCRIPTION_ID")
        return self.subscription_id
    
    def get_auth_config(self):
        credential = self.get_credential()
        subscription_id = self.get_subscription_id()

        if not credential:
            raise RuntimeError("Azure credentials are not set in the environment.")
        if not subscription_id:
            raise RuntimeError("AZURE_SUBSCRIPTION_ID is not set.")
        
        return credential, subscription_id

    def get_resource_client(self):
        if self.resource_client is None:
            credential, subscription_id = self.get_auth_config()
            self.resource_client = ResourceManagementClient(credential, subscription_id)
        return self.resource_client
    
    def get_compute_client(self):
        if self.compute_client is None:
            credential, subscription_id = self.get_auth_config()
            self.compute_client = ComputeManagementClient(credential, subscription_id)
        return self.compute_client
    
    def get_storage_client(self):
        if self.storage_client is None:
            credential, subscription_id = self.get_auth_config()
            self.storage_client = StorageManagementClient(credential, subscription_id)
        return self.storage_client 
    
    def get_network_client(self):
        if self.network_client is None:
            credential, subscription_id = self.get_auth_config()
            self.network_client = NetworkManagementClient(credential, subscription_id)
        return self.network_client 
    
