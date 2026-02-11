targetScope = 'subscription'

param location string // Mandatory
param DC01ImageReferenceID string = '' // Optional
param DC02ImageReferenceID string = '' // Optional
param rootDCName string = ''
param CA01ImageReferenceID string = '' // Optional
param SRV01ImageReferenceID string = '' // Optional
param SRV02ImageReferenceID string = '' // Optional
param JUMPBOXImageReferenceID string = '' // Optional
param enterpriseAdminUsername string // Mandatory
@secure()
param enterpriseAdminPassword string // Mandatory
param caAdminUsername string = '' // Optional
param caName string = ''
param rootStandaloneServerName string = ''
@secure()
param caAdminPassword string = '' // Optional
param standaloneAdminUsername string = '' // Optional
@secure()
param standaloneAdminPassword string = '' // Optional
param subscriptionID string = '' // Optional
param deployResourceGroupName string = '' // Mandatory
param scenarioTagValue string = '' // Mandatory
param expiryTimestamp string = '' // Mandatory
param randomPort string = '' // Optional
param rootOrSub string = ''
param rootDomainFqdn string = ''
param rootDomainName string = ''
param subDCName string = ''
param subStandaloneServerName string = ''
param subDomainName string = ''
param rootDomainNetBIOSName string = ''
param rootDomainControllers array = []
param subDomainControllers array = []
param standaloneServers array = []
param certificateAuthorities array = []
param jumpboxConfig array = []
param callerIPAddress string = ''
param kaliSku string = 'kali-2025-2'


var connectedPrivateIPAddress = length(jumpboxConfig) > 0 ? jumpboxConfig[0].connectedPrivateIPAddress : ''
var jumpboxPrivateIPAddress = length(jumpboxConfig) > 0 ? jumpboxConfig[0].jumpboxPrivateIPAddress : ''


// Assumes at least one root domain controller exists
var firstRootDC = length(rootDomainControllers) > 0 ? rootDomainControllers[0] : {}
var rootDomainNameVar = contains(firstRootDC, 'domainName') ? firstRootDC.domainName : ''

var rootDomainControllerFQDN = contains(firstRootDC, 'name') && rootDomainNameVar != '' ? '${firstRootDC.name}.${rootDomainNameVar}' : ''
var rootDomainNetBIOSNameVar = contains(firstRootDC, 'netbios') ? firstRootDC.netbios : ''



var vnetName = 'lab-network'
var vnetAddressPrefix = '10.10.0.0/16'
var rootSubnetAddressPrefix = '10.10.0.0/24'
var rootDCIP = '10.10.0.10'
var subDCIP = '10.10.0.20'
var caIP = '10.10.0.15'
var windowsVmSize = 'Standard_B1ms'
var jumpboxVmSize = 'Standard_B2s'
var standaloneVmSize = 'Standard_B2s'
var vmDiskType = 'Standard_LRS'
var jumpboxName = 'JUMPBOX'
var vmGalleryName = 'TestBuilds'
var vmGalleryResourceGroup = 'TestBuilds'
var buildResourceGroupName = 'build'

@description('Scenario name for metadata and logging - not used in deployment logic')
param scenarioSelection string

module BuildLab 'BuildMachines.bicep' = {
  name: 'BuildLab-${uniqueString(deployResourceGroupName)}'
  scope: subscription()
  params: {
    location: location
    vnetName: vnetName
    vnetAddressPrefix: vnetAddressPrefix
    rootSubnetAddressPrefix: rootSubnetAddressPrefix
    windowsVmSize: windowsVmSize
    vmDiskType: vmDiskType
    rootDomainControllers: rootDomainControllers
    subDomainControllers: subDomainControllers
    standaloneServers: standaloneServers
    certificateAuthorities: certificateAuthorities
    jumpBoxName: jumpboxName
    rootDomainControllerPrivateIp: rootDomainControllers[0].privateIPAddress // Fixed to access the first element
    rootDCName: firstRootDC.name
    domainName: rootDomainNameVar
    rootDomainControllerFQDN: rootDomainControllerFQDN
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    jumpboxImageReference: JUMPBOXImageReferenceID
    jumpboxVmSize: jumpboxVmSize
    resourceGroupName: deployResourceGroupName
    vmGalleryName: vmGalleryName
    vmGalleryResourceGroup: vmGalleryResourceGroup
    subscriptionID: subscriptionID
    scenarioTagValue: scenarioTagValue
    expiryTimeout: expiryTimestamp
    rootDomainNetBIOSName: rootDomainNetBIOSNameVar
    connectedPrivateIPAddress: connectedPrivateIPAddress
    jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
    jumpboxConfig: jumpboxConfig
    callerIPAddress: callerIPAddress
    kaliSku: kaliSku
  }
}


// debug outputs
output debugJumpboxConfigReceived array = jumpboxConfig
output debugConnectedPrivateIPAddress string = connectedPrivateIPAddress
output debugJumpboxPrivateIPAddress string = jumpboxPrivateIPAddress
