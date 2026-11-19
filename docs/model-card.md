# Model card: Offer Guard uplift model v2

## What it does

For each abandoned cart, the model estimates three numbers: the chance the shopper buys after a **plain reminder**, after a **5% offer**, and after a **10% offer**. The model does not decide anything. A fixed, visible rule in [`policy.py`](../offerguard/policy.py) turns the three numbers into an instruction for the recovery agent:

```
value of offer k = P(buy | k) × (margin − discount_k) − P(buy | reminder) × margin
```

The agent gets the offer with the highest value if it clears the merchant's minimum gain. Otherwise it sends a reminder. The second term charges each offer for the shoppers who would have bought anyway, which is the whole point of the product.

## Intended use

- **For:** a payments platform's cart-recovery agent choosing between offers a merchant has already set up.
- **Not for:** creating or raising discounts, pricing, judging fraud, or deciding who gets contacted at all. Opted-out shoppers are never contacted.

## Training data

| | |
|---|---|
| Source | The **learning phase**: carts where the action (reminder, 5%, 10%) was assigned at random, one-third each |
| Why random | A log from a flow that discounts everyone has no comparison group, so it can't show what an offer *caused*. Random assignment makes the comparison fair |
| Volume | About 3,500 randomised carts per brand over 8 weeks. One brand alone isn't enough (see the learning curve in the [README](../README.md)), so the model is trained on 16 comparable brands' randomised carts |
| Privacy | Other brands contribute cart-level signals and outcomes only. No shopper identity, contact detail or history crosses merchants. In production this would be trained on aggregated parameters rather than pooled rows |

## Inputs

| Signal | Why it is there |
|---|---|
| Cart value (log) and margin rate | Bigger carts respond more to a percentage offer; margin sets what an offer costs |
| Why the shopper left, from the agent's conversation | The strongest signal about *responsiveness*: "waiting for an offer" and "price hesitation" differ from "payment failed" |
| Orders with the brand in the last 6 months | Separates regulars, who come back anyway, from first-timers |
| 30-day abandonments, offers received, bought after an offer, bought at full price after a reminder | Recent behaviour, including whether reminders alone have worked before |
| Confirmed link to another account | Lets a "new" account inherit the history of the account it is linked to |

**Deliberately excluded:**
- **"Possible" account links and the raw risk score.** An uncertain link must never make an offer less generous, so it cannot be an input. A test checks this ([`test_possible_links_never_change_the_inputs`](../tests/test_model_and_sim.py)).
- **Any shopper data from another merchant.**
- **Hidden shopper types.** These exist only inside the simulation as ground truth.

## Architecture

A **two-part** model ([`model.py`](../offerguard/model.py)):

1. **Baseline**, "would they buy after a reminder?": gradient-boosted trees. Baseline behaviour is strongly non-linear (a regular and a window-shopper look nothing alike), and there is plenty of signal to fit it.
2. **Lift**, "how much does an offer add?": logistic regression with offer × signal interactions and strong regularisation. Lifts are a few points on top of noisy outcomes, and a flexible model fits the noise.

Constraint: a bigger offer can never lower the predicted chance of buying.

Four candidates were compared ([Evidence screen](../web/index.html) and [`experiments.model_bakeoff`](../offerguard/experiments.py)). On held-out randomised carts, their observable margin estimates overlapped within error bars, so the choice was made on reasoning and on calibration and lift ranking, not on a single winning number.

## How it is checked

| Check | What it catches | Where |
|---|---|---|
| **Random holdout** (10% of would-be offers get a reminder) | Whether offers are really adding purchases, measured without trusting the model | Overview, AI model screen |
| **Calibration gap** (predicted vs actual purchase rate by band) | Estimates drifting from reality | AI model screen |
| **Drift monitor** (predicted vs actual over the last 2 weeks) | Behaviour changing; trips the safety net at 5 points | `simulate.drift_gap` |
| **Lift ranking** (actual lift in the most vs least persuadable fifth) | A model that predicts purchases well but cannot tell who an offer moves | Bake-off |
| **Engine parity** | The dashboard's JavaScript rule disagreeing with the Python reference | AI model screen, on every page load |

**Safety net:** if the drift monitor exceeds 5 points, Offer Guard switches to reminder-first mode (a 5% offer only if the reminder fails) and alerts the merchant.

The first version of the monitor used the banded calibration gap on a 2-week window. In the simulation that raised false alarms on a healthy model: about 850 carts spread over seven bands is too few. It now uses the overall predicted-vs-actual gap (noise of about ±1.5 points), and the banded gap is kept as a diagnostic.

## Known failure modes

Each of these was produced by the stress tests:

| Situation | What happens | Mitigation |
|---|---|---|
| Shoppers all respond alike | Nothing to target; the model finds patterns in noise and **loses money** against discounting everyone | The lift-ranking check and holdout show it before scaling; don't sell to such categories |
| Fat margins (70–80%) | Almost every discount pays for itself, so blanket 10% is hard to beat | Target thin-margin merchants first |
| Agent rarely hears why the shopper left | Most of the edge disappears | Make "why did you leave?" part of the agent's script |
| Behaviour shifts | Predictions drift | Drift monitor and reminder-first fallback |
| Too little randomised data | Loses money | Pool across merchants; don't switch on until the learning phase is done |

## What is simulated and what isn't

- **Simulated:** shoppers, their true response to offers, outcomes, other brands. Every parameter is in [`config.py`](../offerguard/config.py), anchored to the shopper mix of the challenge prototype. None of it is real merchant data.
- **Real:** the model, the training procedure, the decision rule, the holdout measurement, the checks and the dashboard. They would run unchanged on real logs.
- **Not modelled:** shoppers *learning* to wait for coupons. Shoppers here don't change behaviour because of past discounts, so the long-run benefit of discounting less (breaking the coupon-waiting habit) is **not** credited to Offer Guard. The real upside is likely larger than shown, but that is a hypothesis for the pilot, not a result.

## Responsible use

- Reminders never mention discounts. Offer messages link to terms that disclose that eligibility uses order history (DPDP Act notice).
- Uncertain identity links never reduce an offer.
- The merchant can pause the system, require approval for every offer, set the minimum gain and budget, and override any decision. Every change is logged.
- My reading of the DPDP Act is a design interpretation, not legal advice.
