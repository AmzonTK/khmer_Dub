from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TranscriptSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    original: str = Field(min_length=0, max_length=5000)
    khmer: str = Field(min_length=1, max_length=5000)
    speed: float = Field(default=1.0, ge=1.0, le=1.35)

    @field_validator("original", "khmer")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return " ".join(value.replace("\x00", "").split()).strip()

    @field_validator("start", "end", "speed")
    @classmethod
    def round_numbers(cls, value: float) -> float:
        return round(float(value), 3)

    @model_validator(mode="after")
    def validate_window(self) -> "TranscriptSegment":
        if self.end <= self.start:
            raise ValueError("Segment end must be greater than start.")
        if not self.khmer:
            raise ValueError("Khmer translation cannot be empty.")
        return self


class RenderRequest(BaseModel):
    segments: list[TranscriptSegment] = Field(min_length=1, max_length=1000)
    voice: Literal["km-KH-SreymomNeural", "km-KH-PisethNeural"]
    burn_subtitles: bool = True
    voice_clone: bool | None = None

    @model_validator(mode="after")
    def validate_order(self) -> "RenderRequest":
        previous_start = -1.0
        previous_end = -1.0
        for index, segment in enumerate(self.segments, start=1):
            if segment.start < previous_start:
                raise ValueError("Segments must be ordered by start time.")
            if index > 1 and segment.start < previous_end - 0.01:
                raise ValueError(
                    f"Segment {index} starts before the previous segment ends. "
                    "Timed dubbing segments cannot overlap."
                )
            previous_start = segment.start
            previous_end = segment.end
        return self
