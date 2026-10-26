"""Read access for the Audit Log domain.

Every queryset returned from here is already `select_related` /
`prefetch_related` complete and scoped to the requesting actor. Views,
serializers and templates read through these functions, never through a
raw manager.
"""
