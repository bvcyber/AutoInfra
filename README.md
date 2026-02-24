<div align="center">

  <img src="https://github.com/bvcyber.png" alt="Bureau Veritas" width="64" />

  # Auto Infra

  > Automated deployment and management platform for vulnerable Active Directory environments on Azure

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Next.js](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org/)
[![Flask](https://img.shields.io/badge/Flask-2.x-lightgrey)](https://flask.palletsprojects.com/)
[![Azure](https://img.shields.io/badge/Azure-Bicep-blue)](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)

  [Docs](#) · [Report an Issue](issues)

</div>

**Created by Fabian Vilela and Jay Turner**

*Developed during employment at BV Cyber*

> **WARNING**: This platform deploys intentionally vulnerable Active Directory environments. It is designed for **authorized security testing, training, and research only**. Do not deploy in production environments. Do not expose deployed resources to the internet beyond the auto-configured NSG rules. Users are solely responsible for ensuring compliance with all applicable laws and organizational policies.
>
> **COST DISCLAIMER**: This tool creates real Azure resources (virtual machines, storage, networking) that incur charges on your Azure subscription. You are fully responsible for all costs associated with resources deployed through this platform. Always shut down deployments when finished and verify all resources have been deleted in the Azure Portal. The maintainers are not responsible for any Azure charges incurred.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Overview

Auto Infra is an infrastructure management platform designed to rapidly deploy, configure, and manage vulnerable Active Directory environments in Azure. Built for security professionals, red teamers, and penetration testers, it provides an intuitive web interface to spin up realistic attack scenarios with pre-configured vulnerabilities, automated user generation, and integrated attack path management.

### Who Is This For?

- **Security Training**: Hands-on learning environment for Active Directory attack vectors and defensive techniques
- **Exploit Testing**: Safe sandbox for validating exploits before client engagements
- **Security Research**: Flexible platform for AD security research and vulnerability analysis
- **CTF Development**: Build and deploy custom CTF challenges with realistic AD infrastructure

## Features

### Core Capabilities

- **One-Click Deployment**: Deploy complex multi-domain AD environments in minutes
- **Custom Topology Builder**: Visual drag-and-drop interface for designing network topologies
- **BloodHound Import**: Convert BloodHound collections into deployable Azure infrastructure
- **Attack Path Management**: Enable/disable specific vulnerabilities and attack paths on live environments
- **Automated User Generation**: Create bulk users with configurable attributes and group memberships
- **Certificate Authority Integration**: Deploy AD CS with configurable ESC vulnerabilities
- **Scenario Versioning**: Save deployment states with per-machine version management
- **Resource Management**: Time-limited deployments with extensible timeouts and automated cleanup

## Prerequisites

- **Docker & Docker Compose**: Container runtime ([Install Guide](https://docs.docker.com/compose/install/))
- **Azure Subscription**: Active Azure account with Contributor access
- **Azure Service Principal**: With Contributor role on your subscription

If you don't have a service principal, create one using:

```bash
az ad sp create-for-rbac --name "autoinfra" --role Contributor --scopes /subscriptions/<subscription-id>
```

This outputs the `appId` (Client ID), `password` (Client Secret), and `tenant` (Tenant ID) you'll need.

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/bvcyber/AutoInfra.git
cd autoinfra
```

### 2. Build and Start Services

```bash
docker compose up
```

This will:

- Build the frontend and backend Docker images
- Start both containers
- Expose the frontend on `http://localhost:3000`
- Expose the backend API on `http://localhost:8100`

### 3. Configure Azure Authentication

1. Navigate to `http://localhost:3000`
2. Go to **Azure Setup** page
3. Enter your Azure service principal credentials:
   - **Client ID**: Your service principal's application (client) ID
   - **Client Secret**: Your service principal's secret value
   - **Tenant ID**: Your Azure AD tenant ID
   - **Subscription ID**: Your target Azure subscription ID
4. Click **Authenticate**
5. Select your preferred deployment region

## Quick Start

### Build a Custom Topology

1. Navigate to **Build** page
2. Add nodes from the dropdown (Domain Controllers, CAs, Workstations)
3. Connect nodes to define network relationships
4. Configure node properties (hostnames, passwords, IP addresses)
5. Click **Build** to deploy to Azure
6. Once deployed, enable attacks and create users from the **Home** page

### Import BloodHound Data

1. Navigate to **BloodHound** page
2. Upload your BloodHound JSON export
3. Click **Generate Topology** to convert to a deployable network
4. Review and deploy to Azure
5. Configure users and attacks on the live environment

### Deploy a Saved Scenario

1. Navigate to **Deploy** page
2. Select a scenario from the list
3. Choose version (unified or per-machine)
4. Click **Deploy**

## Usage

For detailed usage instructions covering all features, see [USAGE.md](USAGE.md).

### Managing Deployments

- **Home page** displays deployment status, jumpbox IP, RDP credentials, and remaining time
- **Extend** adds 1 hour (maximum 2 extensions, 4 hours total)
- **Shut Down** destroys all Azure resources immediately
- Deployments automatically clean up after timeout expires

### Configuring Attacks

1. Navigate to **Home** page with an active deployment
2. Open the **Configuration** panel and click **Attacks**
3. Select vulnerabilities to enable
4. Click **Enable Selected Attacks**

### Saving Deployments as Scenarios

1. Wait for the save blocker timer to complete after deployment
2. Click **Save as Scenario**
3. Machine images are captured to Azure Compute Gallery
4. Topology, users, and enabled attacks are preserved
5. Saved scenarios appear on the **Deploy** page for future reuse

## Development

### Running Locally (Without Docker)

**Frontend:**

```bash
cd autoinfra-frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:3000`

**Backend:**

```bash
cd autoinfra-backend
pip install -r requirements.txt
python app.py
```

Backend runs on `http://localhost:8100`

### API Endpoints

See `autoinfra-frontend/src/app/app.config.js` for the complete endpoint list.

## Troubleshooting

| Problem                              | Solution                                                                                                           |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Deployment fails to start            | Check Azure authentication on the Azure Setup page. Verify backend is running with `docker logs autoinfra-backend` |
| Stuck in "Deploying" for >30 minutes | Check Azure Portal for failed deployments in the resource group                                                    |
| Cannot RDP to jumpbox                | Wait 2-3 minutes after "Deployed" status. Verify NSG rules allow your IP in Azure Portal                           |
| Attacks not enabling                 | Check Actions panel for errors. Verify machines are domain-joined and fully initialized                            |
| Users not appearing                  | Click **Sync Users** to refresh. Wait 5 minutes after deployment for domain initialization                         |
| Deployment won't shut down           | Check Azure Portal - resource group may still be deleting. Manually delete if stuck                                |

For more detailed troubleshooting, see [USAGE.md](USAGE.md#troubleshooting).

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

For bug reports and feature requests, open an issue on GitHub.

## Security

This platform deploys **intentionally vulnerable** infrastructure. Please:

- Only deploy in authorized environments
- Do not expose deployments beyond the auto-configured NSG rules
- Properly shut down and delete all resources after use
- Report security vulnerabilities in the platform itself to the maintainers privately

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**See [USAGE.md](USAGE.md) for the complete usage guide.**



<div align="center">

  Maintained by [Bureau Veritas](https://cybersecurity.bureauveritas.com/)

</div>
