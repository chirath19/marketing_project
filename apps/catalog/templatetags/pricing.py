from django import template

from apps.catalog.pricing import price_visible

register = template.Library()
register.filter("public_price", price_visible)
