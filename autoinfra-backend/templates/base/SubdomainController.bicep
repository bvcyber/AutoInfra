param location string
param privateIPAddress string
param virtualMachineSize string
param resourceGroupName string
param deployOrBuild string
param rootDomainControllerPrivateIp string
param virtualMachineHostname string

param imageReference string = ''

param domainName string = ''
param rootDomainNetBIOSName string = ''
param enterpriseAdminUsername string = ''
@secure()
param enterpriseAdminPassword string = ''
param rootDomainControllerFQDN string = ''
param subdomainName string = ''
param osDiskType string = ''

resource virtualNetwork 'Microsoft.Network/networkInterfaces@2023-05-01' existing = {
  name: 'lab-network'
  scope: resourceGroup(resourceGroupName)
}

// Reference to the existing subnet to place these resources
resource subnetReference 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' existing = {
  name: 'lab-network/root-subnet'
  scope: resourceGroup(resourceGroupName)
}

// Network Interface
resource networkInterface 'Microsoft.Network/networkInterfaces@2022-11-01' = {
  name: '${virtualMachineHostname}-NIC'
  location: location
  properties: {
    dnsSettings:{
      dnsServers:[
        rootDomainControllerPrivateIp
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
        }
      }
    ]
  }
  dependsOn: [ virtualNetwork ]
}

resource deployVM 'Microsoft.Compute/virtualMachines@2023-07-01' = if (deployOrBuild == 'deploy'){
  name: virtualMachineHostname
  location: location
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

resource buildVM 'Microsoft.Compute/virtualMachines@2022-11-01' = if (deployOrBuild == 'build'){
  name: virtualMachineHostname
  location: location
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
}

resource domainControllerConfigurationScript 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = if (deployOrBuild == 'build') {
  parent: buildVM
  name: 'InstallAndConfigureADDS'
  location: location
  properties: {
    parameters:[
      {
        name: 'enterpriseAdminUsername'
        value: enterpriseAdminUsername
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
      {
        name: 'subdomainName'
        value: subdomainName
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
}
