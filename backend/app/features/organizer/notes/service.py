from app.shared.storage import StorageProvider
from app.features.organizer.notes.tables import Note  # noqa: F401 — ensures Note is registered with SQLAlchemy mapper

class NoteService:
    
    def __init__(self, provider: StorageProvider) -> None:
        self._provider = provider