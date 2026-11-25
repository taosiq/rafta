"""Realistic synthetic SME dataset (a home & kitchen retailer) for demos and tests.

Demand patterns are mixed on purpose so every model and every ABC/XYZ cell gets exercised:
smooth, weekly-seasonal, yearly-seasonal, trending, intermittent and promo-driven SKUs, with
log-normal price and volume so revenue follows a Pareto-like curve.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

CATEGORIES = {
    "Kitchen": [
        "Chef Knife",
        "Cutting Board",
        "Frying Pan",
        "Saucepan",
        "Mixing Bowl",
        "Spatula",
        "Grater",
        "Coffee Press",
        "Kettle",
        "Toaster",
        "Blender",
        "Measuring Cups",
    ],
    "Tableware": [
        "Dinner Plate",
        "Ceramic Mug",
        "Wine Glass",
        "Tumbler",
        "Serving Bowl",
        "Cutlery Set",
        "Teapot",
        "Placemat",
    ],
    "Home": [
        "Throw Blanket",
        "Cushion Cover",
        "Candle",
        "Picture Frame",
        "Wall Clock",
        "Vase",
        "Doormat",
        "Storage Box",
    ],
    "Bath": ["Bath Towel", "Hand Towel", "Shower Curtain", "Soap Dispenser", "Bath Mat", "Toothbrush Holder"],
    "Lighting": ["Desk Lamp", "Floor Lamp", "LED Bulb", "String Lights", "Lamp Shade"],
    "Garden": ["Plant Pot", "Watering Can", "Garden Gloves", "Pruning Shears", "Bird Feeder", "Hose Nozzle"],
}
ADJECTIVES = ["Classic", "Nordic", "Essential", "Premium", "Rustic", "Modern", "Compact", "Deluxe", "Eco", "Studio"]
PATTERNS = ["smooth", "weekly", "yearly", "trend", "intermittent", "promo"]


def generate(n_skus: int = 150, days: int = 730, end: date | None = None, seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    end = end or date.today() - timedelta(days=1)
    dates = pd.date_range(end - timedelta(days=days - 1), end, freq="D")
    dow = dates.dayofweek.to_numpy()
    doy = dates.dayofyear.to_numpy()

    names: set[str] = set()
    products, sales_frames, stock = [], [], []
    for i in range(n_skus):
        category = rng.choice(list(CATEGORIES))
        while True:
            name = f"{rng.choice(ADJECTIVES)} {rng.choice(CATEGORIES[category])}"
            if name not in names or len(names) > 400:
                break
        if name in names:
            name = f"{name} {i}"
        names.add(name)

        price = float(np.round(np.exp(rng.normal(3.0, 0.8)), 2))
        cost = float(np.round(price * rng.uniform(0.42, 0.68), 2))
        pattern = rng.choice(PATTERNS, p=[0.22, 0.22, 0.14, 0.12, 0.18, 0.12])
        base = float(np.exp(rng.normal(1.2, 1.0)))  # mean units per day

        weekly = 1 + rng.uniform(0.1, 0.45) * np.array([-0.3, -0.2, -0.1, 0.0, 0.2, 0.6, 0.4])[dow]
        if pattern == "smooth":
            lam = base * (1 + 0.05 * weekly - 0.05)
        elif pattern == "weekly":
            lam = base * weekly
        elif pattern == "yearly":
            peak = rng.integers(1, 366)
            lam = base * weekly * (1 + rng.uniform(0.4, 0.8) * np.cos(2 * np.pi * (doy - peak) / 365.25))
        elif pattern == "trend":
            lam = base * weekly * np.linspace(1 - rng.uniform(0, 0.3), 1 + rng.uniform(0.3, 0.9), days)
        elif pattern == "promo":
            lam = base * weekly
            for start in rng.choice(days - 10, size=rng.integers(3, 8), replace=False):
                lam[start : start + rng.integers(3, 8)] *= rng.uniform(2, 4)
        else:  # intermittent
            lam = np.zeros(days)

        if pattern == "intermittent":
            occurs = rng.random(days) < rng.uniform(0.04, 0.3)
            qty = np.where(occurs, rng.lognormal(np.log(max(base, 1.0)) + 0.5, 0.6, days), 0.0)
            qty = np.round(qty)
        else:
            # Negative binomial: Poisson with gamma-distributed rate -> over-dispersion
            shape = rng.uniform(3, 15)
            qty = rng.poisson(rng.gamma(shape, np.maximum(lam, 1e-6) / shape))

        sku = f"SKU-{1000 + i}"
        lead = int(rng.choice([3, 5, 7, 7, 10, 14, 21]))
        products.append(
            {
                "sku": sku,
                "name": name,
                "category": category,
                "unit_cost": cost,
                "unit_price": price,
                "lead_time_days": lead,
                "lead_time_std_days": round(float(lead * rng.uniform(0, 0.3)), 1),
                "order_cost": float(rng.choice([25, 40, 60, 80, 120])),
                "holding_rate": round(float(rng.uniform(0.18, 0.32)), 2),
                "moq": int(rng.choice([1, 1, 5, 6, 10, 12, 24])),
            }
        )
        sales_frames.append(pd.DataFrame({"date": dates.date, "sku": sku, "quantity": qty.astype(int)}))

        recent = float(qty[-56:].mean())
        # Cover relative to lead time: ~10% critical, ~15% near the reorder point, rest healthy.
        cover_days = rng.choice(
            [rng.uniform(0, 0.8) * lead, rng.uniform(1.0, 1.4) * lead, rng.uniform(1.8 * lead + 7, 2 * lead + 50)],
            p=[0.10, 0.15, 0.75],
        )
        stock.append(
            {
                "date": end,
                "sku": sku,
                "on_hand": int(round(recent * cover_days)),
                "on_order": int(round(recent * lead)) if rng.random() < 0.2 else 0,
            }
        )

    sales = pd.concat(sales_frames, ignore_index=True)
    sales = sales[sales["quantity"] > 0]  # store only non-zero days, like a real POS export
    return {"products": pd.DataFrame(products), "sales": sales, "stock": pd.DataFrame(stock)}
