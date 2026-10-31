-- =============================================================================
-- Reporting layer: flat, BI-friendly views in a separate "reporting" schema.
-- Looker Studio works best with one wide table per chart, so the joins live here
-- instead of in the dashboard.
-- =============================================================================

create schema if not exists reporting;

-- Sales fact: one row per order line, Completed orders only.
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
    oi.quantity * (oi.unit_price - oi.unit_cost)   as gross_profit
from public.order_items oi
join public.orders      o   on o.id = oi.order_id
join public.customers   c   on c.id = o.customer_id
join public.products    p   on p.id = oi.product_id
join public.categories  cat on cat.id = p.category_id
where o.status = 'Completed';

-- Monthly headline KPIs (handy for scorecards and for asking Claude questions).
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
    round(s.revenue / nullif(s.orders, 0), 2)                  as avg_order_value
from sales s
left join signups n using (order_month);

-- One row per customer with lifetime value and a simple recency segment.
create or replace view reporting.v_customer_summary as
with stats as (
    select
        customer_id,
        count(distinct order_id) as orders,
        sum(revenue)             as lifetime_revenue,
        min(order_date)          as first_order_date,
        max(order_date)          as last_order_date
    from reporting.v_sales
    group by customer_id
)
select
    c.id                                                        as customer_id,
    coalesce(c.company_name, c.first_name || ' ' || c.last_name) as customer_name,
    c.customer_type,
    c.city,
    c.state,
    c.signup_date,
    coalesce(s.orders, 0)                                       as orders,
    coalesce(s.lifetime_revenue, 0)                             as lifetime_revenue,
    round(s.lifetime_revenue / nullif(s.orders, 0), 2)          as avg_order_value,
    s.first_order_date,
    s.last_order_date,
    current_date - s.last_order_date                            as days_since_last_order,
    case
        when s.last_order_date is null                 then 'No orders yet'
        when current_date - s.last_order_date <= 60    then 'Active'
        when current_date - s.last_order_date <= 180   then 'At risk'
        else 'Lapsed'
    end                                                         as segment
from public.customers c
left join stats s on s.customer_id = c.id;

-- Current stock position with days of cover based on the last 30 days of sales.
create or replace view reporting.v_inventory_status as
with recent_sales as (
    select oi.product_id, sum(oi.quantity) as units_30d
    from public.order_items oi
    join public.orders o on o.id = oi.order_id
    where o.status = 'Completed'
      and o.order_date >= now() - interval '30 days'
    group by oi.product_id
)
select
    p.id                                            as product_id,
    p.sku,
    p.name                                          as product_name,
    cat.name                                        as category,
    i.quantity_on_hand,
    i.reorder_point,
    i.reorder_quantity,
    coalesce(r.units_30d, 0)                        as units_sold_30d,
    round(coalesce(r.units_30d, 0) / 30.0, 2)       as avg_daily_units,
    case when coalesce(r.units_30d, 0) > 0
         then round(i.quantity_on_hand / (r.units_30d / 30.0), 1)
    end                                             as days_of_cover,
    i.quantity_on_hand * p.unit_cost                as stock_value_cost,
    i.quantity_on_hand * p.unit_price               as stock_value_retail,
    case
        when i.quantity_on_hand = 0                       then 'Out of stock'
        when i.quantity_on_hand <= i.reorder_point        then 'Reorder now'
        when i.quantity_on_hand <= i.reorder_point * 1.5  then 'Low'
        else 'Healthy'
    end                                             as stock_status,
    i.updated_at                                    as last_updated
from public.inventory i
join public.products   p   on p.id = i.product_id
join public.categories cat on cat.id = p.category_id
left join recent_sales r on r.product_id = i.product_id;
