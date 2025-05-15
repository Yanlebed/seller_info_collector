import os
import random
import time
import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class ProxyStats:
    """Track statistics for a proxy"""
    address: str
    success_count: int = 0
    failure_count: int = 0
    average_response_time: float = 0.0
    last_used: float = 0.0
    last_success: float = 0.0
    cookies_verified: bool = False
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate of the proxy"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
    
    @property
    def score(self) -> float:
        """Calculate a score for proxy quality"""
        # Simple scoring formula that considers success rate and average response time
        # Higher is better
        if self.success_count == 0:
            return 0.0
        
        response_time_factor = 1.0 / (1.0 + self.average_response_time) if self.average_response_time > 0 else 1.0
        time_since_success = time.time() - self.last_success
        recency_factor = 1.0 / (1.0 + time_since_success / 3600)  # Factor decreases as time since last success increases
        
        return self.success_rate * 0.6 + response_time_factor * 0.2 + recency_factor * 0.2
    
    def update_success(self, response_time: float) -> None:
        """Update stats after a successful request"""
        self.success_count += 1
        # Update average response time using running average
        if self.average_response_time > 0:
            total_requests = self.success_count + self.failure_count - 1
            self.average_response_time = (self.average_response_time * total_requests + response_time) / (total_requests + 1)
        else:
            self.average_response_time = response_time
        
        self.last_used = time.time()
        self.last_success = self.last_used
    
    def update_failure(self) -> None:
        """Update stats after a failed request"""
        self.failure_count += 1
        self.last_used = time.time()

class ProxyManager:
    """Manager for handling proxy rotation, selection, and performance tracking"""
    
    def __init__(self, proxy_file_path: str = "proxies.txt"):
        self.proxy_file_path = proxy_file_path
        self.proxies: Dict[str, ProxyStats] = {}
        self.lock = asyncio.Lock()
        self.verified_proxies: List[str] = []
        self.unverified_proxies: List[str] = []
        
    async def load_proxies(self) -> int:
        """Load proxies from file"""
        if not os.path.exists(self.proxy_file_path):
            logger.warning(f"Proxy file not found: {self.proxy_file_path}")
            return 0
        
        try:
            with open(self.proxy_file_path, 'r') as f:
                proxy_list = [line.strip() for line in f if line.strip()]
            
            async with self.lock:
                # Add new proxies
                for proxy in proxy_list:
                    if proxy not in self.proxies:
                        self.proxies[proxy] = ProxyStats(address=proxy)
                        self.unverified_proxies.append(proxy)
                
                logger.info(f"Loaded {len(proxy_list)} proxies from {self.proxy_file_path}")
                return len(proxy_list)
                
        except Exception as e:
            logger.error(f"Error loading proxies: {str(e)}")
            return 0
    
    async def get_next_proxy(self) -> Optional[str]:
        """Get the next best proxy to use"""
        async with self.lock:
            # If we have verified proxies, prioritize them based on score
            if self.verified_proxies:
                # Sort verified proxies by score
                sorted_proxies = sorted(
                    [p for p in self.verified_proxies if p in self.proxies],
                    key=lambda p: self.proxies[p].score,
                    reverse=True
                )
                
                # Use a weighted random selection to favor better proxies
                # but still give some chance to other proxies
                total_proxies = len(sorted_proxies)
                if total_proxies > 0:
                    # Calculate weights based on position in sorted list
                    weights = [max(0.1, 1.0 - (i / total_proxies)) for i in range(total_proxies)]
                    # Normalize weights
                    sum_weights = sum(weights)
                    norm_weights = [w / sum_weights for w in weights]
                    
                    # Random selection based on weights
                    selection = random.random()
                    cumulative = 0
                    for i, weight in enumerate(norm_weights):
                        cumulative += weight
                        if selection <= cumulative:
                            proxy = sorted_proxies[i]
                            self.proxies[proxy].last_used = time.time()
                            return proxy
                
                # Fallback to first proxy if weighted selection failed
                if sorted_proxies:
                    proxy = sorted_proxies[0]
                    self.proxies[proxy].last_used = time.time()
                    return proxy
            
            # If no verified proxies, try unverified ones
            if self.unverified_proxies:
                proxy = self.unverified_proxies.pop(0)
                self.proxies[proxy].last_used = time.time()
                return proxy
            
            # No proxies available
            return None
    
    async def mark_proxy_success(self, proxy: str, response_time: float, cookies_verified: bool = False) -> None:
        """Mark a proxy as successful"""
        async with self.lock:
            if proxy in self.proxies:
                self.proxies[proxy].update_success(response_time)
                
                # If proxy has cookies verified, add to verified list
                if cookies_verified and not self.proxies[proxy].cookies_verified:
                    self.proxies[proxy].cookies_verified = True
                    if proxy not in self.verified_proxies:
                        self.verified_proxies.append(proxy)
                        # Remove from unverified if it's there
                        if proxy in self.unverified_proxies:
                            self.unverified_proxies.remove(proxy)
                
                # If proxy is successful but not cookies verified yet,
                # move to verified list from unverified
                elif proxy not in self.verified_proxies:
                    self.verified_proxies.append(proxy)
                    # Remove from unverified if it's there
                    if proxy in self.unverified_proxies:
                        self.unverified_proxies.remove(proxy)
    
    async def mark_proxy_failure(self, proxy: str) -> None:
        """Mark a proxy as failed"""
        async with self.lock:
            if proxy in self.proxies:
                self.proxies[proxy].update_failure