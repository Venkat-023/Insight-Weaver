from pydantic import BaseModel, Field


class DebateRequest(BaseModel):
    rounds: int = Field(default=2, ge=1, le=4)


class DebateTurn(BaseModel):
    agent: str
    round: int | str
    content: str


class DebateResult(BaseModel):
    transcript: list[DebateTurn]
    verdict: dict
    duration_seconds: float


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    temperature: float = Field(default=0.25, ge=0.0, le=1.0)
    max_tokens: int = Field(default=512, ge=1, le=1024)
    timeout_seconds: int = Field(default=180, ge=30, le=600)


class ChatResponse(BaseModel):
    response: str
    model: str
    duration_seconds: float
