from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.cms import copy
from apps.permissions.guards import require_permission


@require_permission("cms_view")
@require_http_methods(["GET", "POST"])
def editor(request):
    if request.method == "POST":
        try:
            copy.update(
                actor=request.user,
                key=request.POST.get("key", ""),
                text=request.POST.get("text", ""),
                reset=request.POST.get("action") == "reset",
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, "Website text saved.")
        return redirect(request.get_full_path())
    query = request.GET.get("q", "").strip()
    values = copy.overrides()
    entries = [
        {
            "key": key,
            "label": key.replace("public.", "Website · ")
            .replace("cms.sections.", "Page sections · ")
            .replace(".", " · ")
            .replace("_", " ")
            .title(),
            "text": values.get(key, default),
            "default": default,
        }
        for key, default in copy.defaults().items()
        if not query or query.lower() in (key + default + values.get(key, "")).lower()
    ]
    return render(
        request,
        "cms/admin/copy.html",
        {
            "page_title": "Website wording",
            "page_subtitle": "Edit public headings, guidance and calls to action.",
            "nav_key": "cms",
            "entries": entries,
            "query": query,
        },
    )
