#!/usr/local/bin/python3

import configparser
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Optional

import caldav
import pytz

logging.basicConfig(format="%(levelname)s - %(message)s", level=logging.INFO)


@dataclass
class Config:
    """Config data (creditentials, files, ...)

    Attributes:
    result_file: the org-file with the meetings
    username: username
    password: password
    meetings: keywords in meetings' titles
    days: how many days in the future to retrieve meetings
    calendars: a map of calendar names and shorter names.
    """

    result_file: Path = field(init=False, repr=False)
    username: str = field(init=False, repr=False)
    password: str = field(init=False, repr=False)
    config_file: Path = field(
        init=True, default=Path(__file__).parent.absolute() / "config.cfg"
    )
    meetings: list[str] = field(
        init=False,
        default_factory=list,
    )
    calendars: dict[str, str] = field(init=False, default_factory=dict)
    # How many days in the future
    days: int = field(init=False, default=14)

    def set_default_variables(self) -> tuple[str, str, Path, list, list]:
        """init Config's username, password & result_file"""

        if not self.config_file.exists():
            logging.error(f"{self.config_file} does not exist")
            raise FileNotFoundError

        try:
            confParser = configparser.ConfigParser()
            confParser.read(self.config_file)
        except configparser.Error as error:
            logging.error(f"Could not parse config file {self.config_file}")
            sys.exit(f"{error}")

        username = confParser["calendar"]["username"]
        password = confParser["calendar"]["password"]
        result_file = Path(confParser["calendar"]["result_file"])
        myMeetings = confParser.get("my", "meetings").split(",\n")
        aliases = confParser.get("my", "alias").split(",\n")
        return (username, password, result_file, myMeetings, aliases)

    def touch_file(self, filepath: Path) -> None:
        """Touch result file. Delete if exists"""

        if filepath.exists():
            logging.info(f"file {filepath} exists. Delete")
            filepath.unlink()
            logging.info(f"check existance: {filepath.exists()}")

        logging.info(f"Touch : {filepath}")
        Path.touch(filepath)

    def __post_init__(self) -> None:
        (
            self.username,
            self.password,
            self.result_file,
            self.meetings,
            aliases,
        ) = self.set_default_variables()
        self.touch_file(self.result_file)
        for alias in aliases:
            alias_list = alias.split(":")
            key = alias_list[0].strip()
            value = alias_list[1].strip()
            self.calendars[key] = value


@dataclass
class Meeting:
    """Definition of a Meeting."""

    start: str
    org_start: str = field(init=False)
    summary: str
    calendar_name: str

    def __post_init__(self) -> None:
        # Should be Europe/Berlin!
        self.org_start = org_datetime(self.start, tz=pytz.timezone("Europe/Sofia"))


def org_datetime(
    start: str,
    tz: Optional[tzinfo] = None,
    org_format: str = "<%Y-%m-%d %a %H:%M>",
    date_format: str = "%Y%m%dT%H%M%S%fZ",
    diff_days: int = 0,
) -> str:
    """Convert String to date"""

    dt = datetime.strptime(start, date_format)
    if diff_days:
        # for some unknown reason, caldav returns  the last day of day-events PLUS 1
        # So we have to substruct 1 day to get the right day!
        dt = dt - timedelta(days=diff_days)

    return dt.astimezone(tz).strftime(org_format)


def get_principle(config: Config) -> caldav.objects.Principal:
    """Initialize principle with user, password and b2drop-url"""

    logging.info("Init principle ...")
    caldav_url = "https://b2drop.eudat.eu/remote.php/dav/calendars/" + config.username

    client = caldav.DAVClient(
        url=caldav_url, username=config.username, password=config.password
    )
    logging.info("Done!")
    return client.principal()


def fetch_calendar_meetings(
    calendar: caldav.Calendar, start_time: datetime, end_time: datetime
) -> list[caldav.Event]:
    """Fetch all events from calendar in time interval"""

    logging.info(f"Get events from {start_time} to {end_time}")
    events_fetched = []
    try:
        events_fetched = calendar.date_search(
            start=start_time,
            end=end_time,
            expand=True,
        )

    except Exception as e:
        logging.critical(
            f"""Calendar server does not support expanded search.
            Error: {e}"""
        )

    return events_fetched


def add_meeting(meetings: defaultdict[str, list[Meeting]], meeting: Meeting) -> None:
    """Add meeting if I am supposed to participate in it"""

    for m in config.meetings:
        if m in meeting.summary:
            logging.debug(
                f">> {meeting.summary} at {meeting.org_start} - {meeting.start}"
            )
            meetings[meeting.start].append(meeting)


def is_day_event(event: caldav.objects.Event) -> bool:
    """returns true if this event spands across a whole day or several days"""

    if "DTSTART;VALUE=DATE:" in event.data:
        return True

    return False


def get_meeting_day_span(event: caldav.objects.Event) -> tuple[str, str]:
    """For day events return starting day and end day of meeting"""

    start_day = event.data.split("DTSTART;VALUE=DATE:")[-1].split("\n")[0].strip()
    end_day = event.data.split("DTEND;VALUE=DATE:")[-1].split("\n")[0].strip()
    return (str(start_day), str(end_day))


def get_start(event: caldav.objects.Event) -> str:
    """retrieve start of the meeting"""
    logging.debug("get_start ---------------\n")
    start = ""
    if "DTSTART:" in event.data:
        temptative_start = event.data.split("DTSTART:")
        logging.debug(f"tempative {temptative_start}")
        if temptative_start:
            start = temptative_start[-1].split("\n")[0].strip()
        else:
            logging.error(f"Something is wrong with this meeting!\n{event.data}")

    elif is_day_event(event):
        start = event.data.split("DTSTART;VALUE=DATE:")[-1].split("\n")[0].strip()
        start += "T000000Z"

    logging.debug(f"get start return: {start}\n---------\n")
    return str(start)


def get_summary(event: caldav.objects.Event) -> str:
    """retrieve title of the meeting"""

    summary = event.data.split("SUMMARY:")[-1].split("\n")[0].strip()
    if is_day_event(event):
        start_day, end_day = get_meeting_day_span(event)
        summary += ". From: " + org_datetime(
            start_day, date_format="%Y%m%d", org_format="<%Y-%m-%d %a>"
        )
        summary += " To: " + org_datetime(
            end_day, date_format="%Y%m%d", org_format="<%Y-%m-%d %a>", diff_days=1
        )

    return str(summary)


def get_my_meetings(
    events_fetched: list[caldav.Event],
) -> defaultdict[str, list[Meeting]]:
    """return relevant meetings (cal_name, org_start, summary)"""

    meetings: defaultdict[str, list[Meeting]] = defaultdict(list[Meeting])
    for event in events_fetched:
        logging.info(f"{event.data}\n---------")
        cal_name = str(event.parent)
        calendar_name = config.calendars[cal_name]
        start = get_start(event)
        summary = get_summary(event)
        meeting = Meeting(start=start, summary=summary, calendar_name=calendar_name)
        add_meeting(meetings, meeting)

    return meetings


def dump_in_file(meetings: defaultdict[str, list[Meeting]]) -> None:
    """Format meetings in an org-file and write in org_file"""

    logging.info(f"Dump meetings in {config.result_file}")
    content = ""
    for key in sorted(meetings.keys()):
        for meeting in meetings[key]:
            title = meeting.summary.replace("\\", " ")
            content += f"* {meeting.calendar_name}\n"
            content += f"** CAL {meeting.org_start}, {title}\n"
            content += f"DEADLINE: {meeting.org_start}\n"

    config.result_file.write_text(f"{content}")


def main(my_principal: caldav.objects.Principal) -> None:
    """Init calender, fetch meetings, filter my meetings, dump in org-file"""

    events_fetched = []
    today = datetime.now()
    end = today + timedelta(days=config.days)
    for calendar_name in config.calendars:
        logging.info(f"process calender <{calendar_name}>")
        calendar = my_principal.calendar(calendar_name)
        events_fetched += fetch_calendar_meetings(calendar, today, end)

    meetings = get_my_meetings(events_fetched)
    logging.info(f"Got {len(meetings)} from {len(events_fetched)} events.")
    dump_in_file(meetings)


if __name__ == "__main__":
    config = Config()
    my_principal = get_principle(config)
    logging.info("Start")
    main(my_principal)
