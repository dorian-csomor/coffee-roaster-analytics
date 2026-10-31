-- =============================================================================
-- Security
-- 1. Row Level Security on every table with no policies: Supabase's public API
--    keys (anon / authenticated) cannot read or write business data.
-- 2. A read-only "bi_reader" role that can see ONLY the reporting views.
--    Looker Studio (and anyone you share credentials with) logs in as this role.
--    The password is set by hand after migrating - see README, never in git.
-- =============================================================================

alter table public.categories          enable row level security;
alter table public.products            enable row level security;
alter table public.customers           enable row level security;
alter table public.orders              enable row level security;
alter table public.order_items         enable row level security;
alter table public.inventory           enable row level security;
alter table public.inventory_movements enable row level security;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'bi_reader') then
        create role bi_reader nologin;
    end if;
end
$$;

grant usage on schema reporting to bi_reader;
grant select on all tables in schema reporting to bi_reader;
alter default privileges in schema reporting grant select on tables to bi_reader;

-- Keep long-running BI queries from hogging the free-tier database.
alter role bi_reader set statement_timeout = '30s';
