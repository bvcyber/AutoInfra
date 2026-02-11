param(
    [string]$domainAdminUsername,
    [string]$domainAdminPassword,
    [string]$domainName,
    [string]$attackSelection,
    [string]$targetUser,
    [string]$GrantingUser,
    [string]$ReceivingUser,
    [string]$PermissionType,
    [string]$vulnerablePath,
    [string]$singleUsername,
    [string]$singleUserPassword,
    [string]$dcName,
    [string]$userForMimikatz,
    [string]$userForCDelegation,
    [string]$computerForCDelegation,
    [string]$computerForMimikatz,
    [int]$numberOfUsers,
    [string]$usernameFormat = "firstname"
)

# Define the log file path early for debugging
$logFilePath = "C:\Temp\logfile.txt"
Add-Content -Path $logFilePath -Value "=== ExecuteModule.ps1 START - Script Version with usernameFormat support ==="
Add-Content -Path $logFilePath -Value "ExecuteModule: Received parameters - attackSelection: '$attackSelection', numberOfUsers: '$numberOfUsers', usernameFormat: '$usernameFormat'"

# Convert the password to a secure string
[securestring]$securedomainAdminPassword = ConvertTo-SecureString $domainAdminPassword -AsPlainText -Force

# Create a PSCredential object using the domain admin username and password
[pscredential]$domainAdminCreds = New-Object System.Management.Automation.PSCredential ($domainAdminUsername, $securedomainAdminPassword)

# Define the log file path
$logFilePath = "C:\Temp\logfile.txt"

# Specify the module path
$modulePath = "C:\Temp\ADVulnEnvModule\ADVulnEnvModule.psm1"
$localFilePath = "C:\Temp\ADVulnEnvModule"

# Make sure the module is on the machine and import it
Function Check-ModuleHealth {
    if (Test-Path -Path $modulePath) {
        Add-Content -Path $logFilePath -Value 'Module found at expected path'
    } else {
        Add-Content -Path $logFilePath -Value 'Module not found at expected path - creating directory'

        if (-not (Test-Path -Path $localFilePath)) {
            try {
                New-Item -ItemType Directory -Path $localFilePath -Force | Out-Null
                Add-Content -Path $logFilePath -Value "Created module directory at $localFilePath"
            } catch {
                Add-Content -Path $logFilePath -Value "ERROR: Failed to create module directory: $_"
            }
        }

        Add-Content -Path $logFilePath -Value "WARNING: Module file missing - should have been installed by SetupFiles-Embedded.ps1"
        Add-Content -Path $logFilePath -Value "Attack execution will likely fail without the module"
    }

    try {
        Import-Module $modulePath -ErrorAction Stop
        Add-Content -Path $logFilePath -Value 'Successfully imported ADVulnEnvModule'
        return $true
    } catch {
        Add-Content -Path $logFilePath -Value "ERROR: Failed to import module: $_"
        Add-Content -Path $logFilePath -Value "Module path: $modulePath"
        return $false
    }
}

$moduleHealthy = Check-ModuleHealth
if (-not $moduleHealthy) {
    Add-Content -Path $logFilePath -Value "FATAL: Cannot proceed without ADVulnEnvModule - exiting"
    exit 1
}

Add-Content -Path $logFilePath -Value "Attack selection: $attackSelection"

<# =======================================
    Calling each function in Module
========================================== #>

# Call the generateUsers function, passing the credetnials

#GenerateUsers -DomainAdminCreds $domainAdminCreds -domainName $domainName


# Create 2 OUs and putting all created users in each of them
#CreateAndOrganizeOUs -OU1Name "PrivilegedOU" -OU2Name "NonPrivilegedOU" -NumberOfUsersInOU1 10 -DomainAdminCreds $domainAdminCreds

# Create 5 Computer Objects and adding to 1st OU
#CreateComputerObjects -TargetOU "PrivilegedOU" -DomainAdminCreds $domainAdminCreds

<# =======================================
            Helper Functions
========================================== #>

Function Enable-VulnerableCertificateTemplate {
    param (
        [string]$templateName
    )
    $logLocation = "C:\Temp\logfile.txt"
    $successfulConfiguration = $false
    $maxRetries = 12  # 60 seconds max (12 attempts * 5 seconds)
    $retryCount = 0

    while (!$successfulConfiguration -and $retryCount -lt $maxRetries){
        try {
            Certutil -SetCATemplates +$templateName
            Restart-Service -Name certsvc -Force
            Start-Sleep -Seconds 3
            $certCheck = Get-CATemplate
            if ($certCheck.Name -contains $templateName){
                $successfulConfiguration = $true
                Add-Content -Path $logLocation -Value "Successfully enabled $templateName"
                break
            } else {
                $retryCount++
                Add-Content -Path $logLocation -Value "Failed Setting Template (attempt $retryCount/$maxRetries)"
                Start-Sleep -Seconds 5
            }
        } catch {
            Add-Content -Path $logLocation -Value "Error enabling $templateName : $_"
            break
        }
    }

    if (!$successfulConfiguration) {
        Add-Content -Path $logLocation -Value "Failed to enable $templateName after $maxRetries attempts. Template may need manual configuration."
    }
}



Switch ($attackSelection)
{
    'disable-preauth'
    {
        # Call the Disable-PreAuth function, passing the credentials
        Disable-PreAuth -DomainAdminCreds $domainAdminCreds -targetUser $targetUser
    }

    'kerberoast'
    {
        # Update user to be Kerberoastable
        Update-User-for-Kerberoast -DomainAdminCreds $domainAdminCreds -targetUser $targetUser -domainName $domainName
    }

    'update-user-for-constrained-delegation'
    {
        # Update user to have constrained delegation
        Update-User-for-Constrained-Delegation  -DomainAdminCreds $domainAdminCreds -userForCDelegation $userForCDelegation -dcName $dcName -domainName $domainName
    }
    'update-computer-for-constrained-delegation'
    {
        # Update user to have constrained delegation
        Update-Computer-for-Constrained-Delegation  -DomainAdminCreds $domainAdminCreds -computerForCDelegation $computerForCDelegation -dcName $dcName -domainName $domainName
    }
    'add-creds-for-mimikatz'
    {
        # add user creds to target box
        Add-CredsForMimikatz -userforMimikatz $userForMimikatz -singleUserPassword $singleUserPassword -domainName $domainName -computerForMimikatz $computerForMimikatz
    }
    'local-privesc1'
    {
        # Update User to be able overwite binpath 
        Set-LocalPrivEsc-BinPathWriteAccess -DomainAdminCreds $domainAdminCreds -targetUser $targetUser
    }
    'local-privesc2'
    {
        Create-UnquotedServicePathVulnerability -DomainAdminCreds $domainAdminCreds -targetUser $targetUser -vulnerablePath $vulnerablePath # "C:\Program Files\My Vulnerable App"
    }

    'local-privesc3'
    {
        Set-DomainAdminStoredCreds -DomainAdminCreds $domainAdminCreds -targetName "localhost"
    }

    'other'
    {
        # Giving User8 genericall to user4. This will allow for other attacks as disabling preauth, writing spn, etc
        Set-ADUserPermissions -GrantingUser "User8" -ReceivingUser "User4" -PermissionType "GenericAll"

        # Giving user4 genericwrite onto User2. This will allow for attacks such as writing a spn onto that user
        Set-ADUserPermissions -GrantingUser "User4" -ReceivingUser "User2" -PermissionType "GenericWrite"

        # Simulate User2 traffic by periodically having them try to connect to nonexistent share. Will be used for responder attack
        SimulateUserTrafficAsUser2 -BogusSharePath "\\nonexistent\share" -IntervalSeconds 30
    }
    'playground' # enables all attack vectors
    {
        # Call the Disable-PreAuth function, passing the credentials
        Disable-PreAuth -DomainAdminCreds $domainAdminCreds -targetUser $targetUser

        # Update user8 to be Kerberoastable
        Update-User-for-Kerberoast -DomainAdminCreds $domainAdminCreds -targetUser $targetUser -domainName $domainName

        # Giving User8 genericall to user4. This will allow for other attacks as disabling preauth, writing spn, etc
        Set-ADUserPermissions -GrantingUser $GrantingUser -ReceivingUser $ReceivingUser -PermissionType "GenericAll"

        # Giving user4 genericwrite onto User2. This will allow for attacks such as writing a spn onto that user
        #Set-ADUserPermissions -GrantingUser "User4" -ReceivingUser "User2" -PermissionType "GenericWrite"
    }
    'acls'
    {
        # Set AD user permissions - GrantingUser gets permissions over ReceivingUser
        Set-ADUserPermissions -GrantingUser $GrantingUser -ReceivingUser $ReceivingUser -PermissionType $PermissionType
    }
    'esc1'
    {
        Import-VulnerableCertificateTemplate -domainAdminUsername $domainAdminUsername -domainAdminPassword $domainAdminPassword -domainName $domainName -templateName "ESC1Vuln"
        
        Enable-VulnerableCertificateTemplate -templateName "ESC1Vuln"
        
        #try {
        #    Certutil -SetCATemplates +ESC1Vuln
        #    Add-Content -Path $logFilePath -Value "Successfully enabled ESC1"
        #} catch {
        #    Add-Content -Path $logFilePath -Value "Failed enabling ESC1"
        #}
    }
    'esc3'
    {
        Import-VulnerableCertificateTemplate -domainAdminUsername $domainAdminUsername -domainAdminPassword $domainAdminPassword -domainName $domainName -templateName "ESC3VulnRequestAgent"
        Import-VulnerableCertificateTemplate -domainAdminUsername $domainAdminUsername -domainAdminPassword $domainAdminPassword -domainName $domainName -templateName "ESC3VulnAuthSignatures"
        Enable-VulnerableCertificateTemplate -templateName "ESC3VulnRequestAgent"
        Enable-VulnerableCertificateTemplate -templateName "ESC3VulnAuthSignatures"
        #try {
        #    Certutil -SetCATemplates +ESC3VulnRequestAgent
        #    Certutil -SetCATemplates +ESC3VulnAuthSignatures
        #    Add-Content -Path $logFilePath -Value "Successfully enabled ESC3"
        #} catch {
        #    Add-Content -Path $logFilePath -Value "Failed enabling ESC3: $_"
        #}
    }
    'esc4'
    {
        Import-VulnerableCertificateTemplate -domainAdminUsername $domainAdminUsername -domainAdminPassword $domainAdminPassword -domainName $domainName -templateName "ESC4VulnWrite"
        Enable-VulnerableCertificateTemplate -templateName "ESC4VulnWrite"
        #try {
        #    Certutil -SetCATemplates +ESC4VulnWrite
        #    Add-Content -Path $logFilePath -Value "Successfully enabled ESC4"
        #} catch {
        #    Add-Content -Path $logFilePath -Value "Failed to enable ESC4"
        #}
    }
    'generate-users'
    {
        GenerateUsers -DomainAdminCreds $domainAdminCreds -domainName $domainName
    }
    'create-single-user'
    {
        CreateSingleUser -DomainAdminCreds $domainAdminCreds -domainName $domainName -singleUsername $singleUsername -singleUserPassword $singleUserPassword
    }
    'generate-random-users'
    {
        Add-Content -Path $logFilePath -Value "ExecuteModule: usernameFormat parameter value is: '$usernameFormat'"
        GenerateRandomUsers -DomainAdminCreds $domainAdminCreds -domainName $domainName -numberOfUsers $numberOfUsers -usernameFormat $usernameFormat
    }
    'fixed-ctf1'
    {
        Install-WindowsFeature -Name RSAT-AD-PowerShell # just a temporary fix to always have admodule installed on runtime
        GenerateUsers -DomainAdminCreds $domainAdminCreds -domainName $domainName # First create fixed users for ctf
        Set-LocalPrivEsc-BinPathWriteAccess -DomainAdminCreds $domainAdminCreds -targetUser $targetUser -domainName $domainName # 1st step of attack flow is local privesc with rdp user
        Update-Computer-for-Constrained-Delegation -DomainAdminCreds $domainAdminCreds -computerForCDelegation $computerForCDelegation -dcName $dcName -domainName $domainName # 3rd step in which the computer  you obtained the hash from has constrained delegation in which can get you domain admin permissions
    }
    'random-ctf'
    {
        Install-WindowsFeature -Name RSAT-AD-PowerShell # just a temporary fix to always have admodule installed on runtime
        GenerateRandomCTF -DomainAdminCreds $domainAdminCreds -dcName $dcName -domainName $domainName -numberOfUsers $numberOfUsers -targetBox $targetBox -difficulty $difficulty
    }
}