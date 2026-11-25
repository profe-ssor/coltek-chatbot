"""A scripted fake model for offline tests: the real Runner, guardrails, tools and sessions run,
but no request ever reaches OpenAI.

Implements agents.models.interface.Model (openai-agents 0.25.0):
  get_response(...)    -> ModelResponse
  stream_response(...) -> async iterator of Responses stream events (text deltas + response.completed)

Each model call takes the next step from the script. A step is a list of outputs:
  say("Hello")                          a text reply
  call("check_course_intake", slug=…)   a function tool call
  handoff_to(academy_agent)             a handoff (calls the transfer_to_… tool)
"""
import asyncio
import itertools
import json

from agents import Usage
from agents.handoffs import Handoff
from agents.items import ModelResponse
from agents.models.interface import Model
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
)

_ids = itertools.count(1)


def say(text):
    return ("text", text)


def call(name, **arguments):
    return ("call", name, arguments)


def handoff_to(agent):
    return ("call", Handoff.default_tool_name(agent), {})


class FakeModel(Model):
    def __init__(self, *steps, delay: float = 0):
        self.steps = list(steps)
        self.delay = delay       # seconds to "think" before answering (for keep-alive tests)
        self.calls = []          # what each model call received (for assertions)

    def _next_output(self, input):
        self.calls.append(input)
        if not self.steps:
            raise AssertionError("FakeModel: no more scripted steps")
        output = []
        for part in self.steps.pop(0):
            if part[0] == "text":
                output.append(ResponseOutputMessage(
                    id=f"msg_fake_{next(_ids)}", type="message", role="assistant", status="completed",
                    content=[ResponseOutputText(type="output_text", text=part[1], annotations=[])],
                ))
            else:
                n = next(_ids)
                output.append(ResponseFunctionToolCall(
                    id=f"fc_fake_{n}", call_id=f"call_fake_{n}", type="function_call",
                    name=part[1], arguments=json.dumps(part[2]), status="completed",
                ))
        return output

    @staticmethod
    def _response(output):
        return Response(id=f"resp_fake_{next(_ids)}", created_at=0, model="fake-model", object="response",
                        output=output, parallel_tool_calls=False, tool_choice="auto", tools=[])

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs,
                           tracing, *, previous_response_id=None, conversation_id=None, prompt=None):
        await asyncio.sleep(self.delay)
        return ModelResponse(output=self._next_output(input), usage=Usage(), response_id=None)

    async def stream_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs,
                              tracing, *, previous_response_id=None, conversation_id=None, prompt=None):
        await asyncio.sleep(self.delay)
        output = self._next_output(input)
        sequence = 0
        for index, item in enumerate(output):
            if isinstance(item, ResponseOutputMessage):
                text = item.content[0].text
                for chunk in [text[: len(text) // 2], text[len(text) // 2:]]:   # two deltas per reply
                    if chunk:
                        sequence += 1
                        yield ResponseTextDeltaEvent(type="response.output_text.delta", item_id=item.id,
                                                     output_index=index, content_index=0, delta=chunk,
                                                     logprobs=[], sequence_number=sequence)
        sequence += 1
        yield ResponseCompletedEvent(type="response.completed", response=self._response(output),
                                     sequence_number=sequence)
