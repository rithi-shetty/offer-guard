"""The signals the model is allowed to see.

Deliberately short. Everything here is data one merchant already holds about
its own shoppers. Three things are kept out on purpose:

  * the hidden shopper type and the true probabilities (simulation only)
  * "possible" account links and the raw risk score: an uncertain link must
    never make an offer less generous, so it cannot be an input at all
  * anything from other merchants
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import REASONS

NUMERIC = ["value", "margin_rate", "pa", "po", "pbo", "pf", "orders", "linked"]
REASON_COLS = [f"reason_{r}" for r in REASONS]
FEATURES = NUMERIC + REASON_COLS

# Groups used by the "what is each signal worth?" experiment.
GROUPS = {
    "Why the shopper left (agent conversation)": REASON_COLS,
    "30-day abandonment and offer history": ["pa", "po", "pbo", "pf"],
    "Order history with the brand": ["orders"],
    "Cart value and margin": ["value", "margin_rate"],
}

LABELS = {
    "value": "Cart value", "margin_rate": "Margin rate", "pa": "Abandoned carts (30 days)",
    "po": "Offers received (30 days)", "pbo": "Bought after an offer (30 days)",
    "pf": "Bought at full price after a reminder (30 days)", "orders": "Orders in the last 6 months",
    "linked": "Confirmed link to another account",
}


def build_features(carts: pd.DataFrame, use_links: bool = True) -> pd.DataFrame:
    """Model inputs for a batch of carts.

    With `use_links=False` each account is judged on its own history only,
    which is how the "no account linking" experiment is run.
    """
    sfx = "" if use_links else "_acct"
    X = pd.DataFrame({
        "value": np.log(carts.v.to_numpy(float)),
        "margin_rate": carts.m.to_numpy(float) / carts.v.to_numpy(float),
        "pa": carts["pa" + sfx].to_numpy(float),
        "po": carts["po" + sfx].to_numpy(float),
        "pbo": carts["pbo" + sfx].to_numpy(float),
        "pf": carts["pf" + sfx].to_numpy(float),
        "orders": carts["orders" + sfx].to_numpy(float),
        "linked": carts.linked.to_numpy(float) if use_links else np.zeros(len(carts)),
    }, index=carts.index)
    for r in REASONS:
        X[f"reason_{r}"] = (carts.reason == r).to_numpy(float)
    return X[FEATURES]
