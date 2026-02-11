"""
BloodHound Parser Module for AutoInfra

Parses BloodHound v6 JSON exports (from SharpHound) and extracts:
- Domain information
- Computers (DCs, workstations, servers)
- Users with attack-relevant attributes
- Groups and memberships
- ACL-based attack paths

This data is then mapped to AutoInfra's topology format for sandbox replication.
"""

import json
import zipfile
import os
import tempfile
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BloodHoundUser:
    """Represents a user from BloodHound data with attack-relevant attributes"""
    samaccountname: str
    name: str  # Full UPN like USER1@BUILD.LAB
    sid: str
    domain: str
    enabled: bool = True
    is_admin: bool = False
    is_domain_admin: bool = False
    
    # Attack-relevant attributes
    dontreqpreauth: bool = False      # AS-REP Roastable
    hasspn: bool = False              # Kerberoastable
    unconstraineddelegation: bool = False
    trustedtoauth: bool = False       # Constrained delegation
    admincount: bool = False
    passwordnotreqd: bool = False
    pwdneverexpires: bool = False
    
    # Delegation targets
    allowed_to_delegate: List[str] = field(default_factory=list)
    spn_targets: List[str] = field(default_factory=list)
    
    # Group memberships (SIDs)
    primary_group_sid: Optional[str] = None


@dataclass  
class BloodHoundComputer:
    """Represents a computer from BloodHound data"""
    name: str  # Hostname like DC01.BUILD.LAB
    samaccountname: str
    sid: str
    domain: str
    os: Optional[str] = None
    
    # Machine type detection
    is_domain_controller: bool = False
    unconstraineddelegation: bool = False
    trustedtoauth: bool = False
    
    # Delegation targets
    allowed_to_delegate: List[str] = field(default_factory=list)


@dataclass
class BloodHoundDomain:
    """Represents a domain from BloodHound data"""
    name: str  # FQDN like BUILD.LAB
    sid: str
    functional_level: Optional[str] = None
    
    # Domain-level policy (from Properties)
    lockout_threshold: int = 0
    machine_account_quota: int = 10


@dataclass
class BloodHoundACE:
    """Represents an ACL-based attack path"""
    source_sid: str
    source_type: str  # User, Group, Computer
    target_sid: str
    target_type: str
    right: str  # GenericAll, WriteDacl, WriteOwner, etc.
    is_inherited: bool


@dataclass
class ParsedBloodHoundData:
    """Container for all parsed BloodHound data"""
    domains: List[BloodHoundDomain] = field(default_factory=list)
    computers: List[BloodHoundComputer] = field(default_factory=list)
    users: List[BloodHoundUser] = field(default_factory=list)
    groups: Dict[str, Dict] = field(default_factory=dict)  # SID -> group info
    aces: List[BloodHoundACE] = field(default_factory=list)
    
    # Attack path detection results
    asrep_roastable_users: List[str] = field(default_factory=list)
    kerberoastable_users: List[str] = field(default_factory=list)
    unconstrained_delegation: List[str] = field(default_factory=list)
    constrained_delegation: List[str] = field(default_factory=list)
    acl_attack_paths: List[Dict] = field(default_factory=list)


class BloodHoundParser:
    """
    Parses BloodHound JSON exports from SharpHound.
    
    Supports BloodHound v6 JSON format with files:
    - *_domains.json
    - *_computers.json
    - *_users.json
    - *_groups.json
    - *_ous.json
    - *_gpos.json
    - *_containers.json
    """
    
    def __init__(self):
        self.result = ParsedBloodHoundData()
        self._sid_to_name: Dict[str, str] = {}  # Cache for SID resolution
    
    def parse_zip(self, zip_path: str) -> ParsedBloodHoundData:
        """
        Parse a BloodHound zip file containing JSON exports.
        
        Args:
            zip_path: Path to the BloodHound zip file
            
        Returns:
            ParsedBloodHoundData containing all extracted information
        """
        logger.info(f"BLOODHOUND_PARSER: Parsing zip file: {zip_path}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Extract zip contents
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(temp_dir)
            
            # Find and parse each JSON file type
            for filename in os.listdir(temp_dir):
                filepath = os.path.join(temp_dir, filename)
                if not filename.endswith('.json'):
                    continue
                    
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if '_domains' in filename.lower():
                    self._parse_domains(data)
                elif '_computers' in filename.lower():
                    self._parse_computers(data)
                elif '_users' in filename.lower():
                    self._parse_users(data)
                elif '_groups' in filename.lower():
                    self._parse_groups(data)
        
        # Detect attack paths after parsing all data
        self._detect_attack_paths()
        
        logger.info(f"BLOODHOUND_PARSER: Parsed {len(self.result.domains)} domains, "
                    f"{len(self.result.computers)} computers, {len(self.result.users)} users")
        
        return self.result
    
    def parse_directory(self, dir_path: str) -> ParsedBloodHoundData:
        """
        Parse BloodHound JSON files from a directory.
        
        Args:
            dir_path: Path to directory containing BloodHound JSON files
            
        Returns:
            ParsedBloodHoundData containing all extracted information
        """
        logger.info(f"BLOODHOUND_PARSER: Parsing directory: {dir_path}")
        
        for filename in os.listdir(dir_path):
            filepath = os.path.join(dir_path, filename)
            if not filename.endswith('.json'):
                continue
                
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if '_domains' in filename.lower():
                self._parse_domains(data)
            elif '_computers' in filename.lower():
                self._parse_computers(data)
            elif '_users' in filename.lower():
                self._parse_users(data)
            elif '_groups' in filename.lower():
                self._parse_groups(data)
        
        # Detect attack paths after parsing all data
        self._detect_attack_paths()
        
        logger.info(f"BLOODHOUND_PARSER: Parsed {len(self.result.domains)} domains, "
                    f"{len(self.result.computers)} computers, {len(self.result.users)} users")
        
        return self.result
    
    def _normalize_delegation_targets(self, targets: List) -> List[str]:
        """
        Normalize AllowedToDelegate/SPNTargets to list of strings.
        Newer BloodHound exports contain objects with ObjectIdentifier/ObjectType.
        """
        normalized = []
        for target in targets:
            if isinstance(target, str):
                normalized.append(target)
            elif isinstance(target, dict):
                # Extract ObjectIdentifier (SID) or any useful string
                obj_id = target.get('ObjectIdentifier', '')
                obj_type = target.get('ObjectType', '')
                if obj_id:
                    normalized.append(f"{obj_id} ({obj_type})" if obj_type else obj_id)
        return normalized
    
    def _parse_domains(self, data: Dict) -> None:
        """Parse domains JSON file"""
        items = data.get('data', [])
        for item in items:
            props = item.get('Properties', {})
            
            domain = BloodHoundDomain(
                name=props.get('name', props.get('domain', '')),
                sid=item.get('ObjectIdentifier', ''),
                functional_level=props.get('functionallevel', None)
            )
            
            # Extract domain policy if available
            if 'lockoutthreshold' in props:
                domain.lockout_threshold = props.get('lockoutthreshold', 0) or 0
            if 'machineaccountquota' in props:
                domain.machine_account_quota = props.get('machineaccountquota', 10) or 10
            
            self.result.domains.append(domain)
            self._sid_to_name[domain.sid] = domain.name
    
    def _parse_computers(self, data: Dict) -> None:
        """Parse computers JSON file"""
        items = data.get('data', [])
        for item in items:
            props = item.get('Properties', {})
            
            computer = BloodHoundComputer(
                name=props.get('name', ''),
                samaccountname=props.get('samaccountname', ''),
                sid=item.get('ObjectIdentifier', ''),
                domain=props.get('domain', ''),
                os=props.get('operatingsystem', None),
                is_domain_controller=props.get('isdc', False),
                unconstraineddelegation=props.get('unconstraineddelegation', False),
                trustedtoauth=props.get('trustedtoauth', False),
                allowed_to_delegate=self._normalize_delegation_targets(item.get('AllowedToDelegate', []))
            )
            
            self.result.computers.append(computer)
            self._sid_to_name[computer.sid] = computer.name
    
    def _parse_users(self, data: Dict) -> None:
        """Parse users JSON file"""
        items = data.get('data', [])
        for item in items:
            props = item.get('Properties', {})
            
            # Skip built-in/system users without real SAM account names
            samaccountname = props.get('samaccountname', '')
            if not samaccountname or samaccountname.startswith('$'):
                continue
            
            user = BloodHoundUser(
                samaccountname=samaccountname,
                name=props.get('name', ''),
                sid=item.get('ObjectIdentifier', ''),
                domain=props.get('domain', ''),
                enabled=props.get('enabled', True),
                
                # Attack-relevant attributes
                dontreqpreauth=props.get('dontreqpreauth', False),
                hasspn=props.get('hasspn', False),
                unconstraineddelegation=props.get('unconstraineddelegation', False),
                trustedtoauth=props.get('trustedtoauth', False),
                admincount=props.get('admincount', False),
                passwordnotreqd=props.get('passwordnotreqd', False),
                pwdneverexpires=props.get('pwdneverexpires', False),
                
                # Delegation - normalize to strings (newer BH versions use objects)
                allowed_to_delegate=self._normalize_delegation_targets(item.get('AllowedToDelegate', [])),
                spn_targets=self._normalize_delegation_targets(item.get('SPNTargets', [])),
                primary_group_sid=item.get('PrimaryGroupSID', None)
            )
            
            self.result.users.append(user)
            self._sid_to_name[user.sid] = user.name
            
            # Also parse ACEs for this user
            self._parse_aces(item, 'User')
    
    def _parse_groups(self, data: Dict) -> None:
        """Parse groups JSON file"""
        items = data.get('data', [])
        for item in items:
            props = item.get('Properties', {})
            sid = item.get('ObjectIdentifier', '')
            
            self.result.groups[sid] = {
                'name': props.get('name', ''),
                'samaccountname': props.get('samaccountname', ''),
                'domain': props.get('domain', ''),
                'members': item.get('Members', []),
                'admincount': props.get('admincount', False)
            }
            
            self._sid_to_name[sid] = props.get('name', '')
    
    def _parse_aces(self, item: Dict, source_type: str) -> None:
        """Parse ACEs from an object"""
        aces = item.get('Aces', [])
        source_sid = item.get('ObjectIdentifier', '')
        
        # Important rights for attack paths
        important_rights = {
            'GenericAll', 'GenericWrite', 'WriteDacl', 'WriteOwner',
            'AllExtendedRights', 'ForceChangePassword', 'AddMember',
            'AddKeyCredentialLink', 'ReadLAPSPassword', 'ReadGMSAPassword'
        }
        
        for ace_data in aces:
            right = ace_data.get('RightName', '')
            if right not in important_rights:
                continue
            
            ace = BloodHoundACE(
                source_sid=source_sid,
                source_type=source_type,
                target_sid=ace_data.get('PrincipalSID', ''),
                target_type=ace_data.get('PrincipalType', ''),
                right=right,
                is_inherited=ace_data.get('IsInherited', False)
            )
            
            # Only track non-inherited ACEs for attack paths
            if not ace.is_inherited:
                self.result.aces.append(ace)
    
    def _detect_attack_paths(self) -> None:
        """Analyze parsed data to detect attack paths"""
        
        # AS-REP Roastable users
        for user in self.result.users:
            if user.enabled and user.dontreqpreauth:
                self.result.asrep_roastable_users.append(user.samaccountname)
                logger.info(f"BLOODHOUND_PARSER: Found AS-REP Roastable user: {user.samaccountname}")
        
        # Kerberoastable users
        for user in self.result.users:
            if user.enabled and user.hasspn and not user.samaccountname.lower() == 'krbtgt':
                self.result.kerberoastable_users.append(user.samaccountname)
                logger.info(f"BLOODHOUND_PARSER: Found Kerberoastable user: {user.samaccountname}")
        
        # Unconstrained delegation
        for computer in self.result.computers:
            if computer.unconstraineddelegation:
                self.result.unconstrained_delegation.append(computer.name)
                logger.info(f"BLOODHOUND_PARSER: Found unconstrained delegation: {computer.name}")
        
        for user in self.result.users:
            if user.enabled and user.unconstraineddelegation:
                self.result.unconstrained_delegation.append(user.samaccountname)
        
        # Constrained delegation
        for computer in self.result.computers:
            if computer.allowed_to_delegate:
                self.result.constrained_delegation.append({
                    'name': computer.name,
                    'type': 'computer',
                    'targets': computer.allowed_to_delegate
                })
        
        for user in self.result.users:
            if user.enabled and user.allowed_to_delegate:
                self.result.constrained_delegation.append({
                    'name': user.samaccountname,
                    'type': 'user',
                    'targets': user.allowed_to_delegate
                })
        
        # ACL-based attack paths (non-inherited dangerous ACLs)
        dangerous_rights = {'GenericAll', 'WriteDacl', 'WriteOwner', 'ForceChangePassword'}
        for ace in self.result.aces:
            if ace.right in dangerous_rights:
                source_name = self._sid_to_name.get(ace.source_sid, ace.source_sid)
                target_name = self._sid_to_name.get(ace.target_sid, ace.target_sid)
                
                self.result.acl_attack_paths.append({
                    'source': source_name,
                    'source_type': ace.source_type,
                    'target': target_name,
                    'target_type': ace.target_type,
                    'right': ace.right
                })
    
    def get_attack_summary(self) -> Dict[str, Any]:
        """Get a summary of detected attack paths"""
        return {
            'asrep_roastable': self.result.asrep_roastable_users,
            'kerberoastable': self.result.kerberoastable_users,
            'unconstrained_delegation': self.result.unconstrained_delegation,
            'constrained_delegation': self.result.constrained_delegation,
            'acl_attack_paths': self.result.acl_attack_paths[:20]  # Limit for display
        }
    
    def get_domain_info(self) -> Optional[Dict[str, Any]]:
        """Get primary domain information"""
        if not self.result.domains:
            return None
        
        domain = self.result.domains[0]
        return {
            'name': domain.name,
            'sid': domain.sid,
            'functional_level': domain.functional_level,
            'lockout_threshold': domain.lockout_threshold,
            'machine_account_quota': domain.machine_account_quota
        }


# Utility function for testing
def parse_bloodhound_data(path: str) -> ParsedBloodHoundData:
    """
    Convenience function to parse BloodHound data from a path.
    
    Args:
        path: Path to either a zip file or directory containing JSON files
        
    Returns:
        ParsedBloodHoundData
    """
    parser = BloodHoundParser()
    
    if path.endswith('.zip'):
        return parser.parse_zip(path)
    elif os.path.isdir(path):
        return parser.parse_directory(path)
    else:
        raise ValueError(f"Path must be a .zip file or directory: {path}")
