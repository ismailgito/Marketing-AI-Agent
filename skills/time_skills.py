import datetime
from zoneinfo import ZoneInfo
from livekit.agents import function_tool # type: ignore 

@function_tool
async def get_current_time() -> str:
    """Get the current date and time in India Standard Time (IST)."""
    now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    return now.strftime("%A, %d %B %Y, %I:%M %p %Z")
