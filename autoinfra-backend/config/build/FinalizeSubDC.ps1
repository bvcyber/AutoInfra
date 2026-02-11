param(
    [string]$domainName,
    [string]$parentDomainName
)

$logFilePath = "C:\Temp\DCFinalizeLog.txt"
Start-Transcript -Path $logFilePath -Append

$fullDomainName = "$domainName.$parentDomainName"
Write-Host "Running finalization for domain: $fullDomainName"

# Check if we're in the expected domain context
$currentDomain = (Get-WmiObject Win32_ComputerSystem).Domain
Write-Host "Current domain context: $currentDomain"

if ($currentDomain -ne $fullDomainName) {
    Write-Host "WARNING: Domain context doesn't match expected domain. Domain promotion may have failed."
    
    # Try to determine if we're a domain controller
    $isDC = $false
    try {
        $isDC = (Get-Service -Name "NTDS" -ErrorAction SilentlyContinue).Status -eq "Running"
        if ($isDC) {
            Write-Host "NTDS service is running - system appears to be a domain controller."
        } else {
            Write-Host "NTDS service not running - system does not appear to be a domain controller."
        }
    } catch {
        Write-Host "Error checking domain controller status: $_"
    }
    
    if (-not $isDC) {
        Write-Host "Machine doesn't appear to be a domain controller. Domain promotion may have failed."
        # You could add logic to retry the promotion here if needed
    }
}

# Force DNS registration
Write-Host "Forcing DNS registration..."
ipconfig /registerdns
nltest /dsregdns

# Force Netlogon to register all SRV records
Write-Host "Forcing Netlogon service restart and SRV record registration..."
Restart-Service NetLogon -Force
Start-Sleep -Seconds 10

# Initialize Kerberos settings
Write-Host "Initializing Kerberos settings..."
ksetup /SetRealmFlags $fullDomainName KDC_FLAG_KEY_DATA

# Restart key services
$services = @("NTDS", "DNS", "Netlogon", "KDC", "DFS", "DFSR", "IsmServ")
foreach ($service in $services) {
    try {
        if (Get-Service $service -ErrorAction SilentlyContinue) {
            Write-Host "Restarting service: $service"
            Restart-Service -Name $service -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
    } catch {
        Write-Host "Could not restart $service: $_"
    }
}

# Check replication status
Write-Host "Checking replication status:"
try {
    repadmin /replsummary
    repadmin /showrepl
    dcdiag /test:replications
} catch {
    Write-Host "Error running replication checks: $_"
}

# Verify domain controller health
Write-Host "Running DCDiag:"
try {
    dcdiag
} catch {
    Write-Host "Error running DCDiag: $_"
}

# Verify domain controller is properly registered in DNS
Write-Host "Checking DNS records for domain controller:"
try {
    $dcName = $env:COMPUTERNAME
    Resolve-DnsName -Name "$dcName.$fullDomainName" -Type A -ErrorAction Stop
} catch {
    Write-Host "Warning: Could not resolve DC in DNS: $_"
    
    # Try to register again
    Write-Host "Attempting to re-register DNS records..."
    ipconfig /registerdns
}

Write-Host "Domain controller finalization completed."
Stop-Transcript