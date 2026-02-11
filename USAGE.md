# Auto Infra - Usage Guide

Complete guide for deploying, managing, and configuring vulnerable Active Directory environments and CTF challenges.

## Table of Contents

- [Getting Started](#getting-started)
  - [First Time Setup](#first-time-setup)
  - [Azure Authentication](#azure-authentication)
- [Deploying Scenarios](#deploying-scenarios)
  - [Deploy Saved Scenario](#deploy-saved-scenario)
  - [Version Selection](#version-selection)
- [Building Custom Topologies](#building-custom-topologies)
  - [Topology Builder Interface](#topology-builder-interface)
  - [Adding Nodes](#adding-nodes)
  - [Configuring Nodes](#configuring-nodes)
  - [Connecting Nodes](#connecting-nodes)
  - [Certificate Authority Setup](#certificate-authority-setup)
  - [Generating and Deploying](#generating-and-deploying)
  - [Saving as Scenario](#saving-as-scenario)
- [BloodHound Integration](#bloodhound-integration)
  - [Uploading BloodHound Data](#uploading-bloodhound-data)
  - [Generating Topology from BloodHound](#generating-topology-from-bloodhound)
  - [Deploying BloodHound Topology](#deploying-bloodhound-topology)
  - [Configuring BloodHound Environments](#configuring-bloodhound-environments)
- [Managing Active Deployments](#managing-active-deployments)
  - [Viewing Deployment Information](#viewing-deployment-information)
  - [Accessing the Environment](#accessing-the-environment)
  - [Monitoring Deployment Status](#monitoring-deployment-status)
  - [Extending Deployment Time](#extending-deployment-time)
  - [Shutting Down Deployments](#shutting-down-deployments)
- [Configuration and Attacks](#configuration-and-attacks)
  - [Enabling Attack Paths](#enabling-attack-paths)
  - [Generating Random Users](#generating-random-users)
  - [Creating Single Users](#creating-single-users)
  - [Syncing Users from AD](#syncing-users-from-ad)
  - [Available Attack Vectors](#available-attack-vectors)
- [Advanced Features](#advanced-features)
  - [Saving Deployments](#saving-deployments)
  - [Updating Live Deployments](#updating-live-deployments)
  - [Template Management](#template-management)
  - [Per-Machine Versioning](#per-machine-versioning)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Getting Started

### First Time Setup

1. **Start the Application**

   Ensure you're in the project root directory:

   ```bash
   cd autoinfra
   docker compose up
   ```

   The application will be available at:
   - **Frontend**: http://localhost:3000
   - **Backend API**: http://localhost:8100

2. **Access the Web Interface**

   Open your browser and navigate to http://localhost:3000

### Azure Authentication

Before deploying any environments, you must configure Azure credentials:

1. Navigate to the **Azure Setup** page in the navigation menu
2. Enter your Azure service principal credentials:
   - **Client ID**: Your service principal application ID
   - **Client Secret**: Your service principal secret
   - **Tenant ID**: Your Azure AD tenant ID
   - **Subscription ID**: Your target Azure subscription
3. Click **Connect to Azure**
4. Once authenticated, you'll see a success message

**Note**: You must create a service principal with Contributor permissions before using Auto Infra. See the README for setup instructions.

---

## Deploying Scenarios

Scenarios are created by building custom topologies and saving them for reuse. There are no pre-built scenarios - you create everything from scratch using the Build page or BloodHound import.

### Deploy Saved Scenario

Saved deployments preserve machine states, users, and attack configurations.

1. Navigate to **Deploy** page
2. Click **Load Saved Deployment** tab
3. Select a saved deployment from the list
4. Click **Deploy**
5. The deployment launches with all saved state intact

### Version Selection

**Unified Version**

- Deploys all machines at the same version
- Select from dropdown of available versions
- Default: Latest version

**Per-Machine Versions**

- Toggle **Use per-machine versions**
- Select individual versions for each machine type
- Useful when testing specific machine configurations

---

## Building Custom Topologies

The Topology Builder allows you to visually design custom Active Directory networks.

### Topology Builder Interface

1. Navigate to **Build** page
2. You'll see:
   - **Canvas**: Visual workspace for topology graph
   - **Configuration Form** (left): Node configuration before adding
   - **Templates** (bottom): Save/load templates
   - **Controls**: Zoom, fit view

### Adding and Configuring Nodes

**IMPORTANT**: You must configure nodes BEFORE adding them. Configuration happens in the form, not by clicking nodes on the canvas.

**Available Node Types:**

- **Domain Controller**: Root or Child DC
- **Certificate Authority**: AD CS server
- **Workstation**: Client machine
- **Jumpbox**: Kali Linux entry point

**To Add a Node:**

1. **Select Node Type** from dropdown
2. **Configure the node** in the form:
   - **Domain Controller**: Enter DC Name and Domain Name (e.g., `DC01`, `corp.local`)
   - **Workstation**: Enter Workstation Name
   - **Certificate Authority**: Enter CA Name
   - **Jumpbox**: Automatically named
   - **All Types**: Select IP Range (10.10.0.0/24, 172.16.0.0/24, or 192.168.0.0/24)
   - **All Types**: Select specific IP from available addresses
   - **All Types except Jumpbox**: Toggle "Public IP" (Yes/No)
3. **Click "Add Node"** button
4. Node appears on canvas with your configuration

**You cannot modify node configuration after adding it to the canvas.**

### Connecting Nodes

**Creating Connections:**

1. Click and drag from a node's edge to another node
2. Release to create the connection

**Connection Rules:**

- Root DCs can connect to Child DCs (parent-child relationship)
- CAs must connect to exactly one DC (the domain they join)
- Workstations can connect to DCs (domain membership)
- Jumpboxes connect to any node for network access

**Deleting Connections:**

- Click a connection line to select it
- Press Delete or Backspace

### Generating and Deploying

1. **Generate Topology**
   - Click **Generate Topology** button
   - The system validates your topology
   - Checks for configuration errors

2. **Submit for Deployment**
   - Click **Build** button
   - Deployment begins immediately
   - A unique Build ID is generated (format: `BuildLab-XXXXX`)

3. **Monitor Progress**
   - You're redirected to the Build page
   - Real-time status shows:
     - Kali version compatibility check
     - Bicep template compilation
     - Azure resource deployment
   - Progress bar and deployment logs appear

### Saving as Scenario

After successful deployment and configuration:

1. Navigate to **Home** page
2. Wait for "Save Blocker" timer to complete (ensures all resources are ready)
3. **Configure attacks and users** (optional but recommended)
   - Enabled attacks will be preserved in the saved scenario
   - Generated users will be preserved in the saved scenario
4. Click **Save as Scenario**
5. Enter a scenario name (format: `Build-XXXXX` automatically prefixed)
6. The system:
   - Captures machine images to Azure Compute Gallery
   - Saves topology configuration
   - Preserves all enabled attacks
   - Preserves all user configurations
7. Saved scenarios appear in the **Deploy** page for future use

---

## BloodHound Integration

Convert BloodHound attack path data into live Azure environments.

### Uploading BloodHound Data

1. Navigate to **BloodHound** page
2. Click **Upload BloodHound JSON**
3. Select your BloodHound export file
   - Supports standard BloodHound JSON format
   - Includes computers, users, groups, domains, OUs, GPOs
4. File uploads to backend for processing

### Generating Topology from BloodHound

1. After upload, click **Generate Topology**
2. The system analyzes the BloodHound data:
   - Identifies domain structure
   - Maps Domain Controllers
   - Extracts computer relationships
   - Preserves OU structure
3. A visual topology appears on the canvas
4. Review the generated network structure

### Deploying BloodHound Topology

1. Review the generated topology
2. Click **Deploy to Azure**
3. Deployment process begins:
   - Creates resource group
   - Deploys Domain Controllers based on domains
   - Provisions workstations from computer objects
   - Configures network topology
4. Monitor deployment status in real-time

### Configuring BloodHound Environments

After deployment completes:

1. **Configure Users**
   - Click **Configure Users** tab
   - The system extracts users from BloodHound data
   - Users are created in AD with correct group memberships

2. **Configure Attacks**
   - Click **Configure Attacks** tab
   - The system identifies attack paths from BloodHound
   - Select which attack paths to enable
   - Click **Enable Selected Attacks**

3. **Access Environment**
   - Navigate to **Home** page
   - Jumpbox IP and credentials appear
   - RDP to jumpbox to begin testing

---

## Managing Active Deployments

### Viewing Deployment Information

The **Home** page displays comprehensive information about your active deployment:

**Left Panel - Deployment Overview**

- **Deployment ID**: Unique identifier
- **Scenario Name**: Deployed scenario
- **Entry IPs**: Jumpbox and node-specific public IPs with ports
- **Time Remaining**: Countdown until auto-deletion
- **Enterprise Admin Credentials**: Domain admin username and password
- **Jumpbox Credentials**: Jumpbox username and password (if NETWORK type)
- **Action Buttons**: Extend, Save/Update Scenario, Shut Down

**Right Panel - Topology Graph**

The **Topology** tab shows a visual graph with:
- Color-coded nodes (pink/purple for DCs, green for workstations, orange for jumpbox, yellow for CA)
- "Public IP" badges on nodes with public IPs
- Connection lines showing relationships
- Machine names and IP addresses

### Accessing the Environment

1. **Connect to Jumpbox**

   Use the public IP, username, and password shown on the Home page to connect to the Kali Linux jumpbox.

2. **Attack the Network**

   From the jumpbox, use penetration testing tools to attack the internal AD environment:
   - Run BloodHound collectors
   - Execute Kerberos attacks (Kerberoasting, AS-REP Roasting)
   - Exploit ADCS vulnerabilities (ESC1, ESC3, ESC4)
   - Leverage enabled attack paths

3. **Using Jumpbox as Proxy Tunnel**

   You can tunnel traffic through the jumpbox to access internal resources:
   ```bash
   # SSH SOCKS proxy tunnel
   ssh -D 8080 user@jumpbox-ip

   # Configure your tools to use localhost:8080 as SOCKS proxy
   # Access internal machines via private IPs through the tunnel
   ```

### Monitoring Deployment Status

The Home page automatically refreshes deployment status:

- **Deploying**: Resources are being created in Azure
  - Backend is executing Bicep deployments
  - Machines are provisioning
  - Network infrastructure is being configured

- **Deployed**: Environment is ready for use
  - All resources successfully created
  - Jumpbox accessible
  - Credentials available
  - Ready for attack configuration

- **Destroying**: Resources are being deleted
  - Appears when shutdown is clicked
  - Or when timeout expires
  - All Azure resources being removed

### Extending Deployment Time

All deployments have a default 2-hour timeout.

1. **Check Remaining Time**
   - Displayed on Home page
   - Format: "Xh Ym remaining"

2. **Extend Time**
   - Click **Extend** button
   - Adds 1 hour to the deployment
   - Maximum 2 extensions (4 hours total)

**Note**: Extensions prevent automatic deletion. Plan your work accordingly.

### Shutting Down Deployments

**Manual Shutdown**

1. Click **Shut Down** button on Home page
2. Status changes to "Destroying"
3. All Azure resources are deleted
4. Deployment removed from Active Deployments list

**Automatic Shutdown**

Deployments automatically shut down when:

- Timeout expires (2 hours + extensions)
- Docker containers stop
- Backend verification detects expired deployments

**Resource Cleanup**

On shutdown:

- Resource group deleted from Azure
- Local deployment files removed after Azure confirms deletion
- Gallery images preserved (if saved as scenario)
- Billing stops once resources are deleted

---

## Configuration and Attacks

Configure vulnerabilities and users on live deployments.

### Enabling Attack Paths

1. **Access Configuration Panel**
   - Navigate to **Home** page
   - Scroll to **Configuration** section
   - Click **Attacks** tab

2. **View Available Attacks**
   - List shows all attack vectors for your deployment
   - Depends on scenario configuration and machine types

3. **Select Attacks**
   - Check boxes next to desired attacks
   - Multiple attacks can be enabled simultaneously

4. **Enable Attacks**
   - Click **Enable Selected Attacks**
   - Backend runs PowerShell scripts via Azure CLI
   - Progress shown in Actions panel

5. **Verify Attacks**
   - Click **Check Attack Status**
   - Shows which attacks are successfully configured

**Attack Enablement Time**: 2-5 minutes depending on number of attacks

### Generating Random Users

Create bulk users with randomized attributes:

1. **Navigate to Users Tab**
   - Home page > Configuration > Users

2. **Configure Generation**
   - **Number of Users**: How many to create (1-100)
   - **Username Format**:
     - FirstLast (e.g., JohnSmith)
     - First.Last (e.g., John.Smith)
     - LastFirst (e.g., SmithJohn)
     - Last.First (e.g., Smith.John)

3. **Generate Users**
   - Click **Generate Random Users**
   - Users created with:
     - Random first and last names
     - Auto-generated passwords
     - Random OU assignment
     - Random group memberships

4. **View Generated Users**
   - Click **Sync Users** to see created users
   - List appears in Configuration panel

### Creating Single Users

For precise user creation:

1. **Navigate to Users Tab**
2. Click **Create Single User**
3. Fill in form:
   - **User Principal Name**: username@domain.com
   - **Password**: User password
   - **Organizational Unit**: OU path (e.g., `OU=Users,DC=corp,DC=local`)
   - **Groups**: Comma-separated list of group DNs

4. Click **Create User**
5. User created in specified OU with group memberships

### Syncing Users from AD

View current AD users in the UI:

1. Navigate to **Attacks** tab in the Configuration section
2. Click **Sync Users from AD**
3. Backend queries all Domain Controllers
4. User list refreshes with usernames in UPN format (username@domain)

**Use Case**: Verify user creation, select users for attacks

### Available Attack Vectors

Attack vectors depend on the machine types deployed in your environment.

**ADCS Attacks** (Requires Certificate Authority)

- **ESC1**: Misconfigured certificate templates - Domain User → Domain Admin
- **ESC3**: Certificate request agent enrollment - Domain User → Domain Admin
- **ESC4**: Vulnerable ACLs on certificate templates - Domain User → Domain Admin

**Kerberos Attacks** (Requires Domain Controllers)

- **Kerberoasting**: Target user with SPN for TGT acquisition
- **AS-REP Roasting**: Abuse user with Kerberos pre-auth disabled
- **User Constrained Delegation**: User with constrained delegation on DC SPN
- **Computer Constrained Delegation**: Computer with constrained delegation on DC SPN

**Local Privilege Escalation** (Requires Workstations)

- **Local Privesc 1**: Write access to service binary path
- **Local Privesc 2**: Write access to unquoted service path
- **Local Privesc 3**: RunAs administrator capability
- **Add Creds for Mimikatz**: Inject user credentials on target machine for Mimikatz dump

**ACL Attacks** (Requires Domain Controllers)

- **ACLs**: Grant GenericAll permissions from one user to another user

---

## Advanced Features

### Saving Deployments

Preserve deployment state for future use:

1. **Wait for Save Blocker**
   - After deployment completes, a timer appears
   - Waits ~5 minutes to ensure stability
   - Shows countdown on Home page

2. **Save Deployment**
   - Click **Save as Scenario** button
   - Enter scenario name
   - System captures:
     - Machine images (stored in Azure Compute Gallery)
     - Network topology
     - Enabled attacks
     - User configurations

3. **Access Saved Deployments**
   - Navigate to **Deploy** page
   - Click **Load Saved Deployment** tab
   - Your saved deployment appears in the list

4. **Deploy from Saved**
   - Select saved deployment
   - Click **Deploy**
   - Machines launch from saved images (preserving all configurations)

**Note**: Saved deployments consume Azure storage. Gallery images are retained until manually deleted.

### Updating Live Deployments

Add nodes to running environments without redeployment:

1. **Navigate to Build Page**
2. Click **Update Existing Scenario**
3. Select the scenario to update
4. Current deployment must be active
5. Topology loads with existing nodes
6. Add new nodes to the canvas
7. Connect new nodes to existing infrastructure
8. Click **Deploy Update**
9. New nodes are added to the live environment
10. Click **Save Update to Scenario** to persist changes

**Use Cases**:

- Add workstations to existing domain
- Deploy additional DCs
- Add Certificate Authorities
- Expand network topology

**Limitations**:

- Cannot remove existing nodes
- Cannot modify existing node configurations
- Only additive changes supported

### Template Management

Save and reuse topology templates:

**Saving Templates**

1. Design topology in Build page
2. Click **Save Template**
3. Enter template name
4. Template saved (topology only, no deployment)

**Loading Templates**

1. Build page > Templates section
2. Select template from list
3. Click **Load**
4. Topology populates on canvas
5. Modify as needed
6. Deploy or save as new template

**Deleting Templates**

1. Templates list > Select template
2. Click **Delete** icon
3. Confirm deletion

**Template Contents**:

- Node positions and types
- Node configurations (hostnames, domains, passwords)
- Connection topology
- CA template selections

**Note**: Templates are lightweight (no Azure resources). Use for rapid topology prototyping.

### Per-Machine Versioning

Deploy scenarios with mixed machine versions:

1. **Navigate to Deploy Page**
2. Select a scenario
3. Toggle **Use per-machine versions**
4. Individual version dropdowns appear for each machine type
5. Select desired version for:
   - Domain Controllers
   - Certificate Authorities
   - Workstations
   - Jumpboxes (Kali Linux)
6. Click **Submit**

**Use Cases**:

- Test version compatibility
- Deploy specific vulnerability versions
- Mix production and development versions
- Regression testing

**Version Format**: `MAJOR.MINOR.PATCH` (e.g., 1.0.0, 1.2.3)

---

## Troubleshooting

### Deployment Fails to Start

**Symptoms**: Click Submit, no deployment appears

**Solutions**:

1. Check Azure authentication (Azure Setup page)
2. Verify region is selected
3. Check browser console for errors
4. Ensure backend is running (`docker ps`)
5. Check backend logs (`docker logs autoinfra-backend`)

### Deployment Stuck in "Deploying" Status

**Symptoms**: Deployment shows "Deploying" for >30 minutes

**Solutions**:

1. Check Azure Portal for deployment status
   - Navigate to resource group (deployment ID)
   - View Deployments blade
   - Check for failed deployments
2. Check backend logs for errors
3. Build deployments auto-delete on failure
4. Scenario deployments may require manual intervention

### Cannot Access Jumpbox

**Symptoms**: RDP connection refused or timeout

**Solutions**:

1. Check NSG rules in Azure Portal
   - Resource group > Jumpbox > Networking
   - Verify your public IP is allowed in the inbound rules
2. Confirm jumpbox public IP is correct (shown on Home page)
3. Wait 2-3 minutes after "Deployed" status for RDP to initialize
4. Verify Windows RDP client is configured correctly

### Build Page Shows "Failed to Generate Deployment ID"

**Symptoms**: Error when clicking Build button

**Solutions**:

1. Check backend `/generateBuildID` endpoint is available
2. Verify backend is running
3. Check backend logs for errors
4. Clear browser cookies and retry

### Attacks Not Enabling

**Symptoms**: "Enable Attacks" completes but attacks aren't configured

**Solutions**:

1. Click **Check Attack Status** to verify
2. Check Actions panel for error messages
3. Verify machines are domain-joined
4. Check backend logs for PowerShell script errors
5. Ensure ADVulnEnvModule.psm1 is accessible in Azure Storage

### Users Not Creating

**Symptoms**: "Generate Users" completes but no users appear

**Solutions**:

1. Click **Sync Users** to refresh
2. Check Actions panel for errors
3. Verify Domain Controller is accessible
4. Check backend logs for Azure CLI errors
5. Ensure domain is fully initialized (wait 5 minutes after deployment)

### Deployment Won't Shut Down

**Symptoms**: Click Shut Down, status doesn't change

**Solutions**:

1. Wait 30 seconds and refresh page
2. Check Azure Portal - resource group may be deleting
3. Check backend logs for deletion errors
4. Manually delete resource group in Azure Portal if stuck

---

## Best Practices

### Resource Management

- **Shut Down When Done**: Don't rely on auto-timeout, manually shut down to save costs
- **Design Appropriate Topologies**: Use simpler topologies for basic testing, complex multi-domain forests for enterprise scenarios
- **Monitor Extensions**: Track extension usage to stay within time limits (max 2 extensions, 4 hours total)
- **Save Important States**: Save deployments before making destructive changes

### Topology Design

- **Start Simple**: Begin with basic topologies before complex multi-domain forests
- **Use Templates**: Save working topologies as templates for reuse
- **Test Incrementally**: Deploy and test before adding complexity
- **Document Configurations**: Note custom passwords and configurations
- **Follow Naming Conventions**: Use clear, descriptive hostnames and domain names

### Attack Configuration

- **Enable Attacks Post-Deployment**: Wait for full deployment before enabling attacks
- **Test One Attack at a Time**: Easier to troubleshoot if issues arise
- **Verify Status**: Always check attack status after enabling
- **Document Findings**: Note which attacks work for scenario validation

### User Management

- **Sync Before Attacks**: Sync users to verify creation before enabling attacks
- **Use Realistic Formats**: Choose username formats matching target environments
- **Control User Count**: Start with smaller user counts for testing
- **Verify Group Memberships**: Check users have correct group assignments

### Deployment Workflow

1. **Plan**: Decide scenario or design topology
2. **Deploy**: Submit deployment and monitor status
3. **Wait**: Allow full deployment completion (15-20 minutes)
4. **Configure**: Enable attacks and create users
5. **Verify**: Sync users, check attack status
6. **Test**: RDP to jumpbox and validate environment
7. **Save**: Save deployment if configuration is valuable
8. **Shutdown**: Shut down when finished to avoid costs

### Cost Optimization

- **Use Smaller VMs**: Default B2ms is sufficient for most testing
- **Limit Extensions**: Each hour costs money
- **Delete Unused Saved Deployments**: Gallery images consume storage
- **Monitor Azure Costs**: Check Azure Cost Management regularly

---

## Additional Resources

- **Azure Bicep Documentation**: https://learn.microsoft.com/azure/azure-resource-manager/bicep/
- **BloodHound Documentation**: https://bloodhound.readthedocs.io/
- **GitHub Issues**: https://github.com/[your-org]/autoinfra/issues for bug reports and feature requests

---

**Need Help?**

- Check existing GitHub issues
- Review backend logs: `docker logs autoinfra-backend`
- Review frontend logs: Browser console (F12)
- Check Azure Portal for resource status
- Contact project maintainers

**Last Updated**: February 2026
