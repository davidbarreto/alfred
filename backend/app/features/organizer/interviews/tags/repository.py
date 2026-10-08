from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.tags.tables import (
    InterviewTag,
    interview_question_tag_links,
    interview_story_tag_links,
)


class InterviewTagRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_tag(self, tag_id: int) -> InterviewTag | None:
        return await self._session.get(InterviewTag, tag_id)

    async def get_tag_by_name(self, name: str) -> InterviewTag | None:
        stmt = select(InterviewTag).where(func.lower(InterviewTag.name) == name.lower())
        return await self._session.scalar(stmt)

    async def get_or_create_tags(self, names: list[str]) -> list[InterviewTag]:
        """Resolve names (case-insensitively) to tags, creating missing ones. Does not commit."""
        tags: list[InterviewTag] = []
        for name in names:
            tag = await self.get_tag_by_name(name)
            if tag is None:
                tag = InterviewTag(name=name)
                self._session.add(tag)
                await self._session.flush()
            tags.append(tag)
        return tags

    async def get_tags_with_usage(self) -> list[tuple[InterviewTag, int, int]]:
        story_counts = (
            select(interview_story_tag_links.c.tag_id, func.count().label("n"))
            .group_by(interview_story_tag_links.c.tag_id)
            .subquery()
        )
        question_counts = (
            select(interview_question_tag_links.c.tag_id, func.count().label("n"))
            .group_by(interview_question_tag_links.c.tag_id)
            .subquery()
        )
        stmt = (
            select(
                InterviewTag,
                func.coalesce(story_counts.c.n, 0),
                func.coalesce(question_counts.c.n, 0),
            )
            .outerjoin(story_counts, story_counts.c.tag_id == InterviewTag.id)
            .outerjoin(question_counts, question_counts.c.tag_id == InterviewTag.id)
            .order_by(func.lower(InterviewTag.name))
        )
        return [(tag, s, q) for tag, s, q in (await self._session.execute(stmt)).all()]

    async def rename_tag(self, tag_id: int, name: str) -> InterviewTag | None:
        tag = await self.get_tag(tag_id)
        if tag is None:
            return None
        tag.name = name
        await self._session.commit()
        return tag

    async def delete_tag(self, tag_id: int) -> bool:
        result = await self._session.execute(delete(InterviewTag).where(InterviewTag.id == tag_id))
        await self._session.commit()
        return result.rowcount > 0
