"""
Token Immortality System - Advanced Token Management Framework

A comprehensive system for managing AI tokens with Pluribus-style allocation,
intelligent caching, predictive optimization, and emergency protocols.

Author: Executor AI
Version: 1.0.0
"""

from .immortal_system import ImmortalSystem
from .core.immortal_manager import ImmortalManager
from .core.token_pool import TokenPool
from .core.cache_optimizer import CacheOptimizer
from .core.resource_monitor import ResourceMonitor

__version__ = "1.0.0"
__author__ = "Executor AI"
__description__ = "Advanced Token Management Framework"

__all__ = [
    "ImmortalSystem",
    "ImmortalManager", 
    "TokenPool",
    "CacheOptimizer",
    "ResourceMonitor"
]