@description('Location for resources to be deployed')
param location string

@description('VM Name')
param vmName string

@description('VM Size')
param vmSize string

@description('Resouce group name to deploy to')
param resourceGroupName string

param referenceID string = ''

@description('Private IP Address for the Jumpbox')
param jumpboxPrivateIPAddress string = '10.10.0.45'

@description('Connected Private IP Address for peering')
param connectedPrivateIPAddress string = ''

param deployOrBuild string = 'build'
param osDiskType string = 'Standard_LRS'

@description('Kali Linux SKU version (e.g., kali-2025-2)')
param kaliSku string = 'kali-2025-2'

@description('Image reference ID for custom Jumpbox snapshot (optional - if provided, uses snapshot instead of marketplace)')
param imageReference string = ''

@description('Flag for old scenarios')
param oldScenarios bool = false
param isVNet10Required bool = false
param isVNet172Required bool = false
param isVNet192Required bool = false

param jumpboxAdminUsername string = 'redteamer'
@secure()
param jumpboxAdminPassword string = 'Password#123'

@description('IP address of the caller initiating the build - will be granted full access')
param callerIPAddress string = ''

var isIP10 = startsWith(jumpboxPrivateIPAddress, '10.10.')
var isIP172 = startsWith(jumpboxPrivateIPAddress, '172.16.')
var isIP192 = startsWith(jumpboxPrivateIPAddress, '192.168.')
var vName = oldScenarios ? 'lab-network' : (isIP10 ? 'vnet-10' : (isIP172 ? 'vnet-172' : 'vnet-192'))
var subnetName = oldScenarios ? 'root-subnet' : (isIP10 ? 'vnet-10/subnet-10' : (isIP172 ? 'vnet-172/subnet-172' : 'vnet-192/subnet-192'))

var jumpboxNetwork = oldScenarios ? '' : (startsWith(jumpboxPrivateIPAddress, '10.10.') ? '10' : (startsWith(jumpboxPrivateIPAddress, '172.16.') ? '172' : '192'))
var connectedNetwork = oldScenarios ? '' : (startsWith(connectedPrivateIPAddress, '10.10.') ? '10' : (startsWith(connectedPrivateIPAddress, '172.16.') ? '172' : '192'))
var requiresPeering = oldScenarios ? false : (jumpboxNetwork != connectedNetwork)
var oldScenarioIP = oldScenarios ? '10.10.0.37' : ''
var privateIPAddress = oldScenarios ? oldScenarioIP : jumpboxPrivateIPAddress

resource virtualNetwork 'Microsoft.Network/virtualNetworks@2023-05-01' existing = {
  name: vName
  scope: resourceGroup(resourceGroupName)
}

resource subnetReference 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' existing = {
  name: subnetName
  scope: resourceGroup(resourceGroupName)
}

resource jumpboxPublicIP 'Microsoft.Network/publicIPAddresses@2023-05-01' = {
  name: 'jumpbox-public-ip'
  location: location
  sku: {
    name: 'Basic'
    tier: 'Regional'
  }
  properties:{
    publicIPAllocationMethod: 'Dynamic'
  }
}

var baseSecurityRules = [
  {
    name: 'Inbound-SSH-from-Caller'
    properties: {
      description: 'Allows SSH access from the caller IP address'
      protocol: 'TCP'
      sourcePortRange: '*'
      destinationPortRange: '22'
      sourceAddressPrefix: !empty(callerIPAddress) ? callerIPAddress : '0.0.0.0/0'
      destinationAddressPrefix: '*'
      access: 'Allow'
      priority: 100
      direction: 'Inbound'
    }
  }
  {
    name: 'Inbound-RDP-from-Caller'
    properties: {
      description: 'Allows RDP access from the caller IP address'
      protocol: 'TCP'
      sourcePortRange: '*'
      destinationPortRange: '3389'
      sourceAddressPrefix: !empty(callerIPAddress) ? callerIPAddress : '0.0.0.0/0'
      destinationAddressPrefix: '*'
      access: 'Allow'
      priority: 101
      direction: 'Inbound'
    }
  }
  {
    name: 'Outbound-Internet-Access'
    properties: {
      description: 'Allows outbound internet access for apt-install and updates'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: '*'
      destinationAddressPrefix: 'Internet'
      access: 'Allow'
      priority: 100
      direction: 'Outbound'
    }
  }
  // NOTE: Outbound-VirtualNetwork-Access removed - it was too permissive (allowed traffic to ALL peered VNets)
]

var peeringSecurityRules = [
  {
    name: 'Allow-ConnectedIP-All-Inbound'
    properties: {
      description: 'Allows all inbound traffic from connected private IP'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: connectedPrivateIPAddress
      destinationAddressPrefix: jumpboxPrivateIPAddress
      access: 'Allow'
      priority: 105
      direction: 'Inbound'
    }
  }
  {
    name: 'Allow-ConnectedIP-All-Outbound'
    properties: {
      description: 'Allows all outbound traffic to connected private IP'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: jumpboxPrivateIPAddress
      destinationAddressPrefix: connectedPrivateIPAddress
      access: 'Allow'
      priority: 105
      direction: 'Outbound'
    }
  }
  {
    name: 'Deny-All-Inbound'
    properties: {
      description: 'Denies all other inbound traffic'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: '*'
      destinationAddressPrefix: jumpboxPrivateIPAddress
      access: 'Deny'
      priority: 4000
      direction: 'Inbound'
    }
  }
  {
    name: 'Deny-All-Outbound'
    properties: {
      description: 'Denies all other outbound traffic'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: jumpboxPrivateIPAddress
      destinationAddressPrefix: '*'
      access: 'Deny'
      priority: 4000
      direction: 'Outbound'
    }
  }
]


var allSecurityRules = requiresPeering && !empty(connectedPrivateIPAddress) ? concat(baseSecurityRules, peeringSecurityRules) : baseSecurityRules

resource jumpboxNetworkSecurityGroup 'Microsoft.Network/networkSecurityGroups@2023-05-01' = {
  name: 'jumpbox-nsg-${vmName}'
  location: location
  properties: {
    securityRules: allSecurityRules
  }
}



// Network Interface
resource jumpboxNIC 'Microsoft.Network/networkInterfaces@2023-05-01' = {
  name: 'test-nic-JUMPBOX'
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfigJumpbox'
        properties: {
          privateIPAllocationMethod: 'Static'
          privateIPAddress: privateIPAddress
          publicIPAddress: {
            id: jumpboxPublicIP.id
          }
          subnet: {
            id: subnetReference.id
          }
          primary: true
          privateIPAddressVersion: 'IPv4'
        }
      }
    ]
    networkSecurityGroup: {
      id: jumpboxNetworkSecurityGroup.id
    }
    nicType: 'Standard'
  }
  dependsOn: [virtualNetwork]
}

resource peeringToConnected 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (requiresPeering) {
  name: 'vnet-${jumpboxNetwork}/peer-to-${connectedNetwork}'
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: resourceId('Microsoft.Network/virtualNetworks', 'vnet-${connectedNetwork}')
    }
  }
  dependsOn: [jumpboxNIC]
}

resource deployJumpbox 'Microsoft.Compute/virtualMachines@2023-07-01' = if (deployOrBuild == 'deploy' && empty(imageReference)) {
  name: vmName
  location: location
  tags:{
    VM: 'Jumpbox:${resourceGroupName}'
  }
  plan: {
    name: kaliSku
    publisher: 'kali-linux'
    product: 'kali'
  }
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: vmName
      adminUsername: jumpboxAdminUsername
      adminPassword: jumpboxAdminPassword
      linuxConfiguration: {
        disablePasswordAuthentication: false
        provisionVMAgent: true
      }
      customData: base64(loadTextContent('../../config/build/JumpboxCloudInit.yml'))
    }
    storageProfile: {
      imageReference: {
        publisher: 'kali-linux'
        offer: 'kali'
        sku: kaliSku
        version: 'latest'
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: jumpboxNIC.id
        }
      ]
    }
  }
}

resource deployJumpboxFromSnapshot 'Microsoft.Compute/virtualMachines@2023-07-01' = if (deployOrBuild == 'deploy' && !empty(imageReference)) {
  name: vmName
  location: location
  tags:{
    VM: 'Jumpbox:${resourceGroupName}'
  }
  plan: {
    name: kaliSku
    publisher: 'kali-linux'
    product: 'kali'
  }
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    storageProfile: {
      imageReference: {
        id: imageReference
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: jumpboxNIC.id
        }
      ]
    }
  }
}

resource buildJumpox 'Microsoft.Compute/virtualMachines@2023-07-01' = if (deployOrBuild == 'build'){
  name: vmName
  location: location
  tags:{
    VM: 'Jumpbox:${resourceGroupName}'
  }
  plan: { 
    name: kaliSku
    publisher: 'kali-linux'
    product: 'kali'
  }
  properties: { 
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: 'Jumpbox'
      adminUsername: 'redteamer'
      adminPassword: 'Password#123'
      linuxConfiguration: {
        disablePasswordAuthentication: false
        provisionVMAgent: true
      }
      customData: base64(loadTextContent('../../config/build/JumpboxCloudInit.yml'))
    }
    storageProfile: {
      osDisk: { 
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: osDiskType
        }
      }
      imageReference:{ 
        publisher: 'kali-linux'
        offer: 'kali'
        sku: kaliSku
        version: 'latest'
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: jumpboxNIC.id
        }
      ]
    }
  }
  dependsOn: [ virtualNetwork ]
}


output debugDeployOrBuild string = deployOrBuild
output debugJumpboxIP string = jumpboxPrivateIPAddress
output debugConnectedIP string = connectedPrivateIPAddress
output debugRequiresPeering bool = requiresPeering
output debugJumpboxNetwork string = jumpboxNetwork
output debugConnectedNetwork string = connectedNetwork
