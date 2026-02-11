targetScope = 'subscription'

/// Network & Subnet Parameters
param vnetName string
param vnetAddressPrefix string
param rootSubnetAddressPrefix string
param expiryTimeout string

/// IP Parameters
param rootDomainControllerPrivateIp string
param certificateAuthorityPrivateIp string? // Optional
param standaloneServerPrivateIp string? // Optional

/// VM Configuration Parameters
param windowsVmSize string
param jumpboxVmSize string
param vmDiskType string

param rootDCName string
param caName string = '' // Optional
param rootStandaloneServerName string? // Optional
param jumpBoxName string

param rootDomainNetBIOSName string
param rootDomainControllerFQDN string
param enterpriseAdminUsername string
@secure()
param enterpriseAdminPassword string
param caAdminUsername string? // Optional
@secure()
param caAdminPassword string? // Optional
param standaloneServerUsername string? // Optional
@secure()
param standaloneServerPassword string? // Optional
param resourceGroupName string
param location string
param domainName string
param scenarioTagValue string
param deployOrBuild string = 'build'
param subscriptionID string
param vmGalleryName string
param vmGalleryResourceGroup string
param jumpboxImageReference string
param rootOrSub string = ''// New parameter for dynamic value

// Construct username in UPN format (user@rootdomain.fqdn) for AD authentication
// UPN format is required for child domain operations as it uses DNS resolution
// Always use root domain - enterprise admin account exists in root, not child domains
var domainAndEnterpriseAdminUsername = '${enterpriseAdminUsername}@${rootDomainControllers[0].domainName}'
param rootDomainFqdn string = ''
param standaloneServers array = []
param rootDomainControllers array = []
param subDomainControllers array = []
param certificateAuthorities array = []
param jumpboxConfig array = []
param connectedPrivateIPAddress string = ''
param jumpboxPrivateIPAddress string = ''
param callerIPAddress string = ''
param kaliSku string = 'kali-2025-2'
var allDomainControllers = concat(rootDomainControllers, subDomainControllers)

var rootDomainControllerIPs = [for rootDC in rootDomainControllers: rootDC.privateIPAddress]
var subDomainControllerIPs = [for subDC in subDomainControllers: subDC.privateIPAddress]
var jumpboxIPs = [for jumpbox in jumpboxConfig: jumpbox.jumpboxPrivateIPAddress]
var allDomainControllerIPs = concat(rootDomainControllerIPs, subDomainControllerIPs)

var allStandaloneServersIPs = [for srv in standaloneServers: srv.privateIPAddress]
var allCAIPs = [for ca in certificateAuthorities: ca.privateIPAddress]

var allIP = concat(allDomainControllerIPs, allStandaloneServersIPs, allCAIPs)
var allIPs = concat(allIP,jumpboxIPs)
var all10IPs = [for ip in allIPs: contains(string(ip), '10.10.') ? ip : null]
var all10IPsFiltered = filter(all10IPs, ip => ip != null)
var isVNet10Required = length(all10IPsFiltered) > 0

var all192IPs = [for ip in allIPs: contains(string(ip), '192.168.') ? ip : null]
var all192IPsFiltered = filter(all192IPs, ip => ip != null)
var isVNet192Required = length(all192IPsFiltered) > 0

var all172IPs = [for ip in allIPs: contains(string(ip), '172.16.') ? ip : null]
var all172IPsFiltered = filter(all172IPs, ip => ip != null)
var isVNet172Required = length(all172IPsFiltered) > 0


resource createResourceGroup 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags:{
    Scenario: scenarioTagValue
    expiryTimeout: expiryTimeout
  }
}



module vnet10 '../templates/base/VirtualNetwork.bicep' = if (isVNet10Required) {
  name: 'vnet-10'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    vnetName: 'vnet-10'
    virtualNetworkAddressPrefix: '10.10.0.0/16'
    rootSubnetAddressPrefix: '10.10.0.0/24'
  }
  dependsOn: [createResourceGroup]
}

module vnet192 '../templates/base/VirtualNetwork.bicep' = if (isVNet192Required) {
  name: 'vnet-192'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    vnetName: 'vnet-192'
    virtualNetworkAddressPrefix: '192.168.0.0/16'
    rootSubnetAddressPrefix: '192.168.0.0/24'
  }
  dependsOn: [createResourceGroup]
}


module vnet172 '../templates/base/VirtualNetwork.bicep' = if (isVNet172Required) {
  name: 'vnet-172'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    vnetName: 'vnet-172'
    virtualNetworkAddressPrefix: '172.16.0.0/16'
    rootSubnetAddressPrefix: '172.16.0.0/24'
  }
  dependsOn: [createResourceGroup]
}




module generatedRootDCModules './generated/GeneratedRootDCModules.bicep' = {
  name: 'GeneratedRootDCModules'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    windowsVmSize: windowsVmSize
    vmDiskType: vmDiskType
    resourceGroupName: resourceGroupName
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    deployOrBuild: deployOrBuild
    jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
    connectedPrivateIPAddress: connectedPrivateIPAddress
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
  }
  dependsOn: [
    vnet10
    vnet172
    vnet192
  ]
}

var subDCCount = length(subDomainControllers)

// Dynamically generated Sub Domain Controllers
module generatedSubDCModules './generated/GeneratedSubDCModules.bicep' = {
  name: 'GeneratedSubDCModules'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    windowsVmSize: windowsVmSize
    vmDiskType: vmDiskType
    resourceGroupName: resourceGroupName
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    deployOrBuild: deployOrBuild
    rootDomainControllerFQDN: rootDomainControllerFQDN
    rootDomainControllers: rootDomainControllers
    jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
    connectedPrivateIPAddress: connectedPrivateIPAddress
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
  }
  dependsOn: [
    generatedRootDCModules
  ]
}

module postDCSetup './base/PostDCSetup.bicep' = if (length(rootDomainControllers) > 0) {
  name: 'PostDCSetup'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    resourceGroupName: resourceGroupName
    domainControllers: allDomainControllers
    enterpriseAdminUsername: enterpriseAdminUsername
    domainName: join(skip(split(rootDomainControllerFQDN, '.'), 1), '.')
  }
  dependsOn: [
    generatedRootDCModules
  ]
}

module generatedCAModules './generated/GeneratedCAModules.bicep' = if (length(certificateAuthorities) > 0) {
  name: 'GeneratedCAModules'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    windowsVmSize: windowsVmSize
    vmDiskType: vmDiskType
    resourceGroupName: resourceGroupName
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    deployOrBuild: deployOrBuild
    jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
    connectedPrivateIPAddress: connectedPrivateIPAddress
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
  }
  dependsOn: [
    generatedRootDCModules  // CA must wait for root DC to be ready
  ]
}

module triggerDCCertEnrollment './base/PostCAEnrollment.bicep' = if (length(certificateAuthorities) > 0) {
  name: 'TriggerDCCertEnrollment'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    resourceGroupName: resourceGroupName
    domainControllers: allDomainControllers
    caHostname: certificateAuthorities[0].name
    // Extract domain from DC FQDN (e.g., "DC01.build.lab" -> "build.lab")
    domainFQDN: join(skip(split(rootDomainControllerFQDN, '.'), 1), '.')
    domainNetBIOS: rootDomainNetBIOSName
  }
  dependsOn: [
    generatedCAModules
  ]
}

module CreateAndConfigureCA './base/CertificateAuthority.bicep' = if (!empty(caName)) {
  name: 'CreateAndConfigureCA'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: caName
    resourceGroupName: resourceGroupName
    osDiskType: vmDiskType
    rootDomainControllerPrivateIp: rootDomainControllerPrivateIp
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    domainName: domainName
    deployOrBuild: deployOrBuild
    privateIPAddress: certificateAuthorityPrivateIp
    localAdminUsername: caAdminUsername
    localAdminPassword: caAdminPassword
    jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
    connectedPrivateIPAddress: connectedPrivateIPAddress
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
  }
  dependsOn: [
    generatedRootDCModules
  ]
}

module generatedStandaloneModules './generated/GeneratedStandaloneModules.bicep' = {
  name: 'GeneratedStandaloneModules'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    windowsVmSize: windowsVmSize
    vmDiskType: vmDiskType
    resourceGroupName: resourceGroupName
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    deployOrBuild: deployOrBuild
    jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
    connectedPrivateIPAddress: connectedPrivateIPAddress
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
  }
  dependsOn: [
    generatedSubDCModules
  ]
}

module generatedJumpboxModules './generated/GeneratedJumpboxModules.bicep' = if (length(jumpboxConfig) > 0) {
  name: 'GeneratedJumpboxModules'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    resourceGroupName: resourceGroupName
    deployOrBuild: deployOrBuild
    isVNet10Required: isVNet10Required
    isVNet172Required: isVNet172Required
    isVNet192Required: isVNet192Required
    kaliSku: kaliSku
    jumpboxPrivateIPAddress: jumpboxConfig[0].jumpboxPrivateIPAddress
    connectedPrivateIPAddress: jumpboxConfig[0].connectedPrivateIPAddress
    osDiskType: vmDiskType
    jumpboxAdminUsername: 'redteamer'
    jumpboxAdminPassword: 'Password#123'
  }
  dependsOn: [
    vnet10
    vnet172
    vnet192
  ]
}


module RunPostBuild './base/PostBuild.bicep' = if (!empty(caName)){
  name: 'RunPostBuild'
  scope: resourceGroup(resourceGroupName)
  params: {
    vmName: rootDCName
  }
  dependsOn: [CreateAndConfigureCA]
}

var rootDCObjects = [for rootDC in rootDomainControllers: {
  name: rootDC.name
  serverType: 'RootDC'
}]

var subDCObjects = [for subDC in subDomainControllers: {
  name: subDC.name
  serverType: 'SubDC'
}]

var standaloneServerObjects = [for srv in standaloneServers: {
  name: srv.name
  serverType: 'Standalone'
}]



var caObject = !empty(caName) && caName != '' ? [
  {
    name: caName
    serverType: 'CA'
  }
] : []

var serverObjects = concat(rootDCObjects, subDCObjects, standaloneServerObjects, caObject)

