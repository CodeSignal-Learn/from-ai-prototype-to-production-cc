from dataclasses import dataclass, field
from typing import Protocol


class LLMError(Exception):
    """Base class for anything that goes wrong talking to a model."""


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, completion: Completion) -> None:
        self.input_tokens += completion.input_tokens
        self.output_tokens += completion.output_tokens
        self.calls += 1


class LLMClient(Protocol):
    usage: UsageTotals

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        """Send one system prompt and one user message; return the model's text and usage."""
        ...


@dataclass
class ScriptedClient:
    """Returns prepared answers in order. For tests; raises when the script runs out."""
    answers: list = field(default_factory=list)
    model: str = "scripted"
    usage: UsageTotals = field(default_factory=UsageTotals)
    calls: list = field(default_factory=list)

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        if not self.answers:
            raise LLMError("scripted client has no answer left")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        completion = Completion(text=answer, input_tokens=len(user) // 4, output_tokens=len(answer) // 4, model=self.model)
        self.usage.add(completion)
        return completion
