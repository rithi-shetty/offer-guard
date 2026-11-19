"""Charts for the README. Every figure is drawn from reports/results.json."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INK, MUTED, LINE = "#12284A", "#5A6B84", "#E1E7F0"
BLUE, GREEN, PURPLE, RED, AMBER = "#2F7BF5", "#16895C", "#6A4FE0", "#C63D3D", "#A86A00"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": LINE, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlecolor": INK, "axes.titlelocation": "left",
    "figure.dpi": 150, "savefig.bbox": "tight", "axes.grid": True, "grid.color": LINE, "grid.linewidth": 0.8,
})


def rs(x: float) -> str:
    return ("−" if x < 0 else "") + f"₹{abs(x):,.0f}"


def _save(fig, out: Path, name: str) -> None:
    fig.savefig(out / name, facecolor="white")
    plt.close(fig)


def strategies(R: dict, out: Path) -> None:
    S = R["strategies"]
    order = ["rule_first", "rule_value", "discount_all", "offer_guard", "oracle"]
    names = {"rule_first": "10% on first\nabandonment", "rule_value": "10% on carts\n≥ ₹1,000",
             "discount_all": "Discount\neveryone 10%", "offer_guard": "Offer Guard",
             "oracle": "Perfect\nforesight"}
    vals = [S[k]["exp_inc_margin"] for k in order]
    cols = [MUTED, MUTED, MUTED, BLUE, LINE]
    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    bars = ax.bar([names[k] for k in order], vals, color=cols, edgecolor=[c if c != LINE else MUTED for c in cols])
    bars[-1].set_linestyle("--")
    for b, v, k in zip(bars, vals, order):
        ax.text(b.get_x() + b.get_width() / 2, v, rs(v), ha="center", va="bottom", fontsize=9.5,
                color=BLUE if k == "offer_guard" else INK, fontweight="bold" if k == "offer_guard" else "normal")
    ax.set_ylabel("Extra margin vs reminders only")
    ax.set_title("Same carts, five ways to decide on a discount")
    ax.yaxis.set_major_formatter(lambda x, _: rs(x))
    _save(fig, out, "strategies.png")


def learning_curve(R: dict, out: Path) -> None:
    L = R["learning_curve"]
    x = [r["brands"] for r in L]
    fig, ax = plt.subplots(figsize=(7.6, 3.6))
    for key, col, lab in (("edge", BLUE, "Decisions alone"), ("edge_holdout", PURPLE, "With the 10% holdout")):
        y = [r[key] for r in L]
        sd = [r[key + "_sd"] for r in L]
        ax.plot(x, y, marker="o", color=col, label=lab, linewidth=2)
        ax.fill_between(x, [a - b for a, b in zip(y, sd)], [a + b for a, b in zip(y, sd)], color=col, alpha=0.12)
    ax.axhline(0, color=INK, linewidth=1)
    ax.set_xscale("log", base=2)
    ax.set_xticks(x, [str(v) for v in x])
    ax.set_xlabel("Brands whose randomised carts are pooled for training (1 = this brand alone)")
    ax.set_ylabel("Margin vs discount everyone")
    ax.yaxis.set_major_formatter(lambda v, _: rs(v))
    ax.set_title("One brand's data is not enough; a platform's is")
    ax.legend(frameon=False, loc="lower right")
    _save(fig, out, "learning_curve.png")


def uplift_quintiles(R: dict, out: Path) -> None:
    Q = R["uplift_quintiles"]
    x = [q["group"] for q in Q]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    w = 0.38
    ax.bar([i - w / 2 for i in x], [q["predicted"] * 100 for q in Q], w, color=BLUE, label="Model's predicted lift")
    ax.bar([i + w / 2 for i in x], [q["actual"] * 100 for q in Q], w, color=GREEN, label="True lift (simulation)")
    ax.set_xticks(x, ["Least\npersuadable", "2", "3", "4", "Most\npersuadable"])
    ax.set_ylabel("Extra chance of buying\nwith a 10% offer (points)")
    ax.set_title("The model ranks shoppers by how much an offer moves them")
    ax.legend(frameon=False)
    _save(fig, out, "uplift_quintiles.png")


def calibration(R: dict, out: Path) -> None:
    B = R["calibration"]["bands"]
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot([0, .7], [0, .7], color=MUTED, linestyle="--", linewidth=1)
    mx = max(b["n"] for b in B)
    ax.scatter([b["est"] for b in B], [b["act"] for b in B], s=[40 + 360 * b["n"] / mx for b in B], color=BLUE,
               alpha=.8, edgecolor="white", zorder=3)
    ax.set_xlim(0, .7), ax.set_ylim(0, .7)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("Predicted chance of buying")
    ax.set_ylabel("Actual purchase rate")
    ax.set_title(f"Calibration gap {R['calibration']['gap'] * 100:.1f} pts")
    _save(fig, out, "calibration.png")


def signal_value(R: dict, out: Path) -> None:
    V = R["signal_value"][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.barh([v["signal"] for v in V], [v["worth"] for v in V],
            color=[BLUE if v["worth"] > 0 else MUTED for v in V])
    for i, v in enumerate(V):
        ax.text(v["worth"], i, " " + rs(v["worth"]), va="center", fontsize=9.5, color=INK)
    ax.axvline(0, color=INK, linewidth=1)
    ax.xaxis.set_major_formatter(lambda x, _: rs(x))
    ax.set_xlabel("Margin lost over 8 weeks when the model is retrained without it")
    ax.set_title("What each signal is worth")
    _save(fig, out, "signal_value.png")


def frontier(R: dict, out: Path) -> None:
    F = R["frontier"]
    fig, ax1 = plt.subplots(figsize=(7.2, 3.4))
    g = [f["gain"] for f in F]
    ax1.plot(g, [f["net_vs_all"] for f in F], color=BLUE, marker="o", linewidth=2, label="Margin vs discount everyone")
    ax1.set_ylabel("Margin vs discount everyone", color=BLUE)
    ax1.yaxis.set_major_formatter(lambda x, _: rs(x))
    ax2 = ax1.twinx()
    ax2.plot(g, [f["orders_vs_all"] for f in F], color=AMBER, marker="s", linewidth=2, label="Orders vs discount everyone")
    ax2.set_ylabel("Orders vs discount everyone", color=AMBER)
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    ax1.axvline(R["meta"]["policy"]["gain"], color=MUTED, linestyle=":")
    ax1.set_xlabel("Minimum expected gain before offering (₹ per cart)")
    ax1.set_title("The merchant's dial: stricter is not always better")
    _save(fig, out, "frontier.png")


def robustness(R: dict, out: Path) -> None:
    runs = R["robustness"]["runs"]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    exp = sorted(r["edge_expected"] for r in runs)
    real = [r["edge_realised"] for r in sorted(runs, key=lambda r: r["edge_expected"])]
    ax.scatter(range(len(exp)), real, color=MUTED, s=24, label="Realised (includes luck)", zorder=2)
    ax.scatter(range(len(exp)), exp, color=BLUE, s=34, label="Expected (luck averaged out)", zorder=3)
    ax.axhline(0, color=INK, linewidth=1)
    ax.set_xticks([])
    ax.set_xlabel(f"{len(runs)} freshly simulated brands, sorted by expected result")
    ax.set_ylabel("Margin vs discount everyone")
    ax.yaxis.set_major_formatter(lambda x, _: rs(x))
    ax.set_title("Is the result luck? Re-run in new worlds")
    ax.legend(frameon=False, loc="upper left")
    _save(fig, out, "robustness.png")


def stress(R: dict, out: Path) -> None:
    S = R["stress"]
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    labels = [s["label"] for s in S][::-1]
    og = [s["offer_guard"] - s["discount_all"] for s in S][::-1]
    orc = [s["oracle"] - s["discount_all"] for s in S][::-1]
    y = range(len(S))
    ax.barh([i + 0.2 for i in y], orc, 0.38, color=LINE, edgecolor=MUTED, label="Perfect foresight")
    ax.barh([i - 0.2 for i in y], og, 0.38, color=[BLUE if v > 0 else RED for v in og], label="Offer Guard")
    ax.set_yticks(list(y), labels)
    ax.axvline(0, color=INK, linewidth=1)
    ax.xaxis.set_major_formatter(lambda x, _: rs(x))
    ax.set_xlabel("Expected margin vs discount everyone, 8 weeks")
    ax.set_title("Where Offer Guard helps, and where it does not")
    ax.legend(frameon=False, loc="lower right")
    _save(fig, out, "stress.png")


def draw_all(R: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for fn in (strategies, learning_curve, uplift_quintiles, calibration, signal_value, frontier, robustness, stress):
        fn(R, out)
