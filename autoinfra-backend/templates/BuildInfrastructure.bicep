targetScope = 'subscription'

param resourceGroupName string
param location string
param scenarioTagValue string
param galleryName string
param domainNameTag string
param subscriptionID string
param sourceResourceGroupName string // Resource group where VMs are located
param imageNamePrefix string = '' // Prefix for image names (defaults to sourceResourceGroupName if not provided)
param serverObjects array // Array of objects with name and serverType
param kaliSku string = 'kali-2025-2' // Kali Linux SKU for Jumpbox snapshots
param versionName string = '1.0.0' // Version number for image snapshots

var effectiveImagePrefix = !empty(imageNamePrefix) ? imageNamePrefix : sourceResourceGroupName

resource CreateResourceGroup 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags:{
    Scenario: scenarioTagValue
  }
}

module CreateVMGallery 'base/VMGallery.bicep' = {
  scope: resourceGroup(resourceGroupName)
  name: 'CreateVMGallery'
  params:{
    location: location
    galleryName: galleryName
  }
  dependsOn: [ CreateResourceGroup ]
}

module CreateSnapshot 'base/VMSnapshot.bicep' = [ for serverObject in serverObjects: if (!empty(serverObject.name)) {
  scope: resourceGroup(resourceGroupName)
  name: 'Create${contains(serverObject, 'imageName') ? serverObject.imageName : serverObject.name}Snapshot'
  params:{
    location: location
    galleryName: galleryName
    imageDefinitionName: '${galleryName}/${effectiveImagePrefix}-${contains(serverObject, 'imageName') ? serverObject.imageName : serverObject.name}'
    vmGalleryResourceGroup: resourceGroupName
    publisher: 'si-rtl-${effectiveImagePrefix}-${contains(serverObject, 'imageName') ? serverObject.imageName : serverObject.name}'
    offer: (serverObject.serverType == 'Jumpbox') ? 'kali-${effectiveImagePrefix}-${contains(serverObject, 'imageName') ? serverObject.imageName : serverObject.name}' : 'windows-server-${effectiveImagePrefix}-${contains(serverObject, 'imageName') ? serverObject.imageName : serverObject.name}'
    sku: (serverObject.serverType == 'Jumpbox') ? 'kali-${effectiveImagePrefix}-${contains(serverObject, 'imageName') ? serverObject.imageName : serverObject.name}' : 'datacenter-${effectiveImagePrefix}-${contains(serverObject, 'imageName') ? serverObject.imageName : serverObject.name}'
    osState: 'Specialized'
    osType: (serverObject.serverType == 'Jumpbox') ? 'Linux' : 'Windows'
    vmName: serverObject.name
    versionName: versionName
    serverType: serverObject.serverType
    domainNameTag: domainNameTag
    subscriptionID: subscriptionID
    resourceGroupID: sourceResourceGroupName
    // Pass actual marketplace plan for Jumpbox
    planPublisher: (serverObject.serverType == 'Jumpbox') ? 'kali-linux' : ''
    planProduct: (serverObject.serverType == 'Jumpbox') ? 'kali' : ''
    planName: (serverObject.serverType == 'Jumpbox') ? kaliSku : ''
  }
  dependsOn: [ CreateVMGallery ]
}]