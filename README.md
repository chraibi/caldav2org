# About

Retrieve meetings from CalDav and write an org-file, that can be consumed with
org-calendar.

<img width="586" alt="demo" src="https://user-images.githubusercontent.com/5772973/193898012-14693509-fcf5-4479-99c9-e25540525280.png">


## Requirements

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

