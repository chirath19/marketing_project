"""Form infrastructure.

Django renders unstyled widgets. Rather than repeating class strings in
every template, forms mix in `StyledFormMixin`, which applies the design
system's control classes once.

**This mixin must never read `self.errors`.** Doing so runs `full_clean()`
from inside `__init__`, before any subclass has finished configuring its
fields — so a subclass that then sets `required = True` is silently
ignored and the cached errors are never recomputed. That bug shipped
once; it is why the error-dependent aria attributes (`aria-invalid`,
`aria-describedby`) are applied by the `{% ui_field %}` tag at render
time, when validation has genuinely finished, rather than here.

The class names (`ui-input`, `ui-select`, …) are defined once in
assets/css/app.css, so the widget attributes here and the standalone
control templates stay in step by construction.
"""

from __future__ import annotations

from django import forms

CONTROL_CLASSES = {
    "input": "ui-input",
    "textarea": "ui-input ui-textarea",
    "select": "ui-input ui-select",
    "checkbox": "ui-checkbox",
    "radio": "ui-radio",
    "file": "sr-only",
}


class StyledFormMixin:
    """Apply design-system classes to every widget.

    Styling only. Nothing here inspects the form's data or its errors, so
    the mixin is safe to use with a subclass that reconfigures fields
    after calling `super().__init__()`.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            self._style_widget(field.widget, field)

    @staticmethod
    def _style_widget(widget: forms.Widget, field: forms.Field) -> None:
        if isinstance(widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
            widget.attrs["class"] = "ui-choice-group"
            return
        if isinstance(widget, forms.CheckboxInput):
            key = "checkbox"
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            key = "select"
        elif isinstance(widget, forms.Textarea):
            key = "textarea"
        elif isinstance(widget, (forms.FileInput, forms.ClearableFileInput)):
            key = "file"
        else:
            key = "input"

        existing = widget.attrs.get("class", "")
        widget.attrs["class"] = f"{CONTROL_CLASSES[key]} {existing}".strip()

        if field.required:
            widget.attrs.setdefault("required", "required")


class StyledForm(StyledFormMixin, forms.Form):
    pass


class StyledModelForm(StyledFormMixin, forms.ModelForm):
    pass


class StyleguideDemoForm(StyledForm):
    """Sample fields covering every control the styleguide documents.

    Never processed — it exists so the styleguide shows real Django
    widgets rather than a hand-written approximation that could drift.
    """

    full_name = forms.CharField(label="Your name", max_length=120)
    work_email = forms.EmailField(label="Work email")
    website = forms.URLField(label="Website", required=False,
                             help_text="Include https://")
    budget = forms.ChoiceField(
        label="Monthly budget",
        choices=[("", "Select a range"), ("1", "Under $2,000"),
                 ("2", "$2,000 – $10,000"), ("3", "Over $10,000")],
        required=False,
    )
    goals = forms.CharField(
        label="What do you want to achieve?",
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
    )
    channel = forms.ChoiceField(
        label="Preferred channel",
        choices=[("search", "Search"), ("paid", "Paid ads"), ("social", "Social media")],
        widget=forms.RadioSelect,
        required=False,
    )
    services = forms.MultipleChoiceField(
        label="Services of interest",
        choices=[("seo", "SEO"), ("ads", "Paid ads"), ("email", "Email marketing")],
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    consent = forms.BooleanField(label="Allow tracking cookies", required=False)
