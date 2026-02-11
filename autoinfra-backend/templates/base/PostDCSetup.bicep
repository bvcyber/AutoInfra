// This enables automatic SID inclusion in certificates for PKINIT

param location string
param resourceGroupName string
param domainControllers array
param enterpriseAdminUsername string
param domainName string

// Set UPN only on root domain controllers
resource setEnterpriseAdminUPN 'Microsoft.Compute/virtualMachines/runCommands@2023-07-01' = [for dc in domainControllers: if (dc.isRoot) {
  name: '${dc.name}/SetEnterpriseAdminUPN'
  location: location
  properties: {
    parameters: [
      {
        name: 'enterpriseAdminUsername'
        value: enterpriseAdminUsername
      }
      {
        name: 'domainName'
        value: domainName
      }
    ]
    source: {
      script: '''
        param(
          [string]$enterpriseAdminUsername,
          [string]$domainName
        )

        $logFilePath = "C:\Temp\logfile.txt"
        Add-Content -Path $logFilePath -Value "PostDCSetup: Setting enterprise admin UPN..."

        try {
          # Extract username from domain\username or username@domain format
          $username = $enterpriseAdminUsername
          if ($username -like "*\*") {
            $username = $username.Split('\')[1]
          } elseif ($username -like "*@*") {
            $username = $username.Split('@')[0]
          }

          $upn = "$username@$domainName"
          Set-ADUser $username -UserPrincipalName $upn
          Add-Content -Path $logFilePath -Value "PostDCSetup: Successfully set UPN for $username to $upn"
        } catch {
          Add-Content -Path $logFilePath -Value "PostDCSetup: Failed to set UPN: $_"
        }
      '''
    }
  }
}]
