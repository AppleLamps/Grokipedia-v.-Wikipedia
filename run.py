"""Application entry point"""
from dotenv import load_dotenv
from app import create_app
from app.utils.sdk_manager import initialize_sdk

# Load environment variables
load_dotenv()

# Initialize SDK before creating app
initialize_sdk()

# Create Flask application
app = create_app()

# Note: On Railway, uses SQLite-backed slug index for memory efficiency
# The database is built during the release phase (see Procfile)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

