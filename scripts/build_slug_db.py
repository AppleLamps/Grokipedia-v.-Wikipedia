#!/usr/bin/env python3
"""Build the SQLite slug index from sitemap files.

This script should be run during the Railway build phase to pre-generate
the slug database, avoiding runtime index building.

Usage:
    python scripts/build_slug_db.py [--output /path/to/slugs.db]
"""

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def build_slug_database(links_dir: Path, db_path: str) -> int:
    """Build SQLite database from sitemap files.
    
    Returns:
        Number of slugs loaded
    """
    logger.info(f"Building slug database: {db_path}")
    logger.info(f"Reading from: {links_dir}")
    
    # Remove existing database
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    
    # Create tables
    conn.executescript("""
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
    
    batch = []
    batch_size = 10000
    total_loaded = 0
    
    sitemap_dirs = sorted(links_dir.glob("sitemap-*"))
    logger.info(f"Found {len(sitemap_dirs)} sitemap directories")
    
    for sitemap_dir in sitemap_dirs:
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
                    conn.executemany(
                        "INSERT OR IGNORE INTO slugs (slug, slug_lower, normalized, lastmod) VALUES (?, ?, ?, ?)",
                        batch
                    )
                    conn.commit()
                    total_loaded += len(batch)
                    batch = []
                    if total_loaded % 100000 == 0:
                        logger.info(f"Loaded {total_loaded:,} slugs...")
        
        except Exception as e:
            logger.warning(f"Error reading {names_file}: {e}")
            continue
    
    # Insert remaining batch
    if batch:
        conn.executemany(
            "INSERT OR IGNORE INTO slugs (slug, slug_lower, normalized, lastmod) VALUES (?, ?, ?, ?)",
            batch
        )
        conn.commit()
        total_loaded += len(batch)
    
    # Rebuild FTS index
    logger.info("Building full-text search index...")
    conn.execute("INSERT INTO slug_fts(slug_fts) VALUES('rebuild')")
    conn.commit()
    
    # Optimize database
    logger.info("Optimizing database...")
    conn.execute("VACUUM")
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()
    
    # Log final stats
    db_size = os.path.getsize(db_path) / (1024 * 1024)
    logger.info(f"Database built successfully!")
    logger.info(f"  Total slugs: {total_loaded:,}")
    logger.info(f"  Database size: {db_size:.1f} MB")
    
    return total_loaded


def main():
    parser = argparse.ArgumentParser(description="Build SQLite slug index from sitemap files")
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output database path (default: app/slugs.db)"
    )
    parser.add_argument(
        "--links-dir", "-l",
        default=None,
        help="Links directory path (default: auto-detect)"
    )
    args = parser.parse_args()
    
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Determine links directory
    if args.links_dir:
        links_dir = Path(args.links_dir)
    else:
        links_dir = project_root / "grokipedia-sdk" / "grokipedia_sdk" / "links"
    
    if not links_dir.exists():
        logger.error(f"Links directory not found: {links_dir}")
        sys.exit(1)
    
    # Determine output path
    if args.output:
        db_path = args.output
    else:
        db_path = str(project_root / "app" / "slugs.db")
    
    # Build the database
    count = build_slug_database(links_dir, db_path)
    
    if count == 0:
        logger.error("No slugs loaded - check links directory")
        sys.exit(1)
    
    logger.info(f"Success! Database ready at: {db_path}")


if __name__ == "__main__":
    main()
