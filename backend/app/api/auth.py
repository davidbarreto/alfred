import logging
import secrets

from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings

logger = logging.getLogger(__name__)
bearer = HTTPBearer()


def require_auth(credentials: HTTPAuthorizationCredentials = Security(bearer)):
    if not secrets.compare_digest(credentials.credentials, get_settings().alfred_api_token):
        logger.warning("Auth failed: invalid token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)