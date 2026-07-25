import os

# Must be set before any app module is imported — config.py reads env vars at
# import time via a module-level get_settings() call, and Settings has no
# default for it.
os.environ.setdefault("ALFRED_API_TOKEN", "test-api-token")
