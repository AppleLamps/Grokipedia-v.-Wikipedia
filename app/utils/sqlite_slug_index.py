"""SQLite-based slug index for memory-efficient article lookup.

This module provides a SQLite-backed slug index that can handle millions of
articles with minimal memory footprint, making it suitable for deployment
on memory-constrained platforms like Railway.
"""

import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Thread-local storage for SQLite connections
_local = threading.local()


class SQLiteSlugIndex:
    """Memory-efficient slug index using SQLite for storage."""
    
    def __init__(self, db_path: Optional[str] = None, links_dir: Optional[Path] = None):
        """
        Initialize the SQLite slug index.
        
        Args:
            db_path: Path to SQLite database file. If None, uses default location.
            links_dir: Path to links directory for building the index.
        """
        if db_path is None:
            # Default to a database file in the app directory
            app_dir = Path(__file__).parent.parent
            db_path = str(app_dir / "slugs.db")
        
        self.db_path = db_path
        self.links_dir = links_dir
        self._initialized = False
        self._lock = threading.Lock()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(_local, 'connection') or _local.connection is None:
            _local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            _local.connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent read performance
            _local.connection.execute("PRAGMA journal_mode=WAL")
            _local.connection.execute("PRAGMA synchronous=NORMAL")
            _local.connection.execute("PRAGMA cache_size=10000")
        return _local.connection
    
    def _ensure_initialized(self) -> bool:
        """Ensure the database is initialized and has data."""
        if self._initialized:
            return True
        
        with self._lock:
            if self._initialized:
                return True
            
            # Check if database exists and has data
            if os.path.exists(self.db_path):
                try:
                    conn = self._get_connection()
                    cursor = conn.execute("SELECT COUNT(*) FROM slugs")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        self._initialized = True
                        logger.info(f"SQLite slug index ready with {count:,} articles")
                        return True
                except sqlite3.OperationalError:
                    pass  # Table doesn't exist, need to build
            
            # Need to build the index
            if self.links_dir and Path(self.links_dir).exists():
                logger.info("Building SQLite slug index from sitemap files...")
                self._build_index()
                self._initialized = True
                return True
            
            logger.warning("No slug index available - links_dir not found")
            return False
    
    def _build_index(self) -> None:
        """Build the SQLite index from sitemap files."""
        conn = self._get_connection()
        
        # Create tables
        conn.executescript("""
            DROP TABLE IF EXISTS slugs;
            DROP TABLE IF EXISTS slug_fts;
            
            CREATE TABLE slugs (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                slug_lower TEXT NOT NULL,
                normalized TEXT NOT NULL,
                lastmod TEXT
            );
            
            -- Full-text search table for fast fuzzy matching
            CREATE VIRTUAL TABLE slug_fts USING fts5(
                normalized,
                content='slugs',
                content_rowid='id',
                tokenize='porter unicode61'
            );
            
            CREATE INDEX idx_slug_lower ON slugs(slug_lower);
            CREATE INDEX idx_normalized ON slugs(normalized);
        """)
        
        links_path = Path(self.links_dir)
        batch = []
        batch_size = 10000
        total_loaded = 0
        
        for sitemap_dir in sorted(links_path.glob("sitemap-*")):
            names_file = sitemap_dir / "names.txt"
            dates_file = sitemap_dir / "dates.txt"
            
            if not names_file.exists():
                continue
            
            try:
                with open(names_file, 'r', encoding='utf-8') as f:
                    names = [line.strip() for line in f if line.strip()]
                
                dates = []
                if dates_file.exists():
                    with open(dates_file, 'r', encoding='utf-8') as f:
                        dates = [line.strip() for line in f]
                
                for i, slug in enumerate(names):
                    slug_lower = slug.lower()
                    normalized = slug_lower.replace('_', ' ')
                    lastmod = dates[i] if i < len(dates) else None
                    batch.append((slug, slug_lower, normalized, lastmod))
                    
                    if len(batch) >= batch_size:
                        self._insert_batch(conn, batch)
                        total_loaded += len(batch)
                        batch = []
                        if total_loaded % 100000 == 0:
                            logger.info(f"Loaded {total_loaded:,} slugs...")
            
            except Exception as e:
                logger.warning(f"Error reading {names_file}: {e}")
                continue
        
        # Insert remaining batch
        if batch:
            self._insert_batch(conn, batch)
            total_loaded += len(batch)
        
        # Rebuild FTS index
        conn.execute("INSERT INTO slug_fts(slug_fts) VALUES('rebuild')")
        conn.commit()
        
        logger.info(f"SQLite slug index built with {total_loaded:,} articles")
    
    def _insert_batch(self, conn: sqlite3.Connection, batch: List[Tuple]) -> None:
        """Insert a batch of slugs."""
        conn.executemany(
            "INSERT OR IGNORE INTO slugs (slug, slug_lower, normalized, lastmod) VALUES (?, ?, ?, ?)",
            batch
        )
        conn.commit()
    
    def search(self, query: str, limit: int = 10, fuzzy: bool = True) -> List[str]:
        """
        Search for matching slugs.
        
        Args:
            query: Search query
            limit: Maximum results to return
            fuzzy: Enable fuzzy matching
            
        Returns:
            List of matching slugs
        """
        if not self._ensure_initialized():
            return []
        
        if not query or not query.strip():
            return []
        
        conn = self._get_connection()
        query_normalized = query.lower().replace('_', ' ').strip()
        query_lower = query.lower().strip()
        results = []
        seen = set()
        
        # Strategy 1: Exact match on slug
        cursor = conn.execute(
            "SELECT slug FROM slugs WHERE slug_lower = ? LIMIT 1",
            (query_lower,)
        )
        for row in cursor:
            if row['slug'] not in seen:
                results.append(row['slug'])
                seen.add(row['slug'])
        
        if len(results) >= limit:
            return results[:limit]
        
        # Strategy 2: Prefix match (fast with index)
        cursor = conn.execute(
            """SELECT slug FROM slugs 
               WHERE normalized LIKE ? || '%' 
               ORDER BY LENGTH(slug) 
               LIMIT ?""",
            (query_normalized, limit - len(results))
        )
        for row in cursor:
            if row['slug'] not in seen:
                results.append(row['slug'])
                seen.add(row['slug'])
        
        if len(results) >= limit:
            return results[:limit]
        
        # Strategy 3: Contains match
        cursor = conn.execute(
            """SELECT slug FROM slugs 
               WHERE normalized LIKE '%' || ? || '%' 
               ORDER BY 
                   CASE WHEN normalized LIKE ? || '%' THEN 0 ELSE 1 END,
                   LENGTH(slug) 
               LIMIT ?""",
            (query_normalized, query_normalized, limit - len(results))
        )
        for row in cursor:
            if row['slug'] not in seen:
                results.append(row['slug'])
                seen.add(row['slug'])
        
        if len(results) >= limit or not fuzzy:
            return results[:limit]
        
        # Strategy 4: FTS5 fuzzy search (only if we need more results)
        try:
            # Use FTS5 with prefix matching for fuzzy search
            fts_query = ' '.join(f'{word}*' for word in query_normalized.split() if word)
            if fts_query:
                cursor = conn.execute(
                    """SELECT s.slug FROM slug_fts f
                       JOIN slugs s ON f.rowid = s.id
                       WHERE slug_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (fts_query, limit - len(results))
                )
                for row in cursor:
                    if row['slug'] not in seen:
                        results.append(row['slug'])
                        seen.add(row['slug'])
        except sqlite3.OperationalError as e:
            logger.debug(f"FTS search failed: {e}")
        
        return results[:limit]
    
    def exists(self, slug: str) -> bool:
        """Check if a slug exists in the index."""
        if not self._ensure_initialized():
            return False
        
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT 1 FROM slugs WHERE slug_lower = ? LIMIT 1",
            (slug.lower(),)
        )
        return cursor.fetchone() is not None
    
    def find_best_match(self, query: str, min_similarity: float = 0.6) -> Optional[str]:
        """Find the single best matching slug."""
        results = self.search(query, limit=1, fuzzy=True)
        return results[0] if results else None
    
    def list_by_prefix(self, prefix: str = "", limit: int = 100) -> List[str]:
        """List articles by prefix."""
        if not self._ensure_initialized():
            return []
        
        conn = self._get_connection()
        
        if not prefix:
            cursor = conn.execute("SELECT slug FROM slugs LIMIT ?", (limit,))
        else:
            prefix_lower = prefix.lower()
            cursor = conn.execute(
                """SELECT slug FROM slugs 
                   WHERE slug_lower LIKE ? || '%'
                   ORDER BY slug
                   LIMIT ?""",
                (prefix_lower, limit)
            )
        
        return [row['slug'] for row in cursor]
    
    def get_total_count(self) -> int:
        """Get total number of articles."""
        if not self._ensure_initialized():
            return 0
        
        conn = self._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM slugs")
        return cursor.fetchone()[0]
    
    def get_slug_date(self, slug: str) -> Optional[str]:
        """Get the lastmod date for a slug."""
        if not self._ensure_initialized():
            return None
        
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT lastmod FROM slugs WHERE slug_lower = ?",
            (slug.lower(),)
        )
        row = cursor.fetchone()
        return row['lastmod'] if row else None


# Global instance
_sqlite_index: Optional[SQLiteSlugIndex] = None


def get_sqlite_slug_index(links_dir: Optional[Path] = None) -> SQLiteSlugIndex:
    """Get or create the global SQLite slug index."""
    global _sqlite_index
    
    if _sqlite_index is None:
        from app.config import Config
        if links_dir is None:
            links_dir = Path(Config.LINKS_DIR)
        
        # Use a database in the app directory (persists in container)
        # Priority: SLUG_DB_PATH env var > app/slugs.db
        db_path = os.environ.get('SLUG_DB_PATH')
        if not db_path:
            db_path = str(Path(__file__).parent.parent / "slugs.db")
        
        logger.info(f"Using SQLite slug database: {db_path}")
        _sqlite_index = SQLiteSlugIndex(db_path=db_path, links_dir=links_dir)
    
    return _sqlite_index
    
    return _sqlite_index
