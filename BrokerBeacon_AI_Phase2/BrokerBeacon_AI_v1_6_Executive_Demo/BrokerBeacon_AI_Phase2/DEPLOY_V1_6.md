# BrokerBeacon AI v1.6 deployment

1. Replace the contents of the `BrokerBeacon_AI_Phase2` folder in GitHub with this version.
2. Commit the changes to the `main` branch.
3. Render should redeploy automatically. Otherwise choose **Manual Deploy > Deploy latest commit**.
4. Full app: `/`
5. Full-feature read-only executive demo: `/demo`

Render settings remain:
- Root Directory: `BrokerBeacon_AI_Phase2`
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`
