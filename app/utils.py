from decimal import Decimal, InvalidOperation

CENT = Decimal('0.01')
MAX_AMOUNT = Decimal('99999999.99')  # fits Numeric(10, 2)

AMOUNT_ERROR = 'Enter a positive amount with no more than two decimal places'


def parse_amount(raw):
    """Return a positive Decimal with at most two decimal places, or None."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        amount = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    if (
        not amount.is_finite()
        or amount <= 0
        or amount > MAX_AMOUNT
        or amount.quantize(CENT) != amount
    ):
        return None
    return amount


def json_body(request):
    """Return the request's JSON object, or None if it is missing or not an object."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None
