import os
import secrets

# Flask application configuration
SECRET_KEY = secrets.token_hex(16)  # Generates a random secret key
PANEL_PASSWORD = os.environ.get('PANEL_PASSWORD', 'ChangeMe#12345') # Default password if not set via env var
PANEL_API_KEY = os.environ.get('PANEL_API_KEY', secrets.token_urlsafe(32)) # Generate a random API key if not set

# Session configuration (optional, Flask defaults are usually fine)
# SESSION_COOKIE_SECURE = True
# SESSION_COOKIE_HTTPONLY = True
# SESSION_COOKIE_SAMESITE = 'Lax'

# Logging configuration (optional)
LOGGING_LEVEL = 'INFO'
