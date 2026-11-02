# Shopping (products, list entries)

## Products and entries

**Products** (`organizer.shopping_products`, `features/organizer/shopping_products/`) are the single row per thing bought: case-insensitive unique `name` among live rows, `category_id`, free-text `default_unit` and `default_quantity`.

**List entries** (`organizer.shopping_items`) point at a product through `product_id` (RESTRICT); `name` and `category_id` live only on the product. The ORM exposes them as read-only properties of `ShoppingItem` (joined product), so `ShoppingItemRead` still returns `name`/`category_id`, and changing an entry's name or category renames/recategorises its **product**.

## One pending entry per product

Enforced by the partial unique index `uq_shopping_items_pending_product` and checked first in `ShoppingService.create_item`.

- Adding a pending product is **rejected** with 409 (`ShoppingItemAlreadyPendingError`), never summed.
- Adding by name finds-or-creates the product and fills `unit`/`quantity` from its defaults when omitted.
- Wishlist promote and recurrence accept go through the same `create_item`.

Domain conflicts (`app/features/organizer/shopping/errors.py`) become 409 through one handler in `app/main.py`; the command handler wraps them in `HTTPException(409)` so Telegram/MCP logs a warning, not an error.

## Deleting and merging products

- Deleting a product is soft, blocked while it has a pending entry, and clears `category_id` so the category can be deleted.
- Merging A into B repoints A's entries (history) to B and refuses if both are pending.

## Frequent chips

Most-bought products with no pending entry, excluded in SQL before the limit, default 5.

## Purchase frequency

`GET /organizer/shopping/insights/frequency`, portal `/shopping/insights` "How often you buy". Per product: the mean days between purchase *days* (entries ticked on the same local day count once; pure maths in `shopping/frequency.py`), last purchase, days since and expected next date. Hides products with fewer than `min_purchases` (default 2) purchase days. Intervals follow when items are ticked as bought, not when they ran out.

## Recurrence

`recurrence_items` still carry their own `name`/`category_id`; accepting one resolves the product by name (a `product_id` FK there is a possible follow-up).
