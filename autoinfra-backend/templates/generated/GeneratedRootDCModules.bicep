
param location string = ''
param windowsVmSize string = ''
param vmDiskType string = ''
param resourceGroupName string = ''
param domainAndEnterpriseAdminUsername string = ''
param enterpriseAdminUsername string = ''
@secure()
param enterpriseAdminPassword string = ''
param deployOrBuild string = ''
param rootDomainNetBIOSName string = ''
param rootDomainControllerFQDN string = ''
param rootDomainControllers array = []
param subDomainControllers array = []
param standaloneServers array = []
param standaloneServerPrivateIp string = ''
param callerIPAddress string = ''
param domainControllerPrivateIp string = ''
param oldScenarios bool = false
param jumpboxPrivateIPAddress string = ''
param connectedPrivateIPAddress string = ''
param isVNet10Required bool = false
param isVNet192Required bool = false
param isVNet172Required bool = false
param osDiskType string = ''
param jumpboxAdminUsername string = ''
@secure()
param jumpboxAdminPassword string = ''
param kaliSku string = 'kali-2025-2'
param hasPublicIP bool = false


module RootDC_0 '../base/RootDomainController.bicep' = {
  name: 'RootDC_0'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    privateIPAddress: '10.10.0.9'
    virtualMachineSize: windowsVmSize
    virtualMachineHostname: 'DC01'
    resourceGroupName: resourceGroupName
    osDiskType: vmDiskType
    domainName: 'build.lab'
    domainAndEnterpriseAdminUsername: domainAndEnterpriseAdminUsername
    rootDomainNetBIOSName: 'build'
    enterpriseAdminUsername: enterpriseAdminUsername
    enterpriseAdminPassword: enterpriseAdminPassword
    deployOrBuild: deployOrBuild
    isRoot: true
    parentDomainControllerPrivateIp: ''
    oldScenarios: oldScenarios
    jumpboxPrivateIPAddress: jumpboxPrivateIPAddress
    connectedPrivateIPAddress: connectedPrivateIPAddress
    isVNet10Required: isVNet10Required
    isVNet192Required: isVNet192Required
    isVNet172Required: isVNet172Required
    hasPublicIP: false
    callerIPAddress: callerIPAddress
  }
}
