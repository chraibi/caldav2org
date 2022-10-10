#!/usr/local/bin/python3

import configparser
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import tzinfo, datetime, timedelta
from pathlib import Path
from typing import Optional
import caldav
import pytz

logging.basicConfig(format="%(levelname)s - %(message)s", level=logging.INFO)


@dataclass
class Config:
    """Config data (creditentials, files, ...)"""

    username: str = field(init=False, repr=False)
    password: str = field(init=False, repr=False)
    config_file: Path = field(
        init=True, default=Path(__file__).parent.absolute() / "config.cfg"
    )
    result_file: Path = field(
        init=True, default=Path("/Users/chraibi/Dropbox/Orgfiles/org-files/cal.org")
    )

    def set_username_password(self) -> tuple[str, str]:
        """init Config's username and password"""

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
        return (username, password)

    def touch_file(self, filepath: Path) -> None:
        """Touch result file. Delete if exists"""

        if filepath.exists():
            logging.info(f"file {filepath} exists. Delete")
            filepath.unlink()
            logging.info(f"check existance: {filepath.exists()}")

        logging.info(f"Touch : {filepath}")
        Path.touch(filepath)

    def __post_init__(self) -> None:
        self.touch_file(self.result_file)
        self.username, self.password = self.set_username_password()


@dataclass
class Meeting:
    """Definition of a Meeting."""

    start: str
    org_start: str = field(init=False)
    summary: str
    calendar_name: str

    def __post_init__(self) -> None:
        # Should be Europe/Berlin!
        self.org_start = org_datetime(self.start, tz=pytz.timezone("Europe/Samara"))


@dataclass(frozen=True)
class Constants:
    """How to filter meetings, short names for calendars and days to fetch"""

    # Retrieve meetings with these keywords in title
    meetings: list[str] = field(
        init=False,
        default_factory=list,
    )
    # Use shorter names in org-file
    calendars: dict[str, str] = field(init=False, default_factory=dict)
    # How many days in the future
    days: int = field(init=False, default=14)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "meetings",
            [
                "MC",
                "Mohcine",
                "AL Runde",
                "PRO Runde",
                "Division Meeting Modeling",
                "JuPedSim-Team",
                "Journal Club",
                "PhD workshop",
            ],
        )
        object.__setattr__(
            self,
            "calendars",
            {
                "IAS-7 (Arne Graf)": "Institute",
                "IAS-7 PED simulation (Arne Graf)": "Division.",
            },
        )


def org_datetime(
    start: str, tz: Optional[tzinfo] = None, Format: str = "<%Y-%m-%d %a %H:%M>"
) -> str:
    """Convert String to date"""

    dt = datetime.strptime(start, "%Y%m%dT%H%M%S%fZ")
    return dt.astimezone(tz).strftime(Format)


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

    for m in My.meetings:
        if m in meeting.summary:
            logging.debug(
                f">> {meeting.summary} at {meeting.org_start} - {meeting.start}"
            )
            meetings[meeting.start].append(meeting)


def get_start(event: caldav.objects.Event) -> str:
    """retrieve start of the meeting"""

    if "DTSTART:" in event.data:
        start = event.data.split("DTSTART:")[-1].split("\n")[0].strip()
    else:
        start = event.data.split("DTSTAMP:")[-1].split("\n")[0].strip()

    return str(start)


def get_summary(event: caldav.objects.Event) -> str:
    """retrieve title of the meeting"""

    summary = event.data.split("SUMMARY:")[-1].split("\n")[0].strip()
    return str(summary)


def get_my_meetings(
    events_fetched: list[caldav.Event],
) -> defaultdict[str, list[Meeting]]:
    """return relevant meetings (cal_name, org_start, summary)"""

    meetings: defaultdict[str, list[Meeting]] = defaultdict(list[Meeting])
    for event in events_fetched:
        logging.debug(f"{event.data}\n---------")
        cal_name = str(event.parent)
        calendar_name = My.calendars[cal_name]
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
            content += f"SCHEDULED: {meeting.org_start}\n"

    config.result_file.write_text(f"{content}")


def main(my_principal: caldav.objects.Principal) -> None:
    """Init calender, fetch meetings, filter my meetings, dump in org-file"""

    events_fetched = []
    today = datetime.now()
    end = today + timedelta(days=My.days)
    for calendar_name in My.calendars:
        logging.info(f"process calender <{calendar_name}>")
        calendar = my_principal.calendar(calendar_name)
        events_fetched += fetch_calendar_meetings(calendar, today, end)

    meetings = get_my_meetings(events_fetched)
    logging.info(f"Got {len(meetings)} from {len(events_fetched)} events.")
    dump_in_file(meetings)


if __name__ == "__main__":
    config = Config()
    My = Constants()
    my_principal = get_principle(config)
    logging.info("Start")
    main(my_principal)
