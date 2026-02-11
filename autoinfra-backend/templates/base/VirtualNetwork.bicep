@description('Region to deploy vnet.')
param location string

param virtualNetworkAddressPrefix string = ''

param rootSubnetAddressPrefix string = ''

@description('Virtual Network name.')
param vnetName string = ''
param oldScenarios bool = false

var subnetName = oldScenarios ? 'root-subnet' : (vnetName == 'vnet-10' ? 'subnet-10' : (vnetName == 'vnet-172' ? 'subnet-172' : (vnetName == 'vnet-192' ? 'subnet-192' : '')))



resource createVnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name: vnetName
  location: location
  properties:{
    addressSpace:{
      addressPrefixes:[
        virtualNetworkAddressPrefix
      ]
    }
    subnets: [
      {
        name: subnetName
        properties:{
          addressPrefix: rootSubnetAddressPrefix
        }
      }
    ]
  }
}
