# Decision log

The product and AI calls behind Offer Guard. For each: what I decided, what I rejected, and what would change my mind. Decisions 1–8 come from the Razorpay challenge version. Decisions 9–13 came out of rebuilding it with a trained model, when the evidence overturned some of my earlier assumptions.

---

### 1. Measure incremental margin, not recovery rate
**Decided:** The primary metric is *incremental margin per abandoned cart*: profit from sales the offer actually caused, minus discount and message costs.
**Rejected:** Recovery rate, which every recovery tool reports.
**Why:** Recovery rate goes up with every discount, including loss-making ones. A tool optimised for it will keep discounting regulars who would have bought anyway.
**Would change my mind:** If merchants can't relate to a margin metric at all. Then I'd lead with "discount spent per extra order", which tells the same story in simpler terms.

### 2. The AI predicts; a visible rule decides
**Decided:** The model only estimates three probabilities. A one-line expected-value rule, shown in the UI with the actual numbers, makes the decision.
**Rejected:** A model that outputs "offer 10%" directly.
**Why:** A growth manager can check the arithmetic, tune one number (the minimum gain) and explain any decision to a shopper or their boss. The model can be swapped without changing what the merchant sees.

### 3. Keep a random holdout permanently
**Decided:** One in ten would-be offers gets a plain reminder instead.
**Why:** It's the only way to measure what offers add without trusting the model, and it keeps producing unbiased training data. It costs some margin: the Evidence screen shows the holdout costs roughly half of the gross edge at a 10% holdout. The merchant can see that cost and lower it.

### 4. The merchant stays in control
Suggest-only mode, overrides with logging, a pause switch that falls back to the merchant's old flow, previews before any rule change, and history that never gets rewritten. Overrides are tracked because they show what the model misses.

### 5. Uncertain identity never reduces a discount
Accounts are linked only on a shared phone or email, or a high risk score. "Possible" links are shown but never applied. In v2 they are removed from the model's inputs entirely, and a test enforces it.

### 6. Reminders never mention discounts
**Why:** Telling a shopper "no discount for you" invites gaming and resentment. I removed a "Why no discount?" button that the AI suggested.

### 7. Build on Razorpay's existing AI, not alongside it
Offer Guard reuses the recovery agent's conversation (why the shopper left) and Thirdwatch's risk score. It doesn't talk to shoppers or create offers. That keeps it a single new decision inside an existing flow.

### 8. Left out on purpose
Linking shoppers across merchants (privacy), its own fraud detection (Thirdwatch already does it), creating discounts (merchant's job), and telling shoppers why they got no discount (gaming).

---

## What changed when I rebuilt it with a real model

### 9. A learning phase before going live
**Before:** The prototype showed model estimates without saying where they would come from.
**Now:** Offer Guard needs a period where offers are assigned at random. The merchant's existing logs, where everyone got 10%, contain nobody who wasn't discounted, so nothing can be learned about what the discount *caused*.
**Product consequence:** Onboarding needs an explicit "learning" state with a cost the merchant agrees to up front.

### 10. It is a platform feature, not a plugin
**Evidence:** Trained on one brand's own randomised carts, Offer Guard **loses money** against "discount everyone". It needs roughly 8 brands' worth of evidence before it reliably wins.
**Decision:** This is why it belongs inside Razorpay, which sees thousands of merchants, and not in a single-store Shopify app. It is also a moat: a competitor with fewer merchants can't train it as well. The privacy line holds: only cart-level signals and outcomes are pooled, never shopper identities.

### 11. Pick the model on reasoning when data can't separate them
**Evidence:** Four candidate models, scored on about 55,000 held-out randomised carts. Their observable margin estimates overlapped within error bars. The model with the best log loss was *not* the one that made the most money.
**Decision:** A two-part model: trees for "would they buy anyway?" and a simple regularised model for "how much does an offer add?". The lift is small and noisy, so it gets the model least able to overfit. I documented that the data alone could not settle it.

### 12. The safety net was raising false alarms, so I changed its trigger
**Evidence:** The original trigger (banded calibration gap over two weeks) crossed 5 points on a healthy model in the base simulation. With about 850 carts spread over seven bands, the noise is too high.
**Decision:** Trigger on the overall predicted-vs-actual gap (noise of about ±1.5 points), and keep the banded gap as a diagnostic. In 20 fresh simulated brands it raised **one** false alarm. That is acceptable because the fallback, reminder-first mode, is safe and the merchant is alerted, but it is a number to watch in the pilot. In the "behaviour shifts" stress test it trips in the week of the shift and protects about ₹10,000 of margin over the remaining weeks.

### 13. The pilot can't prove what I said it would, so I redesigned it
**Evidence:** The margin gain per cart is small next to cart-to-cart noise. Detecting it at 80% power needs hundreds of thousands of carts per arm, far more than a 5-brand, 8-week pilot produces. Discount spend per cart, in contrast, is detectable in about a week.
**Decision:** See [pilot-plan.md](pilot-plan.md). Judge the pilot on discount spend per cart and holdout-measured lift. Report recovery rate as a guardrail with its confidence range. Treat margin as a running estimate that accumulates across merchants.

### 14. Where not to sell it
**Evidence (stress tests):** It helps most when margins are thin. It barely helps, or loses, when margins are fat, when every shopper responds alike, or when the agent rarely learns why the shopper left.
**Decision:** First merchants should have thin margins, mixed shopper bases and a recovery agent that asks the "why" question. That's a go-to-market filter, not a footnote.
