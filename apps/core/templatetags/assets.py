"""Static assets that a browser must not serve from a stale cache.

Development deliberately serves static files unhashed, so the dev server
does not need ``collectstatic`` on every change. The cost is that a
browser holding yesterday's ``dist/app.css`` keeps using it: the markup
arrives new, the stylesheet does not, and the page renders unstyled —
which looks like a broken build rather than a cached file.

``{% static_version 'dist/app.css' %}`` appends the file's modification
time, so the URL changes exactly when the file does and never otherwise.
Under a hashing storage backend the name already carries a fingerprint,
so the stamp is skipped.
"""

from __future__ import annotations

from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import HashedFilesMixin, staticfiles_storage
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_version(path: str) -> str:
    """The static URL for ``path`` with a cache-busting stamp."""
    url = static(path)

    # A hashing backend has already fingerprinted the name. `isinstance`
    # rather than a name check: `staticfiles_storage` is a lazy proxy, and
    # `type()` on it reports the proxy, not the storage it wraps.
    if isinstance(staticfiles_storage, HashedFilesMixin):
        return url

    # `finders` resolves through STATICFILES_DIRS, which is where the
    # built stylesheet lives before collectstatic has ever run.
    located = finders.find(path)
    if not located:
        return url

    try:
        stamp = int(Path(located).stat().st_mtime)
    except OSError:
        # The file vanished between finding and stat-ing it. An unstamped
        # URL still serves the page; raising here would not.
        return url

    separator = "&" if "?" in url else "?"
    return f"{url}{separator}v={stamp}"
