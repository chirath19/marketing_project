"""The container-component mechanism.

Slots are what let one modal template serve every modal, so their
isolation matters: content leaking between sibling components would be a
very confusing bug to chase.
"""

import pytest
from django.template import Context, Template, TemplateSyntaxError


def render(template_string: str, **context) -> str:
    return Template("{% load ui %}" + template_string).render(Context(context))


def test_the_body_arrives_as_the_default_slot():
    html = render('{% component "card" title="Leads" %}<p>Inside</p>{% endcomponent %}')

    assert "Leads" in html
    assert "<p>Inside</p>" in html


def test_a_named_slot_is_available_to_the_component():
    html = render(
        '{% component "card" title="Leads" %}'
        'body{% slot "footer" %}<b>Footer</b>{% endslot %}'
        "{% endcomponent %}"
    )

    assert "<b>Footer</b>" in html
    assert "body" in html


def test_named_slot_content_is_removed_from_the_default_slot():
    """Otherwise a footer would render twice: once in place and once in
    the footer region."""
    html = render(
        '{% component "card" %}{% slot "footer" %}FOOTERMARK{% endslot %}{% endcomponent %}'
    )

    assert html.count("FOOTERMARK") == 1


def test_sibling_components_do_not_share_slots():
    html = render(
        '{% component "card" title="One" %}{% slot "footer" %}FIRST{% endslot %}{% endcomponent %}'
        '{% component "card" title="Two" %}second body{% endcomponent %}'
    )

    assert html.count("FIRST") == 1


def test_a_slot_can_be_filled_from_inside_a_loop():
    html = render(
        '{% component "card" %}{% for n in numbers %}{% if forloop.first %}'
        '{% slot "footer" %}from loop{% endslot %}{% endif %}{% endfor %}'
        "{% endcomponent %}",
        numbers=[1, 2],
    )

    assert "from loop" in html


def test_slot_content_outside_a_component_still_renders():
    """Silently swallowing it would be the worst of the options."""
    html = render('{% slot "footer" %}orphan{% endslot %}')

    assert "orphan" in html


def test_variables_inside_a_slot_are_escaped():
    html = render(
        '{% component "card" %}{% slot "footer" %}{{ danger }}{% endslot %}{% endcomponent %}',
        danger="<script>alert(1)</script>",
    )

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_component_arguments_are_escaped():
    html = render('{% component "card" title=danger %}body{% endcomponent %}',
                  danger='<img src=x onerror="alert(1)">')

    assert "onerror" not in html or "&lt;img" in html
    assert "<img src=x" not in html


def test_component_requires_a_name():
    with pytest.raises(TemplateSyntaxError, match="requires a component name"):
        render("{% component %}{% endcomponent %}")


def test_component_rejects_positional_arguments():
    with pytest.raises(TemplateSyntaxError, match="keyword arguments"):
        render('{% component "card" "Recent" %}{% endcomponent %}')


def test_slot_requires_exactly_one_name():
    with pytest.raises(TemplateSyntaxError, match="exactly one name"):
        render('{% component "card" %}{% slot %}x{% endslot %}{% endcomponent %}')
