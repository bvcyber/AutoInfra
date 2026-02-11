from azure_clients import AzureClients
import helpers
import logging

azure_clients = AzureClients()
logger = logging.getLogger(helpers.LOGGER_NAME)
gallery_resource_group = helpers.VM_IMAGE_GALLERY_RESOURCE_GROUP
gallery_name = helpers.VM_IMAGE_GALLERY_NAME
location = helpers.LOCATION

def ensure_resource_group_exists(client, resource_group):
    try:
        if client.resource_groups.check_existence(resource_group):
            logger.info(f"ENSURE_RESOURCE_GROUP_EXISTS: Resource group {resource_group} exists.")
            return True
        else:
            logger.warning(f"ENSURE_RESOURCE_GROUP_EXISTS: Resource group {resource_group} does not exist. Creating..")
            client.resource_groups.create_or_update(resource_group, {"location": location})
            return True
    except Exception as e:
        logging.error(f"ENSURE_RESOURCE_GROUP_EXISTS: Error checking resource group {resource_group}. Full error: {e}")
        return False

def ensure_vm_gallery_exists(client):
    try:
        if client.galleries.get(gallery_resource_group, gallery_name):
            logger.info(f"VM_GALLERY_EXISTENCE_CHECK: Gallery {gallery_name} exists in resource group {gallery_resource_group}.")
            return True
    except Exception as e:
        logger.warning(f"VM_GALLERY_EXISTENCE_CHECK: Gallery {gallery_name} does not exist in resource group {gallery_resource_group}. Creating..")
        poller = client.galleries.begin_create_or_update(gallery_resource_group, gallery_name, {"location": location})
        poller.result()
        return True
    
def check_required_infrastructure():
    compute_client = azure_clients.get_compute_client()
    resource_client = azure_clients.get_resource_client()
    results = []
    try:
        results.append({"resource":"ResourceGroup", "exists": ensure_resource_group_exists(resource_client, gallery_resource_group)})
        results.append({"resource":"VMGallery", "exists": ensure_vm_gallery_exists(compute_client)})

        if all(r.get("exists") for r in results):
            logger.info("CHECK_REQUIRED_INFRASTRUCTURE: All required infrastructure exists.")
            return results
        else:
            logger.warning(f"CHECK_REQUIRED_INFRASTRUCTURE: Some required infrastructure is missing. Results: {results}")
        
        return results

    except Exception as e:
        logger.error(f"CHECK_REQUIRED_INFRASTRUCTURE: Error checking base infrastructure: {e}")
        return {"message": f"Error: {str(e)}", "results": results}

