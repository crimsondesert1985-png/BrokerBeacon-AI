# Priority Auto-Dialer

Open **Priority Auto-Dialer** under **More tools** in the production workspace. AEs can run sessions. Managers and owners can also adjust scoring and record written voicemail consent. Rankings use workspace contact and sales history plus LO-level NonQM production imported through Production Intelligence.

## Voice setup

The contact list works with live dialing disabled. Set these on the Flask service to enable outbound dialing.

| Setting | Value |
|---|---|
| `DIALER_ENABLED` | `true` after testing provider setup |
| `DIALER_PUBLIC_URL` | Public HTTPS origin with no path or trailing slash |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | Voice-enabled Twilio account and outbound caller ID |
| `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET` | Server credentials for short-lived Voice SDK tokens |
| `TWILIO_DIALER_APP_SID` | TwiML App configured to POST to `<DIALER_PUBLIC_URL>/dialer/voice/agent` |
| `SECRET_KEY` | Existing stable Flask secret shared by service workers |

Use a browser headset. In one-click mode, arm the recording while Twilio is dialing or classifying the answer. Playback starts on a confirmed voicemail beep when the exact destination has documented prerecorded-message consent. Before recording a clip, use the wording and opt-out instructions approved by your organization. The only stored audio is the AE’s voicemail clip. Live conversations are not recorded.

Start with controlled numbers for human pickup, voicemail, and no answer. Check that a terminal call opens outcome logging and that saving advances without redialing the prior contact. If a provider timeout leaves an attempt unconfirmed, check Twilio’s call log before clearing it from the dialer.

## Development

The production React bundle is included so BrokerBeacon’s existing Python-only build can serve the screen. Rebuild it after editing the React source.

```sh
npm --prefix dialer-ui ci
npm --prefix dialer-ui run build
python -m unittest -v test_priority_dialer
```
