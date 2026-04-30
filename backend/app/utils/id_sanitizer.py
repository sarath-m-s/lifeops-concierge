import re
from typing import Any

_ID_KEY_PATTERN = re.compile(
    r"^(restaurant_id|item_id|slot_id|order_id|cart_id|booking_id|address_id|"
    r"product_id|session_id|user_id|.*_id)$",
    re.IGNORECASE,
)


def strip_ids(data: Any, _in_display_context: bool = False, _in_params: bool = False) -> Any:
    """Remove internal ID fields from user-facing display contexts.

    IDs are preserved inside any `params` dict (backend needs them for mutations)
    but stripped from display fields: titles, subtitles, spoken_response, details.
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # Always preserve params dicts intact — backend needs IDs there
            if key == "params" and isinstance(value, dict):
                result[key] = value
            # Recurse into action/pending_action but preserve their params
            elif key in ("action", "pending_action") and isinstance(value, dict):
                result[key] = strip_ids(value, _in_display_context=_in_display_context, _in_params=False)
            # ui_payload and items enter display context
            elif key in ("ui_payload", "items"):
                result[key] = strip_ids(value, _in_display_context=True, _in_params=False)
            # Drop ID keys in display context (but NOT in params, handled above)
            elif _in_display_context and not _in_params and _ID_KEY_PATTERN.match(str(key)):
                pass  # omit from user-facing payload
            else:
                result[key] = strip_ids(value, _in_display_context=_in_display_context, _in_params=_in_params)
        return result
    elif isinstance(data, list):
        return [strip_ids(item, _in_display_context=_in_display_context, _in_params=_in_params) for item in data]
    return data
