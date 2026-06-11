from functools import lru_cache
from typing import Annotated
from fastapi import Depends
from app.config import get_settings
from app.integrations.notion.client import NotionClient
from app.integrations.notion.provider import NotionProvider
from app.features.organizer.tasks.service import TaskService
from app.features.organizer.notes.service import NoteService
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session

@lru_cache
def get_notion_client() -> NotionClient:
    s = get_settings()
    return NotionClient(api_key=s.notion_api_key, base_url=s.notion_base_url, api_version=s.notion_api_version)

@lru_cache
def get_task_provider() -> NotionProvider:
    return NotionProvider(get_notion_client(), get_settings().notion_tasks_database_id)

@lru_cache
def get_note_provider() -> NotionProvider:
    return NotionProvider(get_notion_client(), get_settings().notion_notes_database_id)

def get_task_service(session: AsyncSession = Depends(get_session)) -> TaskService:
    return TaskService(get_task_provider(), session)

def get_note_service(session: AsyncSession = Depends(get_session)) -> NoteService:
    return NoteService(get_note_provider(), session)

# Dependencies shortcuts
# DB
DbSessionDep = Annotated[AsyncSession, Depends(get_session)]

# Services
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
NoteServiceDep = Annotated[NoteService, Depends(get_note_service)]