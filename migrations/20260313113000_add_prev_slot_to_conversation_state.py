from beanie import iterative_migration

from app.models.conversation_states import ConversationState


class Forward:
    @iterative_migration()
    async def add_prev_slot(
        self, input_document: ConversationState, output_document: ConversationState
    ):
        output_document.prev_slot = getattr(input_document, "prev_slot", None)


class Backward:
    @iterative_migration()
    async def remove_prev_slot(
        self, input_document: ConversationState, output_document: ConversationState
    ):
        output_document.prev_slot = None
