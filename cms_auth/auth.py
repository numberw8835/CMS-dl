# auth.py
import requests
from requests.exceptions import HTTPError, RequestException
from requests_ntlm import HttpNtlmAuth

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def authenticate(username: str, password: str):
    """Authenticate with GUC CMS and return a session object."""
    session = requests.Session()
    session.verify = False
    session.auth = HttpNtlmAuth(f"GUC\\{username}", password)
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    try:
        response = session.get("https://cms.guc.edu.eg")
        response.raise_for_status()
        return session
    except HTTPError as e:
        if e.response.status_code == 401:
            raise ValueError(
                "Authentication failed: Invalid username or password"
            ) from e
        raise ValueError(f"HTTP error during authentication: {e}") from e
    except RequestException as e:
        raise ValueError(f"Network error during authentication: {e}") from e
