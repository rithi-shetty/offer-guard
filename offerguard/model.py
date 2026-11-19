"""The uplift model: P(buy | shopper signals, action) for all three actions.

An ordinary conversion model answers "will this shopper buy?". That is the
wrong question here: a loyal customer scores high and would get a discount she
never needed. An uplift model answers "how much does the offer *change* the
chance of buying?", which is the only thing a discount can be paid for.

Training data must come from carts where the action was assigned at random
(the learning phase, and later the holdout). Logs from a flow that discounts
everyone contain no shopper who was *not* offered a discount, so there is
nothing to compare against.

Four candidates are compared in experiments.model_bakeoff. All share one
product constraint: a larger offer can never lower the predicted chance of
buying.

The default, "two_part", splits the problem the way the decision does:

  1. Would they buy anyway?        boosted trees. Baseline behaviour is
                                   strongly non-linear (a regular and a
                                   window-shopper look nothing alike) and
                                   there is plenty of signal to fit it.
  2. How much does an offer move   regularised logistic regression. Lifts are
     them?                         a few points on top of noisy outcomes; a
                                   flexible model fits the noise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

KINDS = {
    "two_part": "Boosted trees for the baseline, logistic regression for the lift",
    "gbm_single": "One boosted-tree model, offer size as a monotonic input",
    "gbm_per_action": "Three boosted-tree models, one per action",
    "logistic": "Logistic regression with offer x signal interactions",
}


def _gbm(n_features: int, monotone_last: bool, seed: int):
    cst = [0] * n_features + ([1] if monotone_last else [])
    return HistGradientBoostingClassifier(
        max_depth=3, learning_rate=0.06, max_iter=160, min_samples_leaf=25,
        l2_regularization=1.0, monotonic_cst=cst, early_stopping=False, random_state=seed)


class UpliftModel:
    def __init__(self, kind: str = "two_part", seed: int = 0):
        if kind not in KINDS:
            raise ValueError(f"unknown model kind: {kind}")
        self.kind, self.seed = kind, seed
        self.columns: list[str] = []
        self.n_train = 0

    # ------------------------------------------------------------------ fit
    def fit(self, X: pd.DataFrame, action, bought) -> "UpliftModel":
        """X: signals. action: 0 reminder, 1 for 5%, 2 for 10%. bought: 0/1."""
        self.columns = list(X.columns)
        self.n_train = len(X)
        action, bought = np.asarray(action), np.asarray(bought)
        if self.kind == "two_part":
            self._base = UpliftModel("gbm_single", self.seed).fit(X, action, bought)
            self._lift = UpliftModel("logistic", self.seed).fit(X, action, bought)
        elif self.kind == "gbm_single":
            self._m = _gbm(X.shape[1], True, self.seed).fit(self._with_action(X, action), bought)
        elif self.kind == "gbm_per_action":
            self._m = [_gbm(X.shape[1], False, self.seed).fit(X.to_numpy()[action == a], bought[action == a])
                       for a in range(3)]
        else:
            self._m = make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000))
            self._m.fit(self._interactions(X, action), bought)
        return self

    # -------------------------------------------------------------- predict
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """(n, 3) array: chance of buying with a reminder, a 5% offer, a 10% offer."""
        X = X[self.columns]
        n = len(X)
        if self.kind == "two_part":
            base, lift = self._base.predict(X)[:, [0]], self._lift.predict(X)
            p = np.clip(base + (lift - lift[:, [0]]), 0.0, 1.0)
        elif self.kind == "gbm_per_action":
            p = np.column_stack([m.predict_proba(X.to_numpy())[:, 1] for m in self._m])
        else:
            build = self._with_action if self.kind == "gbm_single" else self._interactions
            p = np.column_stack([self._m.predict_proba(build(X, np.full(n, a)))[:, 1] for a in range(3)])
        # Product constraint: a bigger offer never lowers the chance of buying.
        return np.maximum.accumulate(p, axis=1)

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _with_action(X: pd.DataFrame, action) -> np.ndarray:
        return np.column_stack([X.to_numpy(), np.asarray(action, float)])

    @staticmethod
    def _interactions(X: pd.DataFrame, action) -> np.ndarray:
        x = X.to_numpy()
        any_offer = (np.asarray(action) >= 1).astype(float)[:, None]
        full_offer = (np.asarray(action) == 2).astype(float)[:, None]
        return np.column_stack([x, any_offer, full_offer, x * any_offer, x * full_offer])
