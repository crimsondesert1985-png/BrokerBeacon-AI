# BrokerBeacon Boss Demo Deployment

## Local demo
Run the app and open `http://127.0.0.1:5000/demo`. The demo opens in read-only Boss Mode.

## Public link with Render
1. Create a private GitHub repository and upload the contents of this folder.
2. In Render, create a new Blueprint or Web Service from that repository.
3. Render will use `render.yaml` and start BrokerBeacon with Gunicorn.
4. After deployment, send your boss the URL ending in `/demo`.

Example: `https://your-brokerbeacon-name.onrender.com/demo`

## Important
The bundled SQLite database is ideal for a demonstration. Free hosting may reset local database changes after redeployment or service recreation. Use PostgreSQL before relying on the application as a permanent shared CRM.
