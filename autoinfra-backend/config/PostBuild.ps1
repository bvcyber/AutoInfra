$logFilePath = "C:\Temp\logfile.txt"

Function Test-ADWebServices {
    param(
        [int]$MaxRetries
    )
    for ($i=0; $i -lt $MaxRetries; $i++){
        try {
            $adwsService = Get-Service -Name ADWS
        } catch {
            Add-Content -Path $logFilePath -Value "Iteration ${i}: ERROR retrieving ADWS service."
        }
        if ($adwsService -and $adwsService.Status -eq 'Running') {
            # Confirm that ADWS is listening on port 9389
            $testConnection = Test-NetConnection -ComputerName localhost -Port 9389 -InformationLevel Quiet
            if ($testConnection) {
                Add-Content -Path $logFilePath -Value "ADWS is running and responsive on port 9389."
                return $true
            } else {
                Add-Content -Path $logFilePath -Value "ADWS is running, but not responding on port 9389. Waiting longer..."
                Start-Sleep -Seconds 30
            }
        } else {
            Add-Content -Path $logFilePath -Value "ADWS is NOT running yet. Sleeping and waiting for initialization."
            #Start-Service -Name ADWS -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 30
        }
    }
    Add-Content -Path $logFilePath -Value "ADWS is not running or responsive after $MaxRetries attempts."
    return $false
}

#Create a base user
try {
    #$adwsTest = Test-ADWebServices -MaxRetries 10
    $pw = ConvertTo-SecureString -String "Password#1" -AsPlaintext -Force
    New-AdUser -UserPrincipalName "redteamuser@redteam.lab" -SamAccountName "redteamuser" -AccountPassword $pw -PasswordNeverExpires $true -Name "redteamuser" -Enabled $true

} catch {
   Add-Content -Path $logFilePath -Value "Failed adding user. $_" 
}

# Double-check user addition
$user = Get-ADUser -Filter {SamAccountName -eq "redteamuser"}
if ($user) {
    Add-Content -Path $logFilePath -Value "User added successfully."
} else {
    Add-Content -Path $logFilePath -Value  "User not found."
}

# Try to run gpupdate
try {
    # Force group policy update
    gpupdate /force
    Add-Content -Path $logFilePath -Value "Ran gpupdate"
} catch {
    Add-Content -Path $logFilePath -Value "Failed running gpupdate. $_"
}
