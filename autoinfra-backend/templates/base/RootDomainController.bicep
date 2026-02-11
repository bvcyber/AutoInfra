param virtualMachineSize string
param location string
param deployOrBuild string
param resourceGroupName string
param privateIPAddress string
param virtualMachineHostname string
param parentDomainControllerPrivateIp string = '' // New parameter for parent DC's private IP

param imageReference string = ''

param osDiskType string = ''
param domainName string = ''
param rootDomainNetBIOSName string = ''
param enterpriseAdminUsername string = ''
@secure()
param enterpriseAdminPassword string = ''
param isRoot bool = true
param domainAndEnterpriseAdminUsername string = ''
param rootDomainControllerFQDN string = ''
param jumpboxPrivateIPAddress string = ''
param connectedPrivateIPAddress string = ''
param isVNet10Required bool = false
param isVNet172Required bool = false
param isVNet192Required bool = false
param hasPublicIP bool = false
param callerIPAddress string = ''

output debugIsRoot bool = isRoot

// Calculate the parent domain by removing the leftmost subdomain
var parentDomainName = !empty(domainName) ? join(skip(split(domainName, '.'), 1), '.') : ''

// Add these variables before the network interface resource
var isIP10 = startsWith(privateIPAddress, '10.10.')
var isIP172 = startsWith(privateIPAddress, '172.16.')
var isIP192 = startsWith(privateIPAddress, '192.168.')
var vName = oldScenarios ? 'lab-network' : (isIP10 ? 'vnet-10' : (isIP172 ? 'vnet-172' : 'vnet-192'))
var subnetName = oldScenarios ? 'root-subnet' : (isIP10 ? 'vnet-10/subnet-10' : (isIP172 ? 'vnet-172/subnet-172' : 'vnet-192/subnet-192'))

var currentNetwork = startsWith(privateIPAddress, '10.10.') ? '10' : (startsWith(privateIPAddress, '172.16.') ? '172' : '192')
var parentNetwork = startsWith(parentDomainControllerPrivateIp, '10.10.') ? '10' : (startsWith(parentDomainControllerPrivateIp, '172.16.') ? '172' : '192')
var requiresPeering = !empty(parentDomainControllerPrivateIp) && currentNetwork != parentNetwork
var jumpboxNetwork = empty(jumpboxPrivateIPAddress) ? '00' : (startsWith(jumpboxPrivateIPAddress, '10.10.') ? '10' : (startsWith(jumpboxPrivateIPAddress, '172.16.') ? '172' : '192'))
var isJumpbox = !empty(privateIPAddress) && !empty(connectedPrivateIPAddress) && !empty(currentNetwork) && !empty(jumpboxNetwork) 
  ? privateIPAddress == connectedPrivateIPAddress && currentNetwork != jumpboxNetwork
  : false
param oldScenarios bool = false



resource virtualNetwork 'Microsoft.Network/networkInterfaces@2023-05-01' existing = {
  name: vName
  scope: resourceGroup(resourceGroupName)
}

// Reference to the existing subnet to place these resources
resource subnetReference 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' existing = {
  name: subnetName
  scope: resourceGroup(resourceGroupName)
}




var dcPeeringRules = requiresPeering ? [
  {
    name: 'Allow-SpecificDC-Communication-Inbound'
    properties: {
      description: 'Allows inbound traffic between specific DCs'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: parentDomainControllerPrivateIp
      destinationAddressPrefix: privateIPAddress
      access: 'Allow'
      priority: 100
      direction: 'Inbound'
    }
  }
  {
    name: 'Allow-SpecificDC-Communication-Outbound'
    properties: {
      description: 'Allows outbound traffic between specific DCs'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: privateIPAddress
      destinationAddressPrefix: parentDomainControllerPrivateIp
      access: 'Allow'
      priority: 100
      direction: 'Outbound'
    }
  }
  {
    name: 'Allow-IntraSubnet-Inbound'
    properties: {
      description: 'Allows all inbound traffic within same subnet'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: startsWith(privateIPAddress, '10.10.') ? '10.10.0.0/24' : (startsWith(privateIPAddress, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      destinationAddressPrefix: startsWith(privateIPAddress, '10.10.') ? '10.10.0.0/24' : (startsWith(privateIPAddress, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      access: 'Allow'
      priority: 200
      direction: 'Inbound'
    }
  }
  {
    name: 'Allow-IntraSubnet-Outbound'
    properties: {
      description: 'Allows all outbound traffic within same subnet'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: startsWith(privateIPAddress, '10.10.') ? '10.10.0.0/24' : (startsWith(privateIPAddress, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      destinationAddressPrefix: startsWith(privateIPAddress, '10.10.') ? '10.10.0.0/24' : (startsWith(privateIPAddress, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      access: 'Allow'
      priority: 200
      direction: 'Outbound'
    }
  }
  {
    name: 'Deny-CrossSubnet-Inbound'
    properties: {
      description: 'Denies all other inbound cross-subnet traffic'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: startsWith(parentDomainControllerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(parentDomainControllerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      destinationAddressPrefix: startsWith(privateIPAddress, '10.10.') ? '10.10.0.0/24' : (startsWith(privateIPAddress, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      access: 'Deny'
      priority: 4000
      direction: 'Inbound'
    }
  }
  {
    name: 'Deny-CrossSubnet-Outbound'
    properties: {
      description: 'Denies all other outbound cross-subnet traffic'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: startsWith(privateIPAddress, '10.10.') ? '10.10.0.0/24' : (startsWith(privateIPAddress, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      destinationAddressPrefix: startsWith(parentDomainControllerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(parentDomainControllerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      access: 'Deny'
      priority: 4000
      direction: 'Outbound'
    } 
  }
] : []

var jumpboxRules = isJumpbox ? [
  {
    name: 'Allow-Jumpbox-Communication-Inbound'
    properties: {
      description: 'Allows inbound traffic from jumpbox'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: jumpboxPrivateIPAddress
      destinationAddressPrefix: privateIPAddress
      access: 'Allow'
      priority: 150
      direction: 'Inbound'
    }
  }
  {
    name: 'Allow-Jumpbox-Communication-Outbound'
    properties: {
      description: 'Allows outbound traffic to jumpbox'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: privateIPAddress
      destinationAddressPrefix: jumpboxPrivateIPAddress
      access: 'Allow'
      priority: 150
      direction: 'Outbound'
    }
  }
] : []

var publicIPRules = hasPublicIP ? [
  {
    name: 'Allow-RDP-from-Caller'
    properties: {
      description: 'Allows RDP access from the caller IP address'
      protocol: 'TCP'
      sourcePortRange: '*'
      destinationPortRange: '3389'
      sourceAddressPrefix: !empty(callerIPAddress) ? callerIPAddress : '0.0.0.0/0'
      destinationAddressPrefix: '*'
      access: 'Allow'
      priority: 100
      direction: 'Inbound'
    }
  }
  {
    name: 'Outbound-Internet-Access'
    properties: {
      description: 'Allows outbound internet access'
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
] : []


var allNSG = concat(dcPeeringRules, jumpboxRules, publicIPRules)


resource combinedNSG 'Microsoft.Network/networkSecurityGroups@2023-05-01' = if (!empty(allNSG)){
  name: 'combined-nsg-${virtualMachineHostname}'
  location: location
  properties: {
    securityRules: allNSG
  }
}

resource publicIP 'Microsoft.Network/publicIPAddresses@2023-05-01' = if (hasPublicIP) {
  name: '${virtualMachineHostname}-public-ip'
  location: location
  sku: {
    name: 'Basic'
    tier: 'Regional'
  }
  properties: {
    publicIPAllocationMethod: 'Dynamic'
  }
}


// Network Interface
resource networkInterface 'Microsoft.Network/networkInterfaces@2022-11-01' = {
  name: '${virtualMachineHostname}-NIC'
  location: location
  properties: {
    dnsSettings:{
      dnsServers:[
        privateIPAddress
        '8.8.8.8'
      ]
    }
    ipConfigurations: [
      {
        name: 'ipconfig'
        properties: {
          privateIPAllocationMethod: 'Static'
          privateIPAddress: privateIPAddress
          subnet: {
            id: subnetReference.id
          }
          publicIPAddress: hasPublicIP ? {
            id: publicIP.id
          } : null
        }
      }
    ]
    networkSecurityGroup: !empty(allNSG) ? {
      id: combinedNSG.id
    } : null
  }
  dependsOn: [virtualNetwork]
}


resource peeringCurrentToParent 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (requiresPeering) {
  name: 'vnet-${currentNetwork}/peer-to-${parentNetwork}'
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: resourceId('Microsoft.Network/virtualNetworks', 'vnet-${parentNetwork}')
    }
  }
  dependsOn: [networkInterface]
}

resource peeringParentToCurrent 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (requiresPeering) {
  name: 'vnet-${parentNetwork}/peer-to-${currentNetwork}'
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: resourceId('Microsoft.Network/virtualNetworks', 'vnet-${currentNetwork}')
    }
  }
  dependsOn: [networkInterface
  peeringCurrentToParent]
}

resource peeringControllerToJumpbox 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (isJumpbox) {
  name: 'vnet-${currentNetwork}/peer-to-${jumpboxNetwork}'
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: resourceId('Microsoft.Network/virtualNetworks', 'vnet-${jumpboxNetwork}')
    }
  }
  dependsOn: [networkInterface]
}




resource deployVM 'Microsoft.Compute/virtualMachines@2023-07-01' = if (deployOrBuild == 'deploy'){
  name: virtualMachineHostname
  location: location
  tags:{
    VM: 'RootDC:${resourceGroupName}'
  }
  properties: {
    hardwareProfile: {
      vmSize: virtualMachineSize
    }
    storageProfile: {
      imageReference: {
        id: imageReference
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: networkInterface.id
        }
      ]
    }
  }
  dependsOn: [ virtualNetwork ]
}

resource buildVM 'Microsoft.Compute/virtualMachines@2022-11-01' = if (deployOrBuild == 'build'){
  name: virtualMachineHostname
  location: location
  tags:{
    VM: 'RootDC:${resourceGroupName}'
  }
  properties: {
    hardwareProfile: {
      vmSize: virtualMachineSize
    }
    storageProfile: {
      osDisk: {
        createOption: 'fromImage'
        managedDisk: {
          storageAccountType: osDiskType
        }
      }
      imageReference: {
        publisher: 'MicrosoftWindowsServer'
        offer: 'WindowsServer'
        sku: '2022-datacenter-g2'
        version: 'latest'
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: networkInterface.id
        }
      ]
    }
    osProfile: {
      computerName: virtualMachineHostname
      adminUsername: enterpriseAdminUsername
      adminPassword: enterpriseAdminPassword
      windowsConfiguration: {
        provisionVMAgent: true
      }
    }
  }
  dependsOn: [ virtualNetwork ]
}

resource rootDomainControllerConfigurationScript 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = if (isRoot && deployOrBuild == 'build') {
  parent: buildVM
  name: 'ConfigureRootDC'
  location: location
  properties: {
    parameters:[
      {
        name: 'enterpriseAdminUsername'
        value: domainAndEnterpriseAdminUsername
      }
      {
        name: 'enterpriseAdminPassword'
        value: enterpriseAdminPassword
      }
      {
        name: 'domainName'
        value: domainName
      }
      {
        name: 'rootDomainNetBIOSName'
        value: rootDomainNetBIOSName
      }
    ]
    source: {
      script: loadTextContent('../../config/build/ConfigureRootDC.ps1')
    }
  }
  dependsOn: [ buildVM ]
}

resource subDomainControllerConfigurationScript 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = if (!isRoot && deployOrBuild == 'build') {
  parent: buildVM
  name: 'ConfigureSubDC'
  location: location
  properties: {
    parameters:[
      {
        name: 'enterpriseAdminUsername'
        value: domainAndEnterpriseAdminUsername
      }
      {
        name: 'enterpriseAdminPassword'
        value: enterpriseAdminPassword
      }
      {
        name: 'domainName'
        value: split(domainName, '.')[0] // Extract the leftmost portion of the domain name
      }
      {
        name: 'parentDomainName'
        value: parentDomainName
      }
      {
        name: 'rootDomainNetBIOSName'
        value: rootDomainNetBIOSName
      }
      {
        name: 'rootDomainControllerFQDN'
        value: rootDomainControllerFQDN
      }
    ]
    source: {
      script: loadTextContent('../../config/build/ConfigureSubDC.ps1')
    }
  }
  dependsOn: [ buildVM
  rootDomainControllerConfigurationScript ]
}

resource setupConfigurationFiles 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = if (deployOrBuild == 'build'){
  parent: buildVM
  name: 'setupConfigurationFiles'
  location: location

  properties:{
    parameters:[
      {
        name: 'targetFiles'
        value: 'module'
      }
    ]
    source:{
      script: replace(loadTextContent('../../config/SetupFiles-Embedded.ps1'), '__MODULE_CONTENT_PLACEHOLDER__', loadTextContent('../../config/ADVulnEnvModule.psm1'))
    }
  }
  dependsOn: [ buildVM, rootDomainControllerConfigurationScript ]
}





