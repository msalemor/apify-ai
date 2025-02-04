import uuid
from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


class CompletionRequest(BaseModel):
    messages: list[Message]
    temperature: float = 0.1
    max_new_tokens: int = 500


class Choice(BaseModel):
    text: str
    index: int


class CompletionResponse(BaseModel):
    id: str = str(uuid.uuid4())
    choices: list[Choice]
