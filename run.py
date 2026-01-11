"""Application entry point"""
import os
from dotenv import load_dotenv
from app import create_app
from app.utils.sdk_manager import initialize_sdk

# Load environment variables
load_dotenv()

# Enable lightweight mode by default on Railway (no BK-tree, faster startup)
if os.environ.get('RAILWAY_ENVIRONMENT') and not os.environ.get('GROKIPEDIA_LIGHTWEIGHT'):
    os.environ['GROKIPEDIA_LIGHTWEIGHT'] = 'true'

# Initialize SDK before creating app
initialize_sdk()

# Create Flask application
app = create_app()

# Note: Slug index loads lazily on first search request

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

