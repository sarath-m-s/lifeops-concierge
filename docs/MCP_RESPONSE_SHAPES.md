# Swiggy MCP — live-verified response shapes

Captured 2026-09-09 by calling every read-only tool for real, through a live
authenticated session (via `backend/app/routers/debug.py`'s `/debug/tool`
allowlist, against the same `swiggy_mcp.py` client this app uses in
production — not `mcp-remote` directly). Mutating tools (`place_food_order`,
`checkout`, `book_table`, `delete_address`, `apply_food_coupon`/`apply_coupon`,
cart writes) were **not** executed — their shapes are documented from
`mcp.swiggy.com/builders/docs/reference/` only, per the reference docs already
cited in `CLAUDE.md`.

All example values below are placeholders. Real responses came back with the
tester's actual name, address, phone number, and order history — none of that
is reproduced here.

**Coverage caveat:** what came back depends on the test account's location
(Tiruchirappalli / Trichy) and order history. A different account/city may see
different fields populated (e.g. `swiggyMoney`, `agenticPaymentEligible`).
Treat field *names* as reliable, absence of a field in one account as not
proof it never appears.

## ⚠ Live discrepancies from the reference docs — read this first

These affect real behavior right now, independent of anything this app does:

1. **`get_restaurant_menu` (Food) does not return a flat list**, despite the
   reference doc saying "Browse a restaurant's complete menu as a flat,
   deduplicated list." The real shape is
   `{restaurant, categories: [{title, categoryId, items: [...], totalItems, hasMoreItems}], totalCategories, page, pageSize, hasMore}`
   — items are nested two levels down, one array per category.
   **This app's `components.py::_menu_items()` reads top-level `items`/
   `menuItems`/`data` only** — so `get_menu` (the agent's full-menu tool)
   currently renders empty for any real account. `search_menu` is unaffected;
   it does return a flat top-level `items` array.

2. **`search_restaurants_dineout` drops all structured fields once it finds a
   match.** A zero-result call returns the full documented shape
   (`restaurants: []`, `message`, `latitude`, `longitude`, `total`, `offset`).
   A call that finds ≥1 restaurant returns **only** `{"message": "..."}"` — a
   prose string listing restaurants by name, plus instructions to call a tool
   named `render_restaurants_dineout`, which does not appear anywhere in the
   Dineout tool reference and is not implemented by this app.
   **This app's `_restaurants()` reads a `restaurants` array that no longer
   exists on a successful search** — the Dineout search-and-book flow is
   currently broken against a real account whenever a search actually finds
   something.

3. **`get_available_slots` (Dineout) needs `latitude`/`longitude`**, which
   neither the reference doc nor this app's `live_mcp.get_available_slots`
   signature includes — omitting them 400s with "Valid latitude and longitude
   are required." Even with them supplied, the response is prose-only:
   `{"restaurantId", "date", "guestCount", "message": "Found N available slot(s)...", "latitude", "longitude"}`
   — no `slots` array. **`components.py::_slots()` expects a `slots` array
   that is never present**, so the booking-slot-picker flow renders empty
   too.

4. **`get_food_order_details` (Food) is prose-only**, not the structured
   `{orderId, order_time, items: [...], bill: {...}}` shape the doc describes
   — it returns `{"message": "Order <id> — <restaurant>\nDelivered | regular\n..."}`
   as one formatted string.

5. **Several tools have required params the reference index didn't mention:**
   - `fetch_food_coupons` (Food) needs `restaurantId` **and** `addressId`
     (the doc listed it as taking no params).
   - `get_food_orders` (Food) needs `addressId` (doc listed no params).
   - `list_coupons` (Instamart) needs `addressId`, and additionally returned
     `"Coupon tools are not enabled for your account yet"` on this test
     account — an account-level gate, not a missing-param error.
   - `track_order` (Instamart) needs `lat`/`lng` in addition to `orderId`
     (doc listed `orderId` as the only param).

6. **`get_order_details` (Instamart) is beta-gated** — this test account got
   `"Order details feature is currently available only for beta users."`
   The reference doc's own caveat ("not completely rolled out yet") is
   accurate; budget for this tool being unavailable on most accounts.

None of the above are bugs in Swiggy's server as such — they're the live
behavior differing from what the static reference docs describe, and (for
1–3) from what this app's parsing code assumes. Points 1–3 are real,
reproducible breakage in this app's own rendering path, not just a
documentation gap.

---

## Food

### `get_addresses` — `{}`
```json
{"addresses": [{"id": "<address_id>", "addressLine": "<full address>", "phoneNumber": "****1234", "addressCategory": "Home", "addressTag": "<label>"}]}
```

### `search_restaurants` — `{addressId, query}`
```json
{"restaurants": [{"id": "<restaurant_id>", "name": "...", "cuisines": ["..."], "avgRating": 4.3, "totalRatings": "...", "...": "..."}]}
```

### `get_restaurant_menu` — `{restaurantId, addressId}`
See discrepancy #1 above.
```json
{
  "restaurant": {"id", "name", "city", "areaName", "cuisines", "avgRating", "avgRatingString", "totalRatingsString", "costForTwoMessage", "isOpen", "deliveryTime", "slaString", "address", "imageUrl"},
  "categories": [{"title", "categoryId", "items": [{"id", "name", "price", "inStock", "isVeg", "isBestseller", "rating", "hasVariants", "hasAddons", "description", "imageUrl"}], "totalItems", "hasMoreItems"}],
  "totalCategories", "page", "pageSize", "hasMore"
}
```

### `search_menu` — `{restaurantId, query, addressId}`
Flat, unlike `get_restaurant_menu`:
```json
{"items": [{"name", "price", "menu_item_id", "inStock", "imageUrl", "...": "..."}]}
```

### `get_food_cart` — `{addressId}` (required — not optional, despite `live_mcp.py`'s pre-existing code calling it with none until this session's fix)
```json
{"cart_id": 1193251643, "result": "success", "restaurant": {...}, "items": [...], "item_count": 0, "pricing": {...}, "offers": {...}}
```

### `get_payment_options` — `{addressId}` optional
```json
{"platforms": {"mobile": {"groupName": "UPI", "methods": [{"id", "displayName", "kind", "iconUrl"}]}, "desktop": {...}}, "cod": {...}, "swiggyMoney": {...}, "allMethods": [...], "agenticPaymentEligible": false, "paymentAmount": null, "addressId": "...", "placeOrderToolName": "place_food_order"}
```

### `fetch_food_coupons` — `{restaurantId, addressId}` (both required — see discrepancy #5)
```json
{"status_message": "done successfully", "coupon_sections": [{"title": "Best coupon", "type": "COUPON_SECTION_TYPE_BEST_COUPONS", "coupons": [{"id", "applicable": true, "title": "...", "subtitle": "..."}]}], "summary": {...}}
```
Note: shape differs from the `{coupons: [...]}` this app's `components.py::_coupons()` expects (`_rows(payload, "coupons", "availableCoupons", "data")`) — coupons here live under `coupon_sections[].coupons`, not top-level `coupons`. Same class of issue as #1–3.

### `get_food_orders` — `{addressId}` (required — see discrepancy #5)
```json
{"orders": [{"orderId", "restaurantId", "restaurantName", "restaurantAreaName", "orderTotal", "orderStatus", "orderDeliveryStatus", "orderType", "orderedItems", "orderedTime", "isActiveOrder", "actions"}], "total": 12}
```

### `track_food_order` — `{orderId}`
On an old/delivered order: `{"orders": [], "statusMessage": "No tracking information found for order <id>"}` — live tracking data only exists for a currently-active order.

### `get_food_delivery_status` — `{orderId}`
Matches the reference doc:
```json
{"orderId", "deliveryBy": null, "serverNow": 1788953416325, "cancelled": false, "delivered": true, "statusText": "Delivered", "pollIntervalSec": 45}
```

### `get_food_order_details` — `{orderId}`
Prose-only — see discrepancy #4.

---

## Instamart

### `get_addresses` — `{}`
Same shape as Food's (shared address book).

### `search_products` — `{addressId, query}`
```json
{"nextOffset": "1", "products": [{"displayName", "brand", "inStock", "isAvail", "variations": [...], "productId", "parentProductId", "isPromoted", "badges"}], "similarProducts": [...]}
```

### `your_go_to_items` — `{addressId}`
Same product shape as `search_products`.

### `get_cart` — `{}`
```json
{"cartTotalAmount": "0", "items": [], "billBreakdown": {"lineItems": [], "toPay": {"label": "To Pay", "value": "0"}}, "cartAbsent": true}
```

### `get_payment_options` — `{}`
```json
{"allMethods": [], "agenticPaymentEligible": false, "paymentAmount": null, "placeOrderToolName": "checkout", "imWidgetV2Eligible": true}
```
`allMethods` was empty with nothing in cart — likely populates once a real cart exists.

### `list_coupons` — `{addressId}` (required — see discrepancy #5; also account-gated on this test account)

### `get_orders` — `{}`
```json
{"orders": [{"orderId", "status", "createdAt", "updatedAt", "estimatedDeliveryTime", "itemCount", "totalAmount", "deliveryAddress", "paymentMethod", "orderType", "isActive", "currentStatus", "historyStatus", "storeName", "items", "billDetails", "paymentStatus", "refundStatus"}], "hasMore": false}
```

### `track_order` — `{orderId, lat, lng}` (lat/lng required — see discrepancy #5)
```json
{"orderId", "orderTitle": "Instamart order", "orderSubtitle": "...", "status": {"statusMessage": "Order Delivered"}, "storeInfo": {"name", "address"}, "...": "..."}
```

### `get_order_details` — `{orderId}`
Beta-gated on this account — see discrepancy #6.

---

## Dineout

### `get_saved_locations` — `{}`
```json
{"locations": [{"index": 1, "id": "<location_id>", "addressLine": "...", "phoneNumber": "****1234", "addressCategory": "Home", "addressTag": "<label>"}], "resolution": "..."}
```

### `search_restaurants_dineout` — `{addressId, query}`
Zero results:
```json
{"restaurants": [], "message": "No restaurants found for \"<query>\" near this location. Suggest a different name, cuisine, area or vibe.", "latitude": ..., "longitude": ..., "total": 0, "offset": 0}
```
One or more results — see discrepancy #2:
```json
{"message": "Found 1 restaurant(s) matching \"<query>\", showing 1.\n1. <Name> — <cuisines> | 4.8★ | ₹400 for two | <area> (ID: <id>)\nSearch coordinates: latitude=..., longitude=... (use these for get_restaurant_details and downstream calls).\n\n... call render_restaurants_dineout ..."}
```

### `get_restaurant_details` — `{restaurantId, latitude, longitude}` (all required)
```json
{"restaurantId", "restaurant": {"id", "name", "cuisines", "locality", "area", "address", "...": "..."}, "menuImages": [...], "amenities": [...], "deals": [...]}
```

### `get_available_slots` — `{restaurantId, date, guestCount, latitude, longitude}` (lat/lng required — see discrepancy #3)
```json
{"restaurantId", "date", "guestCount", "message": "Found 336 available slot(s) for 2026-09-12", "latitude", "longitude"}
```

### `get_payment_options` — `{}`
```json
{"allMethods": [], "paymentAmount": null, "placeOrderToolName": "book_table"}
```

### `get_booking_status` — not exercised (no active booking on the test account to query).

---

## Mutating tools — not called, documented from reference docs only

Per the scope decision for this session: these were **not** executed against
the real account (would place a real order/booking or delete/create a real
address). Full param tables were already fetched into this conversation and
summarized in `CLAUDE.md`'s tool inventory section — re-fetch the specific
`.md` page under `mcp.swiggy.com/builders/docs/reference/{server}/{tool}.md`
if the exact response shape is needed later; this file only covers what was
actually observed live.
