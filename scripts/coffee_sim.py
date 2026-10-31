"""
Business simulator for Driftwood Peak Coffee Co. (a fictional specialty roaster).

Generates realistic, internally consistent activity one day at a time:
new customer signups, orders across four channels, and stock movements
(sales + restocks). The same engine builds the 12-month history (seed) and
adds new days later (daily GitHub Action), so the data always lines up.

Pure Python, no database code here - see db.py for that.
"""

from __future__ import annotations

import calendar
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #

CATEGORIES = [
    (1, "Single Origin", "Traceable coffees from a single farm or region"),
    (2, "Blends", "House blends for everyday brewing"),
    (3, "Espresso", "Roasted and blended for espresso machines"),
    (4, "Decaf", "Swiss Water Process decaffeinated coffees"),
    (5, "Brewing Equipment", "Drippers, grinders, kettles and filters"),
    (6, "Merchandise", "Mugs, totes and gift cards"),
]

# (name, category_id, origin, roast, price_250g, popularity)
COFFEES = [
    ("Ethiopia Yirgacheffe", 1, "Ethiopia", "Light", 18.50, 1.4),
    ("Kenya Nyeri AA", 1, "Kenya", "Light", 19.50, 0.9),
    ("Colombia Huila", 1, "Colombia", "Medium", 16.50, 1.5),
    ("Guatemala Antigua", 1, "Guatemala", "Medium", 16.00, 1.0),
    ("Brazil Cerrado", 1, "Brazil", "Medium-Dark", 14.50, 1.1),
    ("Sumatra Mandheling", 1, "Indonesia", "Dark", 16.00, 0.7),
    ("Costa Rica Tarrazu", 1, "Costa Rica", "Medium", 17.50, 0.8),
    ("Morning Ridge Blend", 2, None, "Medium", 14.00, 1.9),
    ("Campfire Blend", 2, None, "Dark", 14.00, 1.2),
    ("Driftwood House Espresso", 3, None, "Medium-Dark", 15.50, 1.8),
    ("Velvet Crema Espresso", 3, None, "Dark", 15.50, 1.0),
    ("Colombia Decaf", 4, "Colombia", "Medium", 16.00, 0.6),
]

# (sku, name, category_id, price, cost, popularity, reorder_point, reorder_qty)
NON_COFFEE = [
    ("EQ-V60", "Ceramic Pour-Over Dripper", 5, 28.00, 11.00, 0.35, 10, 30),
    ("EQ-FILT", "Paper Filters (100 pack)", 5, 8.00, 2.40, 0.60, 25, 80),
    ("EQ-GRIND", "Hand Burr Grinder", 5, 119.00, 58.00, 0.12, 4, 12),
    ("EQ-KETTLE", "Gooseneck Kettle", 5, 69.00, 31.00, 0.15, 5, 15),
    ("EQ-PRESS", "French Press 1L", 5, 39.00, 15.50, 0.20, 6, 20),
    ("MR-MUG", "Driftwood Peak Enamel Mug", 6, 16.00, 5.20, 0.30, 12, 40),
    ("MR-TOTE", "Canvas Tote Bag", 6, 18.00, 6.00, 0.15, 8, 30),
    ("MR-GIFT", "Gift Card $50", 6, 50.00, 50.00, 0.10, 20, 50),
]

ROAST_COST_RATIO = 0.42  # roasted coffee cost (green beans + roasting + bag) vs price


@dataclass
class Product:
    id: int
    sku: str
    name: str
    category_id: int
    origin_country: str | None
    roast_level: str | None
    bag_size_g: int | None
    unit_price: Decimal
    unit_cost: Decimal
    popularity: float
    reorder_point: int
    reorder_quantity: int
    on_hand: int = 0

    @property
    def is_coffee(self) -> bool:
        return self.bag_size_g is not None

    @property
    def is_wholesale_bag(self) -> bool:
        return self.bag_size_g == 1000


def build_catalog() -> list[Product]:
    products: list[Product] = []
    pid = 1
    for name, cat, origin, roast, price_250, pop in COFFEES:
        code = "".join(w[0] for w in name.split()[:3]).upper()
        for size, price, rp, rq in ((250, price_250, 60, 220), (1000, round(price_250 * 3.2, 0) - 0.01, 25, 90)):
            products.append(Product(
                id=pid, sku=f"CF-{code}-{size}G", name=f"{name} {size if size < 1000 else 1}{'g' if size < 1000 else 'kg'}",
                category_id=cat, origin_country=origin, roast_level=roast, bag_size_g=size,
                unit_price=money(price), unit_cost=money(price * ROAST_COST_RATIO),
                popularity=pop, reorder_point=rp, reorder_quantity=rq,
            ))
            pid += 1
    for sku, name, cat, price, cost, pop, rp, rq in NON_COFFEE:
        products.append(Product(
            id=pid, sku=sku, name=name, category_id=cat, origin_country=None, roast_level=None,
            bag_size_g=None, unit_price=money(price), unit_cost=money(cost),
            popularity=pop, reorder_point=rp, reorder_quantity=rq,
        ))
        pid += 1
    return products


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #

FIRST_NAMES = """James Mary Olivia Liam Emma Noah Ava Elijah Sophia Lucas Mia Mateo Amelia Ethan
Harper Logan Evelyn Aiden Abigail Jackson Emily Sebastian Ella Henry Chloe Owen Grace Daniel
Zoe Samuel Nora Jacob Lily Leo Hannah Wyatt Aria Isaac Layla Julian Riley Gabriel Ellie Anthony
Maya Dylan Priya Arjun Mei Kenji Fatima Omar Sofia Diego Camila Andre Nadia Tomas Ingrid""".split()

LAST_NAMES = """Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez
Lopez Wilson Anderson Thomas Taylor Moore Jackson Martin Lee Perez Thompson White Harris Sanchez
Clark Ramirez Lewis Robinson Walker Young Allen King Wright Scott Torres Nguyen Hill Flores Green
Adams Nelson Baker Hall Rivera Campbell Mitchell Carter Roberts Patel Kim Chen Okafor Novak""".split()

# Pacific Northwest roaster: most customers are local, some ship nationwide.
CITIES = [
    ("Portland", "OR", 30), ("Seattle", "WA", 22), ("Eugene", "OR", 8), ("Bend", "OR", 7),
    ("Tacoma", "WA", 6), ("Spokane", "WA", 4), ("Boise", "ID", 4), ("San Francisco", "CA", 5),
    ("Los Angeles", "CA", 4), ("Denver", "CO", 3), ("Austin", "TX", 2), ("Chicago", "IL", 2),
    ("New York", "NY", 2), ("Boston", "MA", 1),
]

CAFE_WORDS_A = "Blue Copper Little Wild Golden Corner Union Hidden North Maple Harbor Cedar Lantern Fox".split()
CAFE_WORDS_B = "Bean Cup Mug Kettle Grounds Cafe Espresso Bar Bakery Kitchen Deli Commons".split()


@dataclass
class Customer:
    id: int
    first_name: str
    last_name: str
    email: str
    company_name: str | None
    customer_type: str
    city: str
    state: str
    signup_date: date

    @property
    def traits(self) -> random.Random:
        """Stable per-customer randomness (same answer every run, in seed or live mode)."""
        return random.Random(self.id * 7919)

    @property
    def loyalty(self) -> float:
        # Long-tail: a few retail customers order far more often than the rest.
        return self.traits.lognormvariate(0, 0.9)

    @property
    def favourite_product_ids(self) -> list[int]:
        rng = self.traits
        return [rng.randint(1, len(COFFEES)) for _ in range(2)]  # coffee index, 1-based


def make_customer(rng: random.Random, cid: int, signup: date, customer_type: str) -> Customer:
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    city, state = weighted_choice(rng, [(c, s) for c, s, _ in CITIES], [w for *_, w in CITIES])
    company = None
    if customer_type == "Wholesale":
        company = f"{rng.choice(CAFE_WORDS_A)} {rng.choice(CAFE_WORDS_B)}"
        if rng.random() < 0.4:
            company += f" {city}"
        email = f"orders{cid}@{company.lower().replace(' ', '')}.example.com"
    else:
        email = f"{first.lower()}.{last.lower()}{cid}@example.com"
    return Customer(cid, first, last, email, company, customer_type, city, state, signup)


# --------------------------------------------------------------------------- #
# Orders & inventory
# --------------------------------------------------------------------------- #

@dataclass
class Order:
    id: int
    customer_id: int
    order_date: datetime
    channel: str
    status: str
    items: list[tuple[int, int, int, Decimal, Decimal]] = field(default_factory=list)
    # items: (order_item_id, product_id, quantity, unit_price, unit_cost)


@dataclass
class Movement:
    product_id: int
    movement_type: str
    quantity: int
    movement_date: datetime
    order_id: int | None = None


@dataclass
class DayResult:
    customers: list[Customer] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    movements: list[Movement] = field(default_factory=list)


# Seasonality: coffee sells more in cold months and around the holidays.
MONTH_FACTOR = {1: 0.88, 2: 0.92, 3: 0.97, 4: 0.95, 5: 0.93, 6: 0.88,
                7: 0.85, 8: 0.87, 9: 0.98, 10: 1.05, 11: 1.22, 12: 1.38}
# Mon..Sun - the café is busiest at weekends.
WEEKDAY_FACTOR = [0.92, 0.90, 0.93, 0.97, 1.08, 1.22, 1.12]


class Simulator:
    """Holds current business state and advances it one day at a time."""

    def __init__(self, products: list[Product], customers: list[Customer],
                 next_customer_id: int, next_order_id: int, next_item_id: int):
        self.products = {p.id: p for p in products}
        self.customers = customers
        self.next_customer_id = next_customer_id
        self.next_order_id = next_order_id
        self.next_item_id = next_item_id

    # ---- public ----------------------------------------------------------- #

    def simulate_day(self, day: date, rng: random.Random) -> DayResult:
        result = DayResult()
        season = MONTH_FACTOR[day.month] * WEEKDAY_FACTOR[day.weekday()]

        # 1. New signups (more in the holiday season).
        for _ in range(poisson(rng, 1.3 * MONTH_FACTOR[day.month])):
            ctype = weighted_choice(rng, ["Retail", "Subscription", "Wholesale"], [80, 17, 3])
            c = make_customer(rng, self.next_customer_id, day, ctype)
            self.next_customer_id += 1
            self.customers.append(c)
            result.customers.append(c)

        active = [c for c in self.customers if c.signup_date <= day]
        retail = [c for c in active if c.customer_type == "Retail"]

        # 2. Retail orders: online shop + café counter.
        if retail:
            n_retail = poisson(rng, 0.06 * len(retail) * season)
            weights = [c.loyalty for c in retail]
            for _ in range(n_retail):
                c = weighted_choice(rng, retail, weights)
                channel = "Cafe" if rng.random() < (0.45 if day.weekday() >= 5 else 0.35) else "Online"
                self._place_order(result, rng, c, day, channel)

        # 3. Subscriptions ship monthly on the customer's signup day-of-month.
        last_dom = calendar.monthrange(day.year, day.month)[1]
        for c in active:
            if c.customer_type == "Subscription" and c.signup_date < day \
                    and min(c.signup_date.day, last_dom) == day.day \
                    and rng.random() < 0.93:  # some skip a month
                self._place_order(result, rng, c, day, "Subscription")

        # 4. Wholesale cafes order on "their" weekday.
        if day.weekday() < 5:
            for c in active:
                if c.customer_type == "Wholesale" and c.id % 5 == day.weekday() \
                        and rng.random() < 0.45 * MONTH_FACTOR[day.month]:  # ~every 2 weeks
                    self._place_order(result, rng, c, day, "Wholesale")

        # 5. Restocks: low items get a delivery on ~35% of days (simulates lead time).
        for p in self.products.values():
            if p.on_hand <= p.reorder_point and rng.random() < 0.35:
                qty = p.reorder_quantity + rng.randint(0, p.reorder_quantity // 4)
                p.on_hand += qty
                result.movements.append(Movement(p.id, "Restock", qty, at(day, time(7, 30))))

        return result

    def opening_balances(self, day: date) -> list[Movement]:
        out = []
        for p in self.products.values():
            p.on_hand = int(p.reorder_quantity * 1.6)
            out.append(Movement(p.id, "Opening Balance", p.on_hand, at(day, time(0, 0))))
        return out

    # ---- internals -------------------------------------------------------- #

    def _place_order(self, result: DayResult, rng: random.Random, c: Customer, day: date, channel: str):
        hours = (7, 19) if channel == "Cafe" else (6, 23)
        ts = at(day, time(rng.randint(*hours), rng.randint(0, 59), rng.randint(0, 59)))
        status = weighted_choice(rng, ["Completed", "Refunded", "Cancelled"], [96, 2, 2])
        order = Order(self.next_order_id, c.id, ts, channel, status)

        for product_id, qty in self._basket(rng, c, channel):
            p = self.products[product_id]
            if status != "Cancelled":
                qty = min(qty, p.on_hand)   # can't sell what we don't have
                if qty == 0:
                    continue                # stock-out: lost sale
                p.on_hand -= qty
                result.movements.append(Movement(p.id, "Sale", -qty, ts, order.id))
            order.items.append((self.next_item_id, p.id, qty, p.unit_price, p.unit_cost))
            self.next_item_id += 1

        if order.items:  # an order where everything was out of stock never happens
            self.next_order_id += 1
            result.orders.append(order)

    def _basket(self, rng: random.Random, c: Customer, channel: str) -> list[tuple[int, int]]:
        coffees = [p for p in self.products.values() if p.is_coffee]
        others = [p for p in self.products.values() if not p.is_coffee]
        lines: dict[int, int] = {}

        def pick_coffee(size: int) -> Product:
            pool = [p for p in coffees if p.bag_size_g == size]
            fav = c.favourite_product_ids
            weights = [p.popularity * (3 if ((p.id + 1) // 2) in fav else 1) for p in pool]
            return weighted_choice(rng, pool, weights)

        if channel == "Wholesale":
            for _ in range(rng.randint(1, 3)):
                p = pick_coffee(1000)
                lines[p.id] = lines.get(p.id, 0) + rng.randint(2, 6)
        elif channel == "Subscription":
            p = pick_coffee(250)
            lines[p.id] = rng.choice([1, 2, 2, 3])
        else:
            for _ in range(weighted_choice(rng, [1, 2, 3], [60, 30, 10])):
                p = pick_coffee(1000 if rng.random() < 0.12 else 250)
                lines[p.id] = lines.get(p.id, 0) + 1
            if rng.random() < (0.22 if channel == "Online" else 0.10):
                p = weighted_choice(rng, others, [o.popularity for o in others])
                lines[p.id] = lines.get(p.id, 0) + 1
        return list(lines.items())


# --------------------------------------------------------------------------- #
# Initial history
# --------------------------------------------------------------------------- #

def initial_customers(rng: random.Random, start: date) -> list[Customer]:
    """Customers who already existed before the history window starts."""
    customers = []
    mix = [("Retail", 300), ("Subscription", 70), ("Wholesale", 18)]
    cid = 1
    for ctype, count in mix:
        for _ in range(count):
            signup = start - timedelta(days=rng.randint(1, 730))
            customers.append(make_customer(rng, cid, signup, ctype))
            cid += 1
    rng.shuffle(customers)  # mix types across ids, then renumber in signup order
    customers.sort(key=lambda c: c.signup_date)
    for i, c in enumerate(customers, start=1):
        c.id = i
        if c.customer_type == "Wholesale":
            c.email = f"orders{i}@" + c.email.split("@", 1)[1]
        else:
            c.email = f"{c.first_name.lower()}.{c.last_name.lower()}{i}@example.com"
    return customers


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def money(x: float) -> Decimal:
    return Decimal(str(round(x, 2))).quantize(Decimal("0.01"))


def at(day: date, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=timezone.utc)


def weighted_choice(rng: random.Random, items, weights):
    return rng.choices(items, weights=weights, k=1)[0]


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 50:  # normal approximation for large rates
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1
