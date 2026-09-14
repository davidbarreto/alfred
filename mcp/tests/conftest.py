import os
from pathlib import Path

# Must be set before any app module is imported — config.py reads env vars at
# import time via a module-level get_settings() call, and Settings has no
# default for it.
os.environ.setdefault("ALFRED_API_TOKEN", "test-api-token")
os.environ.setdefault("MCP_PUBLIC_URL", "http://testserver")
os.environ.setdefault("MCP_LOGIN_PASSWORD", "test-password")
os.environ.setdefault("MCP_SESSION_SECRET_KEY", "test-session-secret")
os.environ.setdefault("MCP_OAUTH_DB_PATH", str(Path(__file__).parent / "_test_oauth.db"))
