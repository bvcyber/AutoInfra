param(
    [string]$domainName,
    [string]$parentDomainName,
    [string]$enterpriseAdminUsername,
    [string]$enterpriseAdminPassword,
    [string]$rootDomainControllerFQDN
)

[securestring]$secureAdminPassword = ConvertTo-SecureString $enterpriseAdminPassword -AsPlainText -Force

# Use the root domain credential as passed (UPN format: buildadmin@build.lab)
# This works once trust relationship is established between parent and root
[pscredential]$enterpriseAdminCreds = New-Object System.Management.Automation.PSCredential ($enterpriseAdminUsername, $secureAdminPassword)
[pscredential]$enterpriseAdminCredsWithDomain = New-Object System.Management.Automation.PSCredential ($enterpriseAdminUsername, $secureAdminPassword)

Write-Host "Using credential: $enterpriseAdminUsername"

$logFilePath = "C:\Temp\logfile.txt"
Start-Transcript -Path $logFilePath -Append

try {
    Write-Host "Installing Active Directory Domain Services..."
    Install-WindowsFeature AD-Domain-Services, rsat-adds -IncludeAllSubFeature

    # DNS resolution retry logic - up to 60 minutes (120 * 30 seconds)
    $maxAttempts = 120
    $attempt = 0
    $dnsResolved = $false

    while ($attempt -lt $maxAttempts -and -not $dnsResolved) {
        try {
            Write-Host "Attempt $($attempt + 1): Resolving $parentDomainName..."
            Resolve-DnsName -Name $parentDomainName -ErrorAction Stop | Out-Null
            $dnsResolved = $true
            Write-Host "Successfully resolved $parentDomainName"
        } catch {
            Write-Host "Could not resolve $parentDomainName. Retrying in 30 seconds..."
            Start-Sleep -Seconds 30
            $attempt++
        }
    }

    if (-not $dnsResolved) {
        throw "DNS resolution for $parentDomainName failed after $maxAttempts attempts."
    }

    # Wait for parent domain controller to be ready (ping + LDAP bind)
    $maxWaitSeconds = 3600
    $interval = 30
    $elapsed = 0
    $parentDomainReady = $false

    while ($elapsed -lt $maxWaitSeconds -and -not $parentDomainReady) {
        try {
            Write-Host "Checking if parent domain controller ($rootDomainControllerFQDN) is reachable..."

            if (Test-Connection -ComputerName $rootDomainControllerFQDN -Count 1 -Quiet) {
                Write-Host "Ping successful. Attempting LDAP bind to $parentDomainName..."
                $ds = [System.DirectoryServices.ActiveDirectory.Domain]::GetDomain(
                    (New-Object System.DirectoryServices.ActiveDirectory.DirectoryContext('Domain', $parentDomainName))
                )
                Write-Host "LDAP bind succeeded. Parent domain controller is ready."
                $parentDomainReady = $true
            } else {
                Write-Host "$rootDomainControllerFQDN is not reachable. Retrying..."
            }
        } catch {
            Write-Host "Parent domain controller not ready yet: $_"
        }

        if (-not $parentDomainReady) {
            Start-Sleep -Seconds $interval
            $elapsed += $interval
        }
    }

    if (-not $parentDomainReady) {
        throw "Timed out waiting for parent domain controller to be ready."
    }

    # Poll until credential can authenticate THROUGH the parent domain controller
    # This ensures the parent DC's trust relationship and replication are complete
    # We authenticate against the parent DC using root domain credentials
    $maxCredAttempts = 120  # Up to 60 minutes (120 * 30 seconds)
    $credAttempt = 0
    $credentialReady = $false
    
    Write-Host "Waiting for parent DC to be able to validate root domain credentials..."
    Write-Host "Testing: Can $rootDomainControllerFQDN authenticate $enterpriseAdminUsername?"
    
    while ($credAttempt -lt $maxCredAttempts -and -not $credentialReady) {
        try {
            Write-Host "Attempt $($credAttempt + 1): Testing credential authentication through parent DC..."
            
            # Connect to the PARENT domain controller and authenticate with root domain creds
            # This proves the parent DC can forward authentication to the root domain (trust is working)
            $ldapPath = "LDAP://$rootDomainControllerFQDN"
            $directoryEntry = New-Object System.DirectoryServices.DirectoryEntry(
                $ldapPath,
                $enterpriseAdminUsername,
                $enterpriseAdminPassword
            )
            
            # Force authentication by accessing a property
            $null = $directoryEntry.distinguishedName
            
            if ($directoryEntry.distinguishedName) {
                Write-Host "Credential validation succeeded! Parent DC can authenticate root domain credentials."
                Write-Host "Trust relationship between parent and root domain is ready."
                $credentialReady = $true
                $directoryEntry.Close()
            } else {
                throw "DirectoryEntry returned but no distinguishedName"
            }
        } catch {
            Write-Host "Parent DC cannot yet validate root credentials: $_"
            Write-Host "Retrying in 30 seconds..."
            Start-Sleep -Seconds 30
            $credAttempt++
        }
    }
    
    if (-not $credentialReady) {
        throw "Timed out waiting for parent DC to validate credentials. Trust relationship may not be established."
    }
    
    # Extract the root domain from the enterprise admin username (e.g., buildadmin@build.lab -> build.lab)
    $rootDomainFromUsername = $enterpriseAdminUsername.Split('@')[1]
    $usernameOnly = $enterpriseAdminUsername.Split('@')[0]
    
    # CRITICAL: Ensure DNS is pointing ONLY to the parent DC
    # Azure NIC DNS settings may not be applied yet - force it
    # Do NOT include 8.8.8.8 as it can cause SRV lookups to fail
    Write-Host "Ensuring DNS client is configured to use parent DC ONLY..."
    Write-Host "Resolving parent DC IP from: $rootDomainControllerFQDN"
    
    try {
        $parentDcIp = (Resolve-DnsName -Name $rootDomainControllerFQDN -Type A -ErrorAction Stop | 
                       Where-Object { $_.Type -eq 'A' } | 
                       Select-Object -First 1).IPAddress
        Write-Host "Parent DC IP resolved: $parentDcIp"
        
        # Get the active network adapter and set DNS to ONLY the parent DC
        $activeAdapter = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | Select-Object -First 1
        if ($activeAdapter) {
            Write-Host "Setting DNS server on adapter '$($activeAdapter.InterfaceAlias)' to $parentDcIp ONLY"
            Set-DnsClientServerAddress -InterfaceAlias $activeAdapter.InterfaceAlias -ServerAddresses @($parentDcIp)
            
            # Flush DNS cache to ensure fresh lookups
            Write-Host "Flushing DNS cache..."
            ipconfig /flushdns | Out-Null
            
            # Verify the change
            $currentDns = (Get-DnsClientServerAddress -InterfaceAlias $activeAdapter.InterfaceAlias -AddressFamily IPv4).ServerAddresses
            Write-Host "DNS servers now set to: $($currentDns -join ', ')"
        }
    } catch {
        Write-Host "Warning: Could not set DNS server dynamically: $_"
        Write-Host "Continuing with existing DNS settings..."
    }
    
    # Check required SRV records that DCPromo needs
    # Include both parent domain AND forest root records for deep hierarchies
    Write-Host "Checking required SRV records..."
    
    # Parent domain SRV records
    $requiredSrvRecords = @(
        "_ldap._tcp.dc._msdcs.$parentDomainName",
        "_kerberos._tcp.$parentDomainName",
        "_ldap._tcp.$parentDomainName"
    )
    
    # Add forest root records if parent domain != root domain (deep hierarchy)
    if ($parentDomainName -ne $rootDomainFromUsername) {
        Write-Host "Deep hierarchy detected: parent=$parentDomainName, root=$rootDomainFromUsername"
        Write-Host "Adding forest root SRV record checks..."
        $requiredSrvRecords += @(
            "_ldap._tcp.dc._msdcs.$rootDomainFromUsername",
            "_kerberos._tcp.$rootDomainFromUsername",
            "_gc._tcp.$rootDomainFromUsername"
        )
    }
    
    $maxSrvAttempts = 120  # Up to 60 minutes (120 * 30 seconds)
    $srvAttempt = 0
    $srvReady = $false
    
    while ($srvAttempt -lt $maxSrvAttempts -and -not $srvReady) {
        $allSrvResolved = $true
        
        Write-Host "Attempt $($srvAttempt + 1): Checking SRV records..."
        
        foreach ($srvRecord in $requiredSrvRecords) {
            try {
                $result = Resolve-DnsName -Name $srvRecord -Type SRV -ErrorAction Stop
                $target = ($result | Select-Object -First 1).NameTarget
                Write-Host "  OK: $srvRecord -> $target"
            } catch {
                Write-Host "  MISSING: $srvRecord - $_"
                $allSrvResolved = $false
            }
        }
        
        if ($allSrvResolved) {
            Write-Host "All required SRV records are resolvable!"
            $srvReady = $true
        } else {
            Write-Host "Some SRV records not ready. Retrying in 30 seconds..."
            Start-Sleep -Seconds 30
            $srvAttempt++
        }
    }
    
    if (-not $srvReady) {
        throw "Timed out waiting for SRV records. Parent DC DNS may not be fully initialized."
    }
    
    # Use nltest to verify DC locator works (this is what Windows uses internally)
    Write-Host "Verifying DC locator with nltest for parent domain..."
    $maxNltestAttempts = 120  # Up to 60 minutes (120 * 30 seconds)
    $nltestAttempt = 0
    $nltestSuccess = $false
    
    while ($nltestAttempt -lt $maxNltestAttempts -and -not $nltestSuccess) {
        try {
            Write-Host "Attempt $($nltestAttempt + 1): Running nltest /dsgetdc:$parentDomainName..."
            $nltestResult = nltest /dsgetdc:$parentDomainName 2>&1
            $nltestExitCode = $LASTEXITCODE
            
            if ($nltestExitCode -eq 0) {
                Write-Host "nltest for parent domain succeeded!"
                Write-Host $nltestResult
                $nltestSuccess = $true
            } else {
                throw "nltest failed with exit code $nltestExitCode : $nltestResult"
            }
        } catch {
            Write-Host "nltest not ready yet: $_"
            Write-Host "Retrying in 30 seconds..."
            Start-Sleep -Seconds 30
            $nltestAttempt++
        }
    }
    
    if (-not $nltestSuccess) {
        throw "Timed out waiting for nltest /dsgetdc to succeed for parent domain."
    }
    
    # CRITICAL for deep hierarchies: Also verify DC locator works for the FOREST ROOT domain
    # Install-ADDSDomain uses the credential's domain (build.lab) to authenticate
    if ($parentDomainName -ne $rootDomainFromUsername) {
        Write-Host "Deep hierarchy: Verifying DC locator for forest root domain..."
        $maxRootNltestAttempts = 120  # Up to 60 minutes (120 * 30 seconds)
        $rootNltestAttempt = 0
        $rootNltestSuccess = $false
        
        while ($rootNltestAttempt -lt $maxRootNltestAttempts -and -not $rootNltestSuccess) {
            try {
                Write-Host "Attempt $($rootNltestAttempt + 1): Running nltest /dsgetdc:$rootDomainFromUsername..."
                $rootNltestResult = nltest /dsgetdc:$rootDomainFromUsername 2>&1
                $rootNltestExitCode = $LASTEXITCODE
                
                if ($rootNltestExitCode -eq 0) {
                    Write-Host "nltest for forest root domain succeeded!"
                    Write-Host $rootNltestResult
                    $rootNltestSuccess = $true
                } else {
                    throw "nltest failed with exit code $rootNltestExitCode : $rootNltestResult"
                }
            } catch {
                Write-Host "nltest for forest root not ready yet: $_"
                Write-Host "Retrying in 30 seconds..."
                Start-Sleep -Seconds 30
                $rootNltestAttempt++
            }
        }
        
        if (-not $rootNltestSuccess) {
            throw "Timed out waiting for nltest /dsgetdc:$rootDomainFromUsername. Forest root DC not reachable via DNS."
        }
    }
    
    # Check SYSVOL and NETLOGON shares are accessible (indicates DC is fully promoted)
    # This is a best-effort check - don't fail if shares aren't accessible
    # as the other checks (SRV, nltest, user lookup) should be sufficient
    Write-Host "Checking SYSVOL and NETLOGON shares on parent DC..."
    $maxShareAttempts = 10  # Reduced from 30 - don't wait too long
    $shareAttempt = 0
    $sharesReady = $false
    
    # Extract parent DC hostname from FQDN
    $parentDcHostname = $rootDomainControllerFQDN.Split('.')[0]
    
    while ($shareAttempt -lt $maxShareAttempts -and -not $sharesReady) {
        try {
            Write-Host "Attempt $($shareAttempt + 1): Checking shares..."
            
            $sysvolPath = "\\$rootDomainControllerFQDN\SYSVOL"
            $netlogonPath = "\\$rootDomainControllerFQDN\NETLOGON"
            
            $sysvolExists = Test-Path $sysvolPath -ErrorAction Stop
            $netlogonExists = Test-Path $netlogonPath -ErrorAction Stop
            
            if ($sysvolExists -and $netlogonExists) {
                Write-Host "  OK: SYSVOL share accessible at $sysvolPath"
                Write-Host "  OK: NETLOGON share accessible at $netlogonPath"
                $sharesReady = $true
            } else {
                throw "Shares not accessible: SYSVOL=$sysvolExists, NETLOGON=$netlogonExists"
            }
        } catch {
            Write-Host "Shares not ready yet: $_"
            Write-Host "Retrying in 30 seconds..."
            Start-Sleep -Seconds 30
            $shareAttempt++
        }
    }
    
    if (-not $sharesReady) {
        Write-Host "WARNING: SYSVOL/NETLOGON shares not accessible after $maxShareAttempts attempts."
        Write-Host "This may indicate DFSR hasn't finished initializing, but other checks passed."
        Write-Host "Continuing with domain installation anyway..."
    }
    
    # Check time synchronization (Kerberos fails with >5 minute skew)
    Write-Host "Checking time synchronization with parent DC..."
    try {
        $w32tmResult = w32tm /stripchart /computer:$rootDomainControllerFQDN /samples:1 /dataonly 2>&1
        Write-Host "Time sync check result:"
        Write-Host $w32tmResult
        
        # Parse the time offset - look for the offset value
        $offsetMatch = $w32tmResult | Select-String -Pattern '([+-]?\d+\.?\d*)s'
        if ($offsetMatch) {
            $offsetSeconds = [math]::Abs([double]$offsetMatch.Matches[0].Groups[1].Value)
            Write-Host "Time offset from parent DC: $offsetSeconds seconds"
            
            if ($offsetSeconds -gt 300) {
                Write-Host "WARNING: Time skew is greater than 5 minutes! Attempting to sync..."
                w32tm /resync /force | Out-Null
                Start-Sleep -Seconds 5
            } else {
                Write-Host "Time synchronization is within acceptable limits."
            }
        }
    } catch {
        Write-Host "Warning: Could not check time sync: $_"
        Write-Host "Continuing anyway..."
    }
    
    # Check required ports are reachable
    Write-Host "Checking required AD ports are reachable on parent DC..."
    $requiredPorts = @(53, 88, 135, 389, 445, 464, 636, 3268)
    $portCheckPassed = $true
    
    foreach ($port in $requiredPorts) {
        try {
            $tcpTest = Test-NetConnection -ComputerName $rootDomainControllerFQDN -Port $port -WarningAction SilentlyContinue -ErrorAction Stop
            if ($tcpTest.TcpTestSucceeded) {
                Write-Host "  OK: Port $port is open"
            } else {
                Write-Host "  WARNING: Port $port is not accessible"
                # Don't fail on port check - some ports may not respond to TCP test
            }
        } catch {
            Write-Host "  WARNING: Could not test port $port - $_"
        }
    }
    
    # Poll until the user account can be resolved via AD
    # CRITICAL: For deep hierarchies, Install-ADDSDomain resolves the credential via DNS
    # to the FOREST ROOT domain, not through the parent DC chain.
    # We must verify the root domain is reachable via DNS from this machine.
    $maxUserCheckAttempts = 120  # Up to 60 minutes (120 * 30 seconds)
    $userCheckAttempt = 0
    $userResolved = $false
    
    # Determine where to search - for deep hierarchies we need the FOREST ROOT DC
    $searchTarget = $rootDomainControllerFQDN
    $isDeepHierarchy = $parentDomainName -ne $rootDomainFromUsername
    
    if ($isDeepHierarchy) {
        Write-Host "Deep hierarchy detected - need to resolve user from forest root domain..."
        Write-Host "Credential domain: $rootDomainFromUsername"
        Write-Host "Parent domain: $parentDomainName"
        
        # Find a DC in the forest root domain via DNS
        try {
            $rootDcSrv = Resolve-DnsName -Name "_ldap._tcp.dc._msdcs.$rootDomainFromUsername" -Type SRV -ErrorAction Stop
            $rootDcFqdn = ($rootDcSrv | Select-Object -First 1).NameTarget
            Write-Host "Found forest root DC via SRV: $rootDcFqdn"
            $searchTarget = $rootDcFqdn
        } catch {
            Write-Host "Warning: Could not find forest root DC via SRV, will try direct DNS..."
            # Try to resolve the root domain directly and use that
            try {
                $rootDomainIp = (Resolve-DnsName -Name $rootDomainFromUsername -Type A -ErrorAction Stop | 
                                 Where-Object { $_.Type -eq 'A' } | 
                                 Select-Object -First 1).IPAddress
                Write-Host "Resolved $rootDomainFromUsername to IP: $rootDomainIp"
                $searchTarget = $rootDomainFromUsername
            } catch {
                Write-Host "Warning: Could not resolve forest root domain - falling back to parent DC"
            }
        }
    }
    
    Write-Host "Verifying user account can be resolved in Active Directory..."
    Write-Host "Looking for user '$usernameOnly' in domain '$rootDomainFromUsername' via $searchTarget..."
    
    while ($userCheckAttempt -lt $maxUserCheckAttempts -and -not $userResolved) {
        try {
            Write-Host "Attempt $($userCheckAttempt + 1): Resolving user account via AD..."
            
            # First verify DNS resolution for the root domain
            $dnsResult = Resolve-DnsName -Name $rootDomainFromUsername -ErrorAction Stop
            Write-Host "DNS resolution for $rootDomainFromUsername succeeded."
            
            # For deep hierarchies, search the FOREST ROOT domain directly
            # This is what Install-ADDSDomain will do internally
            $searchRoot = New-Object System.DirectoryServices.DirectoryEntry(
                "LDAP://$searchTarget",
                $enterpriseAdminUsername,
                $enterpriseAdminPassword
            )
            
            $searcher = New-Object System.DirectoryServices.DirectorySearcher($searchRoot)
            $searcher.Filter = "(sAMAccountName=$usernameOnly)"
            $searcher.SearchScope = "Subtree"
            
            $result = $searcher.FindOne()
            
            if ($result) {
                $userDn = $result.Properties['distinguishedName'][0]
                Write-Host "User account '$usernameOnly' found in Active Directory!"
                Write-Host "User DN: $userDn"
                
                # Verify the user is in the correct domain (forest root)
                if ($isDeepHierarchy -and $userDn -notlike "*DC=$($rootDomainFromUsername.Split('.')[0]),*") {
                    Write-Host "WARNING: User found but may not be in the forest root domain!"
                    Write-Host "Expected domain: $rootDomainFromUsername"
                    Write-Host "This could cause Install-ADDSDomain to fail."
                }
                
                $userResolved = $true
                $searcher.Dispose()
                $searchRoot.Close()
            } else {
                throw "User not found in directory search results"
            }
        } catch {
            Write-Host "User resolution not ready yet: $_"
            Write-Host "Retrying in 30 seconds..."
            Start-Sleep -Seconds 30
            $userCheckAttempt++
        }
    }
    
    if (-not $userResolved) {
        throw "Timed out waiting for user account to be resolvable in AD. AD replication may not be complete."
    }
    
    # Additional check for deep hierarchies: verify we can actually authenticate to the forest root
    if ($isDeepHierarchy) {
        Write-Host "Verifying authentication to forest root domain..."
        $maxForestAuthAttempts = 120  # Up to 60 minutes (120 * 30 seconds)
        $forestAuthAttempt = 0
        $forestAuthReady = $false
        
        while ($forestAuthAttempt -lt $maxForestAuthAttempts -and -not $forestAuthReady) {
            try {
                Write-Host "Attempt $($forestAuthAttempt + 1): Testing authentication to $rootDomainFromUsername..."
                
                # Try to bind directly to the forest root domain via DNS name
                $forestEntry = New-Object System.DirectoryServices.DirectoryEntry(
                    "LDAP://$rootDomainFromUsername",
                    $enterpriseAdminUsername,
                    $enterpriseAdminPassword
                )
                
                # Force authentication
                $null = $forestEntry.distinguishedName
                
                if ($forestEntry.distinguishedName) {
                    Write-Host "Successfully authenticated to forest root domain!"
                    Write-Host "Forest root DN: $($forestEntry.distinguishedName)"
                    $forestAuthReady = $true
                    $forestEntry.Close()
                } else {
                    throw "Could not get distinguishedName from forest root"
                }
            } catch {
                Write-Host "Forest root authentication not ready yet: $_"
                Write-Host "Retrying in 30 seconds..."
                Start-Sleep -Seconds 30
                $forestAuthAttempt++
            }
        }
        
        if (-not $forestAuthReady) {
            throw "Timed out waiting for forest root authentication. DNS forwarding may not be working."
        }
    }
    
    Write-Host "All prerequisites passed."
    
    # CRITICAL: Wait for AD replication/Kerberos/DNS to fully settle
    # This was in the original working script and is apparently necessary. IDK why, but atm, simply waiting a while just cause is the only solution. I really wish to find the actul thing to probe to know for sure install-ad would work. 
    # even after all our checks pass - Install-ADDSDomain has internal timing requirements
    # For deep hierarchies (DC03+), wait longer as there are more replication hops
    if ($isDeepHierarchy) {
        $stabilizationWait = 600  # 10 minutes for deep hierarchies
        Write-Host "Deep hierarchy detected - waiting 10 minutes for AD infrastructure to fully stabilize..."
    } else {
        $stabilizationWait = 300  # 5 minutes for first-level child domains
        Write-Host "Waiting 5 minutes for AD infrastructure to fully stabilize..."
    }
    Write-Host "Start time: $(Get-Date)"
    Start-Sleep -Seconds $stabilizationWait
    Write-Host "Wait complete. Proceeding with domain installation..."
    Write-Host "End time: $(Get-Date)"

    # Final pre-flight check: Run Test-ADDSDomainInstallation to verify everything is ready
    # This is the same validation that Install-ADDSDomain runs internally
    Write-Host "Running Test-ADDSDomainInstallation to verify readiness..."
    $maxTestAttempts = 20
    $testAttempt = 0
    $testPassed = $false
    
    while ($testAttempt -lt $maxTestAttempts -and -not $testPassed) {
        try {
            Write-Host "Test attempt $($testAttempt + 1) of $maxTestAttempts..."
            $testResult = Test-ADDSDomainInstallation `
                -NewDomainName $domainName `
                -ParentDomainName $parentDomainName `
                -DomainType "ChildDomain" `
                -InstallDNS `
                -ReplicationSourceDC $rootDomainControllerFQDN `
                -SafeModeAdministratorPassword $secureAdminPassword `
                -Credential $enterpriseAdminCredsWithDomain
            
            if ($testResult.Status -eq "Success") {
                Write-Host "Test-ADDSDomainInstallation passed!"
                $testPassed = $true
            } else {
                Write-Host "Test-ADDSDomainInstallation returned: $($testResult.Status)"
                Write-Host "Message: $($testResult.Message)"
                $testAttempt++
                if ($testAttempt -lt $maxTestAttempts) {
                    Write-Host "Retrying in 60 seconds..."
                    Start-Sleep -Seconds 60
                }
            }
        } catch {
            Write-Host "Test-ADDSDomainInstallation error: $_"
            $testAttempt++
            if ($testAttempt -lt $maxTestAttempts) {
                Write-Host "Retrying in 60 seconds..."
                Start-Sleep -Seconds 60
            }
        }
    }
    
    if (-not $testPassed) {
        throw "Test-ADDSDomainInstallation failed after $maxTestAttempts attempts. Prerequisites not met."
    }

    # Now run the actual Install-ADDSDomain
    # Retry logic checks the result Status since it doesn't throw exceptions on failure
    $maxInstallAttempts = 20
    $installAttempt = 0
    $installSuccess = $false

    while ($installAttempt -lt $maxInstallAttempts -and -not $installSuccess) {
        Write-Host "Attempting to configure Subdomain Controller (Attempt $($installAttempt + 1) of $maxInstallAttempts)..."
        
        $installResult = Install-ADDSDomain `
            -NewDomainName $domainName `
            -ParentDomainName $parentDomainName `
            -DomainType "ChildDomain" `
            -InstallDNS `
            -CreateDNSDelegation `
            -DomainMode "WinThreshold" `
            -ReplicationSourceDC $rootDomainControllerFQDN `
            -SafeModeAdministratorPassword $secureAdminPassword `
            -Force `
            -Credential $enterpriseAdminCredsWithDomain
        
        # Check the result status - Install-ADDSDomain doesn't throw on failure
        if ($installResult.Status -eq "Success") {
            Write-Host "Install-ADDSDomain completed successfully!"
            $installSuccess = $true
        } else {
            Write-Host "Install-ADDSDomain returned Status: $($installResult.Status)"
            Write-Host "Message: $($installResult.Message)"
            $installAttempt++
            if ($installAttempt -lt $maxInstallAttempts) {
                Write-Host "Retrying in 60 seconds... ($installAttempt of $maxInstallAttempts attempts used)"
                Start-Sleep -Seconds 60
            }
        }
    }

    if (-not $installSuccess) {
        throw "Install-ADDSDomain failed after $maxInstallAttempts attempts (20 minutes)."
    }

    # Restore 8.8.8.8 as secondary DNS for general internet connectivity
    try {
        $activeAdapter = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | Select-Object -First 1
        if ($activeAdapter -and $parentDcIp) {
            Write-Host "Restoring 8.8.8.8 as secondary DNS for internet connectivity..."
            Set-DnsClientServerAddress -InterfaceAlias $activeAdapter.InterfaceAlias -ServerAddresses @($parentDcIp, "8.8.8.8")
        }
    } catch {
        Write-Host "Warning: Could not restore secondary DNS: $_"
    }

    Restart-Service NetLogon -Force -EA 0
    Add-Content -Path $logFilePath -Value "Successfully installed ADDS for subdomain."
} catch {
    Write-Host "Failed to configure Subdomain Controller: $_"
    Add-Content -Path $logFilePath -Value "Failed to install ADDS for subdomain. $_"
}

Stop-Transcript
