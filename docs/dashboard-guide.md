# Looker Studio dashboard guide

This guide builds a two-page report: **Sales Overview** and **Inventory**. Plan on about an hour the first time.

## 1. Connect the data sources

Repeat these steps for each of the four views below.

1. Go to [lookerstudio.google.com](https://lookerstudio.google.com), click **Create → Data source** and choose **PostgreSQL**.
2. Fill in the connection details from Supabase (**Connect → Session pooler**):

   | Field | Value |
   |---|---|
   | Host | `aws-0-<region>.pooler.supabase.com` (from your URI) |
   | Port | `5432` |
   | Database | `postgres` |
   | Username | `bi_reader.<project-ref>` (note the dot and your project ref) |
   | Password | the `bi_reader` password you set |

   Tick **Enable SSL**. If Looker Studio asks for a server certificate, download it in Supabase under **Database → Settings → SSL Configuration**.
3. Choose **Custom query** and enter the query for the view, for example:
   ```sql
   select * from reporting.v_sales
   ```
4. Click **Connect**. Rename the data source (top left) to something like `Sales`.
5. Under **Data freshness**, choose **12 hours**, since the data updates once a day.

| Data source name | Custom query |
|---|---|
| Sales | `select * from reporting.v_sales` |
| Monthly KPIs | `select * from reporting.v_monthly_kpis` |
| Customers | `select * from reporting.v_customer_summary` |
| Inventory | `select * from reporting.v_inventory_status` |

In the **Sales** data source, add one calculated field, **Avg Order Value** = `SUM(revenue) / COUNT_DISTINCT(order_id)`. Set its type to Currency (USD).

## 2. Page 1: Sales Overview

Create a report (**Create → Report**) and add the Sales data source. Add a **date range control** at the top (dimension `order_date`, default *Last 12 months*) and **drop-down filters** for `channel` and `customer_type`.

| Chart | Type | Dimension | Metric(s) |
|---|---|---|---|
| Total Revenue | Scorecard | — | `revenue` (SUM), comparison: previous period |
| Orders | Scorecard | — | `order_id` (Count Distinct) |
| Avg Order Value | Scorecard | — | `Avg Order Value` |
| Gross Profit | Scorecard | — | `gross_profit` (SUM) |
| Revenue trend | Time series | `order_month` | `revenue` |
| Revenue by channel | Donut chart | `channel` | `revenue` |
| Revenue by category | Bar chart | `category` | `revenue` |
| Top 10 products | Table with bars | `product_name` | `revenue`, `quantity`, `gross_profit` · rows: 10 |
| Top customers | Table | `customer_name`, `customer_type` | `revenue`, `order_id` (Count Distinct) · rows: 10 |
| Sales by state | Geo chart | `state` (type: Geo → Region) | `revenue` |

## 3. Page 2: Inventory

Add the **Inventory** data source.

| Chart | Type | Dimension | Metric(s) |
|---|---|---|---|
| Stock value (cost) | Scorecard | — | `stock_value_cost` |
| Items to reorder | Scorecard | — | Record Count, filter: `stock_status` in *Out of stock, Reorder now* |
| Stock status | Donut chart | `stock_status` | Record Count |
| Stock table | Table | `product_name`, `category`, `stock_status` | `quantity_on_hand`, `reorder_point`, `days_of_cover`, `units_sold_30d` |

In the stock table, open **Style → Conditional formatting** and colour rows red where `stock_status` = *Out of stock*, orange for *Reorder now* and yellow for *Low*. Sort by `days_of_cover`, ascending.

## 4. Optional page 3: Customers

Use the **Customers** data source to show a donut chart of `segment`, a bar chart of `lifetime_revenue` by `customer_type`, and an "At risk" table filtered to `segment` = *At risk*, sorted by `lifetime_revenue`.

## 5. Style and share

- **Theme and layout → Theme**: pick a simple light theme. Warm coffee colours work well here, for example `#6F4E37` and `#C8A27A`, with one accent colour.
- Add a header with the business name and a "Data refreshed daily" note.
- **Share → Manage access → Anyone with the link can view**. Put that link in your README and your Upwork portfolio.
- Take a screenshot, save it as `docs/dashboard.png` and un-comment the image line in the README.
