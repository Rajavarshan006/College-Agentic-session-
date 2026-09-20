import os
import inspect
import json
from dataclasses import dataclass, field
from typing import Any


class AgentError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class ModelTurn:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    raw: Any = None


class GeminiProvider:
    def __init__(self, model: str = "gemini-3.6-flash", api_key: str | None = None):
        from google import genai
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise AgentError("missing_api_key", "Set GEMINI_API_KEY before using Gemini.", False)
        self.client, self.model = genai.Client(api_key=key), model

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        from google.genai import errors, types
        converted = []
        for item in contents:
            if item["role"] == "user":
                converted.append(types.Content(role="user", parts=[types.Part.from_text(text=item["text"])]))
            elif item["role"] == "model":
                parts = ([types.Part.from_text(text=item["text"])] if item.get("text") else [])
                parts += [types.Part.from_function_call(name=c["name"], args=c["args"]) for c in item.get("tool_calls", [])]
                converted.append(types.Content(role="model", parts=parts))
            else:
                converted.append(types.Content(role="user", parts=[
                    types.Part.from_function_response(name=item["name"], response=item["result"])]))
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=converted,
                config=types.GenerateContentConfig(system_instruction=system, tools=tools, temperature=0,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
        except errors.APIError as exc:
            if exc.code == 429:
                raise AgentError("provider_rate_limited",
                                 "Gemini quota is exhausted. Wait and retry, or check billing and limits.",
                                 True) from exc
            if exc.code and exc.code >= 500:
                raise AgentError("provider_unavailable", "Gemini is temporarily unavailable.", True) from exc
            raise AgentError("provider_error", str(exc), False) from exc
        except Exception as exc:
            raise AgentError("provider_error", str(exc), False) from exc
        calls = [ToolCall(call.name, dict(call.args or {})) for call in (response.function_calls or [])]
        text = "".join(part.text for part in (response.candidates[0].content.parts if response.candidates else [])
                       if part.text and not getattr(part, "thought", False)) or None
        return ModelTurn(text=text, tool_calls=calls, raw=None)


class GroqProvider:
    """Groq's OpenAI-compatible tool-calling provider."""

    def __init__(self, model: str = "openai/gpt-oss-120b", api_key: str | None = None):
        try:
            from groq import Groq
        except ImportError as exc:
            raise AgentError("missing_dependency",
                             "Install the Groq SDK with: python -m pip install groq",
                             False) from exc

        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise AgentError("missing_api_key", "Set GROQ_API_KEY before using Groq.", False)
        self.client, self.model = Groq(api_key=key), model

    @staticmethod
    def _tools(functions: list) -> list[dict]:
        declarations = []
        for function in functions:
            properties = {}
            required = []
            for name, parameter in inspect.signature(function).parameters.items():
                annotation = parameter.annotation
                kind = "integer" if annotation is int else "string"
                properties[name] = {"type": kind}
                if parameter.default is inspect.Parameter.empty:
                    required.append(name)
            declarations.append({"type": "function", "function": {
                "name": function.__name__,
                "description": inspect.getdoc(function) or function.__name__,
                "parameters": {"type": "object", "properties": properties, "required": required},
            }})
        return declarations

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        messages = [{"role": "system", "content": system}]
        pending_call_ids: list[str] = []
        for item in contents:
            if item["role"] == "user":
                messages.append({"role": "user", "content": item["text"]})
            elif item["role"] == "model":
                assistant = {"role": "assistant", "content": item.get("text") or None}
                calls = item.get("tool_calls", [])
                if calls:
                    pending_call_ids = [f"call_{index}" for index, _ in enumerate(calls)]
                    assistant["tool_calls"] = [
                        {"id": f"call_{index}", "type": "function",
                         "function": {"name": call["name"], "arguments": json.dumps(call["args"])}}
                        for index, call in enumerate(calls)]
                messages.append(assistant)
            else:
                call_id = pending_call_ids.pop(0) if pending_call_ids else "call_0"
                messages.append({"role": "tool", "tool_call_id": call_id,
                                 "content": json.dumps(item["result"], default=str)})
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=self._tools(tools),
                tool_choice="auto", temperature=0)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status == 429:
                raise AgentError("provider_rate_limited",
                                 "Groq quota or rate limit reached. Wait and retry or check Groq limits.",
                                 True) from exc
            if status == 404:
                raise AgentError("provider_model_not_found",
                                 f"Groq model '{self.model}' was not found or is not enabled for this key.",
                                 False) from exc
            if status and status >= 500:
                raise AgentError("provider_unavailable", "Groq is temporarily unavailable.", True) from exc
            raise AgentError("provider_error", str(exc), False) from exc
        message = response.choices[0].message
        calls = []
        for call in (message.tool_calls or []):
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as exc:
                raise AgentError("provider_error", "Groq returned invalid tool arguments.", False) from exc
            calls.append(ToolCall(call.function.name, args))
        usage = response.usage
        return ModelTurn(text=message.content, tool_calls=calls,
                         tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
                         tokens_out=getattr(usage, "completion_tokens", 0) or 0)


class RoutedMock:
    model = "mock"
    def __init__(self, routes: dict[str, list[ModelTurn]], slow: float = 0.0):
        self.routes, self.slow, self.calls = routes, slow, []

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        import time
        self.calls.append(list(contents))
        last = max(i for i, item in enumerate(contents) if item["role"] == "user")
        request = contents[last]["text"]
        position = sum(item["role"] == "model" for item in contents[last:])
        if self.slow:
            time.sleep(self.slow)
        for phrase, turns in self.routes.items():
            if phrase.lower() in request.lower():
                return turns[position] if position < len(turns) else ModelTurn(text="(mock) done.")
        return ModelTurn(text="(mock) no scripted response.")


def _call(name, **args):
    return ModelTurn(text=None, tool_calls=[ToolCall(name, args)], tokens_in=100, tokens_out=10)


def demo_providers(slow: float = 0.0) -> dict:
    return {
        "supervisor": RoutedMock({
            "AI in Education": [_call("ask_catalogue", question="Is AI in Education available?"),
                _call("ask_desk", request="Register member for event 1 (AI in Education) and send a confirmation."),
                ModelTurn(text="(mock) You are registered for AI in Education and a confirmation is queued.")],
            "Robotics": [_call("ask_catalogue", question="Find Robotics Showcase"),
                _call("ask_desk", request="Register member for event 4 (Robotics Showcase)."),
                ModelTurn(text="(mock) Robotics Showcase is full, so no registration was made.")]}, slow),
        "catalogue": RoutedMock({
            "AI in Education": [_call("search_events", text="AI in Education"),
                ModelTurn(text="(mock) Event 1, AI in Education: 2 seats available.")],
            "Robotics": [_call("search_events", text="Robotics Showcase"),
                ModelTurn(text="(mock) Event 4, Robotics Showcase: 0 seats available.")]}, slow),
        "desk": RoutedMock({
            "Register member for event 1": [_call("check_can_register"),
                ModelTurn(text=None, tool_calls=[ToolCall("register_event", {"event_id": 1}),
                    ToolCall("notify_member", {"message": "Your registration for AI in Education is confirmed."})]),
                ModelTurn(text="(mock) Registered event 1 and sent the confirmation.")],
            "Register member for event 4": [_call("check_can_register"),
                _call("register_event", event_id=4),
                ModelTurn(text="(mock) The event is full; no registration was made.")]}, slow),
    }
