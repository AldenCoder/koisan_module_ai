from beanie import iterative_migration

from app.models.conversations import Conversation, ConversationStatus


class Forward:
    @iterative_migration()
    async def add_status_and_summaries(
        self, input_document: Conversation, output_document: Conversation
    ):
        current_status = getattr(input_document, "status", None)
        if current_status:
            output_document.status = current_status
        else:
            output_document.status = ConversationStatus.NEW

        current_summaries = getattr(input_document, "summaries", None)
        if isinstance(current_summaries, list):
            output_document.summaries = [str(item) for item in current_summaries if str(item).strip()]
        else:
            output_document.summaries = None


class Backward:
    @iterative_migration()
    async def remove_status_and_summaries(
        self, input_document: Conversation, output_document: Conversation
    ):
        del input_document
        output_document.status = ConversationStatus.NEW
        output_document.summaries = None
