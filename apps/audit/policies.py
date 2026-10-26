"""Authorisation rules for the Audit Log domain.

Pure predicates of the form `can_<verb>(actor, obj) -> bool`. Called from
`services.py` so every entry point — web, API, admin action, management
command — is covered by the same rule.
"""
