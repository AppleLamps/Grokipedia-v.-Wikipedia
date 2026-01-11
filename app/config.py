"""Application configuration"""
import os
import warnings
from pathlib import Path


class Config:
    """Base configuration"""
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        warnings.warn(
            "SECRET_KEY not set - using insecure default. "
            "Set SECRET_KEY environment variable in production.",
            RuntimeWarning
        )
        SECRET_KEY = 'dev-secret-key-change-in-production'
    
    # OpenRouter API settings
    OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    # Grokipedia SDK settings
    LINKS_DIR = os.path.join(
        Path(__file__).parent.parent,
        'grokipedia-sdk',
        'grokipedia_sdk',
        'links'
    )
    # Lightweight mode disables BK-tree for faster startup (uses ~90% less memory)
    # Auto-enabled on Railway, or set GROKIPEDIA_LIGHTWEIGHT=true
    LIGHTWEIGHT_MODE = os.getenv('GROKIPEDIA_LIGHTWEIGHT', '').strip().lower() in (
        '1', 'true', 'yes', 'on'
    ) or bool(os.environ.get('RAILWAY_ENVIRONMENT'))

