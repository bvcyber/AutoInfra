param galleryName string
param location string
param imageDefinitionName string
param vmGalleryResourceGroup string
param publisher string
param offer string
param sku string
param osState string
param osType string
param subscriptionID string
param vmName string
param versionName string
param serverType string = ''
param domainNameTag string
param resourceGroupID string = 'build'
// Actual marketplace plan info (for VMs from marketplace)
param planPublisher string = ''
param planProduct string = ''
param planName string = ''

resource VMGallery 'Microsoft.Compute/galleries@2021-10-01' existing = {
  name: galleryName
  scope: resourceGroup(vmGalleryResourceGroup)
}

resource ImageDefinition 'Microsoft.Compute/galleries/images@2021-10-01' = {
  name: imageDefinitionName
  location: location
  properties: {
    hyperVGeneration: 'V2'
    osType: osType
    osState: osState
    identifier: {
      publisher: publisher  // Custom identifier for uniqueness
      offer: offer         // Custom identifier for uniqueness
      sku: sku            // Custom identifier for uniqueness
    }
    // If source VM has marketplace plan, include it here
    purchasePlan: !empty(planPublisher) && !empty(planProduct) && !empty(planName) ? {
      name: planName           // Actual marketplace plan
      publisher: planPublisher // Actual marketplace plan
      product: planProduct     // Actual marketplace plan
    } : null
  }
  tags: {
    ServerType: serverType
    DomainName: domainNameTag
  }
  dependsOn: [ VMGallery ]
}

resource ImageDefinitionVersion 'Microsoft.Compute/galleries/images/versions@2023-07-03' = {
  name: '${imageDefinitionName}/${versionName}'
  location: location
  properties: {
    /*publishingProfile: {
      replicaCount: 1
      excludeFromLatest: false
      replicationMode: 'Full'
    }*/
    storageProfile: {
      source: {
        virtualMachineId: '/subscriptions/${subscriptionID}/resourceGroups/${resourceGroupID}/providers/Microsoft.Compute/virtualMachines/${vmName}'
      }
    }
  }
  dependsOn: [ ImageDefinition ]
}
