param vmName string

resource runPostBuild 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' ={
  name: '${vmName}/runPostBuild'
  location: 'eastus'
  properties:{
    source:{
      script: loadTextContent('../../config/PostBuild.ps1')
    }
  }
}
