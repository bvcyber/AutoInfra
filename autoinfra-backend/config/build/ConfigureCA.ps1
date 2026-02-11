param(
	[string]$enterpriseAdminUsername,
	[string]$enterpriseAdminPassword
)

$logFilePath = "C:\Temp\logfile.txt"

# Ensure C:\Temp directory exists
if (!(Test-Path "C:\Temp")) {
    New-Item -ItemType Directory -Path "C:\Temp" -Force | Out-Null
}

try {
    Add-Content -Path $logFilePath -Value "=== ConfigureCA.ps1 Script Started ==="
    Add-Content -Path $logFilePath -Value "Received username: $enterpriseAdminUsername"
    Add-Content -Path $logFilePath -Value "Password received: $($enterpriseAdminPassword.Length) characters"

    Add-Content -Path $logFilePath -Value "Creating credentials..."
    [securestring]$secureEnterpriseAdminPassword = ConvertTo-SecureString $enterpriseAdminPassword -AsPlainText -Force
    [pscredential]$enterpriseAdminCreds = New-Object System.Management.Automation.PSCredential ($enterpriseAdminUsername, $secureEnterpriseAdminPassword)
    Add-Content -Path $logFilePath -Value "Credentials created successfully"
} catch {
    Add-Content -Path $logFilePath -Value "FATAL: Failed to create credentials. $_"
    exit 1
}

try {
    Add-Content -Path $logFilePath -Value "Installing ADCS Windows Feature..."
    Add-WindowsFeature Adcs-Cert-Authority -IncludeManagementTools
    Add-Content -Path $logFilePath -Value "ADCS Windows Feature installed"

    Add-Content -Path $logFilePath -Value "Installing ADCS Certification Authority..."
    Install-AdcsCertificationAuthority -CAType EnterpriseRootCA -Credential $enterpriseAdminCreds -Force
    Add-Content -Path $logFilePath -Value "Successfully Installed ADCS."
} catch {
    Add-Content -Path $logFilePath -Value "Failed Installing ADCS. $_"
    Add-Content -Path $logFilePath -Value "Exception Type: $($_.Exception.GetType().FullName)"
}
try {
    Add-Content -Path $logFilePath -Value "Installing ADLDS Windows Feature..."
    Install-WindowsFeature ADLDS -IncludeManagementTools
    Add-Content -Path $logFilePath -Value "Successfully Installed ADLDS."
} catch {
    Add-Content -Path $logFilePath -Value "Failed installing ADLDS. $_"
}

Add-Content -Path $logFilePath -Value "=== ConfigureCA.ps1 Script Completed ==="
