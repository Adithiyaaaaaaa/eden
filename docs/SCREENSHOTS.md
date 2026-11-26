# Screenshot guide

This directory is the planned home for **real application screenshots**. No screenshots are included yet; add them after running the app locally. Do not use the report's conceptual map or generated charts as screenshots of the live application.

## Capture these views

1. `screenshots/world-overview.png` — World overview on a fresh condition C world, showing the settlement, metrics, event stream, and population.
2. `screenshots/agent-profile.png` — An inhabitant drawer with profile, inventory, health, energy, and recent event history visible.
3. `screenshots/economy.png` — Economy page showing the resource/wealth chart and current resource totals.
4. `screenshots/social-network.png` — Social network page after advancing enough days to record interactions.
5. `screenshots/research-lab.png` — Research Lab after actual repeated trials, with the selected condition and observed per-trial results.

## Capture checklist

- Start the backend and frontend using the instructions in the root README.
- Start with condition C if LLM-provider quota is unavailable. The dashboard should show live data from the SQLite-backed API.
- Advance days before capturing histories or relationship links. Do not invent events or metrics to make the image look busy.
- Use a desktop browser viewport around 1440 × 1000 pixels. Hide unrelated tabs, notifications, and personal browser data.
- Check that no API keys, local secret values, debug output, or unrelated personal information appear in the image.
- Save original PNGs under `screenshots/` and reference them with relative links in the README:

  ```markdown
  ![EDEN world overview](screenshots/world-overview.png)
  ```

- Keep each image focused on one feature. Add concise alt text and a caption describing the state shown (condition, day, and whether the view is illustrative or measured).

## Before committing screenshots

Review each image at full size. Screenshots must show the running application and actual captured state. Avoid posting provider error bodies, account identifiers, tokens, or private machine paths.
