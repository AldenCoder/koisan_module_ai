from beanie import iterative_migration

from app.api.utils.text_utils import remove_accents
from app.models.product import Product


class Forward:
    @iterative_migration()
    async def add_name_unsigned(
        self, input_document: Product, output_document: Product
    ):
        if input_document.name:
            output_document.name_unsigned = remove_accents(input_document.name)


class Backward:
    @iterative_migration()
    async def remove_name_unsigned(
        self, input_document: Product, output_document: Product
    ):
        output_document.name_unsigned = None
