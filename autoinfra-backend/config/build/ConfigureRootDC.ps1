param(
    [string]$domainName,
    [string]$enterpriseAdminUsername,
    [string]$enterpriseAdminPassword
)

$securePassword = ConvertTo-SecureString $enterpriseAdminPassword -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential ($enterpriseAdminUsername, $securePassword)

$logFilePath = "C:\Temp\logfile.txt"

try {
    Write-Host "Installing Active Directory Domain Services..."
    Install-WindowsFeature -Name AD-Domain-Services -IncludeManagementTools

    Write-Host "Configuring Root Domain Controller for $domainName..."
    Install-ADDSForest -DomainName $domainName -SafeModeAdministratorPassword $securePassword -Force
    # Wait for services to init
    #Start-Sleep -Seconds 60
    Restart-Service NetLogon -EA 0
    Add-Content -Path $logFilePath -Value "Successfully Installed ADDS."
    # Note: UPN for enterprise admin is set via separate PostDCSetup run-command
} catch {
    Write-Host "Failed to configure Root Domain Controller: $_"
    Add-Content -Path $logFilePath -Value "Failed Installing ADDS. $_"
}

