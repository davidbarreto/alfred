from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets
from app.config import get_settings

bearer = HTTPBearer()

def require_auth(credentials: HTTPAuthorizationCredentials = Security(bearer)):
    if not secrets.compare_digest(credentials.credentials, get_settings().alfred_api_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)