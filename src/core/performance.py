"""Performance Optimization - Caching and query optimization."""
from typing import Dict, Any, Optional, Callable
from functools import lru_cache
import hashlib
import json
import time
from dataclasses import dataclass


@dataclass
class CacheEntry:
    """Cached query result."""
    result: Any
    timestamp: float
    ttl: int  # Time to live in seconds
    
    def is_expired(self) -> bool:
        """Check if entry is expired."""
        return time.time() - self.timestamp > self.ttl


class QueryCache:
    """
    In-memory cache for query results.
    
    Caches:
    - Parsed intents
    - Generated SQL
    - Query results
    """
    
    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self.default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if exists and not expired."""
        entry = self._cache.get(key)
        
        if entry is None:
            self._misses += 1
            return None
        
        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            return None
        
        self._hits += 1
        return entry.result
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set cache value with TTL."""
        self._cache[key] = CacheEntry(
            result=value,
            timestamp=time.time(),
            ttl=ttl or self.default_ttl,
        )
    
    def invalidate(self, key: str):
        """Remove a specific key from cache."""
        if key in self._cache:
            del self._cache[key]
    
    def invalidate_pattern(self, pattern: str):
        """Remove keys matching pattern."""
        to_delete = [k for k in self._cache.keys() if pattern in k]
        for k in to_delete:
            del self._cache[k]
    
    def clear(self):
        """Clear all cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "size": len(self._cache),
        }


class OptimizedQueryEngine:
    """
    Optimized execution engine with caching.
    """
    
    def __init__(self, execution_engine, cache_ttl: int = 300):
        self.engine = execution_engine
        self.cache = QueryCache(cache_ttl)
    
    def execute(self, query: str, use_cache: bool = True) -> Any:
        """
        Execute query with caching.
        
        Args:
            query: SQL query
            use_cache: Whether to use cache
            
        Returns:
            Execution result
        """
        if not use_cache:
            return self.engine.execute(query)
        
        # Generate cache key
        cache_key = self._generate_cache_key(query)
        
        # Try cache first
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        # Execute and cache
        result = self.engine.execute(query)
        
        # Only cache successful results
        if result.success:
            self.cache.set(cache_key, result)
        
        return result
    
    def _generate_cache_key(self, query: str) -> str:
        """Generate cache key from query."""
        return hashlib.md5(query.encode()).hexdigest()
    
    def invalidate_for_table(self, table: str):
        """Invalidate cache when table data changes."""
        self.cache.invalidate_pattern(table)
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        return self.cache.get_stats()


class IntentParserCache:
    """
    Cache for parsed intents.
    """
    
    def __init__(self):
        self.cache = QueryCache(default_ttl=600)  # 10 minutes for intents
    
    def get_intent(self, query: str, previous: Optional[str] = None) -> Optional[Any]:
        """Get cached intent."""
        key = self._make_key(query, previous)
        return self.cache.get(key)
    
    def set_intent(self, query: str, intent: Any, previous: Optional[str] = None):
        """Cache intent."""
        key = self._make_key(query, previous)
        self.cache.set(key, intent)
    
    def _make_key(self, query: str, previous: Optional[str]) -> str:
        """Make cache key."""
        data = f"{query}|{previous or ''}"
        return hashlib.md5(data.encode()).hexdigest()


# Global cache instance
_query_cache: Optional[QueryCache] = None


def get_query_cache() -> QueryCache:
    """Get global query cache."""
    global _query_cache
    if _query_cache is None:
        _query_cache = QueryCache()
    return _query_cache


def cached_intent_parse(parser_func: Callable) -> Callable:
    """
    Decorator to cache intent parsing.
    
    Usage:
        @cached_intent_parse
        def parse(self, query):
            ...
    """
    def wrapper(self, query: str, *args, **kwargs):
        # Try to get from cache
        cache = get_query_cache()
        key = hashlib.md5(f"{query}:{args}:{kwargs}".encode()).hexdigest()
        
        cached = cache.get(f"intent:{key}")
        if cached:
            return cached
        
        # Parse and cache
        result = parser_func(self, query, *args, **kwargs)
        cache.set(f"intent:{key}", result)
        
        return result
    
    return wrapper


def create_optimized_engine(engine) -> OptimizedQueryEngine:
    """Create optimized query engine."""
    return OptimizedQueryEngine(engine)