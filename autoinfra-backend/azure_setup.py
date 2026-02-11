import os
import logging
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import SubscriptionClient
import helpers

class AzureSetup:
    def __init__(self):
        self.logger = logging.getLogger(helpers.LOGGER_NAME)

    def set_env_with_creds(self, client_id, client_secret, tenant_id, subscription_id):
        os.environ["AZURE_CLIENT_ID"] = client_id
        os.environ["AZURE_CLIENT_SECRET"] = client_secret
        os.environ["AZURE_TENANT_ID"] = tenant_id
        os.environ["AZURE_SUBSCRIPTION_ID"] = subscription_id
        self.logger.info("SET_ENV_WITH_CREDS: Environment variables set.")


    def validate_creds(self, client_id, client_secret, tenant_id, subscription_id):
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
        sub_client = SubscriptionClient(credential)
        subs = list(sub_client.subscriptions.list())
        valid_ids = [sub.subscription_id for sub in subs]

        if subscription_id not in valid_ids:
            raise Exception(f"Provided subscription ID {subscription_id} is not valid.")

        return {"credential": credential, "subscriptionId": subscription_id}

    def azure_auth(self, client_id, client_secret, tenant_id, subscription_id):
        try:
            self.validate_creds(client_id, client_secret, tenant_id, subscription_id)
            self.set_env_with_creds(client_id, client_secret, tenant_id, subscription_id)

            self.logger.info(f"AZURE_AUTH: Successfully authenticated to subscription {subscription_id}")
            helpers.update_config_value("azureAuth", "true")
            return {"message": "success", "subscriptionId": subscription_id}

        except Exception as e:
            self.logger.error(f"AZURE_AUTH: Authentication failed: {e}")
            helpers.update_config_value("azureAuth", "false")
            return {"message": f"error: {str(e)}"}
        
    def check_auth(self):
        try:
            keys = ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID"]
            env = {key: os.getenv(key) for key in keys}
            if not all(env.values()):
                raise Exception("Missing environment variables")

            self.validate_creds(
                env["AZURE_CLIENT_ID"],
                env["AZURE_CLIENT_SECRET"],
                env["AZURE_TENANT_ID"],
                env["AZURE_SUBSCRIPTION_ID"]
            )

            self.logger.info("CHECK_AUTH: Successfully validated credentials.")
            return {"message": "Authorized"}

        except Exception as e:
            self.logger.error(f"CHECK_AUTH: Failed: {e}")
            return {"message": "Not authorized"}
        
    def is_authenticated(self) -> bool:
        return self.check_auth().get("message") == "Authorized"