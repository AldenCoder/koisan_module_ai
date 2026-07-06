from typing import List

from app.api.schemas.shop_order_items import ShopOrderItemCreate
from app.api.utils.enums import DiscountType


def calculate_total_value(items: List[ShopOrderItemCreate]) -> float:
    total = 0
    for item in items:
        item_total = item.price * item.quantity

        if item.discount_type == DiscountType.PERCENT:
            discount_amount = item_total * item.discount / 100
        else:
            discount_amount = item.discount

        final_item_total = max(item_total - discount_amount, 0)
        total += final_item_total

    return total