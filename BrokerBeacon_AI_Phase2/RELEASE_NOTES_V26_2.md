# Version 26.2 — Owner-Gated Platform Admin

- Moves the Autopilot Control Tower and shared-index population tools out of the Prospects workflow.
- Adds a dedicated **Platform Admin** group in the left navigation.
- Shows that navigation group only to authenticated platform owners.
- Prevents direct client-side navigation to the admin view without platform-owner context.
- Keeps the existing server-side authorization boundary on all platform automation APIs.
- Stops customer sessions from loading disabled platform automation data during startup.
