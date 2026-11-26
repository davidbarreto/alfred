"""What the photo picker shows: one Commons photo to choose as a city's or country's cover."""
from pydantic import BaseModel


class CoverCandidateRead(BaseModel):
    # "File:<name>": sent back as `commons_file` to set it as the cover.
    title: str
    # Wikimedia's 400 px thumbnail, shown in the picker only (the cover itself is downloaded and kept).
    thumb_url: str
    width: int
    height: int
    credit: str
    page_url: str

    model_config = {"from_attributes": True}
