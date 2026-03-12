"""Simple API key authentication and rate limiting.

Supports free and paid tiers with configurable rate limits.

Env vars:
  REQUIRE_AUTH - Set to 'true' to enforce auth (default: false)
  API_KEYS     - Comma-separated list of valid API keys for paid tier
"""
import os
import time
from typing import Dict, Optional, Tuple


# Rate limits
FREE_TIER_DAILY_LIMIT = 100
PAID_TIER_DAILY_LIMIT = 10_000

# Cleanup interval: remove stale tracking entries older than this (seconds)
_STALE_THRESHOLD = 86_400 * 2  # 2 days


class AuthManager:
    """Manages API key authentication and per-key rate limiting."""

    def __init__(self):
        # usage[key_or_"free"] = {"count": int, "day": str, "calls_per_minute": {minute_ts: int}}
        self._usage: Dict[str, Dict] = {}

    @property
    def require_auth(self) -> bool:
        """Whether authentication is required."""
        return os.environ.get("REQUIRE_AUTH", "false").lower() in ("true", "1", "yes")

    @property
    def valid_api_keys(self) -> set:
        """Set of valid API keys from env."""
        raw = os.environ.get("API_KEYS", "")
        if not raw.strip():
            return set()
        return {k.strip() for k in raw.split(",") if k.strip()}

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def _current_minute(self) -> int:
        return int(time.time()) // 60

    def _get_usage(self, key: str) -> Dict:
        """Get or initialize usage record for a key."""
        today = self._today()
        if key not in self._usage or self._usage[key].get("day") != today:
            self._usage[key] = {
                "count": 0,
                "day": today,
                "calls_per_minute": {},
            }
        return self._usage[key]

    def check_auth(self, api_key: Optional[str] = None) -> Tuple[bool, str, int]:
        """Check if a request is allowed.

        Args:
            api_key: The API key provided by the caller (None for free tier).

        Returns:
            (allowed, tier, remaining) tuple:
                - allowed: Whether the request should proceed
                - tier: 'free' or 'paid'
                - remaining: Number of requests remaining today
        """
        if not self.require_auth:
            # Auth not required - allow everything, still track as free tier
            tier = "free"
            if api_key and api_key in self.valid_api_keys:
                tier = "paid"
            usage_key = api_key or "free"
            usage = self._get_usage(usage_key)
            limit = PAID_TIER_DAILY_LIMIT if tier == "paid" else FREE_TIER_DAILY_LIMIT
            remaining = max(0, limit - usage["count"])
            return (True, tier, remaining)

        # Auth is required
        if api_key and api_key in self.valid_api_keys:
            # Paid tier
            usage = self._get_usage(api_key)
            remaining = max(0, PAID_TIER_DAILY_LIMIT - usage["count"])
            if remaining <= 0:
                return (False, "paid", 0)
            return (True, "paid", remaining)

        # Free tier (no key or invalid key)
        usage = self._get_usage("free")
        remaining = max(0, FREE_TIER_DAILY_LIMIT - usage["count"])
        if remaining <= 0:
            return (False, "free", 0)
        return (True, "free", remaining)

    def track_usage(self, api_key: Optional[str] = None) -> Dict:
        """Increment usage counter for a key.

        Args:
            api_key: The API key (None for free tier).

        Returns:
            Dict with usage info: tier, count, remaining, calls_this_minute.
        """
        valid_keys = self.valid_api_keys
        if api_key and api_key in valid_keys:
            tier = "paid"
            usage_key = api_key
            limit = PAID_TIER_DAILY_LIMIT
        else:
            tier = "free"
            usage_key = "free"
            limit = FREE_TIER_DAILY_LIMIT

        usage = self._get_usage(usage_key)
        usage["count"] += 1

        # Track per-minute calls
        minute = self._current_minute()
        cpm = usage.get("calls_per_minute", {})
        cpm[minute] = cpm.get(minute, 0) + 1

        # Clean old minute entries (keep last 10 minutes)
        cutoff = minute - 10
        cpm = {m: c for m, c in cpm.items() if m >= cutoff}
        usage["calls_per_minute"] = cpm

        remaining = max(0, limit - usage["count"])

        return {
            "tier": tier,
            "count_today": usage["count"],
            "remaining_today": remaining,
            "daily_limit": limit,
            "calls_this_minute": cpm.get(minute, 0),
        }
