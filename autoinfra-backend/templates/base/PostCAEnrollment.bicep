
param location string
param resourceGroupName string
param domainControllers array
param caHostname string
param domainFQDN string
param domainNetBIOS string

// Trigger certificate enrollment on each domain controller
resource triggerDCEnrollment 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = [for dc in domainControllers: {
  name: '${dc.name}/TriggerCertEnrollment'
  location: location
  properties: {
    parameters: [
      {
        name: 'caHostname'
        value: caHostname
      }
      {
        name: 'domainFQDN'
        value: domainFQDN
      }
      {
        name: 'domainNetBIOS'
        value: domainNetBIOS
      }
    ]
    source: {
      script: '''
        param(
          [string]$caHostname,
          [string]$domainFQDN,
          [string]$domainNetBIOS
        )

        $logFilePath = "C:\Temp\logfile.txt"
        Add-Content -Path $logFilePath -Value "Post-CA: Requesting Domain Controller certificate for PKINIT support"

        gpupdate /force | Out-Null
        Start-Sleep -Seconds 5

        # Request the DomainControllerAuthentication template with explicit CA config (non-interactive)
        $caConfig = "$caHostname.$domainFQDN\$domainNetBIOS-$caHostname-CA"
        Add-Content -Path $logFilePath -Value "Post-CA: Using CA config: $caConfig"
        certreq -enroll -machine -q -config $caConfig DomainControllerAuthentication

        Add-Content -Path $logFilePath -Value "Post-CA: Domain Controller certificate enrollment completed"
      '''
    }
  }
}]
