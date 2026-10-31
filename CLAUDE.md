# Project notes for Claude

Portfolio project: free analytics stack (Supabase + GitHub Actions + Looker Studio + Claude) for a fictional coffee roaster, Driftwood Peak Coffee Co.

- Schema changes go in a **new** file in `supabase/migrations/` (`YYYYMMDDHHMMSS_description.sql`). Never edit a migration that has already been applied. `scripts/db.py migrate` tracks applied files in `ops.schema_migrations`.
- Dashboards read only from the `reporting` schema views. New views there are automatically readable by the `bi_reader` role.
- `scripts/coffee_sim.py` is pure simulation logic with no DB access. `scripts/db.py` handles all database I/O.
- Business rules: only `status = 'Completed'` orders count as revenue. Channels are Online, Cafe, Wholesale and Subscription.
- When answering business questions through the Supabase MCP, prefer the `reporting.*` views and stay read-only.
