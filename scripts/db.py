"""
Database command line for the coffee roaster analytics project.

    python scripts/db.py migrate              apply new SQL files from supabase/migrations
    python scripts/db.py seed                 build ~12 months of history (empty database only)
    python scripts/db.py seed --reset         wipe all business data and rebuild the history
    python scripts/db.py simulate             add every missing day up to yesterday (GitHub Action)
    python scripts/db.py export-csv --out data   generate the dataset as CSV files, no database needed

Connection string comes from the DATABASE_URL environment variable or a .env file
in the project root. Use the Supabase *Session pooler* URI (see README).
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import coffee_sim as sim

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
SEED_RNG = 42
LOCK_ID = 727274  # advisory lock so two simulator runs can never overlap

BOOTSTRAP_SQL = """
create schema if not exists ops;
create table if not exists ops.schema_migrations (
    version    text primary key,
    applied_at timestamptz not null default now()
);
create table if not exists ops.simulation_log (
    sim_date   date primary key,
    orders     integer not null,
    created_at timestamptz not null default now()
);
"""

# Column lists shared by CSV export and database COPY.
COLUMNS = {
    "categories": ["id", "name", "description"],
    "products": ["id", "sku", "name", "category_id", "origin_country", "roast_level",
                 "bag_size_g", "unit_price", "unit_cost"],
    "customers": ["id", "first_name", "last_name", "email", "company_name", "customer_type",
                  "city", "state", "signup_date"],
    "orders": ["id", "customer_id", "order_date", "channel", "status"],
    "order_items": ["id", "order_id", "product_id", "quantity", "unit_price", "unit_cost"],
    "inventory": ["product_id", "quantity_on_hand", "reorder_point", "reorder_quantity"],
    "inventory_movements": ["product_id", "movement_type", "quantity", "movement_date", "order_id"],
}
TABLES_IN_LOAD_ORDER = list(COLUMNS)


# --------------------------------------------------------------------------- #
# Turning simulator objects into rows
# --------------------------------------------------------------------------- #

def product_rows(products):
    return [(p.id, p.sku, p.name, p.category_id, p.origin_country, p.roast_level,
             p.bag_size_g, p.unit_price, p.unit_cost) for p in products]


def customer_rows(customers):
    return [(c.id, c.first_name, c.last_name, c.email, c.company_name, c.customer_type,
             c.city, c.state, c.signup_date) for c in customers]


def order_rows(orders):
    return [(o.id, o.customer_id, o.order_date, o.channel, o.status) for o in orders]


def item_rows(orders):
    return [(item_id, o.id, pid, qty, price, cost)
            for o in orders for item_id, pid, qty, price, cost in o.items]


def inventory_rows(products):
    return [(p.id, p.on_hand, p.reorder_point, p.reorder_quantity) for p in products]


def movement_rows(movements):
    return [(m.product_id, m.movement_type, m.quantity, m.movement_date, m.order_id) for m in movements]


def history_start(months: int, end: date) -> date:
    """First day of the month `months` months before `end`, so charts start on a full month."""
    y, m = divmod(end.year * 12 + end.month - 1 - months, 12)
    return date(y, m + 1, 1)


def build_history(start: date, end: date) -> tuple[dict[str, list[tuple]], list[tuple[date, int]]]:
    """Simulate every day from `start` to `end` (inclusive). Returns rows per table + daily log."""
    products = sim.build_catalog()
    customers = sim.initial_customers(random.Random(SEED_RNG), start)
    s = sim.Simulator(products, customers, next_customer_id=len(customers) + 1,
                      next_order_id=1, next_item_id=1)

    movements = s.opening_balances(start)
    orders, log = [], []
    day = start
    while day <= end:
        r = s.simulate_day(day, random.Random(day.toordinal()))
        orders += r.orders
        movements += r.movements
        log.append((day, len(r.orders)))
        day += timedelta(days=1)

    rows = {
        "categories": sim.CATEGORIES,
        "products": product_rows(products),
        "customers": customer_rows(s.customers),
        "orders": order_rows(orders),
        "order_items": item_rows(orders),
        "inventory": inventory_rows(products),
        "inventory_movements": movement_rows(movements),
    }
    return rows, log


def yesterday_utc() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=1)


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #

def connect():
    import psycopg  # imported here so export-csv works without the driver installed

    url = os.environ.get("DATABASE_URL") or read_dotenv().get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set. Copy .env.example to .env and fill it in (see README).")
    return psycopg.connect(url, connect_timeout=20)


def read_dotenv() -> dict[str, str]:
    env_file = ROOT / ".env"
    values = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def copy_rows(cur, table: str, rows):
    cols = ", ".join(COLUMNS[table])
    with cur.copy(f"copy public.{table} ({cols}) from stdin") as cp:
        for row in rows:
            cp.write_row(row)


def reset_sequences(cur):
    for table in ("categories", "products", "customers", "orders", "order_items", "inventory_movements"):
        cur.execute(
            f"select setval(pg_get_serial_sequence('public.{table}', 'id'),"
            f" (select coalesce(max(id), 0) + 1 from public.{table}), false)"
        )


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

def cmd_migrate(_args):
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    with connect() as conn:
        conn.execute(BOOTSTRAP_SQL)
        applied = {r[0] for r in conn.execute("select version from ops.schema_migrations")}
        pending = [f for f in files if f.stem not in applied]
        if not pending:
            print("Database is up to date.")
            return
        for f in pending:
            print(f"Applying {f.name} ...")
            with conn.transaction():
                conn.execute(f.read_text(encoding="utf-8"))
                conn.execute("insert into ops.schema_migrations (version) values (%s)", (f.stem,))
        print(f"Applied {len(pending)} migration(s).")


def cmd_seed(args):
    end = yesterday_utc()
    start = history_start(args.months, end)
    print(f"Simulating trading from {start} to {end} ...")
    rows, log = build_history(start, end)

    with connect() as conn, conn.cursor() as cur:
        cur.execute("select pg_advisory_xact_lock(%s)", (LOCK_ID,))
        cur.execute("select count(*) from public.orders")
        if cur.fetchone()[0] and not args.reset:
            sys.exit("The database already has orders. Use --reset to wipe and rebuild it.")
        if args.reset:
            print("Wiping existing data ...")
            cur.execute("truncate " + ", ".join(f"public.{t}" for t in TABLES_IN_LOAD_ORDER)
                        + ", ops.simulation_log restart identity cascade")
        for table in TABLES_IN_LOAD_ORDER:
            copy_rows(cur, table, rows[table])
            print(f"  {table:<20} {len(rows[table]):>7,} rows")
        with cur.copy("copy ops.simulation_log (sim_date, orders) from stdin") as cp:
            for row in log:
                cp.write_row(row)
        reset_sequences(cur)
    print("Seed complete.")


def cmd_simulate(args):
    end = yesterday_utc()
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select pg_advisory_xact_lock(%s)", (LOCK_ID,))
        cur.execute("select max(sim_date) from ops.simulation_log")
        last = cur.fetchone()[0]
        if last is None:
            sys.exit("No history found - run `python scripts/db.py seed` first.")
        if last >= end:
            print(f"Already simulated up to {last}. Nothing to do.")
            return
        start = max(last + timedelta(days=1), end - timedelta(days=args.max_days - 1))

        # Rebuild simulator state from the database.
        catalog = {p.sku: p for p in sim.build_catalog()}
        cur.execute("""select p.id, p.sku, p.name, p.category_id, p.origin_country, p.roast_level,
                              p.bag_size_g, p.unit_price, p.unit_cost,
                              i.reorder_point, i.reorder_quantity, i.quantity_on_hand
                       from public.products p join public.inventory i on i.product_id = p.id
                       where p.is_active""")
        products = []
        for (pid, sku, name, cat, origin, roast, size, price, cost, rp, rq, on_hand) in cur.fetchall():
            popularity = catalog[sku].popularity if sku in catalog else 0.5
            products.append(sim.Product(pid, sku, name, cat, origin, roast, size, price, cost,
                                        popularity, rp, rq, on_hand))
        cur.execute("""select id, first_name, last_name, email, company_name, customer_type,
                              city, state, signup_date from public.customers""")
        customers = [sim.Customer(*r) for r in cur.fetchall()]
        ids = {}
        for table in ("customers", "orders", "order_items"):
            cur.execute(f"select coalesce(max(id), 0) + 1 from public.{table}")
            ids[table] = cur.fetchone()[0]

        s = sim.Simulator(products, customers, ids["customers"], ids["orders"], ids["order_items"])
        new_customers, orders, movements, log = [], [], [], []
        day = start
        while day <= end:
            r = s.simulate_day(day, random.Random(day.toordinal()))
            new_customers += r.customers
            orders += r.orders
            movements += r.movements
            log.append((day, len(r.orders)))
            day += timedelta(days=1)

        copy_rows(cur, "customers", customer_rows(new_customers))
        copy_rows(cur, "orders", order_rows(orders))
        copy_rows(cur, "order_items", item_rows(orders))
        copy_rows(cur, "inventory_movements", movement_rows(movements))
        cur.executemany(
            "update public.inventory set quantity_on_hand = %s, updated_at = now() where product_id = %s",
            [(p.on_hand, p.id) for p in products],
        )
        cur.executemany("insert into ops.simulation_log (sim_date, orders) values (%s, %s)", log)
        reset_sequences(cur)

    for d, n in log:
        print(f"{d}: {n} orders")
    print(f"Added {len(new_customers)} new customers and {len(orders)} orders.")


def cmd_export_csv(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    end = yesterday_utc()
    rows, _ = build_history(history_start(args.months, end), end)
    for table in TABLES_IN_LOAD_ORDER:
        with open(out / f"{table}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS[table])
            w.writerows(rows[table])
        print(f"  {table:<20} {len(rows[table]):>7,} rows -> {out / (table + '.csv')}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="apply pending SQL migrations").set_defaults(func=cmd_migrate)

    p = sub.add_parser("seed", help="generate historical data")
    p.add_argument("--months", type=int, default=12)
    p.add_argument("--reset", action="store_true", help="delete all existing data first")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("simulate", help="add missing days up to yesterday")
    p.add_argument("--max-days", type=int, default=14, help="catch up at most this many days")
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("export-csv", help="write the dataset to CSV files (no database)")
    p.add_argument("--out", default="data")
    p.add_argument("--months", type=int, default=12)
    p.set_defaults(func=cmd_export_csv)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
