"""The design-system template tags.

Three shapes of component:

* **Leaf components** (button, badge, metric card) are inclusion tags with
  explicit, documented keyword arguments.
* **Container components** (card, modal, table) are written with
  ``{% component "name" %} … {% endcomponent %}``. Their body is available
  to the component template as ``slot``.
* **Multi-slot containers** additionally accept ``{% slot "footer" %} …
  {% endslot %}`` blocks, which arrive as ``slots.footer``. That is what
  lets one modal template serve every modal rather than each feature
  growing its own.

Templates never write raw brand hex values and never hand-roll a control's
class string: they call these tags, and the tags read from
``apps.core.design``. That is what keeps the public site and the
dashboards looking like one product.
"""

from __future__ import annotations

from django import template
from django.template.base import FilterExpression, NodeList, Parser, Token
from django.template.loader import render_to_string

from apps.core import design

register = template.Library()

SLOT_CONTEXT_KEY = "_component_slots"


# ---------------------------------------------------------------------------
# Container components
# ---------------------------------------------------------------------------


def _parse_kwargs(parser: Parser, bits: list[str], tag: str) -> dict[str, FilterExpression]:
    kwargs: dict[str, FilterExpression] = {}
    for bit in bits:
        if "=" not in bit:
            raise template.TemplateSyntaxError(
                f"{{% {tag} %}} arguments must be keyword arguments, got {bit!r}"
            )
        key, raw = bit.split("=", 1)
        kwargs[key] = parser.compile_filter(raw)
    return kwargs


class ComponentNode(template.Node):
    def __init__(self, name: FilterExpression, kwargs: dict[str, FilterExpression],
                 nodelist: NodeList) -> None:
        self.name = name
        self.kwargs = kwargs
        self.nodelist = nodelist

    def render(self, context: template.Context) -> str:
        name = self.name.resolve(context)
        resolved = {key: value.resolve(context) for key, value in self.kwargs.items()}

        # Named slots are collected while the body renders. The dict is
        # pushed onto the context so a {% slot %} anywhere inside — including
        # within a loop or an {% if %} — can find it, and popped afterwards so
        # sibling components never see each other's slots.
        slots: dict[str, str] = {}
        with context.push(**{SLOT_CONTEXT_KEY: slots}):
            default_slot = self.nodelist.render(context)

        # `NodeList.render` returns a SafeString: the body was rendered by
        # the template engine, which escaped each variable as it went. No
        # further marking is needed, and marking raw input safe here would
        # be exactly the bug to avoid.
        resolved["slot"] = default_slot
        resolved["slots"] = slots
        return render_to_string(
            f"components/{name}.html", resolved, request=context.get("request")
        )


@register.tag("component")
def do_component(parser: Parser, token: Token) -> ComponentNode:
    """``{% component "card" title="Leads" %} … {% endcomponent %}``"""
    bits = token.split_contents()
    if len(bits) < 2:
        raise template.TemplateSyntaxError(
            '{% component %} requires a component name, e.g. {% component "card" %}'
        )

    name = parser.compile_filter(bits[1])
    kwargs = _parse_kwargs(parser, bits[2:], "component")
    nodelist = parser.parse(("endcomponent",))
    parser.delete_first_token()
    return ComponentNode(name, kwargs, nodelist)


class SlotNode(template.Node):
    def __init__(self, name: FilterExpression, nodelist: NodeList) -> None:
        self.name = name
        self.nodelist = nodelist

    def render(self, context: template.Context) -> str:
        slots = context.get(SLOT_CONTEXT_KEY)
        content = self.nodelist.render(context)
        if slots is None:
            # Outside a component the content would otherwise vanish
            # silently; rendering it in place is the least surprising
            # behaviour.
            return content
        slots[self.name.resolve(context)] = content  # already a SafeString
        return ""


@register.tag("slot")
def do_slot(parser: Parser, token: Token) -> SlotNode:
    """``{% slot "footer" %} … {% endslot %}`` inside a ``{% component %}``."""
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError(
            '{% slot %} takes exactly one name, e.g. {% slot "footer" %}'
        )

    name = parser.compile_filter(bits[1])
    nodelist = parser.parse(("endslot",))
    parser.delete_first_token()
    return SlotNode(name, nodelist)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@register.inclusion_tag("components/button.html")
def ui_button(label: str = "", href: str = "", variant: str = "primary", size: str = "md",
              type: str = "button", icon: str = "", icon_after: str = "",
              full: bool = False, disabled: bool = False, busy_label: str = "",
              extra_class: str = "", **attrs: str) -> dict:
    """variant: primary | secondary | outline | ghost | subtle | danger.

    Renders an ``<a>`` when ``href`` is given and a ``<button>`` otherwise,
    so a navigation control is never a button a keyboard user cannot
    middle-click or open in a new tab.

    Extra keyword arguments are emitted as attributes, with ``_``
    translated to ``-`` so HTMX and Alpine attributes can be passed
    (``hx_get=…`` becomes ``hx-get=…``).
    """
    return {
        "label": label,
        "href": href,
        "type": type,
        "icon": icon,
        "icon_after": icon_after,
        "disabled": disabled,
        "busy_label": busy_label,
        "css": design.classes(design.button_classes(variant, size, full=full),
                              extra_class, _extra_class(attrs)),
        "attrs": _attrs(attrs),
    }


@register.inclusion_tag("components/icon_button.html")
def ui_icon_button(icon: str, label: str, href: str = "", variant: str = "ghost",
                   size: str = "md", type: str = "button", extra_class: str = "",
                   **attrs: str) -> dict:
    """An icon-only control.

    ``label`` is required and becomes the accessible name — an icon button
    without one is invisible to a screen reader.
    """
    return {
        "icon": icon, "label": label, "href": href, "type": type,
        "css": design.classes(design.button_classes(variant, size, icon_only=True),
                              extra_class, _extra_class(attrs)),
        "attrs": _attrs(attrs),
    }


def _attrs(attrs: dict[str, object]) -> dict[str, object]:
    """Turn tag keyword arguments into HTML attribute names.

    `class` is removed: a component sets its own, and emitting a second
    `class` attribute produces markup where the browser keeps the first
    and silently ignores the caller's. Use `extra_class` instead, which
    is merged into the component's own classes.
    """
    return {key.replace("_", "-"): value for key, value in attrs.items()
            if value is not None and value is not False and key != "class"}


def _extra_class(attrs: dict[str, object]) -> str:
    """Classes the caller wants merged in, from `extra_class` or `class`."""
    return " ".join(str(attrs.get(name, "")) for name in ("extra_class", "class")).strip()


# ---------------------------------------------------------------------------
# Status and data display
# ---------------------------------------------------------------------------


@register.inclusion_tag("components/badge.html")
def ui_badge(label: str, tone: str = "neutral", dot: bool = False) -> dict:
    """tone: neutral | gold | live | paused | planned | done | danger | info."""
    return {"label": label, "css": design.badge_tone(tone), "dot": dot,
            "tone": tone}


@register.inclusion_tag("components/badge.html")
def ui_status_badge(status, label: str = "", dot: bool = True) -> dict:  # noqa: ANN001
    """A badge whose tone is derived from a domain status value.

    Accepts a TextChoices member, a raw string or None, so callers never
    have to normalise first.
    """
    tone = design.tone_for_status(status)
    return {"label": label or design.status_label(status),
            "css": design.badge_tone(tone), "dot": dot, "tone": tone}


@register.inclusion_tag("components/metric_card.html")
def ui_metric_card(label: str, value: str, delta: str = "", direction: str = "flat",
                   caption: str = "", href: str = "", icon: str = "") -> dict:
    """A KPI tile: the four headline numbers at the top of a dashboard.

    ``direction`` is always supplied by the caller — see
    ``design.DELTA_DIRECTIONS`` for why it is never inferred.
    """
    delta_css, arrow = design.delta_style(direction)
    return {"label": label, "value": value, "delta": delta, "delta_css": delta_css,
            "arrow": arrow, "caption": caption, "href": href, "icon": icon}


@register.inclusion_tag("components/progress_bar.html")
def ui_progress(current, target, label: str = "", suffix: str = "") -> dict:  # noqa: ANN001
    """The "412 of 450" goal bar from the dashboard reference."""
    return {"current": current, "target": target, "label": label,
            "suffix": suffix, "pct": design.percentage(current, target)}


@register.inclusion_tag("components/alert.html")
def ui_alert(message: str = "", tone: str = "info", title: str = "",
             dismissible: bool = False) -> dict:
    """tone: info | success | warning | danger."""
    css, role = design.alert_tone(tone)
    return {"message": message, "title": title, "dismissible": dismissible,
            "css": css, "role": role}


@register.inclusion_tag("components/empty_state.html")
def ui_empty_state(title: str, body: str = "", action_label: str = "",
                   action_href: str = "", icon: str = "") -> dict:
    return {"title": title, "body": body, "icon": icon,
            "action_label": action_label, "action_href": action_href}


@register.inclusion_tag("components/table_empty.html")
def ui_table_empty(title: str, colspan: int = 6, body: str = "",
                   action_label: str = "", action_href: str = "",
                   icon: str = "") -> dict:
    """An empty state sized to span a table.

    Same shape as `ui_empty_state`, plus the column count, because an
    empty row that does not span the table leaves a ragged cell where
    the explanation should be.
    """
    return {"title": title, "body": body, "icon": icon, "colspan": colspan,
            "action_label": action_label, "action_href": action_href}


@register.inclusion_tag("components/skeleton.html")
def ui_skeleton(variant: str = "text", lines: int = 3) -> dict:
    """Placeholder shown while content loads. variant: text | card | table.

    Marked ``aria-hidden`` with a polite live region alongside, so a screen
    reader hears "Loading" once instead of reading a wall of empty boxes.
    """
    return {"variant": variant, "lines": range(max(1, int(lines)))}


@register.inclusion_tag("components/spinner.html")
def ui_spinner(label: str = "Loading") -> dict:
    """HTMX indicator. Invisible until htmx marks the request in flight."""
    return {"label": label}


# ---------------------------------------------------------------------------
# Page structure and navigation
# ---------------------------------------------------------------------------


# The page header is a container component — `{% component "page_header"
# title="Campaigns" %}` with its action controls in the body — because the
# actions are real buttons, not strings to be passed around.


@register.inclusion_tag("components/breadcrumbs.html")
def ui_breadcrumbs(items, current: str = "") -> dict:  # noqa: ANN001
    """items: an iterable of ``{"label": …, "href": …}``.

    The final entry is rendered as text with ``aria-current="page"``,
    because a link to the page you are on is noise for keyboard and screen
    reader users alike.
    """
    return {"items": items or [], "current": current}


@register.inclusion_tag("components/tabs.html")
def ui_tabs(tabs, active: str = "", label: str = "Filter") -> dict:  # noqa: ANN001
    """Filter tabs: ``{"key", "label", "href", "count"}`` per tab.

    Rendered as links, matching the All / Live / Paused / Planned / Done
    filter in the product reference: the choice is server-side state, so it
    belongs in the URL and must survive a reload and a shared link.
    """
    return {"tabs": tabs or [], "active": active, "label": label}


@register.inclusion_tag("components/pagination.html")
def ui_pagination(page_obj, querystring: str = "", label: str = "Pagination") -> dict:  # noqa: ANN001
    """Django ``Page`` object in, accessible pager out."""
    if page_obj is None:
        return {"page_obj": None}

    paginator = page_obj.paginator
    current = page_obj.number
    total = paginator.num_pages

    # A compact window: first, last, and two either side of the current
    # page, with gaps marked so the template can render an ellipsis.
    window = {1, total, current}
    window.update(n for n in range(current - 2, current + 3) if 1 <= n <= total)
    ordered = sorted(window)

    pages: list[dict] = []
    previous = 0
    for number in ordered:
        if previous and number - previous > 1:
            pages.append({"gap": True})
        pages.append({"number": number, "current": number == current})
        previous = number

    prefix = f"?{querystring}&" if querystring else "?"
    return {"page_obj": page_obj, "pages": pages, "prefix": prefix,
            "label": label, "total": total}


@register.inclusion_tag("components/search_box.html")
def ui_search_box(name: str = "q", value: str = "", placeholder: str = "Search",
                  label: str = "Search", **attrs: str) -> dict:
    """A labelled search input. The label is visually hidden, never absent."""
    return {"name": name, "value": value, "placeholder": placeholder,
            "label": label, "attrs": _attrs(attrs)}


@register.inclusion_tag("components/nav_item.html", takes_context=True)
def ui_nav_item(context, label: str, href: str, active: bool = False,
                count=None, icon: str = "", variant: str = "top") -> dict:  # noqa: ANN001
    """variant: top (dashboard bar) | side (staff sidebar) | public."""
    return {"label": label, "href": href, "active": active, "count": count,
            "icon": icon, "variant": variant, "request": context.get("request")}


@register.inclusion_tag("components/toasts.html", takes_context=True)
def ui_toasts(context) -> dict:  # noqa: ANN001
    """The toast region.

    Server-side messages are rendered into it on load; client-side ones
    arrive as a ``ui:toast`` event, which HTMX responses can raise with an
    ``HX-Trigger`` header. One region, one live-region announcement.
    """
    return {"messages": context.get("messages", [])}


@register.filter
def column_label(column) -> str:  # noqa: ANN001
    """The heading text for a table column.

    A column is either a plain string or a mapping with a `label`. The
    obvious template spelling, ``{{ column.label|default:column }}``,
    breaks on a mapping whose label is deliberately blank — an actions
    column, say — because `default` fires on the empty string and prints
    the mapping's repr into the page. It did exactly that.
    """
    if isinstance(column, str):
        return column
    try:
        return str(column.get("label", "") or "")
    except AttributeError:
        return str(column)


@register.filter
def column_sr_label(column) -> str:  # noqa: ANN001
    """Accessible name for a column with no visible heading."""
    if isinstance(column, str):
        return column
    try:
        return str(column.get("sr_label", "") or "Actions")
    except AttributeError:
        return "Actions"


@register.filter
def get_attribute(obj, name: str):  # noqa: ANN001, ANN201
    """Read an attribute whose name is itself a variable.

    Needed by the generic collection table, where the columns are declared
    in Python rather than written out in the template. Callables are
    called, so a column can name `get_placement_display`. Returns an empty
    string for anything missing — a list page must not 500 because one
    column was renamed.
    """
    value = getattr(obj, name, "")
    if callable(value):
        try:
            value = value()
        except TypeError:
            return ""
    return "" if value is None else value


# ---------------------------------------------------------------------------
# Forms
#
# `ui_field` is the one tag a form template normally needs: it works out
# which control a bound field wants and wires up the label, help text,
# error messages and the aria attributes that tie them together. The
# standalone control tags exist for the cases with no Django form behind
# them, such as a filter bar built from query parameters.
# ---------------------------------------------------------------------------


def _field_kind(field) -> str:  # noqa: ANN001
    """Classify a bound field by the control it should render as."""
    from django import forms

    widget = field.field.widget

    if isinstance(widget, forms.CheckboxInput):
        return "checkbox"
    if isinstance(widget, forms.CheckboxSelectMultiple):
        return "checkbox_group"
    if isinstance(widget, forms.RadioSelect):
        return "radio_group"
    if isinstance(widget, (forms.Select, forms.SelectMultiple)):
        return "select"
    if isinstance(widget, forms.Textarea):
        return "textarea"
    if isinstance(widget, (forms.FileInput, forms.ClearableFileInput)):
        return "file"
    return "input"


@register.inclusion_tag("components/field.html")
def ui_field(field, help_text: str = "", label: str = "") -> dict:  # noqa: ANN001
    """Render a bound Django form field with its label, help and errors.

    The layout differs by control — a checkbox puts its label after the
    box, a radio group needs a fieldset and legend — so the kind is
    resolved here rather than asking every form template to know.
    """
    help_id = f"id_{field.name}_help"
    error_id = f"id_{field.name}_error"
    resolved_help = help_text or field.help_text

    # Applied here rather than in StyledFormMixin.__init__: reading
    # `field.errors` there would run full_clean() before a subclass had
    # finished configuring its fields. By render time validation is done,
    # so these attributes describe the form's real state.
    described_by = [
        anchor for anchor, present in
        ((help_id, bool(resolved_help)), (error_id, bool(field.errors)))
        if present
    ]
    widget_attrs = field.field.widget.attrs
    if described_by:
        widget_attrs["aria-describedby"] = " ".join(described_by)
    if field.errors:
        widget_attrs["aria-invalid"] = "true"

    return {
        "field": field,
        "kind": _field_kind(field),
        "label": label or field.label,
        "help_text": resolved_help,
        "help_id": help_id,
        "error_id": error_id,
        "required": field.field.required,
    }


@register.inclusion_tag("components/form_errors.html")
def ui_form_errors(form, title: str = "There is a problem") -> dict:  # noqa: ANN001
    """Form-level errors, as an error summary at the top of the form.

    Each entry links to the field it concerns, so a keyboard user can jump
    straight to the input that needs fixing instead of hunting for it.
    """
    entries = []
    for name, errors in getattr(form, "errors", {}).items():
        if name == "__all__":
            continue
        bound = form[name]
        entries.extend({"label": bound.label, "message": error,
                        "target": bound.id_for_label} for error in errors)

    return {
        "non_field_errors": getattr(form, "non_field_errors", list)(),
        "entries": entries,
        "title": title,
    }


@register.inclusion_tag("components/control_input.html")
def ui_input(name: str, value: str = "", type: str = "text", label: str = "",
             placeholder: str = "", required: bool = False, disabled: bool = False,
             help_text: str = "", error: str = "", id: str = "",
             **attrs: str) -> dict:
    return _control(locals_=locals(), kind="input")


@register.inclusion_tag("components/control_textarea.html")
def ui_textarea(name: str, value: str = "", label: str = "", rows: int = 4,
                placeholder: str = "", required: bool = False, disabled: bool = False,
                help_text: str = "", error: str = "", id: str = "",
                **attrs: str) -> dict:
    return _control(locals_=locals(), kind="textarea")


@register.inclusion_tag("components/control_select.html")
def ui_select(name: str, options, value: str = "", label: str = "",  # noqa: ANN001
              placeholder: str = "", required: bool = False, disabled: bool = False,
              help_text: str = "", error: str = "", id: str = "",
              **attrs: str) -> dict:
    """options: an iterable of ``(value, label)`` pairs or plain strings."""
    normalised = [
        option if isinstance(option, (tuple, list)) else (option, option)
        for option in (options or [])
    ]
    context = _control(locals_=locals(), kind="select")
    context["options"] = normalised
    return context


@register.inclusion_tag("components/control_checkbox.html")
def ui_checkbox(name: str, label: str, value: str = "1", checked: bool = False,
                disabled: bool = False, help_text: str = "", error: str = "",
                id: str = "", **attrs: str) -> dict:
    context = _control(locals_=locals(), kind="checkbox")
    context["checked"] = checked
    return context


@register.inclusion_tag("components/control_radio_group.html")
def ui_radio_group(name: str, options, value: str = "", label: str = "",  # noqa: ANN001
                   required: bool = False, disabled: bool = False,
                   help_text: str = "", error: str = "", inline: bool = False,
                   **attrs: str) -> dict:
    """A radio group in a fieldset with a legend.

    Radios without a grouping element are announced one by one with no
    indication of what the choice is for.
    """
    normalised = [
        option if isinstance(option, (tuple, list)) else (option, option)
        for option in (options or [])
    ]
    context = _control(locals_=locals(), kind="radio_group")
    context["options"] = normalised
    context["inline"] = inline
    return context


@register.inclusion_tag("components/file_upload.html")
def ui_file_upload(name: str, label: str = "Upload a file", accept: str = "",
                   multiple: bool = False, help_text: str = "", error: str = "",
                   id: str = "", **attrs: str) -> dict:
    """A drop zone that is also a plain file input.

    The input is a real ``<input type="file">`` wrapped by its label, so it
    is reachable and operable by keyboard; the drag-and-drop behaviour is
    an enhancement layered on top, not the only way in.
    """
    context = _control(locals_=locals(), kind="file")
    context["accept"] = accept
    context["multiple"] = multiple
    return context


def _control(locals_: dict, kind: str) -> dict:
    """Shared plumbing for the standalone control tags.

    Builds the element id, the help and error ids, and the
    ``aria-describedby`` / ``aria-invalid`` pair — the wiring that is easy
    to forget by hand and invisible when it is missing.
    """
    attrs = dict(locals_.get("attrs") or {})
    name = locals_["name"]
    element_id = locals_.get("id") or f"id_{name}"
    help_text = locals_.get("help_text", "")
    error = locals_.get("error", "")

    described_by = " ".join(filter(None, [
        f"{element_id}_help" if help_text else "",
        f"{element_id}_error" if error else "",
    ]))

    return {
        "kind": kind,
        "name": name,
        "id": element_id,
        "value": locals_.get("value", ""),
        "type": locals_.get("type", "text"),
        "label": locals_.get("label", ""),
        "placeholder": locals_.get("placeholder", ""),
        "rows": locals_.get("rows", 4),
        "required": locals_.get("required", False),
        "disabled": locals_.get("disabled", False),
        "help_text": help_text,
        "error": error,
        "help_id": f"{element_id}_help",
        "error_id": f"{element_id}_error",
        "described_by": described_by,
        "attrs": _attrs(attrs),
    }


# ---------------------------------------------------------------------------
# Business components
#
# These compose the primitives above into the shapes the product actually
# shows: a service in the catalogue, a campaign in a list, an approval
# waiting on a client. They take a plain object and read attributes from
# it, so they work with a model instance, a dataclass or a dict without
# any adapter — and they can be exercised before the models exist.
#
# Each tag documents the attributes it reads. Anything missing renders as
# empty rather than raising, because a half-populated record should still
# produce a usable card.
# ---------------------------------------------------------------------------


@register.inclusion_tag("components/business/service_card.html")
def ui_service_card(service, href: str = "", action_label: str = "Add to quote",  # noqa: ANN001
                    action_attrs: str = "", selected: bool = False) -> dict:
    """A catalogue service.

    Reads: ``name``, ``category``, ``summary``, ``price_display``,
    ``billing_period`` ("per month" / "one time"), ``inclusions``
    (iterable of strings), ``slug``.
    """
    return {"service": service, "href": href, "action_label": action_label,
            "selected": selected}


@register.inclusion_tag("components/business/client_card.html")
def ui_client_card(client, href: str = "") -> dict:  # noqa: ANN001
    """A client organization.

    Reads: ``name``, ``industry``, ``status``, ``logo``, ``owner``
    (assigned staff member), ``active_services`` (int), ``monthly_value``.
    """
    return {"client": client, "href": href,
            "tone": design.tone_for_status(getattr(client, "status", None))}


@register.inclusion_tag("components/business/campaign_card.html")
def ui_campaign_card(campaign, href: str = "") -> dict:  # noqa: ANN001
    """A campaign.

    Reads: ``name``, ``service``/``module_label``, ``status``, ``spend_display``,
    ``result_summary``, ``start_date``, ``owner``.
    """
    return {"campaign": campaign, "href": href,
            "tone": design.tone_for_status(getattr(campaign, "status", None))}


@register.inclusion_tag("components/business/lead_card.html")
def ui_lead_card(lead, href: str = "") -> dict:  # noqa: ANN001
    """A lead or enquiry.

    Reads: ``name``, ``company``, ``email``, ``source``, ``status``,
    ``value_display``, ``created_at``, ``summary``.
    """
    return {"lead": lead, "href": href,
            "tone": design.tone_for_status(getattr(lead, "status", None))}


@register.inclusion_tag("components/business/approval_card.html")
def ui_approval_card(approval, approve_url: str = "", reject_url: str = "",  # noqa: ANN001
                     compact: bool = False) -> dict:
    """An item waiting on a client decision.

    Reads: ``title``, ``module_label``, ``summary``, ``requested_by``,
    ``due_date``, ``status``.

    The approve and reject controls are real form submissions, never links:
    a decision changes state and must not be triggered by a prefetch or a
    crawler.
    """
    return {"approval": approval, "approve_url": approve_url,
            "reject_url": reject_url, "compact": compact,
            "tone": design.tone_for_status(getattr(approval, "status", None))}


@register.inclusion_tag("components/business/report_card.html")
def ui_report_card(report, href: str = "", download_url: str = "") -> dict:  # noqa: ANN001
    """A generated report.

    Reads: ``title``, ``period_label``, ``module_label``, ``generated_at``,
    ``summary``, ``format``.
    """
    return {"report": report, "href": href, "download_url": download_url}


@register.inclusion_tag("components/business/activity_timeline.html")
def ui_activity_timeline(entries, empty_title: str = "Nothing yet") -> dict:  # noqa: ANN001
    """The "Recent activity" feed.

    Each entry reads: ``title``, ``module_label``, ``timestamp``,
    ``timesince`` (pre-formatted relative time), ``tone``, ``href``.
    """
    return {"entries": entries or [], "empty_title": empty_title}


@register.inclusion_tag("components/business/notification_item.html")
def ui_notification_item(notification, href: str = "") -> dict:  # noqa: ANN001
    """One row in the Notification Center.

    Reads: ``title``, ``body``, ``created_at``, ``is_read``, ``severity``,
    ``link``.
    """
    return {"notification": notification,
            "href": href or getattr(notification, "link", ""),
            "tone": design.tone_for_status(getattr(notification, "severity", None))}


@register.inclusion_tag("components/business/inbox_message_item.html")
def ui_inbox_message_item(message, href: str = "", selected: bool = False) -> dict:  # noqa: ANN001
    """One row in the staff Inbox.

    Reads: ``subject``, ``preview``, ``sender_name``, ``sender_org``,
    ``received_at``, ``is_read``, ``kind_label`` (enquiry, quote request,
    client message), ``has_attachments``.
    """
    return {"message": message, "href": href, "selected": selected}
