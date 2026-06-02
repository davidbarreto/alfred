from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets
import os

bearer = HTTPBearer()

def require_auth(credentials: HTTPAuthorizationCredentials = Security(bearer)):
    token = os.environ["ALFRED_API_TOKEN"]
    if not secrets.compare_digest(credentials.credentials, token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)