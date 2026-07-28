# Reply Inbox setup

Set these Render environment variables:

- `INBOX_EMAIL` — mailbox address
- `INBOX_APP_PASSWORD` — Gmail app password or IMAP password
- `INBOX_IMAP_HOST` — defaults to `imap.gmail.com`
- `INBOX_IMAP_PORT` — defaults to `993`
- `INBOX_FOLDER` — defaults to `INBOX`

For Gmail, enable 2-Step Verification and create an app password. BrokerBeacon reads only unread messages when Sync mailbox is pressed.
