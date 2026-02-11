param virtualMachineSize string
param location string
param deployOrBuild string
param resourceGroupName string
param privateIPAddress string
param rootDomainControllerPrivateIp string
param virtualMachineHostname string

param imageReference string = ''

param osDiskType string = ''
param localAdminUsername string = ''
@secure()
param localAdminPassword string = ''
param enterpriseAdminUsername string = ''
@secure()
param enterpriseAdminPassword string = ''
param domainName string = ''
param domainAndEnterpriseAdminUsername string = ''
param oldScenarios bool = false
param jumpboxPrivateIPAddress string = ''
param connectedPrivateIPAddress string = ''
param isVNet10Required bool = false
param isVNet172Required bool = false
param isVNet192Required bool = false
param hasPublicIP bool = false
param callerIPAddress string = ''
// Skip peering flag - used during Update mode when peerings already exist from locked nodes
param skipPeering bool = false

var isIP10 = startsWith(privateIPAddress, '10.10.')
var isIP172 = startsWith(privateIPAddress, '172.16.')
var isIP192 = startsWith(privateIPAddress, '192.168.')
var vName = oldScenarios ? 'lab-network' : (isIP10 ? 'vnet-10' : (isIP172 ? 'vnet-172' : 'vnet-192'))
var subnetName = oldScenarios ? 'root-subnet' : (isIP10 ? 'vnet-10/subnet-10' : (isIP172 ? 'vnet-172/subnet-172' : 'vnet-192/subnet-192'))

var currentNetwork = startsWith(privateIPAddress, '10.10.') ? '10' : (startsWith(privateIPAddress, '172.16.') ? '172' : '192')
var dcNetwork = startsWith(rootDomainControllerPrivateIp, '10.10.') ? '10' : (startsWith(rootDomainControllerPrivateIp, '172.16.') ? '172' : '192')
var requiresPeering = !empty(rootDomainControllerPrivateIp) && currentNetwork != dcNetwork && !skipPeering
var jumpboxNetwork = empty(jumpboxPrivateIPAddress) ? '00' : (startsWith(jumpboxPrivateIPAddress, '10.10.') ? '10' : (startsWith(jumpboxPrivateIPAddress, '172.16.') ? '172' : '192'))
var isJumpbox = !empty(privateIPAddress) && !empty(connectedPrivateIPAddress) && !empty(currentNetwork) && !empty(jumpboxNetwork) 
  ? privateIPAddress == connectedPrivateIPAddress && currentNetwork != jumpboxNetwork
  : false

resource virtualNetwork 'Microsoft.Network/virtualNetworks@2023-05-01' existing = {
  name: vName
  scope: resourceGroup(resourceGroupName)
}

// Reference to the existing subnet to place these resources
resource subnetReference 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' existing = {
  name: subnetName
  scope: resourceGroup(resourceGroupName)
}

var caPeeringRules = requiresPeering ? [
  {
    name: 'Allow-DC-to-CA-Inbound'
    properties: {
      description: 'Allows inbound traffic from Domain Controller'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: rootDomainControllerPrivateIp
      destinationAddressPrefix: privateIPAddress
      access: 'Allow'
      priority: 100
      direction: 'Inbound'
    }
  }
  {
    name: 'Allow-CA-to-DC-Outbound'
    properties: {
      description: 'Allows outbound traffic to Domain Controller'
      protocol: '*'
      sourcePortRange: '*'
      destinationPortRange: '*'
      sourceAddressPrefix: privateIPAddress
      destinationAddressPrefix: rootDomainControllerPrivateIp
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
      sourceAddressPrefix: startsWith(rootDomainControllerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(rootDomainControllerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
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
      destinationAddressPrefix: startsWith(rootDomainControllerPrivateIp, '10.10.') ? '10.10.0.0/24' : (startsWith(rootDomainControllerPrivateIp, '172.16.') ? '172.16.0.0/24' : '192.168.0.0/24')
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
    name: 'Allow-RDP-From-Public'
    properties: {
      description: 'Allows RDP from caller IP'
      protocol: 'Tcp'
      sourcePortRange: '*'
      destinationPortRange: '3389'
      sourceAddressPrefix: callerIPAddress
      destinationAddressPrefix: privateIPAddress
      access: 'Allow'
      priority: 102
      direction: 'Inbound'
    }
  }
] : []

var allNSGRules = concat(caPeeringRules, jumpboxRules, publicIPRules)

resource caNetworkSecurityGroup 'Microsoft.Network/networkSecurityGroups@2023-05-01' = if (!empty(allNSGRules)) {
  name: 'ca-nsg-${virtualMachineHostname}'
  location: location
  properties: {
    securityRules: allNSGRules
  }
}

resource publicIPAddress 'Microsoft.Network/publicIPAddresses@2023-05-01' = if (hasPublicIP) {
  name: '${virtualMachineHostname}-pip'
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    publicIPAllocationMethod: 'Dynamic'
    dnsSettings: {
      domainNameLabel: toLower('${virtualMachineHostname}-${uniqueString(resourceGroup().id)}')
    }
  }
}

// Certificate Authority network interface
resource networkInterface 'Microsoft.Network/networkInterfaces@2023-05-01' = {
  name: '${virtualMachineHostname}-NIC'
  location: location
  properties: {
    dnsSettings:{
      dnsServers:[
        rootDomainControllerPrivateIp
        '8.8.8.8'
      ]
    }
    ipConfigurations: [
      {
        name: 'ipconfigCA'
        properties: {
          privateIPAllocationMethod: 'Static'
          privateIPAddress: privateIPAddress
          subnet: {
            id: subnetReference.id
          }
          publicIPAddress: hasPublicIP ? {
            id: publicIPAddress.id
          } : null
        }
      }
    ]
    networkSecurityGroup: !empty(allNSGRules) ? {
      id: caNetworkSecurityGroup.id
    } : null
  }
  dependsOn: [ virtualNetwork ]
}

resource peeringCAToBC 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (requiresPeering) {
  name: 'vnet-${currentNetwork}/peer-to-${dcNetwork}'
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: resourceId('Microsoft.Network/virtualNetworks', 'vnet-${dcNetwork}')
    }
  }
  dependsOn: [networkInterface]
}

resource peeringDCToCA 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (requiresPeering) {
  name: 'vnet-${dcNetwork}/peer-to-${currentNetwork}'
  properties: {
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
    remoteVirtualNetwork: {
      id: resourceId('Microsoft.Network/virtualNetworks', 'vnet-${currentNetwork}')
    }
  }
  dependsOn: [networkInterface, peeringCAToBC]
}

resource peeringCAToJumpbox 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2023-05-01' = if (isJumpbox) {
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
    VM: 'CA:${resourceGroupName}'
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

resource buildVM 'Microsoft.Compute/virtualMachines@2023-07-01' = if (deployOrBuild == 'build'){
  name: virtualMachineHostname
  location: location
  tags:{
    VM: 'CA:${resourceGroupName}'
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

resource setupConfigurationFilesCA 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = if (deployOrBuild == 'build'){
  parent: buildVM
  name: 'setupConfigurationFilesCA'
  location: location
  properties:{
    parameters:[
      {
        name: 'targetFiles'
        value: 'module,esc'
      }
      {
        name: 'domainName'
        value: domainName
      }
    ]
    source:{
      script: replace(
        replace(
          replace(
            replace(
              replace(
                replace(
                  replace(
                    replace(
                      replace(
                        loadTextContent('../../config/SetupFiles-Embedded.ps1'),
                        '__MODULE_CONTENT_PLACEHOLDER__', loadTextContent('../../config/ADVulnEnvModule.psm1')
                      ),
                      '__ESC1_VULN_PLACEHOLDER__', loadTextContent('../../config/adcs-files/ESC1Vuln.ldf')
                    ),
                    '__ESC1_VULN_SD_PLACEHOLDER__', loadTextContent('../../config/adcs-files/ESC1VulnSecurityDescriptor.ldf')
                  ),
                  '__ESC3_AUTH_SIG_PLACEHOLDER__', loadTextContent('../../config/adcs-files/ESC3VulnAuthSignatures.ldf')
                ),
                '__ESC3_REQ_AGENT_SD_PLACEHOLDER__', loadTextContent('../../config/adcs-files/ESC3VulnRequestAgentSecurityDescriptor.ldf')
              ),
              '__ESC4_VULN_PLACEHOLDER__', loadTextContent('../../config/adcs-files/ESC4VulnWrite.ldf')
            ),
            '__ESC3_REQ_AGENT_PLACEHOLDER__', loadTextContent('../../config/adcs-files/ESC3VulnRequestAgent.ldf')
          ),
          '__ESC3_AUTH_SIG_SD_PLACEHOLDER__', loadTextContent('../../config/adcs-files/ESC3VulnAuthSignaturesSecurityDescriptor.ldf')
        ),
        '__ESC4_VULN_SD_PLACEHOLDER__', loadTextContent('../../config/adcs-files/ESC4VulnWriteSecurityDescriptor.ldf')
      )
    }
  }
  dependsOn: [ buildVM ]
}

// Joins the Domain
resource joinDomain 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' =  if (deployOrBuild == 'build'){
  parent: buildVM
  name: 'JoinDomain'
  location: location
  properties: {
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
  dependsOn: [ setupConfigurationFilesCA ]
}

resource certificateAuthorityConfigurationScript 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = if(deployOrBuild == 'build') {
  parent: buildVM
  name: 'CertificateAuthorityConfigurationScript'
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
    ]
    source: {
      script: loadTextContent('../../config/build/ConfigureCA.ps1')
    }
  }
  dependsOn: [ joinDomain ]
}

