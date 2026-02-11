
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

