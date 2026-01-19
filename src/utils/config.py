import yaml
import os

def load_config(config_path='config.yaml'):
    """Loads the configuration from a YAML file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def validate_config(config):
    """Validates that all required fields are present in the config."""
    if 'credentials' not in config:
        raise ValueError("Missing 'credentials' section in configuration")
    
    required_creds = ['email', 'password', 'query_name']
    for field in required_creds:
        if field not in config['credentials']:
            raise ValueError(f"Missing required credential field: {field}")
    
    if 'urls' not in config or 'login' not in config['urls'] or 'advanced_query' not in config['urls']:
        raise ValueError("Missing required 'urls' section (login/advanced_query)")
    
    return True
