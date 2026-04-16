# Phases

Build is sliced into 7 phases. Each phase lands a validable deliverable.

| Phase | Focus | Deliverable |
| --- | --- | --- |
| **0 — Scaffold** | Repo skeleton, Flask factory, health endpoint, deploy config | `flask run` serves `/health`, deploys to Railway |
| **1 — Auth + Layout** | bcrypt login for the 3 internal users, session, base UI shell | Login/logout, protected routes |
| **2 — Data Model + Client CRUD** | SQLAlchemy models, migrations, create/edit/list clients & accounts | Team can set up a client once (US1) |
| **3 — Quarterly Data Entry + Calculations** | Per-report form with pre-filled static data, real-time SACS/TCC math | Balances in → totals computed (US2) |
| **4 — SACS PDF** | WeasyPrint template matching sample layout (2 pages) | Pixel-accurate SACS download |
| **5 — TCC PDF** | Dynamic TCC layout (variable account bubbles, liabilities box) | Pixel-accurate TCC download |
| **6 — Export + History + Polish** | PDF download pipeline, report history, Canva export if confirmed | V1 complete — team prep drops from 1 day to <1 hour |

Each phase folder (added as we go) contains: plan, open questions, and validation checklist.
