# HashMargin Pro staging preview

This repository contains a **local pilot** API (bridge.py) and a **separate public preview** (staging.py).

To create a preview on Render, choose New > Blueprint, connect this repository, and select the branch containing render.yaml. Confirm the service is **hashmargin-preview** and starts with `python staging.py`. Review any plan costs before approving.

The preview exposes only `/` and `/healthz`. It does not start bridge.py, expose miner telemetry, store customer records, accept payments, or connect to mining equipment.

Do **not** switch the public service to `python bridge.py` until authentication, tenant isolation, login abuse protections, secure persistent storage, and billing webhook verification have been reviewed and tested.

This setup is not a production subscription service.
