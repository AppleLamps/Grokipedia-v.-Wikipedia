"""SDK client management and initialization"""
import sys
from pathlib import Path

# SDK module-level storage
_sdk_available = False
_cached_client = None
Client = None
ArticleNotFound = Exception
RequestError = Exception


def initialize_sdk():
    """Initialize the Grokipedia SDK and set availability flag"""
    global _sdk_available, Client, ArticleNotFound, RequestError

    try:
        # Prefer local SDK in repo if present (keeps search index in sync)
        sdk_path = Path(__file__).parent.parent.parent / "grokipedia-sdk"
        if sdk_path.exists() and str(sdk_path) not in sys.path:
            sys.path.insert(0, str(sdk_path))
        from grokipedia_sdk import Client as SDKClient, ArticleNotFound as SDKArticleNotFound, RequestError as SDKRequestError
        _sdk_available = True
        Client = SDKClient
        ArticleNotFound = SDKArticleNotFound
        RequestError = SDKRequestError
        return True
    except ImportError:
        # If that fails, try importing as installed package
        try:
            from grokipedia_sdk import Client as SDKClient, ArticleNotFound as SDKArticleNotFound, RequestError as SDKRequestError
            _sdk_available = True
            Client = SDKClient
            ArticleNotFound = SDKArticleNotFound
            RequestError = SDKRequestError
            return True
        except ImportError as e:
            print(f"Warning: Could not import Grokipedia SDK: {e}")
            print("Please ensure dependencies are installed: pip install -r requirements.txt")
            print("Or install the SDK package: pip install -e grokipedia-sdk/")
            _sdk_available = False
            return False


def is_sdk_available():
    """Check if SDK is available"""
    return _sdk_available


def get_cached_client():
    """Get or create a cached SDK client instance for reuse"""
    global _cached_client
    if _cached_client is None and _sdk_available:
        print("Initializing Grokipedia SDK client (loading article index)...")
        try:
            from app.config import Config
            from grokipedia_sdk import SlugIndex
            slug_index = SlugIndex(links_dir=Config.LINKS_DIR)
            _cached_client = Client(slug_index=slug_index)
        except Exception:
            _cached_client = Client()
        print("SDK client ready!")
    return _cached_client


def get_sdk_client():
    """Get a new SDK client instance (for one-off operations)"""
    if not _sdk_available:
        raise RuntimeError("SDK not available")
    return Client()


def warm_slug_index():
    """Preload slug index to reduce first-search latency."""
    if not _sdk_available:
        return False

    try:
        client = get_cached_client()
        if not client:
            return False
        client.get_total_article_count()
        client.search_slug("indexwarm", limit=1, fuzzy=False)
        return True
    except Exception as e:
        print(f"Warning: failed to warm slug index: {e}")
        return False

