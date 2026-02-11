
param virtualMachineSize string
param location string
param deployOrBuild string
param standaloneServerPrivateIp string = ''
//param subDomainControllerPrivateIp string = ''
param resourceGroupName string
param virtualMachineHostname string
param rootDomainControllerPrivateIp string = ''
param imageReference string = ''
param osDiskType string = ''
param localAdminUsername string = 'localAdmin'
@secure()
param localAdminPassword string = 'localPassword#123'
@secure()
param enterpriseAdminPassword string = ''
param domainName string = ''
param domainAndEnterpriseAdminUsername string = ''
param rootOrSub string = ''
param rootDomainFqdn string = ''
param oldScenarios bool = false
param domainControllerPrivateIp string = ''
param jumpboxPrivateIPAddress string = ''
param connectedPrivateIPAddress string = ''
param hasPublicIP bool = false
param callerIPAddress string = ''
// Skip peering flag - used during Update mode when peerings already exist from locked nodes
param skipPeering bool = false
var parentJoinDomain = rootOrSub == 'sub' ? rootDomainFqdn : ''
param isVNet10Required bool = false
param isVNet172Required bool = false
param isVNet192Required bool = false

var isIP10 = startsWith(standaloneServerPrivateIp, '10.10.')
var isIP172 = startsWith(standaloneServerPrivateIp, '172.16.')
var isIP192 = startsWith(standaloneServerPrivateIp, '192.168.')
var vName = oldScenarios ? 'lab-network' : (isIP10 ? 'vnet-10' : (isIP172 ? 'vnet-172' : 'vnet-192'))
var subnetName = oldScenarios ? 'root-subnet' : (isIP10 ? 'vnet-10/subnet-10' : (isIP172 ? 'vnet-172/subnet-172' : 'vnet-192/subnet-192'))


var serverNetwork = startsWith(standaloneServerPrivateIp, '10.10.') ? '10' : (startsWith(standaloneServerPrivateIp, '172.16.') ? '172' : '192')
var dcNetwork = startsWith(domainControllerPrivateIp, '10.10.') ? '10' : (startsWith(domainControllerPrivateIp, '172.16.') ? '172' : '192')
var requiresPeering = serverNetwork != dcNetwork && !skipPeering
var jumpboxNetwork = empty(jumpboxPrivateIPAddress) ? '00' : (startsWith(jumpboxPrivateIPAddress, '10.10.') ? '10' : (startsWith(jumpboxPrivateIPAddress, '172.16.') ? '172' : '192'))
var isJumpbox = !empty(standaloneServerPrivateIp) && !empty(connectedPrivateIPAddress) && !empty(serverNetwork) && !empty(jumpboxNetwork) 
  ? standaloneServerPrivateIp == connectedPrivateIPAddress && serverNetwork != jumpboxNetwork
  : false

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
      sourceAddressPrefix: domainControllerPrivateIp
      destinationAddressPrefix: standaloneServerPrivateIp
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
      sourceAddressPrefix: standaloneServerPrivateIp
      destinationAddressPrefix: domainControllerPrivateIp
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
      sourceAddressPrefix: startsWith(standaloneServerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(standaloneServerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      destinationAddressPrefix: startsWith(standaloneServerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(standaloneServerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
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
      sourceAddressPrefix: startsWith(standaloneServerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(standaloneServerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      destinationAddressPrefix: startsWith(standaloneServerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(standaloneServerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
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
      sourceAddressPrefix: startsWith(domainControllerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(domainControllerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      destinationAddressPrefix: startsWith(standaloneServerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(standaloneServerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
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
      sourceAddressPrefix: startsWith(standaloneServerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(standaloneServerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
      destinationAddressPrefix: startsWith(domainControllerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(domainControllerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
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
      destinationAddressPrefix: standaloneServerPrivateIp
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
      sourceAddressPrefix: standaloneServerPrivateIp
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


// Network interface
resource networkInterface 'Microsoft.Network/networkInterfaces@2023-05-01' = {
  name: '${virtualMachineHostname}-NIC'
  location: location
  properties: {
    dnsSettings:{
      dnsServers:[
        domainControllerPrivateIp
        standaloneServerPrivateIp
        '8.8.8.8'
      ]
    }
    ipConfigurations: [
      {
      name: 'ipconfig'
      properties: {
        privateIPAllocationMethod: 'Static'
        privateIPAddress: standaloneServerPrivateIp
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
    dependsOn: [ virtualNetwork ]
}


resource peeringServerToDC 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (requiresPeering) {
  name: 'vnet-${serverNetwork}/peer-to-${dcNetwork}'
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: resourceId('Microsoft.Network/virtualNetworks', 'vnet-${dcNetwork}')
    }
  }
  dependsOn: [ networkInterface]
}

resource peeringDCToServer 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (requiresPeering) {
  name: 'vnet-${dcNetwork}/peer-to-${serverNetwork}'
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: resourceId('Microsoft.Network/virtualNetworks', 'vnet-${serverNetwork}')
    }
  }
  dependsOn: [ networkInterface]
}

resource peeringStandaloneToJumpbox 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (isJumpbox) {
  name: 'vnet-${serverNetwork}/peer-to-${jumpboxNetwork}'
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
    VM: 'Workstation:${resourceGroupName}' 
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
}

resource virtualMachine 'Microsoft.Compute/virtualMachines@2023-07-01' = if (deployOrBuild == 'build'){
  name: virtualMachineHostname
  location: location
  tags:{
    VM: 'Workstation:${resourceGroupName}'
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
      adminUsername: localAdminUsername
      adminPassword: localAdminPassword
      windowsConfiguration: {
        provisionVMAgent: true
      }
    }
  }
}

resource joinDomain 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = if (deployOrBuild == 'build'){
  parent: virtualMachine
  name: 'JoinDomain'
  location: location
  properties:{
    parameters:[
      {
        name: 'domainAndEnterpriseAdminUsername'
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
  
    ]
    source: {
      script: loadTextContent('../../config/build/JoinDomain.ps1')
    }
  }
}


resource setupConfigurationFiles 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = if (deployOrBuild == 'build'){
  parent: virtualMachine
  name: 'setupConfigurationFiles'
  location: location
  dependsOn: [
    joinDomain
  ]
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
}


