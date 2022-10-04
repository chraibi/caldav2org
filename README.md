# About

Retrieve meetings from CalDav and write an org-file, that can be consumed with
org-calendar.

## Requierements

Depends on [python-caldav](https://github.com/python-caldav/)

```bash
python install -r requierements.txt
```

## User credentials

First, create a file called `config.cfg` in the same directory as the script
with the following content:

```bash
[calendar]
username = your_username
password = your_password
```
