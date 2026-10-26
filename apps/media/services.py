"""Write operations for the Media domain.

The only place state changes. Each function is transactional, authorises
through `policies.py` first, and emits domain events via the core event
bus rather than importing other domains directly.
"""
