import re

def validate_username(username) -> str | bool:
    if bool(re.match(r'^\w{3,20}$', username)):
        return username
    else:
        return False

def validate_machine_name(machine_name) -> str | bool:
    if bool(re.match(r'^[a-zA-Z0-9-]{1,15}$', machine_name)):
        return machine_name
    else:
        return False

def validate_domain_name(domain_name) -> str | bool:
    parts = domain_name.split('.')
    if len(parts) < 2:
        return False

    for part in parts:
        if not part or len(part) > 15 or not re.match(r'^[a-zA-Z0-9-]+$', part):
            return False

    return domain_name
