"""Turn-level tests: does the real model pick the right tool and speak sensibly?

These call an LLM through LiveKit Inference (needs LIVEKIT_API_KEY / LIVEKIT_API_SECRET in
.env.local), so they are skipped unless you opt in:

    RUN_LLM_TESTS=1 uv run pytest tests/test_agent_turns.py -s

Tools that touch disk or the network are mocked, so only tool *selection* and the spoken
reply are under test. The docs MCP toolset is not attached (Assistant() default), so
no MCP connection is opened.
"""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from livekit.agents import AgentSession, inference, mock_tools

from agent import Assistant

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(os.environ.get("RUN_LLM_TESTS") != "1", reason="set RUN_LLM_TESTS=1 to run"),
]

TEST_MODEL = "google/gemini-3-flash"


@pytest.fixture
async def llm():
    async with inference.LLM(model=TEST_MODEL) as instance:
        yield instance


async def _session(llm):
    session = AgentSession(llm=llm)
    await session.start(Assistant())
    return session


async def test_time_question_calls_time_tool(llm):
    async with await _session(llm) as session:
        with mock_tools(Assistant, {"get_current_time": lambda: "Tuesday, 10 November 2026, 06:11 PM IST"}):
            result = await session.run(user_input="What time is it right now?")

        result.expect.next_event().is_function_call(name="get_current_time")
        result.expect.next_event().is_function_call_output()
        await result.expect.next_event().is_message(role="assistant").judge(
            llm, intent="Tells the user it is around 6:11 PM on Tuesday 10 November 2026, India time."
        )
        result.expect.no_more_events()


async def test_save_note_is_called_with_the_content(llm):
    async with await _session(llm) as session:
        with mock_tools(Assistant, {"save_note": lambda text: f"saved: {text}"}):
            result = await session.run(user_input="Please note down that I need to buy milk tomorrow.")

        call = result.expect.next_event(type="function_call")
        assert call.event().item.name == "save_note"
        assert "milk" in call.event().item.arguments.lower()


async def test_private_url_is_refused_not_fetched(llm):
    """Uses the REAL web tool: an internal address must come back as a refusal, spoken plainly."""
    async with await _session(llm) as session:
        result = await session.run(
            user_input="What's the title of http://169.254.169.254/latest/meta-data/ ?"
        )
        output = result.expect.contains_function_call_output()
        assert output.event().item.is_error
        await result.expect[-1].is_message(role="assistant").judge(
            llm, intent="Explains it can't open that address because it is a private or internal network address."
        )


async def test_web_tool_failure_is_explained(llm):
    async with await _session(llm) as session:
        with mock_tools(
            Assistant, {"get_webpage_title": lambda: RuntimeError("The site took too long to respond.")}
        ):
            result = await session.run(user_input="What's the title of https://example.com ?")

        await result.expect.contains_message(role="assistant").judge(
            llm, intent="Tells the user it could not get the page title; does not invent a title."
        )


async def test_reply_has_no_markdown(llm):
    async with await _session(llm) as session:
        result = await session.run(user_input="Give me three tips for sleeping better.")
        text = result.expect.next_event().is_message(role="assistant").event().item.text_content or ""
        assert "*" not in text and "#" not in text and "`" not in text
