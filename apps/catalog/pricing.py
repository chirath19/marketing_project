"""Public price visibility; agreed proposal amounts are independent."""


def price_visible(priced, operating):
    visibility = getattr(priced, "price_visibility", "inherit")
    if visibility == "inherit" and getattr(priced, "service_id", None):
        visibility = priced.service.price_visibility
    if visibility != "inherit":
        return visibility == "show"
    return operating.show_public_prices
