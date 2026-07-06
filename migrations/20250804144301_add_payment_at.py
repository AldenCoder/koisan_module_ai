from beanie import iterative_migration

from app.models.shop_order import ShopOrder


class Forward:
    @iterative_migration()
    async def add_payment_at(
        self, input_document: ShopOrder, output_document: ShopOrder
    ):
        if input_document.created_at:
            output_document.payment_at = int(input_document.created_at.timestamp())


class Backward:
    @iterative_migration()
    async def remove_payment_at(
        self, input_document: ShopOrder, output_document: ShopOrder
    ):
        output_document.payment_at = None
