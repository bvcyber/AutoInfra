targetScope = 'subscription'
param resourceGroupName string
param location string = 'eastus'
param scenarioTagValue string = 'Saved Deployment'
param galleryName string
param domainNameTag string = 'N/A'
param subscriptionID string
param machineObjects object
param timeout string
param resourceGroupID string



resource CreateResourceGroup 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags:{
    Scenario: scenarioTagValue
    expiryTimeout: timeout
  }
}

module CreateVMGallery 'base/VMGallery.bicep' = {
  scope: resourceGroup(resourceGroupName)
  name: 'CreateVMGallery'
  params:{
    location:location
    galleryName: galleryName
  }
  dependsOn: [ CreateResourceGroup ]
}

// TODO - make osType dynamic so linux images can be snapshotted
module CreateSnapshot 'base/VMSnapshot.bicep' = [ for machineObject in items(machineObjects): {
  scope: resourceGroup(resourceGroupName)
  name: 'Create${machineObject.value.Name}Snapshot'
  params:{
    location:location
    galleryName:galleryName
    imageDefinitionName:'${galleryName}/${machineObject.value.Name}'
    vmGalleryResourceGroup:resourceGroupName
    publisher: (machineObject.value.Name == 'JUMPBOX') ? 'kali-linux' : 'si-rtl-${machineObject.value.Name}'
    offer: (machineObject.value.Name == 'JUMPBOX') ? 'kali' : 'si-rtl-${machineObject.value.Name}'
    sku: (machineObject.value.Name == 'JUMPBOX') ? 'kali-2024-3' : 'si-rtl-${machineObject.value.Name}'
    osState: 'Specialized'
    osType: machineObject.value.OSType
    vmName: machineObject.value.Name
    versionName: '1.0.0'
    domainNameTag: domainNameTag
    subscriptionID: subscriptionID
    resourceGroupID: resourceGroupID
  }
  dependsOn:[ CreateVMGallery ]
}]

