"""Slug index for fast article lookup"""

import asyncio
import bisect
import heapq
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    # Fallback to difflib if rapidfuzz is not installed
    from difflib import SequenceMatcher
    HAS_RAPIDFUZZ = False
else:
    from difflib import SequenceMatcher

try:
    from .bk_tree import BKTree
    HAS_BKTREE = True
except ImportError:
    HAS_BKTREE = False

# Set up logger for this module
logger = logging.getLogger(__name__)


class SlugIndex:
    """Index of available article slugs from sitemap"""
    
    def __init__(self, links_dir: Optional[Path] = None, use_bktree: bool = True):
        """
        Initialize slug index.
        
        Args:
            links_dir: Path to links directory (default: auto-detect)
            use_bktree: Enable BK-Tree for O(log n) fuzzy search (default: True)
                       When enabled, provides 100-1000x speedup for fuzzy queries.
                       Adds ~5-10 seconds to initial load time for large datasets.
        """
        if links_dir is None:
            # Auto-detect links directory relative to this file
            sdk_dir = Path(__file__).parent
            links_dir = sdk_dir / "links"
        
        self.links_dir = Path(links_dir)
        self.use_bktree = use_bktree and HAS_BKTREE
        self._index: Optional[Dict[str, str]] = None
        self._all_slugs: Optional[List[str]] = None
        self._slug_dates: Optional[Dict[str, str]] = None  # slug -> lastmod date
        self._bk_tree: Optional['BKTree'] = None
        self._load_errors: List[Tuple[str, Exception]] = []  # Track file load errors
        self._all_slugs_lower_sorted: Optional[List[str]] = None
        self._all_slugs_sorted_by_lower: Optional[List[str]] = None
        self._token_index: Optional[Dict[str, List[str]]] = None
        self._token_keys_sorted: Optional[List[str]] = None
    
    @staticmethod
    def _normalize_name(slug: str) -> str:
        """
        Normalize a slug for lookup.
        
        Converts to lowercase and replaces underscores with spaces.
        This allows flexible matching across different formats.
        
        Args:
            slug: The slug to normalize
            
        Returns:
            Normalized slug (lowercase, underscores → spaces)
            
        Example:
            >>> SlugIndex._normalize_name("Joe_Biden")
            'joe biden'
        """
        return slug.lower().replace('_', ' ')

    @staticmethod
    def _substring_match_score(text: str, pattern: str) -> Optional[Tuple[int, int, int]]:
        """Calculate a relevance score for substring matches.

        Scores favour exact matches, then word-boundary matches, prefixes, and finally
        loose substring matches. Returns None when pattern does not occur."""

        if not pattern:
            return None

        if text == pattern:
            return (4, 0, -len(text))

        best_score: Optional[Tuple[int, int, int]] = None
        start = 0

        while True:
            idx = text.find(pattern, start)
            if idx == -1:
                break

            before_char = text[idx - 1] if idx > 0 else ' '
            after_index = idx + len(pattern)
            after_char = text[after_index] if after_index < len(text) else ' '

            left_boundary = not before_char.isalnum()
            right_boundary = not after_char.isalnum()

            if left_boundary and right_boundary:
                primary = 3
            elif left_boundary or right_boundary:
                primary = 2
            else:
                primary = 1

            candidate_score = (primary, -idx, -len(text))
            if best_score is None or candidate_score > best_score:
                best_score = candidate_score

            # If we matched at the start with a word boundary on both sides, we won't
            # find a better occurrence for this string.
            if primary == 3 and idx == 0:
                break

            start = idx + 1

        return best_score

    @staticmethod
    def _compute_similarity_score(query: str, candidate: str) -> float:
        """Return a similarity score in the range [0, 100]."""

        if HAS_RAPIDFUZZ:
            if ' ' in query or ' ' in candidate:
                return float(max(
                    fuzz.token_set_ratio(query, candidate),
                    fuzz.WRatio(query, candidate),
                ))
            return float(fuzz.ratio(query, candidate))

        return SequenceMatcher(None, query, candidate).ratio() * 100.0

    def _collect_substring_candidates(
        self,
        index: Dict[str, str],
        query_normalized: str,
        limit: int,
    ) -> List[str]:
        """Gather top substring matches ranked by relevance."""

        candidate_scores: Dict[str, Tuple[int, int, int]] = {}

        for normalized_name, slug in index.items():
            if query_normalized not in normalized_name:
                continue

            score = self._substring_match_score(normalized_name, query_normalized)
            if score is None:
                continue

            existing = candidate_scores.get(slug)
            if existing is None or score > existing:
                candidate_scores[slug] = score

        if not candidate_scores:
            return []

        sorted_slugs = sorted(
            candidate_scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        return [slug for slug, _ in sorted_slugs[:limit]]
    
    def load(self) -> Dict[str, str]:
        """
        Load the slug index from sitemap files.
        
        Returns:
            Dictionary mapping normalized names to slugs
        """
        if self._index is not None:
            return self._index
        
        self._index = {}
        self._slug_dates = {}
        unique_slugs = set()
        self._load_errors = []  # Reset errors for this load
        
        if not self.links_dir.exists():
            logger.warning(
                f"Links directory does not exist: {self.links_dir}. "
                "Slug index will be empty."
            )
            return self._index
        
        # Load all sitemap files
        total_files = 0
        failed_files = 0
        
        for sitemap_dir in sorted(self.links_dir.glob("sitemap-*")):
            names_file = sitemap_dir / "names.txt"
            dates_file = sitemap_dir / "dates.txt"
            if names_file.exists():
                total_files += 1
                try:
                    # Load names
                    with open(names_file, 'r', encoding='utf-8') as f:
                        names_lines = [line.strip() for line in f]
                    
                    # Load dates if available
                    dates_lines = []
                    if dates_file.exists():
                        with open(dates_file, 'r', encoding='utf-8') as f:
                            dates_lines = [line.strip() for line in f]
                    
                    for i, slug in enumerate(names_lines):
                        if slug:
                            unique_slugs.add(slug)
                            # Store normalized version for flexible matching
                            normalized = self._normalize_name(slug)
                            self._index[normalized] = slug
                            # Also store the lowercase original for exact matches
                            self._index[slug.lower()] = slug
                            # Store date if available
                            if i < len(dates_lines) and dates_lines[i]:
                                self._slug_dates[slug] = dates_lines[i]
                except (IOError, OSError) as e:
                    # Handle file access errors (permissions, disk issues, etc.)
                    failed_files += 1
                    error_msg = f"Failed to read sitemap file {names_file}: {e}"
                    self._load_errors.append((str(names_file), e))
                    logger.warning(error_msg)
                    continue
                except UnicodeDecodeError as e:
                    # Handle encoding issues in the file
                    failed_files += 1
                    error_msg = (
                        f"Invalid UTF-8 encoding in {names_file}: {e}"
                    )
                    self._load_errors.append((str(names_file), e))
                    logger.error(error_msg)
                    continue
        
        # Log summary if files failed to load
        if total_files > 0 and failed_files == total_files:
            logger.error(
                f"All {total_files} sitemap files failed to load. "
                "Slug index may be incomplete or empty."
            )
        elif failed_files > 0:
            logger.warning(
                f"{failed_files} out of {total_files} sitemap files failed to load. "
                "Slug index may be incomplete."
            )
        
        # Store sorted list of all unique slugs
        self._all_slugs = sorted(unique_slugs)
        self._all_slugs_lower_sorted = None
        self._all_slugs_sorted_by_lower = None
        self._token_index = None
        self._token_keys_sorted = None
        
        # Build BK-Tree for O(log n) fuzzy search (if enabled)
        if self.use_bktree and HAS_BKTREE:
            self._bk_tree = BKTree()
            for slug in self._all_slugs:
                normalized = self._normalize_name(slug)
                self._bk_tree.add(slug, normalized)

        return self._index

    def _build_token_index(self) -> None:
        """Build a token-to-slugs index for fast multi-word search."""
        if self._token_index is not None:
            return
        self._token_index = {}
        self._token_keys_sorted = []

        if not self._all_slugs:
            return

        for slug in self._all_slugs:
            normalized = self._normalize_name(slug)
            tokens = [token for token in normalized.split() if len(token) >= 2]
            for token in tokens:
                self._token_index.setdefault(token, []).append(slug)

        self._token_keys_sorted = sorted(self._token_index.keys())

    def _collect_token_candidates(
        self,
        query_normalized: str,
        limit: int,
        max_candidates: int = 5000,
    ) -> List[str]:
        """Gather top matches using token index for speed."""
        tokens = [token for token in query_normalized.split() if len(token) >= 2]
        if not tokens:
            return []

        self._build_token_index()
        if not self._token_index:
            return []

        token_index = self._token_index
        candidates: Optional[Set[str]] = None

        if len(tokens) == 1 and len(tokens[0]) < 4:
            prefix = tokens[0]
            if not self._token_keys_sorted:
                return []
            upper_bound = prefix + '{'
            start = bisect.bisect_left(self._token_keys_sorted, prefix)
            end = bisect.bisect_left(self._token_keys_sorted, upper_bound)
            for token in self._token_keys_sorted[start:end]:
                slugs = token_index.get(token, [])
                if not slugs:
                    continue
                if candidates is None:
                    candidates = set(slugs)
                else:
                    candidates.update(slugs)
                if candidates and len(candidates) >= max_candidates:
                    break
        else:
            tokens_by_size = sorted(tokens, key=lambda t: len(token_index.get(t, [])))
            for token in tokens_by_size:
                slugs = token_index.get(token)
                if not slugs:
                    return []
                if candidates is None:
                    candidates = set(slugs)
                else:
                    candidates.intersection_update(slugs)
                if not candidates:
                    return []

        if not candidates:
            return []

        ranked: List[Tuple[Tuple[float, float, float, float], str]] = []
        for slug in candidates:
            normalized = self._normalize_name(slug)
            substring_score = self._substring_match_score(normalized, query_normalized)
            if substring_score is not None:
                rank = (2, float(substring_score[0]), float(substring_score[1]), float(substring_score[2]))
            else:
                similarity = self._compute_similarity_score(query_normalized, normalized)
                rank = (1, similarity, float(-len(normalized)), 0.0)
            ranked.append((rank, slug))

        ranked.sort(reverse=True)
        return [slug for _, slug in ranked[:limit]]
    
    async def load_async(self) -> Dict[str, str]:
        """
        Load the slug index from sitemap files asynchronously.
        
        Useful when integrating with async frameworks or when loading
        from slow I/O sources. For typical local file systems, the
        synchronous load() method is recommended.
        
        Returns:
            Dictionary mapping normalized names to slugs
            
        Example:
            >>> index = SlugIndex()
            >>> index_dict = await index.load_async()
        """
        # Run the blocking load() in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.load)
    
    def get_load_errors(self) -> List[Tuple[str, Exception]]:
        """
        Get list of errors that occurred during index loading.
        
        Returns:
            List of tuples containing (file_path, exception) for each file that failed to load.
            Empty list if no errors occurred or if load() hasn't been called yet.
            
        Example:
            >>> index = SlugIndex()
            >>> index.load()
            >>> errors = index.get_load_errors()
            >>> if errors:
            ...     print(f"Failed to load {len(errors)} files")
            ...     for file_path, exc in errors:
            ...         print(f"  {file_path}: {exc}")
        """
        return self._load_errors.copy()
    
    def get_slug_date(self, slug: str) -> Optional[str]:
        """
        Get the lastmod date for a slug.
        
        Args:
            slug: The article slug
            
        Returns:
            Date string (YYYY-MM-DD) or None if not available
        """
        self.load()
        return self._slug_dates.get(slug) if self._slug_dates else None
    
    def _sort_by_date(self, slugs: List[str]) -> List[str]:
        """Sort slugs by lastmod date (most recent first)."""
        if not self._slug_dates:
            return slugs
        
        def date_key(slug: str) -> str:
            # Return date or empty string (sorts to end)
            return self._slug_dates.get(slug, "")
        
        return sorted(slugs, key=date_key, reverse=True)
    
    def search(self, query: str, limit: int = 10, fuzzy: bool = True, min_similarity: float = 0.6, sort_by_date: bool = False) -> List[str]:
        """
        Search for matching slugs with optimized fuzzy matching.
        
        Args:
            query: Search query (can use spaces or underscores)
            limit: Maximum number of results to return
            fuzzy: Enable fuzzy matching if no exact matches found
            min_similarity: Minimum similarity score for fuzzy matching (0.0 to 1.0)
            sort_by_date: Sort results by lastmod date (most recent first)
            
        Returns:
            List of matching slugs, ordered by relevance (or date if sort_by_date=True)
            
        Example:
            >>> index = SlugIndex()
            >>> index.search("joe biden")
            ['Joe_Biden', 'Joe_Biden_presidential_campaign', ...]
            
        Note:
            - Uses BK-Tree for O(log n) fuzzy search when enabled (100-1000x faster)
            - Falls back to linear search with rapidfuzz if BK-Tree unavailable
            - Uses difflib.SequenceMatcher as final fallback
        """
        index = self.load()
        query_normalized = self._normalize_name(query)

        if limit <= 0:
            return []

        if not query_normalized:
            if not self._all_slugs:
                return []
            return self._all_slugs[:limit]

        # Strategy 1: Token-based matches ranked by relevance
        matches: List[str] = []
        seen = set()

        token_candidates = self._collect_token_candidates(query_normalized, limit)
        for slug in token_candidates:
            if slug not in seen:
                matches.append(slug)
                seen.add(slug)
            if len(matches) >= limit:
                break

        if not fuzzy or len(matches) >= limit:
            return matches[:limit]
        
        # Strategy 2: Fuzzy matching if enabled and we don't have enough matches
        if fuzzy and len(matches) < limit:
            remaining = limit - len(matches)
            min_similarity_threshold = min_similarity * 100.0
            
            # Strategy 2a: Use BK-Tree for O(log n) fuzzy search (if available)
            if self._bk_tree is not None:
                # Convert similarity threshold to max edit distance
                query_len = len(query_normalized)
                max_distance = int(query_len * (1 - min_similarity))
                
                # Search BK-Tree (dramatically faster than linear scan)
                bk_results = self._bk_tree.search(query_normalized, max_distance, remaining * 5)

                ranked_candidates: List[Tuple[float, int, str]] = []

                for slug, distance in bk_results:
                    if slug in seen:
                        continue

                    candidate_normalized = self._normalize_name(slug)
                    similarity = self._compute_similarity_score(query_normalized, candidate_normalized)

                    if similarity < min_similarity_threshold:
                        continue

                    ranked_candidates.append((similarity, distance, slug))

                ranked_candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

                for similarity, _, slug in ranked_candidates:
                    if slug not in seen:
                        matches.append(slug)
                        seen.add(slug)
                    if len(matches) >= limit:
                        break
            
            # Strategy 2b: Fallback to optimized linear search (if BK-Tree unavailable)
            else:
                # Use min-heap to efficiently track top-k results without sorting all items
                top_matches = []
                
                query_len = len(query_normalized)
                
                for normalized_name, slug in index.items():
                    if slug in seen:
                        continue  # Skip already matched slugs
                    
                    # Quick filter: skip if length difference is too large
                    name_len = len(normalized_name)
                    len_diff_ratio = abs(query_len - name_len) / max(query_len, name_len, 1)
                    
                    # Skip if length difference implies similarity below threshold
                    if len_diff_ratio > (1 - min_similarity):
                        continue
                    
                    # Calculate similarity ratio
                    similarity = self._compute_similarity_score(query_normalized, normalized_name)
                    
                    if similarity >= min_similarity_threshold:
                        if len(top_matches) < remaining:
                            heapq.heappush(top_matches, (similarity, -len(normalized_name), slug))
                        else:
                            smallest = top_matches[0]
                            if similarity > smallest[0]:
                                heapq.heapreplace(top_matches, (similarity, -len(normalized_name), slug))
                
                # Extract and sort matches from heap
                fuzzy_matches = sorted(top_matches, reverse=True)
                
                for _, _, slug in fuzzy_matches:
                    if slug not in seen:
                        matches.append(slug)
                        seen.add(slug)
        
        # Apply date sorting if requested
        if sort_by_date and matches:
            matches = self._sort_by_date(matches)
        
        return matches
    
    def find_best_match(self, query: str, min_similarity: float = 0.6) -> Optional[str]:
        """
        Find the single best matching slug for a query.
        
        Args:
            query: Article name or partial slug
            min_similarity: Minimum similarity score for fuzzy matching
            
        Returns:
            Best matching slug or None if not found
            
        Example:
            >>> index = SlugIndex()
            >>> index.find_best_match("elon musk")
            'Elon_Musk'
        """
        results = self.search(query, limit=1, fuzzy=True, min_similarity=min_similarity)
        return results[0] if results else None
    
    def exists(self, slug: str) -> bool:
        """
        Check if a slug exists in the index.
        
        Args:
            slug: Slug to check
            
        Returns:
            True if slug exists, False otherwise
            
        Example:
            >>> index = SlugIndex()
            >>> index.exists("Joe_Biden")
            True
        """
        index = self.load()
        slug_lower = slug.lower()
        
        # Check both normalized and original forms
        return slug_lower in index or slug in set(index.values())
    
    def list_by_prefix(self, prefix: str = "", limit: int = 100) -> List[str]:
        """
        List available articles, optionally filtered by prefix.
        
        Args:
            prefix: Filter articles starting with this prefix (case-insensitive)
            limit: Maximum number of results
            
        Returns:
            List of article slugs matching the prefix

        Example:
            >>> index = SlugIndex()
            >>> index.list_by_prefix(prefix="Artificial", limit=20)
            ['Artificial_Intelligence', 'Artificial_Neural_Network', ...]
        """
        self.load()  # Ensure index is loaded

        if not self._all_slugs:
            return []

        if limit <= 0:
            return []

        prefix_lower = prefix.lower()
        if not prefix_lower:
            return self._all_slugs[:limit]

        self._ensure_prefix_cache()
        if not self._all_slugs_lower_sorted or not self._all_slugs_sorted_by_lower:
            return []

        upper_bound = prefix_lower + '{'
        start = bisect.bisect_left(self._all_slugs_lower_sorted, prefix_lower)
        end = bisect.bisect_left(self._all_slugs_lower_sorted, upper_bound)

        matches = self._all_slugs_sorted_by_lower[start:end]
        return matches[:limit]

    def _ensure_prefix_cache(self) -> None:
        """Build a lowercase-sorted slug list for fast prefix searches."""
        if self._all_slugs is None:
            return
        if self._all_slugs_lower_sorted is not None:
            return

        pairs = sorted(
            ((slug.lower(), slug) for slug in self._all_slugs),
            key=lambda item: item[0]
        )
        self._all_slugs_lower_sorted = [item[0] for item in pairs]
        self._all_slugs_sorted_by_lower = [item[1] for item in pairs]
    
    def get_total_count(self) -> int:
        """
        Get the total number of articles in the index.
        
        Returns:
            Total number of unique article slugs
        """
        self.load()
        return len(self._all_slugs) if self._all_slugs else 0
    
    def random_slugs(self, count: int = 10) -> List[str]:
        """
        Get random article slugs from the index.
        
        Args:
            count: Number of random slugs to return
            
        Returns:
            List of random slugs
        """
        self.load()
        
        if not self._all_slugs:
            return []
        
        # Don't try to sample more than available
        sample_size = min(count, len(self._all_slugs))
        return random.sample(self._all_slugs, sample_size)

