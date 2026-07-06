from datetime import datetime, timezone

from beanie import iterative_migration

from app.models.shop_order import ShopOrder


class Forward:
    @iterative_migration()
    async def convert_payment_at_to_int(
        self, input_document: ShopOrder, output_document: ShopOrder
    ):
        if isinstance(input_document.payment_at, datetime):
            output_document.payment_at = int(input_document.payment_at.timestamp())


class Backward:
    @iterative_migration()
    async def revert_payment_at_to_datetime(
        self, input_document: ShopOrder, output_document: ShopOrder
    ):
        if isinstance(input_document.payment_at, int):
            output_document.payment_at = datetime.fromtimestamp(
                input_document.payment_at, tz=timezone.utc
            )
