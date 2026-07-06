from enum import Enum


class DiscountType(str, Enum):
    VALUE = "value"
    PERCENT = "percent"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    UNPAID = "unpaid"


class PaymentTargetType(str, Enum):
    shop_order = "shop_order"
    goods_receipt = "goods_receipt"
    posx = "posx"
    plan = "plan"


class OrderType(str, Enum):
    RETAIL = "retail"
    FANDB = "f_and_b"