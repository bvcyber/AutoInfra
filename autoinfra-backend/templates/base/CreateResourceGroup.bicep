targetScope = 'subscription'

@description('Location for the resource group')
param location string

@description('Name of the resource group to be created.')
param name string

resource createResourceGroup 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: name
  location: location
}
