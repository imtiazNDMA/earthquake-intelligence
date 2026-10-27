---
title: eqMonitoring API
emoji: 🌍
colorFrom: red
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

Backend for eqMonitoring2: the FastAPI service plus the eq_arc exposure engine.
The frontend is hosted on Vercel and proxies API routes here.

Deployed with `scripts/deploy_hf_space.py` from the main repository — edits made
directly in this Space are overwritten on the next deploy.
