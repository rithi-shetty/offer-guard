# Pilot plan (revised)

The challenge version proposed an 8-week pilot with 3–5 merchants, judged on incremental margin per cart. Rebuilding the product with a real model showed that pilot **could not have detected** the margin gain. This is the revised plan. Numbers are from [`reports/results.json`](../reports/results.json) (`pilot` section).

## Why the original success metric fails in a pilot

| Quantity | Effect per cart | Cart-to-cart noise | Carts per arm for 80% power |
|---|---|---|---|
| Net margin | ₹3 more | ₹377 | **258,818** |
| Discount spend | ₹16 less | ₹66 | **277** |
| Recovery rate no more than 2 points lower | 1.7 points lower | binary | **309,732** |

A 5-brand, 8-week pilot produces about **8,485 carts per arm**. That's plenty for discount spend, nowhere near enough for margin, and too few to *prove* the 2-point guardrail.

Margin is noisy because a single cart's margin swings by hundreds of rupees depending on whether the shopper bought. The gain from targeting is a few rupees a cart, spread thinly across thousands of carts.

## Revised design

**Setup.** 3–5 Magic Checkout merchants with thin-to-medium margins, a mixed shopper base, and a recovery agent that asks why the shopper left (the stress tests show these are the conditions where Offer Guard helps). Carts are split at random between the merchant's current flow and Offer Guard, with Offer Guard in **Suggest only** mode for the first week.

**Before the pilot (2 weeks).** Confirm with Razorpay how the agent picks offers today and whether Thirdwatch's score is available. Run the randomised learning phase on pooled merchants (the model needs roughly 8 brands' worth of randomised carts; see the learning curve).

**Primary readouts, judged at 8 weeks:**

1. **Discount spend per cart**, Offer Guard vs current flow. Powered within weeks. Success: down by at least 25%.
2. **Holdout-measured lift**, the extra purchase rate offers create among shoppers Offer Guard chose to discount. Success: 95% range excludes zero, and the model's expected lift sits inside it.
3. **Calibration gap** under 5 points, with no safety-net trips.

**Guardrails, reported with confidence ranges rather than as pass/fail:** recovery rate, opt-outs and complaints, override rate, discount budget. **Stop rule:** if the recovery-rate gap's 95% range lies entirely below −2 points at any weekly check.

**Margin.** Reported every week as a running estimate with its range, and pooled across pilot merchants. Treat it as a direction-of-travel signal; it becomes a proven number only at scale.

## Decision at the end

| Outcome | Decision |
|---|---|
| Discount spend down, lift confirmed, guardrails held | Scale to more merchants in the fitting segments; keep the holdout |
| Discount spend down but lift not confirmed | Extend: lift may be real but too small to see; widen the holdout |
| Lift ranking near zero, or the model's lift outside the measured range | Stop: the merchants' shoppers may respond alike (stress test: Offer Guard loses money there) |
