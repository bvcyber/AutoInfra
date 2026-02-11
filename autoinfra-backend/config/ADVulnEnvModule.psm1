<# =============================
          Creation Functions
    ============================#>


Function GenerateUsers {
    param (
        [pscredential]$DomainAdminCreds,
        [string]$domainName
    )

    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"

    # Define an array of 25 names
    $userNames = @("User1", "User2", "User3", "User4", "User5",
                   "User6", "User7", "User8", "User9", "User10",
                   "User11", "User12", "User13", "User14", "User15",
                   "User16", "User17", "User18", "User19", "User20",
                   "User21", "User22", "User23", "User24", "EntryUser")

    # Loop through each name and create a user
    foreach ($name in $userNames) {
        try {
            Add-Type -AssemblyName System.Web
    
            # Assign specific simple passwords for User8(Kerberoast User) and EntryUser
            if ($name -eq "User8") {
                $password = "Password123"
            } elseif ($name -eq "EntryUser" -or $name -eq "User2") { # Assign simple passwords for entryuser(user to login with and user2 for responder attack)
                $password = "Password#1"
            } else {
                # Generate a random password for other users
                $password = [System.Web.Security.Membership]::GeneratePassword(25, 1)
            }
    
            $description = 'Inspired by secframe.com/badblood.'
            $upn = "$name@$domainName"
    
            # Create the user with New-ADUser using the provided credentials
            New-ADUser -Name $name -SamAccountName $name -Surname $name -Enabled $true -AccountPassword (ConvertTo-SecureString $password -AsPlainText -Force) -UserPrincipalName $upn -Description $description -Credential $DomainAdminCreds
    
            # Add successful execution in logs
            $successMessage = "GenerateUsers Function: Successfully created user: $name"
            Add-Content -Path $logFilePath -Value $successMessage
            Write-Output $successMessage

            # Add EntryUser and User2 to rdp group (entryuser to be utilize to rdp into domain and User2 used to similate traffic for responder attack)
            if ($name -eq "EntryUser") {
                # Add to domain Remote Desktop Users group (DCs don't have local groups)
                Add-ADGroupMember -Identity "Remote Desktop Users" -Members $name -Credential $DomainAdminCreds
                $rdpMessage = "GenerateUsers Function: Added $name to Remote Desktop Users domain group"
                Add-Content -Path $logFilePath -Value $rdpMessage
                Write-Output $rdpMessage
            }
        } catch {
            # Add failed execution in logs
            Add-Content -Path $logFilePath -Value "GenerateUsers Function: Error in running function and creating user $name : $_ "
        }
    }
}




Function GenerateRandomUsers {
    param (
        [pscredential]$DomainAdminCreds,
        [string]$domainName,
        [int]$numberOfUsers,
        [string]$usernameFormat = "firstname"  # Options: "firstname", "firstname.lastname", "firstinitial.lastname"
    )

    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"
    
    # Log the received parameters for debugging
    Add-Content -Path $logFilePath -Value "GenerateRandomUsers Function: Received usernameFormat parameter: '$usernameFormat'"

    # Read first names from the file
    $fileURL = "https://raw.githubusercontent.com/davidprowe/BadBlood/master/AD_Users_Create/Names/names.txt"
    $namesFilePath = "C:\temp\names.txt"
    Invoke-WebRequest -Uri $fileURL -OutFile $namesFilePath
    if (-Not (Test-Path $namesFilePath)) {
        Write-Error "Names file not found at $namesFilePath"
        return
    }

    $allFirstNames = Get-Content $namesFilePath

    # Read last names from the file (if needed for format)
    $allLastNames = @()
    if ($usernameFormat -ne "firstname") {
        $lastNamesURL = "https://raw.githubusercontent.com/your-repo/lastnames.txt"
        $lastNamesFilePath = "C:\temp\lastnames.txt"
        
        # For now, use a predefined list of common last names
        $allLastNames = @(
            "smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis", 
            "rodriguez", "martinez", "hernandez", "lopez", "gonzalez", "wilson", "anderson", 
            "thomas", "taylor", "moore", "jackson", "martin", "lee", "perez", "thompson", 
            "white", "harris", "sanchez", "clark", "ramirez", "lewis", "robinson", "walker",
            "young", "allen", "king", "wright", "scott", "torres", "nguyen", "hill", "flores",
            "green", "adams", "nelson", "baker", "hall", "rivera", "campbell", "mitchell",
            "carter", "roberts", "gomez", "phillips", "evans", "turner", "diaz", "parker",
            "cruz", "edwards", "collins", "reyes", "stewart", "morris", "morales", "murphy",
            "cook", "rogers", "gutierrez", "ortiz", "morgan", "cooper", "peterson", "bailey",
            "reed", "kelly", "howard", "ramos", "kim", "cox", "ward", "richardson", "watson",
            "brooks", "chavez", "wood", "james", "bennett", "gray", "mendoza", "ruiz", "hughes",
            "price", "alvarez", "castillo", "sanders", "patel", "myers", "long", "ross", "foster"
        )
    }

    # Generate usernames based on format
    $generatedUsernames = @()
    for ($i = 0; $i -lt $numberOfUsers; $i++) {
        $firstName = (Get-Random -InputObject $allFirstNames).ToLower()
        
        switch ($usernameFormat) {
            "firstname" {
                $username = $firstName
            }
            "firstname.lastname" {
                $lastName = (Get-Random -InputObject $allLastNames).ToLower()
                $username = "$firstName.$lastName"
            }
            "firstinitial.lastname" {
                $lastName = (Get-Random -InputObject $allLastNames).ToLower()
                $firstInitial = $firstName.Substring(0, 1).ToLower()
                $username = "$firstInitial$lastName"
            }
            default {
                $username = $firstName
            }
        }
        
        # Ensure username is unique in this batch
        $counter = 1
        $originalUsername = $username
        while ($generatedUsernames -contains $username) {
            $username = "$originalUsername$counter"
            $counter++
        }
        
        $generatedUsernames += $username
    }

    # Loop through each generated username and create a user
    foreach ($username in $generatedUsernames) {
        try {
            Add-Type -AssemblyName System.Web

            # Generate a random password for the user
            $password = [System.Web.Security.Membership]::GeneratePassword(25, 1)

            $description = 'Inspired by secframe.com/badblood.'
            $upn = "$username@$domainName"
            
            # Use the username as both the display name and SAM account name
            $displayName = $username

            # Create the user with New-ADUser using the provided credentials
            New-ADUser -Name $displayName -SamAccountName $username -Surname $username -Enabled $true -AccountPassword (ConvertTo-SecureString $password -AsPlainText -Force) -UserPrincipalName $upn -Description $description -Credential $DomainAdminCreds

            # Add successful execution in logs
            $successMessage = "GenerateRandomUsers Function: Successfully created user: $username"
            Add-Content -Path $logFilePath -Value $successMessage
            Write-Output $successMessage
        } catch {
            # Add failed execution in logs
            Add-Content -Path $logFilePath -Value "GenerateRandomUsers Function: Error in running function and creating user $username : $_ "
        }
    }
}
Function CreateSingleUser {
    param (
        [pscredential]$DomainAdminCreds,
        [string]$domainName,
        [string]$singleUsername,
        [string]$singleUserPassword
    )

    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"
    $description = 'Single User Creation'
    $upn = "$singleUsername@$domainName"
    
    try {
        # Create the user with New-ADUser using the provided credentials
        New-ADUser -Name $singleUsername -SamAccountName $singleUsername -Surname $singleUsername -Enabled $true -AccountPassword (ConvertTo-SecureString $singleUserPassword -AsPlainText -Force) -UserPrincipalName $upn -Description $description -Credential $DomainAdminCreds

        # Add successful execution in logs
        $successMessage = "CreateSingleUser Function: Successfully created user: $singleUsername"
        Add-Content -Path $logFilePath -Value $successMessage
        Write-Output $successMessage

    }
    catch {
        # Add failed execution in logs
        Add-Content -Path $logFilePath -Value "CreateSingleUser Function: Error in running function and creating user $singleUsername : $_ "
    }
    
}

Function ConfigureUserToRDP {
    param (
        [pscredential]$DomainAdminCreds,
        [string]$domainName,
        [string]$targetUser
    )

    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"
    
    try {
        Add-Type -AssemblyName System.Web


        Add-ADGroupMember -Identity "Remote Desktop Users" -Members $targetUser -Credential $DomainAdminCreds
        Add-LocalGroupMember -Group "Remote Desktop Users" -Member $targetUser 
        Add-Content -Path $logFilePath -Value "ConfigureUserToRDP Function: Added $targetUser to Remote Desktop Users group"
        
    } catch {
        # Add failed execution in logs
        Add-Content -Path $logFilePath -Value "ConfigureUserToRDP Function: Error in running function $targetUser : $_ "
    }
}

Function CreateAndOrganizeOUs {
    param (
        [string]$OU1Name,
        [string]$OU2Name,
        [int]$NumberOfUsersInOU1,
        [pscredential]$DomainAdminCreds
    )

    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"

    try {
        # Create the first OU
        New-ADOrganizationalUnit -Name $OU1Name -Credential $DomainAdminCreds
        Add-Content -Path $logFilePath -Value "Created OU: $OU1Name"

        # Create the second OU
        New-ADOrganizationalUnit -Name $OU2Name -Credential $DomainAdminCreds
        Add-Content -Path $logFilePath -Value "Created OU: $OU2Name"

        # Move users to the first OU
        $users = Get-ADUser -Filter * -SearchBase "CN=Users,DC=redteam,DC=lab" | Select-Object -First $NumberOfUsersInOU1
        foreach ($user in $users) {
            Move-ADObject -Identity $user.DistinguishedName -TargetPath "OU=$OU1Name,DC=redteam,DC=lab"
            Add-Content -Path $logFilePath -Value "Moved user $($user.Name) to OU: $OU1Name"
        }

        # Move the remaining users to the second OU
        $remainingUsers = Get-ADUser -Filter * -SearchBase "CN=Users,DC=redteam,DC=lab" 
        foreach ($user in $remainingUsers) {
            Move-ADObject -Identity $user.DistinguishedName -TargetPath "OU=$OU2Name,DC=redteam,DC=lab"
            Add-Content -Path $logFilePath -Value "Moved user $($user.Name) to OU: $OU2Name"
        }

    } catch {
        Add-Content -Path $logFilePath -Value "Error in CreateAndOrganizeOUs: $_ "
    }
}

Function CreateComputerObjects {
    param (
        [string]$TargetOU, # Optional: OU to place the computer objects
        [pscredential]$DomainAdminCreds
    )

    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"

    # Predefined list of computer names
    $ComputerNames = @("Computer1", "Computer2", "Computer3", "Computer4", "Computer5")

    foreach ($name in $ComputerNames) {
        try {
            $params = @{
                Name = $name
                Credential = $DomainAdminCreds
                Path = if ($TargetOU) { "OU=$TargetOU,DC=redteam,DC=lab" } else { "CN=Computers,DC=redteam,DC=lab" }
            }

            # Create the computer object
            New-ADComputer @params

            # Log success
            Add-Content -Path $logFilePath -Value "CreateComputerObjects: Successfully created computer object: $name"
        } catch {
            # Log any errors
            Add-Content -Path $logFilePath -Value "CreateComputerObjects: Error creating computer object $name : $_ "
        }
    }
}






<# =================================
        Attack Vector Functions
    ================================#>

Function Import-VulnerableCertificateTemplate {
    param (
        [string]$domainAdminUsername,
        [string]$domainAdminPassword,
        [string]$domainName,
        [string]$templateName
    )
    $logLocation = "C:\Temp\logfile.txt"
    try {
        ldifde -i -k -f "C:\Temp\adcs-files\$templateName.ldf" -b $domainAdminUsername $domainName $domainAdminPassword
        ldifde -i -k -f $("C:\Temp\adcs-files\" + $templateName + "SecurityDescriptor.ldf") -b $domainAdminUsername $domainName $domainAdminPassword

        # For ESC4, grant Domain Users WriteProperty and Enroll permissions
        if ($templateName -eq "ESC4VulnWrite") {
            Add-Content -Path $logLocation -Value "Setting ESC4VulnWrite ACL for Domain Users..."
            $domain = (Get-ADDomain).NetBIOSName
            $templateDN = "CN=$templateName,CN=Certificate Templates,CN=Public Key Services,CN=Services,CN=Configuration,DC=$($domainName.Replace('.', ',DC='))"

            # Grant Write Property permission (to modify template attributes)
            $result1 = dsacls $templateDN /G "${domain}\Domain Users:RPWP" 2>&1
            Add-Content -Path $logLocation -Value "dsacls WriteProperty result: $result1"

            # Grant enrollment extended right (GUID 0e10c968-78fb-11d2-90d4-00c04f79dc55)
            $result2 = dsacls $templateDN /G "${domain}\Domain Users:CA;0e10c968-78fb-11d2-90d4-00c04f79dc55" 2>&1
            Add-Content -Path $logLocation -Value "dsacls Enrollment result: $result2"

            Add-Content -Path $logLocation -Value "ESC4VulnWrite ACL updated successfully"
        }

        Restart-Service -Name certsvc -Force
    } catch {
        Add-Content -Path $logLocation -Value "Error Enabling $templateName : $_ "
    }
}

Function Disable-PreAuth {
    param (
        [PSCredential]$domainAdminCreds,
        [string]$targetUser
    )
    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"

    try {
        # Use the credentials for AD operations
        Set-ADAccountControl -Credential $domainAdminCreds -Identity $targetUser -DoesNotRequirePreAuth:$true

        # Add successfull execution in logs
        Add-Content -Path $logFilePath -Value "DisablePreAuth Function: Successfully disabled preauth for $targetUser"
    }
    catch {
        # Log any errors
        Add-Content -Path $logFilePath -Value "DisablePreAuth Function: Error running Disable-PreAuth: $_ "
    }
}

Function Update-User-for-Kerberoast {
    param (
        [PSCredential]$domainAdminCreds,
        [string]$targetUser,
        [string]$domainName
    )
    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"

    try {
        # Generate unique SPN per user by including username in hostname
        $uniqueSpn = "MSSQLSvc/sql-$targetUser.$domainName:1433"

        # Use the credentials for AD operations
        Set-ADUser -Credential $domainAdminCreds -Identity $targetUser -ServicePrincipalNames @{Add=$uniqueSpn}

        # Add successfull execution in logs
        Add-Content -Path $logFilePath -Value "Update-User-for-Kerberoast Function: Made $targetUser be kerberoasted with SPN $uniqueSpn"
    }
    catch {
        # Log any errors
        Add-Content -Path $logFilePath -Value "Update-User-for-Kerberoast Function: Error running Update-User-for-Kerberoast: $_ "
    }
}

Function Update-User-for-Constrained-Delegation {
    param (
        [PSCredential]$domainAdminCreds,
        [string]$userForCDelegation,
        [string]$dcName,
        [string]$domainName
    )
    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"

    try {
        # Set the SPN for the DC
        $spn = "HTTP/$dcName.$domainName"
        Set-ADComputer -Credential $domainAdminCreds -Identity $dcName -ServicePrincipalNames @{ADD=$spn}
        # Use the credentials for AD operations
        Get-ADUser -Credential $domainAdminCreds -Identity $userForCDelegation | Set-ADAccountControl -TrustedToAuthForDelegation $true
        Set-ADUser -Credential $domainAdminCreds -Identity $userForCDelegation -Add @{'msDS-AllowedToDelegateTo'=@($spn)}
        
        # Add successful execution in logs
        Add-Content -Path $logFilePath -Value "Update-User-for-Constrained-Delegation Function: Configured $userForCDelegation for constrained delegation with SPN $spn"
    }
    catch {
        # Log any errors
        Add-Content -Path $logFilePath -Value "Update-User-for-Constrained-Delegation Function: Error running Update-User-for-Constrained-Delegation: $_ "
    }
}

Function Update-Computer-for-Constrained-Delegation {
    param (
        [PSCredential]$domainAdminCreds,
        [string]$computerForCDelegation,
        [string]$dcName,
        [string]$domainName
    )
    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"
    try {
        # Set the SPN for the DC
        $spn = "HTTP/$dcName.$domainName"
        #Add spn onto DC
        Set-ADComputer -Credential $domainAdminCreds -Identity $dcName -ServicePrincipalNames @{ADD=$spn}
        # set target computer to be able to delegate
        Get-ADComputer -Credential $domainAdminCreds -Identity $computerForCDelegation | Set-ADAccountControl -TrustedToAuthForDelegation $true
        Set-ADComputer -Credential $domainAdminCreds -Identity $computerForCDelegation -Add @{'msDS-AllowedToDelegateTo'=@($spn)}
        
        # Add successful execution in logs
        Add-Content -Path $logFilePath -Value "Update-Computer-for-Constrained-Delegation Function: Configured $computerForCDelegation for constrained delegation with SPN $spn"
    }
    catch {
        # Log any errors
        Add-Content -Path $logFilePath -Value "Update-Computer-for-Constrained-Delegation Function: Error running Update-Computer-for-Constrained-Delegation: $_ "
    }
}


Function Set-ADUserPermissions {
    param (
        [string]$GrantingUser,
        [string]$ReceivingUser,
        [string]$PermissionType
    )

    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"
    
    try {
        # Get the AD user object for the receiving user
        $user = Get-ADUser -Identity $ReceivingUser

        # Define the type of access right based on the PermissionType string
        $accessRight = @{
            "GenericAll" = [System.DirectoryServices.ActiveDirectoryRights]::GenericAll
            "GenericWrite" = [System.DirectoryServices.ActiveDirectoryRights]::WriteProperty
        }

        # Create an Access Control Entry (ACE)
        $ace = New-Object System.DirectoryServices.ActiveDirectoryAccessRule(
            (New-Object System.Security.Principal.NTAccount($GrantingUser)),
            $accessRight[$PermissionType],
            'Allow'
        )

        # Get the current ACL for the user
        $acl = Get-Acl "AD:$($user.DistinguishedName)"

        # Add the new ACE to the ACL
        $acl.AddAccessRule($ace)

        # Set the new ACL on the user object
        Set-Acl "AD:$($user.DistinguishedName)" $acl

        # Log success
        Add-Content -Path $logFilePath -Value "Set-ADUserPermissions: Successfully set $PermissionType permission for $GrantingUser on $ReceivingUser"
    } catch {
        # Log any errors
        Add-Content -Path $logFilePath -Value "Set-ADUserPermissions: Error setting permissions for $GrantingUser on $ReceivingUser : $_ "
    }
}

Function SimulateUserTrafficAsUser2 {
    param (
        [string]$BogusSharePath,
        [int]$IntervalSeconds
    )
    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"

    # User2's credentials
    $user2Username = "redteam.lab\User2"
    $user2Password = ConvertTo-SecureString "Password#1" -AsPlainText -Force
    $user2Creds = New-Object System.Management.Automation.PSCredential ($user2Username, $user2Password)

    # Script block to simulate traffic
    $scriptBlock = {
        param($BogusSharePath, $logFilePath, $IntervalSeconds)
        while ($true) {
            try {
                # Attempt to access the bogus file share
                & cmd.exe /c dir $BogusSharePath

                # Log the attempt
                Add-Content -Path $logFilePath -Value "SimulateUserTraffic: Attempted to access $BogusSharePath"
            } catch {
                # Log any errors from the attempt
                Add-Content -Path $logFilePath -Value "SimulateUserTraffic: Error accessing $BogusSharePath : $_ "
            }

            # Wait for the specified interval
            Start-Sleep -Seconds $IntervalSeconds
        }
    }

    # Start the script block as a background job
    Start-Job -ScriptBlock $scriptBlock -ArgumentList $BogusSharePath, $logFilePath, $IntervalSeconds -Credential $user2Creds
}

Function Set-LocalPrivEsc-BinPathWriteAccess {
    param (
        [PSCredential]$domainAdminCreds,
        [string]$targetUser,
        [string]$domainName
    )
    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"
    # Specify the service you're targeting
    $service = "wuauserv"
    $domainUser = "$domainName\$targetUser"
    # File for acl updates
    $downloadUrl =  "http://web.archive.org/web/20190910062448if_/http://download.microsoft.com/download/1/7/d/17d82b72-bc6a-4dc8-bfaa-98b37b22b367/subinacl.msi"
    $localPath = "C:\Temp\subinacl.msi"  
    try {
        # Download subinacl.msi
        Invoke-WebRequest -Uri $downloadUrl -OutFile $localPath  
        # Install it silently to prevent gui
        Start-Process "msiexec.exe" -ArgumentList "/i $localPath /qn /norestart" -NoNewWindow -Wait  
        $subinaclPath = "C:\Program Files (x86)\Windows Resource Kits\Tools\subinacl.exe"  
        # Grant targetuser full permissions on bin
        & $subinaclPath /service $service /grant=$domainUser=F
        # Log success
        Add-Content -Path $logFilePath -Value "Grant-ServiceBinPathWriteAccess: Successfully granted write access to binPath of $service for $targetUser."
    }
    catch {
        # Log any errors
        Add-Content -Path $logFilePath -Value "Grant-ServiceBinPathWriteAccess: Error granting write access to binPath of $service for $targetUser : $_"
    }
}


Function Set-UnquotedServicePathVulnerability {
    param (
        [PSCredential]$domainAdminCreds,
        [string]$targetUser,
        [string]$vulnerablePath = "C:\Program Files\My Vulnerable App"
    )

    # Define the benign executable and service details
    $benignExecutable = "C:\Windows\System32\notepad.exe" # Example benign executable
    $serviceName = "BenignService"
    $serviceDisplayName = "Benign Service"
    $servicePath = "$vulnerablePath\service.exe" # Construct the service path with spaces

    # Define the log file path
    $logFilePath = "C:\Temp\unquotedServicePathVulnerabilityLog.txt"

    try {
        # Ensure the vulnerable directory path exists
        New-Item -ItemType Directory -Path $vulnerablePath -Force

        # Copy the benign executable to the service path (simulating a service installation)
        Copy-Item -Path $benignExecutable -Destination $servicePath -Force

        # Create the new service using sc.exe to bypass PowerShell cmdlet limitations on path quoting
        $scArgs = "create $serviceName binPath= `"$servicePath`" DisplayName= `"$serviceDisplayName`""
        $scCreateResult = Start-Process sc.exe -ArgumentList $scArgs -Wait -PassThru -NoNewWindow

        # Verify service creation was successful
        if ($scCreateResult.ExitCode -eq 0) {
            Add-Content -Path $logFilePath -Value "Create-UnquotedServicePathVulnerability: Service '$serviceName' created successfully."
        } else {
            throw "Failed to create service. Exit Code: $($scCreateResult.ExitCode)"
        }

        # Grant write access to the target user for the vulnerable part of the path
        $acl = Get-Acl $vulnerablePath
        $permission = "$targetUser","Modify","Allow"
        $accessRule = New-Object System.Security.AccessControl.FileSystemAccessRule $permission
        $acl.AddAccessRule($accessRule)
        Set-Acl -Path $vulnerablePath -AclObject $acl

        Add-Content -Path $logFilePath -Value "Create-UnquotedServicePathVulnerability: Granted Modify access to '$targetUser' on '$vulnerablePath'."
    }
    catch {
        Add-Content -Path $logFilePath -Value "Create-UnquotedServicePathVulnerability: Error encountered: $_ "
    }
}


<#
Function Set-DomainAdminStoredCreds {
    param (
        [PSCredential]$domainAdminCreds,
        [string]$targetUser,
        [string]$domainName
    )

    # Generate a simple password for the target user
    $newPassword = "Password123!"

    # Define the log file path
    $logFilePath = "C:\Temp\domainAdminStoredCredsLog.txt"

    try {
        # Change the password of the target user
        Set-ADAccountPassword -Identity $targetUser -NewPassword (ConvertTo-SecureString $newPassword -AsPlainText -Force) -Credential $domainAdminCreds

        # Extract domain admin credentials
        $domainAdminUser = $domainAdminCreds.UserName
        $domainAdminPassword = $domainAdminCreds.GetNetworkCredential().Password

        # Use cmdkey to add stored credentials
        $targetUserFQDN = "$domainName\$targetUser"

        Start-Process -FilePath "cmdkey" -ArgumentList "/generic:$targetUserFQDN /user:$targetUserFQDN /pass:$newPassword" -Credential $adminCreds -NoNewWindow -Wait

        # Logging the action
        Add-Content -Path $logFilePath -Value "Set-DomainAdminStoredCreds: Successfully changed password and added stored credentials for '$targetUser'."
    }
    catch {
        Add-Content -Path $logFilePath -Value "Set-DomainAdminStoredCreds: Error encountered: $_ "
    }
}
#>
Function Add-CredsForMimikatz {
    param (
        [string]$userForMimikatz,
        [string]$singleUserPassword,
        [string]$domainName,
        [string]$computerForMimikatz
    )
    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"
    try {
       # Need to add user to local admin group in order to be able to psremote in and provide creds.
       #Add-LocalGroupMember -Group "Administrators" -Member $userForMimikatz
 
       $username = "$domainName\$userForMimikatz"
       $password = ConvertTo-SecureString $singleUserPassword -AsPlainText -Force
       $credential = New-Object System.Management.Automation.PSCredential ($username, $password)
       Invoke-Command -Credential $credential -ComputerName $computerForMimikatz -ScriptBlock {Start-Process powershell.exe}
       Add-Content -Path $logFilePath -Value "Add-CredsForMimikatz: Configured $userForMimikatz to have hash within the targetbox"
    }
    catch {
        # Log any errors
        Add-Content -Path $logFilePath -Value "Add-CredsForMimikatz Function: Error running Add-CredsForMimikatz: $_ "
    }


}


Function GenerateRandomCTF {
    param (
        [pscredential]$DomainAdminCreds,
        [string]$domainName,
        [string]$dcName,
        [int]$numberOfUsers,
        [string]$targetBox,
        [string]$difficulty
    )

    # Define the log file path
    $logFilePath = "C:\Temp\logfile.txt"

    # Generate random users
    GenerateRandomUsers -DomainAdminCreds $DomainAdminCreds -domainName $domainName -numberOfUsers $numberOfUsers

    # Get all generated users
    $randomUsers = Get-ADUser -Filter * | Select-Object -ExpandProperty SamAccountName

    # Assign RDP permissions to a random user
    $entryUser = Get-Random -InputObject $randomUsers
    ConfigureUserToRDP -DomainAdminCreds $DomainAdminCreds -domainName $domainName -targetUser $entryUser
    Set-ADAccountPassword -Identity $entryUser -NewPassword (ConvertTo-SecureString "Password123" -AsPlainText -Force) -Credential $DomainAdminCreds

    # Determine attack count based on difficulty
    $attackCount = switch ($difficulty) {
        "easy" { 2 }
        "medium" { 3 }
        "hard" { 4 }
        default { 2 }
    }

    # Define all attacks
    $attacks = @(
        "Disable-PreAuth", 
        "Update-User-for-Kerberoast", 
        "Update-User-for-Constrained-Delegation", 
        "Update-Computer-for-Constrained-Delegation", 
        "Set-LocalPrivEsc-BinPathWriteAccess", 
        "Set-UnquotedServicePathVulnerability", 
        "Add-CredsForMimikatz"
    )

    # Select the first attack
    $firstAttackOptions = $attacks | Where-Object { $_ -in @("Set-LocalPrivEsc-BinPathWriteAccess", "Set-UnquotedServicePathVulnerability", "Disable-PreAuth", "Update-User-for-Kerberoast") }
    $firstAttack = Get-Random -InputObject $firstAttackOptions

    # Remove first attack from remaining attacks
    $remainingAttacks = $attacks | Where-Object { $_ -ne $firstAttack }

    # Ensure the last attack leads to domain admin
    $lastAttackOptions = @("Update-User-for-Constrained-Delegation", "Update-Computer-for-Constrained-Delegation", "Add-CredsForMimikatz")
    $lastAttack = Get-Random -InputObject $lastAttackOptions

    # Adjust attack count to ensure it's valid
    $countToSelect = [math]::Max($attackCount - 2, 0)
    if ($countToSelect -gt 0) {
        $selectedAttacks = @($firstAttack) + (Get-Random -InputObject $remainingAttacks -Count $countToSelect) + $lastAttack
    } else {
        $selectedAttacks = @($firstAttack, $lastAttack)
    }

    # Ensure Mimikatz or Update-Computer-for-Constrained-Delegation follows a priv esc attack and adjust selection if necessary
    if ($selectedAttacks[-1] -in @("Add-CredsForMimikatz", "Update-Computer-for-Constrained-Delegation") -and $firstAttack -notin @("Set-LocalPrivEsc-BinPathWriteAccess", "Set-UnquotedServicePathVulnerability")) {
        $firstAttack = Get-Random -InputObject @("Set-LocalPrivEsc-BinPathWriteAccess", "Set-UnquotedServicePathVulnerability")
        $selectedAttacks[0] = $firstAttack
    }

    # Initialize applied attacks array and previous user
    $appliedAttacks = @()
    $previousUser = $null

    # Process attacks
    foreach ($attack in $selectedAttacks) {
        switch ($attack) {
            "Disable-PreAuth" {
                $user = Get-Random -InputObject ($randomUsers | Where-Object { $_ -ne $entryUser })
                Disable-PreAuth -domainAdminCreds $DomainAdminCreds -targetUser $user
                Set-ADAccountPassword -Identity $user -NewPassword (ConvertTo-SecureString "Password123" -AsPlainText -Force) -Credential $DomainAdminCreds
                $appliedAttacks += "Disable-PreAuth"
                $previousUser = $user
            }
            "Update-User-for-Kerberoast" {
                $user = Get-Random -InputObject ($randomUsers | Where-Object { $_ -ne $entryUser })
                Update-User-for-Kerberoast -domainAdminCreds $DomainAdminCreds -targetUser $user -domainName $domainName
                Set-ADAccountPassword -Identity $user -NewPassword (ConvertTo-SecureString "Password123" -AsPlainText -Force) -Credential $DomainAdminCreds
                $appliedAttacks += "Update-User-for-Kerberoast"
                $previousUser = $user
            }
            "Update-User-for-Constrained-Delegation" {
                if ($previousUser -ne $null -and $appliedAttacks -contains "Disable-PreAuth" -or $appliedAttacks -contains "Update-User-for-Kerberoast" -or $appliedAttacks -contains "Add-CredsForMimikatz") {
                    Update-User-for-Constrained-Delegation -domainAdminCreds $DomainAdminCreds -userForCDelegation $previousUser -dcName $dcName -domainName $domainName
                    $appliedAttacks += "Update-User-for-Constrained-Delegation"
                }
            }
            "Update-Computer-for-Constrained-Delegation" {
                if ($appliedAttacks -contains "Set-LocalPrivEsc-BinPathWriteAccess" -or $appliedAttacks -contains "Set-UnquotedServicePathVulnerability") {
                    Update-Computer-for-Constrained-Delegation -domainAdminCreds $DomainAdminCreds -computerForCDelegation $targetBox -dcName $dcName -domainName $domainName
                    $appliedAttacks += "Update-Computer-for-Constrained-Delegation"
                }
            }
            "Set-LocalPrivEsc-BinPathWriteAccess" {
                Set-LocalPrivEsc-BinPathWriteAccess -domainAdminCreds $DomainAdminCreds -targetUser $entryUser -domainName $domainName
                $appliedAttacks += "Set-LocalPrivEsc-BinPathWriteAccess"
            }
            "Set-UnquotedServicePathVulnerability" {
                Set-UnquotedServicePathVulnerability -domainAdminCreds $DomainAdminCreds -targetUser $entryUser
                $appliedAttacks += "Set-UnquotedServicePathVulnerability"
            }
            "Add-CredsForMimikatz" {
                if ($appliedAttacks -contains "Set-LocalPrivEsc-BinPathWriteAccess" -or $appliedAttacks -contains "Set-UnquotedServicePathVulnerability") {
                    $mimikatzUser = Get-Random -InputObject ($randomUsers | Where-Object { $_ -ne $entryUser })
                    Set-ADAccountPassword -Identity $mimikatzUser -NewPassword (ConvertTo-SecureString "Password123" -AsPlainText -Force) -Credential $DomainAdminCreds
                    Add-CredsForMimikatz -userForMimikatz $mimikatzUser -singleUserPassword "Password123" -domainName $domainName -computerForMimikatz $targetBox
                    $appliedAttacks += "Add-CredsForMimikatz"
                    $previousUser = $mimikatzUser
                }
            }
        }
    }

    # Log applied attacks
    Add-Content -Path $logFilePath -Value "GenerateRandomCTF: Successfully generated a random CTF with $($appliedAttacks.Count) attacks: $($appliedAttacks -join ', ')"
}



