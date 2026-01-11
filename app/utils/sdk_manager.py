"""SDK client management and initialization"""
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# SDK module-level storage
_sdk_available = False
_cached_client = None
_sqlite_index = None
Client = None
ArticleNotFound = Exception
RequestError = Exception


def _use_sqlite_index() -> bool:
    """Check if we should use the SQLite index (for Railway/production)."""
    # Use SQLite on Railway or when explicitly requested
    return bool(
        os.environ.get('RAILWAY_ENVIRONMENT') or
        os.environ.get('USE_SQLITE_INDEX', '').lower() in ('1', 'true', 'yes')
    )


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
            logger.warning(
                "Could not import Grokipedia SDK: %s. "
                "Please ensure dependencies are installed: pip install -r requirements.txt "
                "or install the SDK package: pip install -e grokipedia-sdk/",
                e
            )
            _sdk_available = False
            return False


def is_sdk_available():
    """Check if SDK is available"""
    return _sdk_available


def get_sqlite_index():
    """Get the SQLite-based slug index (memory efficient for production)."""
    global _sqlite_index
    if _sqlite_index is None:
        from app.utils.sqlite_slug_index import get_sqlite_slug_index
        _sqlite_index = get_sqlite_slug_index()
    return _sqlite_index


def get_cached_client():
    """Get or create a cached SDK client instance for reuse.
    
    On Railway/production, uses SQLite-backed index for memory efficiency.
    Locally, uses the in-memory index for faster development iteration.
    """
    global _cached_client
    
    if _cached_client is None and _sdk_available:
        logger.info("Initializing Grokipedia SDK client")
        
        if _use_sqlite_index():
            # Production: Use SQLite-based client wrapper
            logger.info("Using SQLite-backed slug index for memory efficiency")
            _cached_client = _SQLiteClientWrapper()
        else:
            # Development: Use in-memory index
            try:
                from app.config import Config
                from grokipedia_sdk import SlugIndex
                slug_index = SlugIndex(
                    links_dir=Config.LINKS_DIR,
                    use_bktree=not Config.LIGHTWEIGHT_MODE
                )
                _cached_client = Client(slug_index=slug_index)
            except Exception:
                _cached_client = Client()
        
        logger.info("SDK client ready")
    return _cached_client


class _SQLiteClientWrapper:
    """Wrapper that provides SDK-like interface using SQLite index."""
    
    def __init__(self):
        self._sqlite_index = None
        self._client = None
    
    @property
    def sqlite_index(self):
        if self._sqlite_index is None:
            self._sqlite_index = get_sqlite_index()
        return self._sqlite_index
    
    @property 
    def client(self):
        """Lazy-load the actual SDK client (without slug index) for article fetching."""
        if self._client is None and _sdk_available:
            self._client = Client()
        return self._client
    
    def search_slug(self, query: str, limit: int = 10, fuzzy: bool = True, min_similarity: float = 0.6) -> list:
        """Search for slugs using SQLite index."""
        return self.sqlite_index.search(query, limit=limit, fuzzy=fuzzy)
    
    def list_available_articles(self, prefix: str = "", limit: int = 100) -> list:
        """List articles by prefix using SQLite index."""
        return self.sqlite_index.list_by_prefix(prefix=prefix, limit=limit)
    
    def get_total_article_count(self) -> int:
        """Get total article count from SQLite index."""
        return self.sqlite_index.get_total_count()
    
    def slug_exists(self, slug: str) -> bool:
        """Check if slug exists in SQLite index."""
        return self.sqlite_index.exists(slug)
    
    def find_best_match(self, query: str, min_similarity: float = 0.6) -> str:
        """Find best matching slug."""
        return self.sqlite_index.find_best_match(query, min_similarity)
    
    def get_article(self, slug: str):
        """Fetch article content (delegates to actual SDK client)."""
        if self.client:
            return self.client.get_article(slug)
        raise RuntimeError("SDK client not available")
    
    def get_article_async(self, slug: str):
        """Fetch article content asynchronously."""
        if self.client:
            return self.client.get_article_async(slug)
        raise RuntimeError("SDK client not available")


def get_sdk_client():
    """Get a new SDK client instance (for one-off operations)"""
    if not _sdk_available:
        raise RuntimeError("SDK not available")
    
    if _use_sqlite_index():
        return _SQLiteClientWrapper()
    
    try:
        from app.config import Config
        from grokipedia_sdk import SlugIndex
        slug_index = SlugIndex(
            links_dir=Config.LINKS_DIR,
            use_bktree=not Config.LIGHTWEIGHT_MODE
        )
        return Client(slug_index=slug_index)
    except Exception:
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
        logger.warning("Failed to warm slug index: %s", e)
        return False

