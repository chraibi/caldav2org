#!/usr/bin/env python3

from typing import List, Optional
import os
from datetime import datetime
import requests
from ics import Calendar, Event
from pytz import utc

from configparser import ConfigParser


def fetch_calendar_events(url: str) -> Optional[List[Event]]:
    """
    Fetch calendar events from a given ICS URL.

    Parameters:
        url (str): The URL of the ICS calendar file.

    Returns:
        Optional[List[Event]]: A list of Event objects if successful, otherwise None.
    """
    response = requests.get(url)
    if response.status_code != 200:
        return None
    calendar = Calendar(response.text)
    return [
        event
        for event in calendar.events
        if event.begin >= datetime.now().replace(tzinfo=utc)
    ]


def write_events_to_file(events: List[Event], filepath: str) -> None:
    """
    Write the list of calendar events to a file in Org mode format.

    Parameters:
        events (List[Event]): A list of Event objects to write to the file.
        filepath (str): The path of the file to write to.

    Returns:
        None
    """
    with open(filepath, "w") as my_file:
        for event in sorted(events, key=lambda x: x.begin):
            start_time_str = event.begin.strftime("%Y-%m-%d %H:%M")
            org_todo_string = (
                f"* TODO {event.name} {'(at ' + event.location + ')' if event.location else ''}\n"
                f"SCHEDULED: {start_time_str}\n:PROPERTIES:\n:END:\n"
            )
            my_file.write(org_todo_string)


def main(filepath: str, url: str) -> None:
    """
    Fetch calendar events from a URL and write them to a file.

    Returns:
        None
    """

    # Ensure the directory exists
    directory = os.path.dirname(filepath)
    if not os.path.exists(directory):
        print("directory does not exist")
        return

    try:
        events = fetch_calendar_events(url)
        if events is None:
            print("Failed to download the ICS file")
            return

        write_events_to_file(events, filepath)
        print(f"Succesfully updated {filepath}")

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    config = ConfigParser()
    config.read("config.cfg")
    result_file = config.get("calendar", "result_file")
    ics_file = config.get("calendar", "ics_file")
    main(result_file, ics_file)
