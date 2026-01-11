"""Application entry point"""
from dotenv import load_dotenv
from app import create_app
from app.utils.sdk_manager import initialize_sdk, warm_slug_index

# Load environment variables
load_dotenv()

# Initialize SDK before creating app
initialize_sdk()
warm_slug_index()

# Create Flask application
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

