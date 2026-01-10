"""Core SDK client for interacting with Grokipedia"""

import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import Optional, List, Union, Tuple
from collections import OrderedDict
from urllib.parse import quote
import time
import os
import asyncio
from threading import Lock

from .models import Article, ArticleSummary, Section, ArticleMetadata
from .exceptions import ArticleNotFound, RequestError
from .slug_index import SlugIndex
from . import parsers

# Default configuration constants
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_CACHE_SIZE = 1000
DEFAULT_RATE_LIMIT = 1.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_TOC_LIMIT = 10
DEFAULT_USER_AGENT = "GrokipediaSDK/1.0 (Python SDK; +https://github.com/AppleLamps/grokipedia-sdk)"


class Client:
    """
    Client for accessing Grokipedia content.
    
    Important: This client manages HTTP connections that must be properly closed.
    Always use one of the following patterns:
    
    1. Context manager (recommended):
        >>> with Client() as client:
        ...     article = client.get_article("Joe_Biden")
    
    2. Explicit close:
        >>> client = Client()
        >>> try:
        ...     article = client.get_article("Joe_Biden")
        ... finally:
        ...     client.close()
    """
    
    def __init__(
        self, 
        base_url: Optional[str] = None, 
        timeout: float = DEFAULT_TIMEOUT,
        slug_index: Optional[SlugIndex] = None,
        max_cache_size: int = DEFAULT_MAX_CACHE_SIZE,
        rate_limit: float = DEFAULT_RATE_LIMIT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        verify: bool = True,
        cert: Optional[Union[str, Tuple[str, str]]] = None,
        user_agent: Optional[str] = None
    ):
        """
        Initialize the Grokipedia SDK client.
        
        Args:
            base_url: Base URL for Grokipedia. If None, uses GROKIPEDIA_BASE_URL 
                    environment variable or defaults to https://grokipedia.com
            timeout: Request timeout in seconds (default: 30.0)
            slug_index: Optional SlugIndex instance for article lookup. 
                       If None, a default SlugIndex will be created.
            max_cache_size: Maximum number of articles to cache (default: 1000).
                           Uses LRU eviction when limit is reached.
            rate_limit: Minimum seconds between requests (default: 1.0).
                       Set to 0 to disable rate limiting.
            max_retries: Maximum number of retry attempts for transient failures (default: 3).
                        Set to 0 to disable retries.
            verify: Enable SSL/TLS certificate verification (default: True).
                   Set to False to disable verification (not recommended for production).
            cert: Path to client certificate or tuple of (cert, key) paths for client cert auth.
                  (default: None)
            user_agent: Custom User-Agent string for HTTP requests. If None, uses default.
                       (default: None)
                   
        Example:
            >>> # Default usage (auto-creates SlugIndex)
            >>> client = Client()
            
            >>> # With custom SlugIndex
            >>> from grokipedia_sdk import SlugIndex
            >>> custom_index = SlugIndex(links_dir="/custom/path")
            >>> client = Client(slug_index=custom_index)
            
            >>> # For testing with mock
            >>> mock_index = MockSlugIndex()
            >>> client = Client(slug_index=mock_index)
            
            >>> # With custom cache size and rate limiting
            >>> client = Client(max_cache_size=500, rate_limit=0.5)
            
            >>> # Using environment variable for base URL
            >>> # Set GROKIPEDIA_BASE_URL=https://staging.grokipedia.com
            >>> client = Client()  # Automatically uses env var
            
            >>> # With custom SSL certificate
            >>> client = Client(verify=True, cert="/path/to/cert.pem")
            
            >>> # With custom User-Agent
            >>> client = Client(user_agent="MyApp/1.0 (Custom Client)")
        """
        # Support environment variable for base_url
        if base_url is None:
            base_url = os.getenv("GROKIPEDIA_BASE_URL", "https://grokipedia.com")
        
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._verify = verify
        self._cert = cert
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            verify=verify,
            cert=cert
        )
        self._async_client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=verify,
            cert=cert
        )
        self._slug_index = slug_index if slug_index is not None else SlugIndex()
        self._article_cache: OrderedDict[str, Article] = OrderedDict()
        self.max_cache_size = max_cache_size
        self._rate_limit = rate_limit
        self._last_request_time = 0.0
        self._rate_limit_lock = Lock()  # Lock for sync rate limiting
        self._async_rate_limit_lock = asyncio.Lock()  # Lock for async rate limiting
        self._cache_lock = Lock()  # Lock for sync cache operations
        self._async_cache_lock = asyncio.Lock()  # Lock for async cache operations
        self.max_retries = max_retries
    
    def __enter__(self):
        """Support for context manager"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up httpx client on exit"""
        self.close()
    
    def close(self):
        """
        Close the HTTP clients (synchronous).
        
        For async contexts, prefer using aclose() instead.
        """
        if hasattr(self, '_client') and self._client:
            self._client.close()
            self._client = None
        if hasattr(self, '_async_client') and self._async_client:
            # Run async cleanup in a way that works even from sync context
            try:
                # Try to get the running loop
                loop = asyncio.get_running_loop()
                # If we're here, a loop is running - schedule cleanup as a task
                asyncio.create_task(self._async_client.aclose())
            except RuntimeError:
                # No event loop is running, run cleanup synchronously
                try:
                    asyncio.run(self._async_client.aclose())
                except RuntimeError:
                    # If asyncio.run() fails, try the legacy approach
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(self._async_client.aclose())
                    finally:
                        loop.close()
            self._async_client = None
    
    async def aclose(self):
        """
        Close the HTTP clients (asynchronous).
        
        This is the preferred method for closing clients in async contexts.
        
        Example:
            >>> async def main():
            ...     client = Client()
            ...     try:
            ...         article = await client.get_article_async("Joe_Biden")
            ...     finally:
            ...         await client.aclose()
        """
        if hasattr(self, '_client') and self._client:
            self._client.close()
            self._client = None
        if hasattr(self, '_async_client') and self._async_client:
            await self._async_client.aclose()
            self._async_client = None
    
    def _validate_slug(self, slug: str) -> str:
        """
        Validate and sanitize slug input to prevent path traversal and injection attacks.
        
        Args:
            slug: The slug to validate
            
        Returns:
            Validated and URL-encoded slug
            
        Raises:
            ValueError: If slug is invalid or empty
        """
        if not slug or not isinstance(slug, str):
            raise ValueError("Slug must be a non-empty string")
        
        # Strip whitespace
        slug = slug.strip()
        
        if not slug:
            raise ValueError("Slug cannot be empty")
        
        # URL encode to prevent injection and handle special characters safely
        # Allow underscores and hyphens to pass through as-is (common in slugs)
        encoded_slug = quote(slug, safe='_-')
        
        return encoded_slug
    
    def _fetch_html(self, url: str, slug: Optional[str] = None) -> str:
        """
        Fetch HTML content from URL with error handling, rate limiting, and retry logic.
        
        Args:
            url: URL to fetch
            slug: Optional article slug for better error messages
            
        Returns:
            HTML content as string
            
        Raises:
            ArticleNotFound: If the article is not found (404)
            RequestError: For other HTTP errors or network issues
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            # Rate limiting
            if self._rate_limit > 0:
                with self._rate_limit_lock:
                    elapsed = time.time() - self._last_request_time
                    if elapsed < self._rate_limit:
                        time.sleep(self._rate_limit - elapsed)
                    self._last_request_time = time.time()
            
            try:
                headers = {
                    "User-Agent": self.user_agent
                }
                response = self._client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
            except httpx.ConnectError as e:
                # Connection errors - retryable
                last_exception = RequestError(f"Failed to connect to {self.base_url}: {str(e)}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise last_exception
            except httpx.TimeoutException as e:
                # Timeout errors - retryable
                last_exception = RequestError(f"Request timeout after {self.timeout}s: {str(e)}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise last_exception
            except httpx.HTTPStatusError as e:
                # HTTP status errors
                status_code = e.response.status_code
                if status_code == 404:
                    slug_display = slug if slug else 'unknown'
                    raise ArticleNotFound(
                        f"Article '{slug_display}' not found at {url}. "
                        f"Status: {status_code}"
                    )
                elif status_code == 429:
                    # Rate limited - retryable
                    last_exception = RequestError(f"Rate limited by server. Please retry after delay.")
                    if attempt < self.max_retries:
                        # Longer delay for rate limiting
                        time.sleep(2 ** (attempt + 2))
                        continue
                    raise last_exception
                elif status_code >= 500:
                    # Server errors - retryable
                    last_exception = RequestError(f"Server error {status_code} fetching {url}: {str(e)}")
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    raise last_exception
                else:
                    # Client errors (4xx except 404, 429) - not retryable
                    raise RequestError(f"HTTP error {status_code} fetching {url}: {str(e)}")
            except httpx.RequestError as e:
                # Other request errors - retryable
                last_exception = RequestError(f"Request failed: {str(e)}")
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise last_exception
            except Exception as e:
                # Unexpected errors - not retryable
                raise RequestError(f"Unexpected error fetching {url}: {str(e)}")
        
        # If we exhausted retries, raise the last exception
        if last_exception:
            raise last_exception
        raise RequestError(f"Failed to fetch {url} after {self.max_retries + 1} attempts")
    
    def _parse_article_html(
        self, html: str, slug: str, url: str, full_content: bool = True
    ) -> Union[Article, ArticleSummary]:
        """
        Parse HTML content into Article or ArticleSummary object.
        
        This method extracts common parsing logic shared between get_article()
        and get_summary() to reduce code duplication.
        
        Args:
            html: HTML content to parse
            slug: Article slug
            url: Article URL
            full_content: If True, parse full article; if False, parse summary only
            
        Returns:
            Article object if full_content=True, ArticleSummary otherwise
        """
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else slug.replace('_', ' ')
        summary = parsers.extract_summary(soup, title_tag)
        
        if full_content:
            # Extract references BEFORE modifying soup
            references = parsers.extract_references(soup)
            
            # Extract metadata BEFORE modifying soup
            fact_checked = parsers.extract_fact_check_info(soup)
            
            # NOW remove unwanted elements for clean text
            parsers.clean_html_for_text_extraction(soup)
            
            # Get full text content
            full_content_text = soup.get_text(separator='\n', strip=True)
            
            # Extract sections and TOC
            sections, toc = parsers.extract_sections(soup)
            
            # Calculate word count
            word_count = len(full_content_text.split())
            
            metadata = ArticleMetadata(
                fact_checked=fact_checked,
                word_count=word_count
            )
            
            return Article(
                title=title,
                slug=slug,
                url=url,
                summary=summary,
                full_content=full_content_text,
                sections=sections,
                table_of_contents=toc,
                references=references,
                metadata=metadata,
                scraped_at=datetime.now(timezone.utc).isoformat()
            )
        else:
            # Summary-only parsing
            _, toc = parsers.extract_sections(soup)
            
            return ArticleSummary(
                title=title,
                slug=slug,
                url=url,
                summary=summary,
                table_of_contents=toc[:DEFAULT_TOC_LIMIT],
                scraped_at=datetime.now(timezone.utc).isoformat()
            )
    
    def get_article(self, slug: str) -> Article:
        """
        Get a complete article from Grokipedia by slug.
        
        Articles are automatically cached after the first fetch to improve
        performance for subsequent requests. Cache uses LRU eviction policy.
        
        Args:
            slug: Article slug (e.g., "Joe_Biden")
            
        Returns:
            Article object with full content
            
        Raises:
            ValueError: If slug is invalid
            ArticleNotFound: If the article doesn't exist
            RequestError: For network or HTTP errors
            
        Example:
            >>> client = Client()
            >>> article = client.get_article("Joe_Biden")
            >>> print(article.title)
            'Joe Biden'
            >>> print(f"Word count: {article.metadata.word_count}")
            Word count: 1234
        """
        # Validate and sanitize slug
        slug = self._validate_slug(slug)
        
        # Check cache first (with LRU ordering) - thread-safe
        with self._cache_lock:
            if slug in self._article_cache:
                self._article_cache.move_to_end(slug)
                return self._article_cache[slug]
        
        # Not in cache, fetch from network
        url = f"{self.base_url}/page/{slug}"
        html = self._fetch_html(url, slug=slug)
        article = self._parse_article_html(html, slug, url, full_content=True)
        
        # Cache the article for future use (with LRU eviction) - thread-safe with double-check
        with self._cache_lock:
            # Double-check pattern: another thread might have cached it while we were fetching
            if slug not in self._article_cache:
                if len(self._article_cache) >= self.max_cache_size:
                    self._article_cache.popitem(last=False)  # Remove oldest entry
                self._article_cache[slug] = article
            self._article_cache.move_to_end(slug)  # Mark as most recently used
        
        return article
    
    def get_summary(self, slug: str) -> ArticleSummary:
        """
        Get just the summary/intro of an article (faster, less data).
        
        Args:
            slug: Article slug (e.g., "Joe_Biden")
            
        Returns:
            ArticleSummary object with summary and TOC
            
        Raises:
            ValueError: If slug is invalid
            ArticleNotFound: If the article doesn't exist
            RequestError: For network or HTTP errors
            
        Example:
            >>> client = Client()
            >>> summary = client.get_summary("Joe_Biden")
            >>> print(summary.title)
            'Joe Biden'
            >>> print(f"TOC sections: {len(summary.table_of_contents)}")
            TOC sections: 10
        """
        # Validate and sanitize slug
        slug = self._validate_slug(slug)
        url = f"{self.base_url}/page/{slug}"
        html = self._fetch_html(url, slug=slug)
        return self._parse_article_html(html, slug, url, full_content=False)
    
    def get_section(self, slug: str, section_title: str) -> Optional[Section]:
        """
        Get a specific section of an article by title.
        
        Args:
            slug: Article slug (e.g., "Joe_Biden")
            section_title: Section title to search for
            
        Returns:
            Section object if found, None otherwise
            
        Raises:
            ValueError: If slug is invalid
            ArticleNotFound: If the article doesn't exist
            RequestError: For network or HTTP errors
            
        Example:
            >>> client = Client()
            >>> section = client.get_section("Joe_Biden", "Early Life")
            >>> if section:
            ...     print(f"Found: {section.title}")
            ...     print(section.content[:100])
            Found: Early Life
            Joe Biden was born...
        """
        # Validation happens in get_article
        article = self.get_article(slug)
        
        # Find matching section (case-insensitive, partial match)
        section_title_lower = section_title.lower().replace('_', ' ')
        
        for section in article.sections:
            if section_title_lower in section.title.lower():
                return section
        
        return None
    
    # Slug search and discovery methods
    
    def search_slug(self, query: str, limit: int = 10, fuzzy: bool = True, sort_by_date: bool = False) -> List[str]:
        """
        Search for article slugs matching a query.
        
        This method searches through the local sitemap index to find articles
        matching your query. It's fast and doesn't require network requests.
        
        Args:
            query: Search query (partial name or slug, case-insensitive)
            limit: Maximum number of results to return (default: 10)
            fuzzy: Enable fuzzy matching for approximate matches (default: True)
            sort_by_date: Sort results by lastmod date, most recent first (default: False)
            
        Returns:
            List of matching slugs ordered by relevance (or date if sort_by_date=True)
            
        Example:
            >>> client = Client()
            >>> client.search_slug("joe biden")
            ['Joe_Biden', 'Joe_Biden_presidential_campaign', ...]
            >>> client.search_slug("artificial intelligence", limit=5)
            ['Artificial_Intelligence', 'Artificial_Neural_Network', ...]
        """
        return self._slug_index.search(query, limit=limit, fuzzy=fuzzy, sort_by_date=sort_by_date)
    
    def find_slug(self, query: str) -> Optional[str]:
        """
        Find the best matching slug for a query.
        
        This is a convenience method that returns the single best match
        for your query. Useful when you want to quickly find one article.
        
        Args:
            query: Article name or partial slug (case-insensitive)
            
        Returns:
            Best matching slug or None if not found
            
        Example:
            >>> client = Client()
            >>> slug = client.find_slug("elon musk")
            >>> print(slug)
            'Elon_Musk'
            >>> article = client.get_article(slug)
        """
        return self._slug_index.find_best_match(query)
    
    def slug_exists(self, slug: str) -> bool:
        """
        Check if a slug exists in the sitemap index.
        
        Args:
            slug: Slug to check
            
        Returns:
            True if slug exists, False otherwise
            
        Example:
            >>> client = Client()
            >>> client.slug_exists("Joe_Biden")
            True
            >>> client.slug_exists("Nonexistent_Article")
            False
        """
        return self._slug_index.exists(slug)
    
    def list_available_articles(self, prefix: str = "", limit: int = 100) -> List[str]:
        """
        List available articles, optionally filtered by prefix.
        
        Args:
            prefix: Filter articles starting with this prefix (case-insensitive)
            limit: Maximum number of results (default: 100)
            
        Returns:
            List of article slugs matching the prefix
            
        Example:
            >>> client = Client()
            >>> articles = client.list_available_articles(prefix="Artificial", limit=20)
            >>> print(articles)
            ['Artificial_Intelligence', 'Artificial_Neural_Network', ...]
            >>> all_articles = client.list_available_articles(limit=50)
        """
        return self._slug_index.list_by_prefix(prefix=prefix, limit=limit)
    
    def get_total_article_count(self) -> int:
        """
        Get the total number of articles available in the index.
        
        Returns:
            Total number of unique articles
            
        Example:
            >>> client = Client()
            >>> total = client.get_total_article_count()
            >>> print(f"Total articles available: {total}")
            Total articles available: 50000
        """
        return self._slug_index.get_total_count()
    
    def get_random_articles(self, count: int = 10) -> List[str]:
        """
        Get random article slugs from the index.
        
        Useful for exploring the content or building sample datasets.
        
        Args:
            count: Number of random slugs to return (default: 10)
            
        Returns:
            List of random article slugs
            
        Example:
            >>> client = Client()
            >>> random_slugs = client.get_random_articles(5)
            >>> for slug in random_slugs:
            ...     article = client.get_summary(slug)
            ...     print(article.title)
        """
        return self._slug_index.random_slugs(count=count)
    
    # Async methods
    
    async def _fetch_html_async(self, url: str, slug: Optional[str] = None) -> str:
        """
        Async version of _fetch_html for concurrent operations.
        
        Args:
            url: URL to fetch
            slug: Optional article slug for better error messages
            
        Returns:
            HTML content as string
            
        Raises:
            ArticleNotFound: If the article is not found (404)
            RequestError: For other HTTP errors or network issues
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            # Rate limiting with async lock to prevent race conditions
            if self._rate_limit > 0:
                async with self._async_rate_limit_lock:
                    elapsed = time.time() - self._last_request_time
                    if elapsed < self._rate_limit:
                        await asyncio.sleep(self._rate_limit - elapsed)
                    self._last_request_time = time.time()
            
            try:
                headers = {
                    "User-Agent": self.user_agent
                }
                response = await self._async_client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
            except httpx.ConnectError as e:
                # Connection errors - retryable
                last_exception = RequestError(f"Failed to connect to {self.base_url}: {str(e)}")
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise last_exception
            except httpx.TimeoutException as e:
                # Timeout errors - retryable
                last_exception = RequestError(f"Request timeout after {self.timeout}s: {str(e)}")
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise last_exception
            except httpx.HTTPStatusError as e:
                # HTTP status errors
                status_code = e.response.status_code
                if status_code == 404:
                    slug_display = slug if slug else 'unknown'
                    raise ArticleNotFound(
                        f"Article '{slug_display}' not found at {url}. "
                        f"Status: {status_code}"
                    )
                elif status_code == 429:
                    # Rate limited - retryable
                    last_exception = RequestError(f"Rate limited by server. Please retry after delay.")
                    if attempt < self.max_retries:
                        # Longer delay for rate limiting
                        await asyncio.sleep(2 ** (attempt + 2))
                        continue
                    raise last_exception
                elif status_code >= 500:
                    # Server errors - retryable
                    last_exception = RequestError(f"Server error {status_code} fetching {url}: {str(e)}")
                    if attempt < self.max_retries:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    raise last_exception
                else:
                    # Client errors (4xx except 404, 429) - not retryable
                    raise RequestError(f"HTTP error {status_code} fetching {url}: {str(e)}")
            except httpx.RequestError as e:
                # Other request errors - retryable
                last_exception = RequestError(f"Request failed: {str(e)}")
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise last_exception
            except Exception as e:
                # Unexpected errors - not retryable
                raise RequestError(f"Unexpected error fetching {url}: {str(e)}")
        
        # If we exhausted retries, raise the last exception
        if last_exception:
            raise last_exception
        raise RequestError(f"Failed to fetch {url} after {self.max_retries + 1} attempts")
    
    async def get_article_async(self, slug: str) -> Article:
        """
        Async version of get_article() for concurrent operations.
        
        Get a complete article from Grokipedia by slug using async/await.
        This method is useful when fetching multiple articles concurrently.
        
        Args:
            slug: Article slug (e.g., "Joe_Biden")
            
        Returns:
            Article object with full content
            
        Raises:
            ValueError: If slug is invalid
            ArticleNotFound: If the article doesn't exist
            RequestError: For network or HTTP errors
            
        Example:
            >>> import asyncio
            >>> async def fetch_multiple():
            ...     client = Client()
            ...     articles = await asyncio.gather(
            ...         client.get_article_async("Joe_Biden"),
            ...         client.get_article_async("Barack_Obama")
            ...     )
            ...     return articles
            >>> articles = asyncio.run(fetch_multiple())
        """
        # Validate and sanitize slug
        slug = self._validate_slug(slug)
        
        # Check cache first (with LRU ordering) - async-safe
        async with self._async_cache_lock:
            if slug in self._article_cache:
                self._article_cache.move_to_end(slug)
                return self._article_cache[slug]
        
        # Not in cache, fetch from network
        url = f"{self.base_url}/page/{slug}"
        html = await self._fetch_html_async(url, slug=slug)
        article = self._parse_article_html(html, slug, url, full_content=True)
        
        # Cache the article for future use (with LRU eviction) - async-safe with double-check
        async with self._async_cache_lock:
            # Double-check pattern: another async task might have cached it while we were fetching
            if slug not in self._article_cache:
                if len(self._article_cache) >= self.max_cache_size:
                    self._article_cache.popitem(last=False)  # Remove oldest entry
                self._article_cache[slug] = article
            self._article_cache.move_to_end(slug)  # Mark as most recently used
        
        return article
    
    async def get_summary_async(self, slug: str) -> ArticleSummary:
        """
        Async version of get_summary() for concurrent operations.
        
        Get just the summary/intro of an article using async/await.
        This method is useful when fetching multiple summaries concurrently.
        
        Args:
            slug: Article slug (e.g., "Joe_Biden")
            
        Returns:
            ArticleSummary object with summary and TOC
            
        Raises:
            ValueError: If slug is invalid
            ArticleNotFound: If the article doesn't exist
            RequestError: For network or HTTP errors
            
        Example:
            >>> import asyncio
            >>> async def fetch_summaries():
            ...     client = Client()
            ...     slugs = ["Joe_Biden", "Barack_Obama", "Donald_Trump"]
            ...     summaries = await asyncio.gather(
            ...         *[client.get_summary_async(slug) for slug in slugs]
            ...     )
            ...     return summaries
            >>> summaries = asyncio.run(fetch_summaries())
        """
        # Validate and sanitize slug
        slug = self._validate_slug(slug)
        url = f"{self.base_url}/page/{slug}"
        html = await self._fetch_html_async(url, slug=slug)
        return self._parse_article_html(html, slug, url, full_content=False)

