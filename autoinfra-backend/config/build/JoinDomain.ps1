param(
    [string]$domainName,                   # The FQDN of the domain to join (e.g., dev.build.lab or build.lab
    [string]$domainAndEnterpriseAdminUsername,      # Domain admin user e.g., build\admin
    [string]$enterpriseAdminPassword                # Plain text password for domain join
)


[securestring]$enterpriseAdminPassword = ConvertTo-SecureString $enterpriseAdminPassword -AsPlainText -Force
[pscredential]$enterpriseAdminCreds = New-Object System.Management.Automation.PSCredential ($domainAndEnterpriseAdminUsername, $enterpriseAdminPassword)


$logFilePath = "C:\Temp\logfile.txt"

# Ensure C:\Temp directory exists
if (!(Test-Path "C:\Temp")) {
    New-Item -ItemType Directory -Path "C:\Temp" -Force | Out-Null
}

Add-Content -Path $logFilePath -Value "=== JoinDomain.ps1 Script Started ==="
Add-Content -Path $logFilePath -Value "Target domain: $domainName"

$joinedDomain = $false
$maxAttempts = 10
$attempt = 0

while (!$joinedDomain -and $attempt -lt $maxAttempts){
	$attempt++
	Add-Content -Path $logFilePath -Value "Attempt $attempt of $maxAttempts to join domain..."

	try {
		# Join domain WITHOUT automatic restart to maintain run-command control
		Add-Computer -DomainName $domainName -Credential $enterpriseAdminCreds -Force -ErrorAction Stop
		Add-Content -Path $logFilePath -Value "Add-Computer command completed successfully"

		# Verify the join was successful
		$currentDomain = (Get-CimInstance Win32_ComputerSystem).Domain
		Add-Content -Path $logFilePath -Value "Current domain after join: $currentDomain"

		if ($currentDomain -eq $domainName){
			$joinedDomain = $true
			Add-Content -Path $logFilePath -Value "Successfully joined domain $domainName"

			# Now restart the computer for domain join to take full effect
			Add-Content -Path $logFilePath -Value "Restarting computer to complete domain join..."
			Restart-Computer -Force
			break
		} else {
			Add-Content -Path $logFilePath -Value "Domain join command completed but domain is $currentDomain, not $domainName. Retrying..."
			Start-Sleep -Seconds 30
		}
	} catch {
		Add-Content -Path $logFilePath -Value "Error joining the $domainName domain (attempt $attempt): $_"
		Add-Content -Path $logFilePath -Value "Exception Type: $($_.Exception.GetType().FullName)"
		Start-Sleep -Seconds 30
	}
}

if (!$joinedDomain) {
	Add-Content -Path $logFilePath -Value "FATAL: Failed to join domain after $maxAttempts attempts"
	exit 1
}

Add-Content -Path $logFilePath -Value "=== JoinDomain.ps1 Script Completed ==="
