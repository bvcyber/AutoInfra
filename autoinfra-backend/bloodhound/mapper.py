"""
Topology Mapper Module for AutoInfra

Converts parsed BloodHound data into AutoInfra topology format for sandbox creation.

AutoInfra topology format:
{
    "credentials": {
        "enterpriseAdminUsername": "buildadmin",
        "enterpriseAdminPassword": "Password#123"
    },
    "nodes": [
        {
            "id": "node-1",
            "type": "domainController",
            "data": {
                "domainControllerName": "DC01",
                "domainName": "build.lab",
                "privateIPAddress": "10.10.0.5",
                "adminUsername": "buildadmin",
                "adminPassword": "Password#123",
                "isSub": false,
                "hasPublicIP": true
            }
        },
        {
            "id": "node-2", 
            "type": "workstation",
            "data": {
                "workstationName": "SRV01",
                "privateIPAddress": "10.10.0.6",
                ...
            }
        }
    ],
    "edges": [
        {"source": "node-1", "target": "node-2", ...}
    ],
    "jumpboxConfig": {...}
}
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .parser import ParsedBloodHoundData, BloodHoundComputer, BloodHoundUser

logger = logging.getLogger(__name__)


@dataclass
class TopologyConfig:
    """Configuration options for topology generation"""
    admin_username: str = "labadmin"
    admin_password: str = "P@ssw0rd123!"
    base_ip_prefix: str = "10.10.0"
    start_ip_octet: int = 5
    include_jumpbox: bool = True
    include_all_machines: bool = True  # If False, only include DCs
    max_workstations: int = 10  # Limit workstations to avoid huge deployments


class TopologyMapper:
    """
    Maps BloodHound data to AutoInfra topology format.
    
    Creates a topology that replicates:
    - Domain structure (DCs, domain names)
    - Computer hierarchy (DCs, servers, workstations)
    - Network connectivity (edges between nodes)
    """
    
    def __init__(self, config: Optional[TopologyConfig] = None):
        self.config = config or TopologyConfig()
        self._node_counter = 0
        self._ip_counter = self.config.start_ip_octet
    
    def map_to_topology(self, bh_data: ParsedBloodHoundData) -> Dict[str, Any]:
        """
        Convert BloodHound data to AutoInfra topology format.
        
        Args:
            bh_data: Parsed BloodHound data
            
        Returns:
            AutoInfra topology dict ready for deployment
        """
        logger.info("TOPOLOGY_MAPPER: Starting topology generation from BloodHound data")
        
        self._node_counter = 0
        self._ip_counter = self.config.start_ip_octet
        
        # Build the topology structure
        topology = {
            "credentials": {
                "enterpriseAdminUsername": self.config.admin_username,
                "enterpriseAdminPassword": self.config.admin_password
            },
            "nodes": [],
            "edges": []
        }
        
        # Get root domain info
        root_domain_name = "lab.local"
        if bh_data.domains:
            root_domain_name = bh_data.domains[0].name.lower()
        
        # Track node IDs for edge creation
        dc_nodes = []
        workstation_nodes = []
        root_dc_node = None
        sub_dc_nodes = []
        
        # Create DC nodes first - sort to put root DC first
        dc_computers = [c for c in bh_data.computers if c.is_domain_controller]
        # Sort by domain depth (root domain has fewer parts)
        dc_computers.sort(key=lambda c: len(c.name.split('.')))
        
        for computer in dc_computers:
            node = self._create_dc_node(computer, root_domain_name)
            topology["nodes"].append(node)
            dc_nodes.append(node["id"])
            
            # Track root vs sub DCs for edge creation
            if node["data"].get("isSub", False):
                sub_dc_nodes.append(node)
            else:
                root_dc_node = node
        
        # Create workstation/server nodes
        if self.config.include_all_machines:
            non_dc_count = 0
            for computer in bh_data.computers:
                if not computer.is_domain_controller:
                    if non_dc_count >= self.config.max_workstations:
                        logger.warning(f"TOPOLOGY_MAPPER: Limiting workstations to {self.config.max_workstations}")
                        break
                    
                    node = self._create_workstation_node(computer, root_domain_name)
                    topology["nodes"].append(node)
                    workstation_nodes.append(node["id"])
                    non_dc_count += 1
        
        # Add jumpbox if configured
        if self.config.include_jumpbox:
            jumpbox_node = self._create_jumpbox_node()
            topology["nodes"].append(jumpbox_node)
            
            # Find the deepest subdomain DC (most domain parts = most nested)
            # e.g., test.sub.build.lab (4 parts) is deeper than sub.build.lab (3 parts)
            deepest_dc = None
            deepest_dc_depth = 0
            for node in topology["nodes"]:
                if node["type"] == "domainController":
                    domain = node["data"].get("domainName", "")
                    depth = len(domain.split('.'))
                    if depth > deepest_dc_depth:
                        deepest_dc_depth = depth
                        deepest_dc = node
            
            # Configure jumpbox to connect to deepest subdomain DC
            connect_to_ip = self.config.base_ip_prefix + "." + str(self.config.start_ip_octet + 1)
            if deepest_dc:
                connect_to_ip = deepest_dc["data"].get("privateIPAddress", connect_to_ip)
            
            topology["jumpboxConfig"] = {
                "privateIPAddress": jumpbox_node["data"]["privateIPAddress"],
                "connectedPrivateIPAddress": connect_to_ip
            }
        
        # Create edges (domain membership relationships)
        # Build domain-to-DC mapping for edge creation
        domain_to_dc = {}
        for node in topology["nodes"]:
            if node["type"] == "domainController":
                domain = node["data"].get("domainName", "").lower()
                domain_to_dc[domain] = node
        
        # Create edges - connect sub DCs to their parent DC
        # Parent domain is determined by removing the first part of the domain name
        # e.g., sub.build.lab -> build.lab, test.sub.build.lab -> sub.build.lab
        for node in topology["nodes"]:
            if node["type"] == "domainController" and node["data"].get("isSub", False):
                domain = node["data"].get("domainName", "").lower()
                domain_parts = domain.split('.')
                
                if len(domain_parts) > 2:
                    # Find parent domain (remove first part)
                    parent_domain = '.'.join(domain_parts[1:])
                    
                    if parent_domain in domain_to_dc:
                        parent_dc = domain_to_dc[parent_domain]
                        topology["edges"].append({
                            "source": parent_dc["id"],
                            "target": node["id"],
                            "sourceHandle": "source",
                            "targetHandle": "target"
                        })
                        logger.info(f"TOPOLOGY_MAPPER: Connected {node['data']['domainControllerName']} ({domain}) to parent {parent_dc['data']['domainControllerName']} ({parent_domain})")
                    elif root_dc_node:
                        # Fallback: connect to root DC
                        topology["edges"].append({
                            "source": root_dc_node["id"],
                            "target": node["id"],
                            "sourceHandle": "source",
                            "targetHandle": "target"
                        })
        
        # Connect workstations to their domain's DC
        for node in topology["nodes"]:
            if node["type"] == "workstation":
                ws_domain = node["data"].get("domainName", "").lower()
                
                # Find the DC for this workstation's domain
                target_dc = None
                if ws_domain in domain_to_dc:
                    target_dc = domain_to_dc[ws_domain]
                elif root_dc_node:
                    target_dc = root_dc_node
                
                if target_dc:
                    topology["edges"].append({
                        "source": target_dc["id"],
                        "target": node["id"],
                        "sourceHandle": "source", 
                        "targetHandle": "target"
                    })
                    logger.info(f"TOPOLOGY_MAPPER: Connected workstation {node['data'].get('workstationName', 'N/A')} to DC {target_dc['data']['domainControllerName']}")
        
        # Connect jumpbox to deepest subdomain DC (most nested domain)
        if self.config.include_jumpbox:
            # Find the deepest subdomain DC
            deepest_dc_node = None
            deepest_dc_depth = 0
            for node in topology["nodes"]:
                if node["type"] == "domainController":
                    domain = node["data"].get("domainName", "")
                    depth = len(domain.split('.'))
                    if depth > deepest_dc_depth:
                        deepest_dc_depth = depth
                        deepest_dc_node = node
            
            if deepest_dc_node:
                jumpbox_id = f"node-{self._node_counter}"
                topology["edges"].append({
                    "source": deepest_dc_node["id"],
                    "target": jumpbox_id,
                    "sourceHandle": "source",
                    "targetHandle": "target"
                })
                logger.info(f"TOPOLOGY_MAPPER: Connected jumpbox to deepest DC {deepest_dc_node['data']['domainControllerName']} ({deepest_dc_node['data']['domainName']})")
        
        logger.info(f"TOPOLOGY_MAPPER: Generated topology with {len(topology['nodes'])} nodes "
                    f"and {len(topology['edges'])} edges")
        
        return topology
    
    def _create_dc_node(self, computer: BloodHoundComputer, root_domain_name: str) -> Dict[str, Any]:
        """Create a domain controller node"""
        self._node_counter += 1
        node_id = f"node-{self._node_counter}"
        
        # Extract hostname and domain from FQDN (e.g., DC02.SUB.BUILD.LAB -> DC02, sub.build.lab)
        parts = computer.name.split('.')
        hostname = parts[0].upper() if parts else computer.name.upper()
        
        # Domain is everything after the hostname
        if len(parts) > 1:
            computer_domain = '.'.join(parts[1:]).lower()
        else:
            computer_domain = root_domain_name
        
        # Determine if this is a sub DC by comparing to root domain
        is_sub = computer_domain.lower() != root_domain_name.lower()
        
        logger.info(f"TOPOLOGY_MAPPER: DC {hostname} domain={computer_domain}, root={root_domain_name}, isSub={is_sub}")
        
        ip_address = f"{self.config.base_ip_prefix}.{self._ip_counter}"
        self._ip_counter += 1
        
        return {
            "id": node_id,
            "type": "domainController",
            "data": {
                "domainControllerName": hostname,
                "domainName": computer_domain,
                "privateIPAddress": ip_address,
                "adminUsername": self.config.admin_username,
                "adminPassword": self.config.admin_password,
                "isSub": is_sub,
                "hasPublicIP": not is_sub  # Only root DC gets public IP by default
            }
        }
    
    def _create_workstation_node(self, computer: BloodHoundComputer, root_domain_name: str) -> Dict[str, Any]:
        """Create a workstation/server node"""
        self._node_counter += 1
        node_id = f"node-{self._node_counter}"
        
        # Extract hostname and domain from FQDN (e.g., SRV01.SUB.BUILD.LAB -> SRV01, sub.build.lab)
        parts = computer.name.split('.')
        hostname = parts[0].upper() if parts else computer.name.upper()
        
        # Domain is everything after the hostname
        if len(parts) > 1:
            computer_domain = '.'.join(parts[1:]).lower()
        else:
            computer_domain = root_domain_name
        
        logger.info(f"TOPOLOGY_MAPPER: Workstation {hostname} domain={computer_domain}")
        
        ip_address = f"{self.config.base_ip_prefix}.{self._ip_counter}"
        self._ip_counter += 1
        
        return {
            "id": node_id,
            "type": "workstation",
            "data": {
                "workstationName": hostname,
                "serverName": hostname,  # Also set serverName for standalone detection
                "privateIPAddress": ip_address,
                "adminUsername": self.config.admin_username,
                "adminPassword": self.config.admin_password,
                "hasPublicIP": False,  # Workstations don't need public IP
                "domainName": computer_domain
            }
        }
    
    def _create_jumpbox_node(self) -> Dict[str, Any]:
        """Create a Kali jumpbox node"""
        self._node_counter += 1
        node_id = f"node-{self._node_counter}"
        
        ip_address = f"{self.config.base_ip_prefix}.{self._ip_counter}"
        self._ip_counter += 1
        
        return {
            "id": node_id,
            "type": "jumpbox",
            "data": {
                "privateIPAddress": ip_address
            }
        }
    
    def generate_user_list(self, bh_data: ParsedBloodHoundData) -> List[Dict[str, Any]]:
        """
        Generate a list of users to create in the sandbox.
        
        Returns list of user dicts with attack attributes for the createSingleUser API.
        """
        users = []
        
        # Skip system accounts
        skip_accounts = {'administrator', 'guest', 'krbtgt', 'defaultaccount'}
        
        for user in bh_data.users:
            sam = user.samaccountname.lower()
            if sam in skip_accounts or sam.endswith('$'):
                continue
            
            if not user.enabled:
                continue
            
            user_info = {
                "username": user.samaccountname,
                "password": "Password#123",  # Standard password for all users
                "attacks": []
            }
            
            # Map BloodHound attributes to AutoInfra attacks
            if user.dontreqpreauth:
                user_info["attacks"].append({
                    "type": "ASREPRoasting",
                    "description": "User has Kerberos pre-auth disabled"
                })
            
            if user.hasspn:
                user_info["attacks"].append({
                    "type": "Kerberoasting",
                    "description": f"User has SPN: {', '.join(user.spn_targets) if user.spn_targets else 'SPN set'}"
                })
            
            if user.unconstraineddelegation:
                user_info["attacks"].append({
                    "type": "UserConstrainedDelegation",  # Actually unconstrained
                    "description": "User has unconstrained delegation"
                })
            
            if user.trustedtoauth and user.allowed_to_delegate:
                user_info["attacks"].append({
                    "type": "UserConstrainedDelegation",
                    "description": f"User can delegate to: {', '.join(user.allowed_to_delegate)}"
                })
            
            users.append(user_info)
        
        logger.info(f"TOPOLOGY_MAPPER: Generated {len(users)} users for sandbox creation")
        return users
    
    def generate_attack_config(self, bh_data: ParsedBloodHoundData) -> Dict[str, Any]:
        """
        Generate attack configuration based on BloodHound findings.
        
        Maps detected vulnerabilities to AutoInfra attack types.
        Also tracks unsupported attacks that BloodHound detected but AutoInfra can't replicate.
        
        Returns:
            Dict with 'attacks' (supported) and 'unsupported' (count of unsupported attacks)
        """
        attacks = {
            "ASREPRoasting": [],
            "Kerberoasting": [],
            "UserConstrainedDelegation": [],
            "ComputerConstrainedDelegation": [],
            "ACLs": []
        }
        
        # Track unsupported attacks
        unsupported_count = 0
        unsupported_types = []
        
        # AS-REP Roasting targets
        for username in bh_data.asrep_roastable_users:
            attacks["ASREPRoasting"].append({
                "targetUser": username,
                "enabled": True
            })
        
        # Kerberoasting targets
        for username in bh_data.kerberoastable_users:
            attacks["Kerberoasting"].append({
                "targetUser": username,
                "enabled": True
            })
        
        # Unconstrained delegation - NOT SUPPORTED by AutoInfra
        if bh_data.unconstrained_delegation:
            unsupported_count += len(bh_data.unconstrained_delegation)
            if "Unconstrained Delegation" not in unsupported_types:
                unsupported_types.append("Unconstrained Delegation")
            logger.info(f"TOPOLOGY_MAPPER: {len(bh_data.unconstrained_delegation)} unconstrained delegation attacks not supported")
        
        # Constrained delegation
        for delegation in bh_data.constrained_delegation:
            if delegation['type'] == 'user':
                attacks["UserConstrainedDelegation"].append({
                    "targetUser": delegation['name'],
                    "targets": delegation['targets'],
                    "enabled": True
                })
            else:
                attacks["ComputerConstrainedDelegation"].append({
                    "targetComputer": delegation['name'],
                    "targets": delegation['targets'],
                    "enabled": True
                })
        
        # ACL-based attacks - only GenericAll is supported
        supported_acl_count = 0
        for acl_path in bh_data.acl_attack_paths[:20]:  # Limit to first 20
            if acl_path['right'] == 'GenericAll':
                attacks["ACLs"].append({
                    "grantingUser": acl_path['source'],
                    "receivingUser": acl_path['target'],
                    "right": acl_path['right'],
                    "enabled": True
                })
                supported_acl_count += 1
            else:
                # Track unsupported ACL rights (WriteDacl, WriteOwner, ForceChangePassword, etc.)
                unsupported_count += 1
        
        # Check if we have unsupported ACL types
        unsupported_acl_rights = set()
        for acl_path in bh_data.acl_attack_paths[:20]:
            if acl_path['right'] != 'GenericAll':
                unsupported_acl_rights.add(acl_path['right'])
        
        if unsupported_acl_rights:
            for right in unsupported_acl_rights:
                if right not in unsupported_types:
                    unsupported_types.append(f"ACL-{right}")
        
        # Filter out empty attack types
        attacks = {k: v for k, v in attacks.items() if v}
        
        total_supported = sum(len(v) for v in attacks.values())
        logger.info(f"TOPOLOGY_MAPPER: Generated attack config with {total_supported} supported attacks, {unsupported_count} unsupported")
        
        return {
            "attacks": attacks,
            "unsupported_count": unsupported_count,
            "unsupported_types": unsupported_types
        }


def map_bloodhound_to_autoinfra(
    bh_data: ParsedBloodHoundData,
    config: Optional[TopologyConfig] = None
) -> Dict[str, Any]:
    """
    Convenience function to map BloodHound data to complete AutoInfra scenario.
    
    Returns a dict containing:
    - topology: AutoInfra topology format
    - users: List of users to create
    - attacks: Attack configuration
    - unsupported_attacks_count: Number of attacks BloodHound found that AutoInfra can't replicate
    - unsupported_attack_types: List of unsupported attack types
    - summary: BloodHound attack summary
    """
    mapper = TopologyMapper(config)
    
    # Get attack config which now includes unsupported info
    attack_result = mapper.generate_attack_config(bh_data)
    
    return {
        "topology": mapper.map_to_topology(bh_data),
        "users": mapper.generate_user_list(bh_data),
        "attacks": attack_result.get("attacks", {}),
        "unsupported_attacks_count": attack_result.get("unsupported_count", 0),
        "unsupported_attack_types": attack_result.get("unsupported_types", []),
        "summary": {
            "domain": bh_data.domains[0].name if bh_data.domains else "Unknown",
            "computers_count": len(bh_data.computers),
            "users_count": len(bh_data.users),
            "asrep_roastable": len(bh_data.asrep_roastable_users),
            "kerberoastable": len(bh_data.kerberoastable_users),
            "delegation_issues": len(bh_data.constrained_delegation) + len(bh_data.unconstrained_delegation),
            "acl_paths": len(bh_data.acl_attack_paths)
        }
    }
