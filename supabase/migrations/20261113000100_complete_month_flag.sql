-- =============================================================================
-- Adds is_complete_month to the sales views.
-- Monthly charts can filter on it to hide the current, still-incomplete month,
-- which would otherwise look like a sudden drop in sales.
-- New columns must go at the end: "create or replace view" can only append.
-- =============================================================================

create or replace view reporting.v_sales as
select
    oi.id                                          as order_item_id,
    o.id                                           as order_id,
    o.order_date::date                             as order_date,
    date_trunc('month', o.order_date)::date        as order_month,
    o.channel,
    c.id                                           as customer_id,
    coalesce(c.company_name, c.first_name || ' ' || c.last_name) as customer_name,
    c.customer_type,
    c.city,
    c.state,
    p.id                                           as product_id,
    p.sku,
    p.name                                         as product_name,
    cat.name                                       as category,
    p.roast_level,
    p.origin_country,
    oi.quantity,
    oi.unit_price,
    oi.unit_cost,
    oi.quantity * oi.unit_price                    as revenue,
    oi.quantity * oi.unit_cost                     as cost,
    oi.quantity * (oi.unit_price - oi.unit_cost)   as gross_profit,
    date_trunc('month', o.order_date) < date_trunc('month', now()) as is_complete_month
from public.order_items oi
join public.orders      o   on o.id = oi.order_id
join public.customers   c   on c.id = o.customer_id
join public.products    p   on p.id = oi.product_id
join public.categories  cat on cat.id = p.category_id
where o.status = 'Completed';

create or replace view reporting.v_monthly_kpis as
with sales as (
    select
        order_month,
        count(distinct order_id)    as orders,
        count(distinct customer_id) as active_customers,
        sum(quantity)               as units_sold,
        sum(revenue)                as revenue,
        sum(gross_profit)           as gross_profit
    from reporting.v_sales
    group by order_month
),
signups as (
    select date_trunc('month', signup_date)::date as order_month, count(*) as new_customers
    from public.customers
    group by 1
)
select
    s.order_month                                              as month,
    s.orders,
    s.active_customers,
    coalesce(n.new_customers, 0)                               as new_customers,
    s.units_sold,
    s.revenue,
    s.gross_profit,
    round(s.gross_profit / nullif(s.revenue, 0) * 100, 1)      as gross_margin_pct,
    round(s.revenue / nullif(s.orders, 0), 2)                  as avg_order_value,
    s.order_month < date_trunc('month', now())::date           as is_complete_month
from sales s
left join signups n using (order_month);
