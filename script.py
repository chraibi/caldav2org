#!/usr/bin/env python3

import configparser
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
import logging
import caldav
from typing import TextIO
import os
from dataclasses import dataclass, field
import pytz

logging.basicConfig(format="%(levelname)s - %(message)s", level=logging.INFO)
dirname = os.path.dirname(__file__)
config_file = os.path.join(dirname, "config.cfg")


@dataclass
class Meeting:
    """Definition of a Meeting."""

    start: str
    org_start: str = field(init=False)  # todo initialise this using start
    summary: str
    calendar_name: str

    def __post_init__(self):
        self.org_start = org_datetime(self.start, tz=pytz.timezone('Europe/Berlin'))


class My(Enum):
    """How to filter meetings, short names for calendars and days to fetch"""

    # Retrieve meetings with these keywords in title
    meetings: list = [
        "MC",
        "Mohcine",
        "AL Runde",
        "PRO Runde",
        "Division Meeting Modeling",
        "JuPedSim-Team",
        "Journal Club",
        "PhD workshop",
    ]
    # Use shorter names in org-file
    calendars: dict = {
        "IAS-7 (Arne Graf)": "Institute",
        "IAS-7 PED simulation (Arne Graf)": "Division.",
    }
    # How many days in the future
    days: int = 14


def get_username_password() -> (str, str):
    """Return username and password"""

    confParser = configparser.ConfigParser()
    confParser.read(config_file)
    try:
        username = confParser["calendar"]["username"]
        password = confParser["calendar"]["password"]
    except Exception as e:
        logging.critical(
            f"""Can't parse the config file.
            Error: {e}"""
        )
        sys.exit()

    return username, password


def org_datetime(s: str, tz=None, Format: str = "<%Y-%m-%d %a %H:%M>") -> str:
    """Convert String to date"""

    dt = datetime.strptime(s, "%Y%m%dT%H%M%S%fZ")
    return dt.astimezone(tz).strftime(Format)


def get_principle() -> caldav.objects.Principal:
    """Initialize principle with user, password and b2drop-url"""

    logging.info("Init principle ...")
    username, password = get_username_password()
    caldav_url = "https://b2drop.eudat.eu/remote.php/dav/calendars/" + username

    client = caldav.DAVClient(url=caldav_url, username=username, password=password)
    logging.info("Done!")
    return client.principal()


def fetch_calendar_meetings(calendar, start_time: datetime, end_time: datetime) -> list:
    """Fetch all events from calendar in time interval"""

    logging.info(f"Get events from {start_time} to {end_time}")
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
        events_fetched = []

    return events_fetched


def add_meeting(meetings, meeting: Meeting) -> None:
    """Add meeting if I am supposed to participate in it"""

    for m in My.meetings.value:
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

    return start


def get_summary(event: caldav.objects.Event) -> str:
    """retrieve title of the meeting"""

    summary = event.data.split("SUMMARY:")[-1].split("\n")[0].strip()
    return summary


def get_my_meetings(events_fetched: list) -> defaultdict(list):
    """return relevant meetings (cal_name, org_start, summary)

    :param events_fetched:
    :type events_fetched: list) -> defaultdict(list)
    :returns:

    """
    meetings = defaultdict(list)
    for event in events_fetched:
        logging.debug(f"{event.data}\n---------")
        calendar_name = My.calendars.value[event.parent.name]
        start = get_start(event)
        summary = get_summary(event)
        meeting = Meeting(start=start, summary=summary, calendar_name=calendar_name)
        add_meeting(meetings, meeting)

    return meetings


def dump_in_file(meetings: defaultdict(list), org_file: TextIO) -> None:
    """Format meetings in an org-file and write in org_file"""

    logging.info("Dump meetings in cal.org")
    for key in sorted(meetings.keys()):
        for meeting in meetings[key]:
            title = meeting.summary.replace("\\", " ")
            org_file.write(f"* {meeting.calendar_name}\n")
            org_file.write(f"** CAL {meeting.org_start}, {title}\n")
            org_file.write(f"SCHEDULED: {meeting.org_start}\n")


def main(my_principal: caldav.objects.Principal, org_file: TextIO) -> None:
    """Init calender, fetch meetings, filter my meetings, dump in org-file"""

    events_fetched = []
    today = datetime.now()
    end = today + timedelta(days=My.days.value)
    for calendar_name in My.calendars.value:
        logging.info(f"process calender <{calendar_name}>")
        calendar = my_principal.calendar(calendar_name)
        events_fetched += fetch_calendar_meetings(calendar, today, end)

    meetings = get_my_meetings(events_fetched)
    logging.info(f"Got {len(meetings)} from {len(events_fetched)} events.")
    dump_in_file(meetings, org_file)


if __name__ == "__main__":
    my_principal = get_principle()
    with open("cal.org", "w") as org_file:
        logging.info("Start")
        main(my_principal, org_file)
