import os
from pathlib import Path
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    inference,
    room_io,
)
from livekit.plugins import ai_coustics

# Import your newly created skills and MCP tools
from skills.time_skills import get_current_time
from skills.notes_skills import save_note, list_notes
from skills.web_skills import get_webpage_title
from agent_mcp.toolsets import get_livekit_docs_toolset

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env.local")

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
            You are Jarvis, a helpful, friendly, and concise voice assistant.

            You have local skills and external MCP tools available to you.
            - Use get_current_time for questions about the current date or time.
            - Use save_note and list_notes for handling personal notes.
            - Use get_webpage_title if given a public website link.
            - Use livekit_docs to lookup technical information about LiveKit setup.

            Speak naturally and conversationally.
            Keep responses short unless explicit depth is requested.
            Do not speak with markdown syntax, asterisks, or emojis.
            """,
            tools=[
                get_current_time,
                save_note,
                list_notes,
                get_webpage_title,
                get_livekit_docs_toolset(), # MCP toolset injected alongside local skills
            ],
        )

server = AgentServer()

@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: agents.JobContext):
    await ctx.connect()

    session = AgentSession(
        llm=inference.RealtimeModel(
            model="google/gemini-3.8-live",
            voice="Puck",
        ),
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                )
            ),
        ),
    )

    await session.generate_reply(
        instructions="Briefly greet the user as Jarvis and say you are ready to test tools."
    )

if __name__ == "__main__":
    agents.cli.run_app(server)
