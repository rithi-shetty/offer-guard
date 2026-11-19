"""Every assumption behind the simulated world, in one place.

Nothing in this file is real merchant data. The numbers describe a fictional
D2C skincare brand ("Glow & Co") and are anchored to the shopper mix used in
the original challenge prototype. Change them here and re-run the pipeline to
see how the conclusions move; `SCENARIOS` at the bottom does exactly that for
the stress tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

# What Offer Guard can tell the recovery agent to do.
ACTIONS = ("none", "small", "full")          # reminder only, 5% offer, 10% offer
DISCOUNT = {"none": 0.0, "small": 0.05, "full": 0.10}

# Cost of contacting a shopper: two messages per abandoned cart (in rupees).
MSG_COST = 0.8631
MSGS = 2

# Hidden shopper types. The model never sees these labels; it only sees the
# signals in features.py. They exist so the simulation has a ground truth.
TYPES = ("loyal_repeat", "hesitant_new", "price_sensitive", "discount_seeker", "low_intent")

# Why the shopper left, as reported by the recovery agent's conversation.
# "not_captured" means the shopper never told the agent.
REASONS = (
    "comparing", "delivery_time", "got_distracted", "just_browsing", "payment_issue",
    "price_hesitation", "shipping_cost", "trust_new_brand", "waiting_for_offer", "not_captured",
)


@dataclass(frozen=True)
class Policy:
    """The rules a merchant controls. Mirrors the Policy screen of the dashboard."""
    small: bool = True        # may the agent use the 5% offer?
    full: bool = True         # may the agent use the 10% offer?
    gain: float = 5.0         # minimum expected extra margin (rupees) before offering
    hold: int = 10            # % of would-be-discounted carts held out for measurement
    budget: float = 50_000.0  # monthly discount budget (rupees)
    cold: bool = False        # new-merchant mode: reminder first, 5% only if no response


@dataclass(frozen=True)
class World:
    """Parameters of the simulated merchant."""
    seed: int = 2026
    live_start: str = "2026-08-01"
    weeks_warmup: int = 4      # merchant's old flow: 10% to every abandoned cart
    weeks_learning: int = 8    # offers randomised so the model has unbiased data
    weeks_live: int = 8        # Offer Guard decides

    # Returning shoppers: (how many, abandoned carts per week each).
    residents: dict = field(default_factory=lambda: {
        "loyal_repeat": (350, 0.25),
        "price_sensitive": (230, 0.26),
        "discount_seeker": (225, 0.70),
    })
    # New shoppers: (arrivals per week, average extra carts after the first).
    transients: dict = field(default_factory=lambda: {
        "hesitant_new": (60, 0.45),
        "low_intent": (30, 0.45),
    })

    # True chance of buying after a plain reminder, and the absolute lift from
    # a 5% and a 10% offer, for an average shopper of each type.
    base: dict = field(default_factory=lambda: {
        #                   p(reminder)  +5% offer  +10% offer
        "loyal_repeat":    (0.43,        0.010,     0.020),
        "hesitant_new":    (0.06,        0.040,     0.100),
        "price_sensitive": (0.07,        0.030,     0.110),
        "discount_seeker": (0.34,        0.060,     0.090),
        "low_intent":      (0.022,       0.002,     0.004),
    })
    shopper_sd_p0: float = 0.20    # person-to-person spread in baseline (log scale)
    shopper_sd_lift: float = 0.30  # person-to-person spread in discount response

    # Why each type tends to leave. Overlapping on purpose: the reason is a
    # useful but noisy signal, not a label.
    reason_given_type: dict = field(default_factory=lambda: {
        "loyal_repeat":    {"got_distracted": .34, "payment_issue": .26, "comparing": .16, "delivery_time": .10,
                            "price_hesitation": .06, "shipping_cost": .05, "just_browsing": .03},
        "hesitant_new":    {"trust_new_brand": .30, "price_hesitation": .28, "delivery_time": .14, "comparing": .12,
                            "shipping_cost": .10, "got_distracted": .04, "just_browsing": .02},
        "price_sensitive": {"price_hesitation": .40, "shipping_cost": .32, "comparing": .12, "waiting_for_offer": .08,
                            "delivery_time": .04, "got_distracted": .04},
        "discount_seeker": {"waiting_for_offer": .38, "price_hesitation": .34, "comparing": .10, "shipping_cost": .08,
                            "got_distracted": .06, "just_browsing": .04},
        "low_intent":      {"just_browsing": .46, "comparing": .30, "got_distracted": .10, "price_hesitation": .06,
                            "delivery_time": .05, "trust_new_brand": .03},
    })
    # The reason also shifts behaviour a little within a type.
    reason_lift_mult: dict = field(default_factory=lambda: {
        "price_hesitation": 1.25, "shipping_cost": 1.25, "waiting_for_offer": 1.15, "comparing": 1.0,
        "trust_new_brand": 0.8, "delivery_time": 0.7, "got_distracted": 0.7, "just_browsing": 0.6, "payment_issue": 0.5,
    })
    reason_p0_mult: dict = field(default_factory=lambda: {
        "payment_issue": 1.10, "got_distracted": 1.05, "waiting_for_offer": 0.90, "just_browsing": 0.60,
    })
    heard_rate: float = 0.75       # share of carts where the agent learns the reason
    reason_mislabel: float = 0.0   # share of heard reasons the agent gets wrong (stress test)

    # Carts.
    value_median: float = 1110.0
    value_sd: float = 0.55         # log scale
    value_range: tuple = (399, 4999)
    margin_rate: tuple = (0.55, 0.65)
    value_lift_range: tuple = (0.8, 1.2)   # bigger carts respond a little more to a % offer
    optout_rate: float = 0.016

    # Order history with the brand in the last 6 months (average count by type).
    orders_180d: dict = field(default_factory=lambda: {
        "loyal_repeat": 4.0, "price_sensitive": 0.8, "discount_seeker": 1.5, "hesitant_new": 0.0, "low_intent": 0.1,
    })

    # Second accounts: some discount-seekers open one to look like a new shopper.
    alt_account_share: float = 0.45   # share of discount-seekers who have one
    alt_use: float = 0.50             # how often they use it
    alt_shared_contact: tuple = (0.35, 0.25)   # same phone, same email
    link_confirm_score: float = 0.50  # risk score at or above this confirms a link
    link_possible_score: float = 0.30 # between the two is "possible": never applied

    # Stress-test switches.
    homogeneous: bool = False         # everyone responds identically to discounts
    drift_week: int | None = None     # live week (1-based) from which behaviour shifts
    drift_p0_mult: float = 1.0
    drift_lift_mult: float = 1.0

    @property
    def weeks_total(self) -> int:
        return self.weeks_warmup + self.weeks_learning + self.weeks_live


BASE = World()

# Alternative worlds for the stress tests in experiments.py.
SCENARIOS = {
    "base": BASE,
    "everyone_responds_alike": replace(BASE, homogeneous=True),
    "agent_rarely_hears_reason": replace(BASE, heard_rate=0.30, reason_mislabel=0.25),
    "thin_margins": replace(BASE, margin_rate=(0.25, 0.35)),
    "fat_margins": replace(BASE, margin_rate=(0.70, 0.80)),
    "discounts_stop_working": replace(BASE, drift_week=4, drift_p0_mult=0.60, drift_lift_mult=0.25),
}

SCENARIO_LABELS = {
    "base": "Base case",
    "everyone_responds_alike": "Every shopper responds the same way",
    "agent_rarely_hears_reason": "Agent hears the reason on 30% of carts, 1 in 4 wrong",
    "thin_margins": "Thin margins (25-35%)",
    "fat_margins": "Fat margins (70-80%)",
    "discounts_stop_working": "Behaviour shifts mid-way (week 4)",
}
