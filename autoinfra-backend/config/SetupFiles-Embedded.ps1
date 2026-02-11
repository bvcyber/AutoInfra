
param(
    [string]$targetFiles,
    [string]$domainName
)

$logFilePath = "C:\Temp\logfile.txt"

$domainDN = ($domainName -split '\.' | ForEach-Object { "DC=$_" }) -join ','
Add-Content -Path $logFilePath -Value "Domain DN: $domainDN"

$targetFilesArray = $targetFiles -split ","

foreach ($file in $targetFilesArray)
{
    switch ($file)
    {
        'module'
        {
            Install-WindowsFeature -Name RSAT-AD-PowerShell
            $localFilePath = "C:\Temp\ADVulnEnvModule"
            $fileName = "C:\Temp\ADVulnEnvModule\ADVulnEnvModule.psm1"

            # Create directory if it doesn't exist
            New-Item -ItemType Directory -Path $localFilePath -Force | Out-Null

            Add-Content -Path $logFilePath -Value "=== EMBEDDED SETUP STARTED ==="
            Add-Content -Path $logFilePath -Value "Writing embedded module content to $fileName"

            # Module content embedded directly in script (will be replaced by bicep)
            $moduleContent = @'
__MODULE_CONTENT_PLACEHOLDER__
'@

            Add-Content -Path $logFilePath -Value "Module content size: $($moduleContent.Length) characters"

            # Write the embedded module content to file
            try {
                [System.IO.File]::WriteAllText($fileName, $moduleContent, [System.Text.Encoding]::UTF8)
                Add-Content -Path $logFilePath -Value "Module content written to $fileName"

                # Verify file was created
                if (Test-Path $fileName) {
                    $fileSize = (Get-Item $fileName).Length
                    Add-Content -Path $logFilePath -Value "Module file verified: $fileSize bytes"
                } else {
                    Add-Content -Path $logFilePath -Value "ERROR: Module file was not created at $fileName"
                }
            }
            catch {
                Add-Content -Path $logFilePath -Value "ERROR writing module file: $_"
                Add-Content -Path $logFilePath -Value "Exception type: $($_.Exception.GetType().FullName)"
                Add-Content -Path $logFilePath -Value "Exception message: $($_.Exception.Message)"
            }
        }
        'esc'
        {
            # Create ADCS files directory
            $adcsPath = "C:\Temp\adcs-files"
            New-Item -ItemType Directory -Path $adcsPath -Force | Out-Null
            Add-Content -Path $logFilePath -Value "=== ESC FILES SETUP STARTED ==="

            # ESC file contents embedded directly in script (will be replaced by bicep)
            $esc1Vuln = @'
__ESC1_VULN_PLACEHOLDER__
'@
            $esc1VulnSecurityDescriptor = @'
__ESC1_VULN_SD_PLACEHOLDER__
'@
            $esc3VulnAuthSignatures = @'
__ESC3_AUTH_SIG_PLACEHOLDER__
'@
            $esc3VulnRequestAgentSecurityDescriptor = @'
__ESC3_REQ_AGENT_SD_PLACEHOLDER__
'@
            $esc4VulnWrite = @'
__ESC4_VULN_PLACEHOLDER__
'@
            $esc3VulnRequestAgent = @'
__ESC3_REQ_AGENT_PLACEHOLDER__
'@
            $esc3VulnAuthSignaturesSecurityDescriptor = @'
__ESC3_AUTH_SIG_SD_PLACEHOLDER__
'@
            $esc4VulnWriteSecurityDescriptor = @'
__ESC4_VULN_SD_PLACEHOLDER__
'@

            # Replace hardcoded domain with actual domain DN
            $esc1Vuln = $esc1Vuln -replace 'DC=redteam,DC=lab', $domainDN
            $esc1VulnSecurityDescriptor = $esc1VulnSecurityDescriptor -replace 'DC=redteam,DC=lab', $domainDN
            $esc3VulnAuthSignatures = $esc3VulnAuthSignatures -replace 'DC=redteam,DC=lab', $domainDN
            $esc3VulnRequestAgentSecurityDescriptor = $esc3VulnRequestAgentSecurityDescriptor -replace 'DC=redteam,DC=lab', $domainDN
            $esc4VulnWrite = $esc4VulnWrite -replace 'DC=redteam,DC=lab', $domainDN
            $esc3VulnRequestAgent = $esc3VulnRequestAgent -replace 'DC=redteam,DC=lab', $domainDN
            $esc3VulnAuthSignaturesSecurityDescriptor = $esc3VulnAuthSignaturesSecurityDescriptor -replace 'DC=redteam,DC=lab', $domainDN
            $esc4VulnWriteSecurityDescriptor = $esc4VulnWriteSecurityDescriptor -replace 'DC=redteam,DC=lab', $domainDN

            Add-Content -Path $logFilePath -Value "Replaced hardcoded domain with $domainDN in all ESC templates"

            # Write each ESC .ldf file from embedded content
            $esc1Vuln | Set-Content -Path "$adcsPath\ESC1Vuln.ldf" -Force
            $esc1VulnSecurityDescriptor | Set-Content -Path "$adcsPath\ESC1VulnSecurityDescriptor.ldf" -Force
            $esc3VulnAuthSignatures | Set-Content -Path "$adcsPath\ESC3VulnAuthSignatures.ldf" -Force
            $esc3VulnRequestAgentSecurityDescriptor | Set-Content -Path "$adcsPath\ESC3VulnRequestAgentSecurityDescriptor.ldf" -Force
            $esc4VulnWrite | Set-Content -Path "$adcsPath\ESC4VulnWrite.ldf" -Force
            $esc3VulnRequestAgent | Set-Content -Path "$adcsPath\ESC3VulnRequestAgent.ldf" -Force
            $esc3VulnAuthSignaturesSecurityDescriptor | Set-Content -Path "$adcsPath\ESC3VulnAuthSignaturesSecurityDescriptor.ldf" -Force
            $esc4VulnWriteSecurityDescriptor | Set-Content -Path "$adcsPath\ESC4VulnWriteSecurityDescriptor.ldf" -Force

            Add-Content -Path $logFilePath -Value "Successfully wrote 8 ADCS template files to $adcsPath"
        }
        Default
        {
            Add-Content -Path $logFilePath -Value "Error: Unknown target file type '$file'"
        }
    }
}
