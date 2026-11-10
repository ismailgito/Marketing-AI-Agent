import re

from skills.time_skills import get_current_time
from tests.conftest import call


async def test_time_is_ist_and_formatted():
    out = await call(get_current_time)
    assert re.fullmatch(r"\w+, \d{2} \w+ \d{4}, \d{2}:\d{2} [AP]M IST", out), out


def test_tzdata_is_installed():
    # Windows has no system tz database; this is the regression guard for the old ZoneInfo crash.
    from zoneinfo import ZoneInfo

    assert ZoneInfo("Asia/Kolkata")
