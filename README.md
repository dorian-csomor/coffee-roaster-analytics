# ☕ Coffee Roaster Sales & Inventory Analytics

**A complete, zero-cost analytics stack for a small business**: a cloud database, automated data pipeline, AI assistant and live BI dashboard, built entirely on free tools.

> Driftwood Peak Coffee Co. is a fictional specialty coffee roaster in Portland, Oregon. It sells through an online shop, its own café, monthly subscriptions and wholesale accounts with local cafés. All data is simulated, but it behaves like a real business: holiday peaks, weekend café rushes, loyal regulars, stock running low and getting restocked.

**🔗 [Open the live dashboard](https://datastudio.google.com/reporting/02a517ba-5fe3-4581-966b-15e2c5b83e41)** · 📊 [How it was built](docs/dashboard-guide.md)

The dashboard updates every morning with new sales and stock data. No login is needed to view it.

| Sales Overview | Inventory |
|---|---|
| [![Sales Overview page](docs/dashboard-sales.png)](https://datastudio.google.com/reporting/02a517ba-5fe3-4581-966b-15e2c5b83e41) | [![Inventory page](docs/dashboard-inventory.png)](https://datastudio.google.com/reporting/02a517ba-5fe3-4581-966b-15e2c5b83e41) |

---

## Why this project

Most small businesses can't justify $10–20 per user per month for Power BI or Tableau. This project shows that a small business can get proper reporting for **$0 a month**:

| Need | Tool | Cost |
|---|---|---|
| Cloud database | [Supabase](https://supabase.com) (PostgreSQL) | Free tier |
| Version control & automation | GitHub + GitHub Actions | Free |
| BI dashboard, shareable by link | [Looker Studio](https://lookerstudio.google.com) | Free |
| Ask questions in plain English | Claude + Supabase MCP connector | Included in Claude plan |

## Architecture

```mermaid
flowchart LR
    subgraph GitHub
        A[SQL migrations] --> W1[Action: deploy migrations]
        S[Python simulator] --> W2[Action: daily sales, every morning]
    end
    W1 --> DB[(Supabase PostgreSQL)]
    W2 --> DB
    DB -->|reporting views, read-only user| L[Looker Studio dashboard]
    DB -->|MCP, read-only| C[Claude]
```

- **Database as code.** Every table, view and permission is a SQL file in [`supabase/migrations`](supabase/migrations). Pushing a change to `main` deploys it automatically.
- **Live data.** A scheduled GitHub Action simulates each new day's trading, so the dashboard is never stale. This also keeps the free Supabase project from pausing.
- **Reporting layer.** The BI tool never touches raw tables. It reads flat views in a `reporting` schema, so dashboards stay simple and fast.
- **Secure by default.** Row Level Security blocks the public API from reaching business data, and the dashboard logs in as `bi_reader`, a role that can only read the reporting views.

## Data model

```mermaid
erDiagram
    categories ||--o{ products : contains
    products ||--|| inventory : "stock level"
    products ||--o{ inventory_movements : "stock ledger"
    customers ||--o{ orders : places
    orders ||--|{ order_items : contains
    products ||--o{ order_items : "sold as"
    orders ||--o{ inventory_movements : triggers
```

| Reporting view | What it answers |
|---|---|
| `reporting.v_sales` | Every sold line with product, customer, channel, revenue, cost and profit |
| `reporting.v_monthly_kpis` | Revenue, orders, average order value, margin and new customers per month |
| `reporting.v_customer_summary` | Lifetime value and recency segment (Active / At risk / Lapsed) per customer |
| `reporting.v_inventory_status` | Stock on hand, days of cover, stock value and reorder alerts |

## Ask Claude about the business

With the Supabase connector, Claude can query the database directly (read-only). For example:

- *"What were our top 5 products by gross profit last quarter?"*
- *"Which wholesale customers haven't ordered in the last 30 days?"*
- *"Which products will run out within a week at the current sales rate?"*
- *"Compare this October with last October by channel."*

---

## Setup guide

### 1. Create the Supabase project
1. Sign up at [supabase.com](https://supabase.com). The free plan is enough.
2. Click **New project**, choose a region near you and **save the database password**.
3. Click **Connect** at the top of the project page. Under **Session pooler**, copy the URI. It looks like
   `postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres`

   > Use the *Session pooler*, not the direct connection. GitHub Actions and Looker Studio need it.

### 2. Load the database from your PC
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then paste your URI into .env
python scripts/db.py migrate    # creates tables, views, security
python scripts/db.py seed       # ~13 months of history, ~15k orders
```

### 3. Give the dashboard user a password
In Supabase, open **SQL Editor** and run this with a strong password of your own:
```sql
alter role bi_reader with login password 'choose-a-strong-password';
```

### 4. Connect GitHub
1. Create a new repository and push this project to it. Your `.env` file is git-ignored and is never uploaded.
2. Go to **Settings → Secrets and variables → Actions → New repository secret**. Name it `DATABASE_URL` and paste the same URI.
3. Open the **Actions** tab, choose **Daily sales simulation**, then **Run workflow** to test it. After that it runs every morning.

> GitHub pauses scheduled workflows in repositories with no commits for 60 days. If that happens, it emails you and you can re-enable the workflow with one click.

### 5. Build the Looker Studio dashboard
Follow the step-by-step guide in [docs/dashboard-guide.md](docs/dashboard-guide.md).

### 6. Connect Claude (optional)
- **Claude app / claude.ai:** go to **Settings → Connectors**, add **Supabase** and sign in.
- **Claude Code:**
  ```bash
  claude mcp add --transport http supabase "https://mcp.supabase.com/mcp?project_ref=YOUR_PROJECT_REF&read_only=true"
  ```
  Your project ref is the `abcdefgh` part of your URL. `read_only=true` makes sure Claude can look but not change anything.

## Project structure
```
├── supabase/migrations/     database schema, reporting views, security (SQL)
├── scripts/
│   ├── coffee_sim.py        business simulator: customers, orders, inventory
│   └── db.py                CLI: migrate | seed | simulate | export-csv
├── .github/workflows/       automated migrations + daily sales simulation
└── docs/dashboard-guide.md  how to build the Looker Studio report
```

No database yet? `python scripts/db.py export-csv --out data` writes the whole dataset to CSV files.

---

*Built by Dorian Csomor · Available for small-business reporting and data projects on Upwork.*
