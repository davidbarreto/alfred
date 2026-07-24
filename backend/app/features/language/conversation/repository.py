from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.messages.tables import Message
from app.features.language.conversation.tables import ConversationThread, ConversationTurn


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_thread(
        self, track_id: int, chat_session_id: int, scenario: str, voice_reply: bool
    ) -> ConversationThread:
        thread = ConversationThread(
            track_id=track_id, chat_session_id=chat_session_id, scenario=scenario, voice_reply=voice_reply
        )
        self._session.add(thread)
        await self._session.commit()
        await self._session.refresh(thread)
        return thread

    async def get_thread(self, thread_id: int) -> ConversationThread | None:
        result = await self._session.execute(
            select(ConversationThread).where(ConversationThread.id == thread_id)
        )
        return result.scalars().first()

    async def end_thread(self, thread_id: int, tip: str | None) -> None:
        thread = await self.get_thread(thread_id)
        if thread is None:
            return
        thread.ended_at = datetime.now(tz=timezone.utc)
        thread.tip = tip
        await self._session.commit()

    async def create_turn(
        self,
        thread_id: int,
        message_id: int,
        is_audio: bool,
        audio_ref: str | None,
        tip: str | None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            thread_id=thread_id, message_id=message_id, is_audio=is_audio, audio_ref=audio_ref, tip=tip
        )
        self._session.add(turn)
        await self._session.commit()
        await self._session.refresh(turn)
        return turn

    async def get_turn(self, turn_id: int) -> ConversationTurn | None:
        result = await self._session.execute(select(ConversationTurn).where(ConversationTurn.id == turn_id))
        return result.scalars().first()

    async def get_turns_with_messages(self, thread_id: int) -> list[tuple[ConversationTurn, Message]]:
        result = await self._session.execute(
            select(ConversationTurn, Message)
            .join(Message, Message.id == ConversationTurn.message_id)
            .where(ConversationTurn.thread_id == thread_id)
            .order_by(ConversationTurn.created_at)
        )
        return list(result.all())
