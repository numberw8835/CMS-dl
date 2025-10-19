# config.py
import os
import json

def load_credentials():
    """Load credentials from ~/.guc_account.json or prompt for input."""
    config_path = os.path.expanduser("~/.guc_account.json")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
                return data.get('username'), data.get('password')
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    
    return None, None

def save_credentials(username, password):
    """Save credentials to ~/.guc_account.json."""
    config_path = os.path.expanduser("~/.guc_account.json")
    try:
        with open(config_path, 'w') as f:
            json.dump({"username": username, "password": password}, f)
        return True
    except Exception as e:
        print(f"Warning: Could not save credentials: {e}")
        return False

def load_course_definitions():  
    """Load course definitions from courses.json from current directory."""  
    config_path = 'courses.json'  # Look in current directory
    if os.path.exists(config_path):  
        try:  
            with open(config_path, 'r') as f:  
                return json.load(f)  
        except (json.JSONDecodeError, FileNotFoundError):  
            print(f"Warning: Could not load course definitions from {config_path}")
            return {}
    return {}  