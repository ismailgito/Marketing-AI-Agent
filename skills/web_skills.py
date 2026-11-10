import aiohttp # type: ignore 
from livekit.agents import function_tool, utils # type: ignore 
from livekit.agents.llm import ToolError # type: ignore 

@function_tool
async def get_webpage_title(url: str) -> str:
    """Fetch the title tag element of a public webpage URL.

    Args:
        url: The complete HTTP/HTTPS target webpage string to access.
    """
    # Uses LiveKit recommended managed client session tracking context
    session = utils.http_context.http_session()

    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=12)
        ) as response:
            if response.status != 200:
                raise ToolError(f"Target site returned status code {response.status}")

            text = await response.text()
            start = text.find("<title>")
            end = text.find("</title>")

            if start == -1 or end == -1:
                return "The web resource layout missing plain title descriptors."

            return text[start + 7 : end].strip()

    except Exception as error:
        raise ToolError(f"Network call execution failure during crawl process: {error}")
