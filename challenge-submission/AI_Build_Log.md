# AI Build Log: Offer Guard

**Razorpay AI PM Build Challenge, Track 2** | Rithika, ISB PGP

Offer Guard is an AI add-on to Razorpay's Cart Abandonment Recovery Agent that predicts, per shopper, whether a discount will change their decision. This log covers how I used AI to research, design and build it, and where I made the calls.

## 1. AI tools and models used

| Tool | Used for |
|---|---|
| **Claude Opus 5.5** (Anthropic, claude.ai) | Main partner: critique, web research, synthetic data, prototype assist, automated testing |
| **ChatGPT** | Second critique on ideas and direction |
| **Kimi Agent** | Deep research run: evidence report and academic paper lists |

Claude's built-in tools: web search and page fetching.

## 2. Key prompts and workflows

**1. Constrained ideation, cross-checked across tools.** My opening prompt set hard limits: *"if my suggested ideas are not feasible, state it; do not fabricate."* Every idea had to pass three tests: does it recover or grow merchant revenue, does Razorpay or a competitor already have it, and is there evidence of the problem? I passed outputs between tools and asked each to challenge the other.

**2. A research prompt built to prevent invented numbers.**

> *"Never invent, estimate or round a number into existence. If you cannot find a figure, write 'Not found'... Label every source by type... If a statistic is repeated across sites, trace it to its original source. If you cannot find the original, flag it as 'UNTRACEABLE — do not use'."*

**3. Spec, then build, then test.** I locked a written spec before any code. Claude generated simulated data (3,519 carts, with all assumptions listed at the top of the script) and built the prototype. Every version was syntax-checked and run through an automated browser test of all screens and controls, then reviewed by me as a merchant would use it.

## 3. An AI output I rejected and corrected

An AI research pass declared the idea "100% confirmed," citing:

- *"Cart abandonment in India is 55–65%"* and *"discounts train 30–40% of repeat buyers to abandon deliberately"*
- *"Identity linking is a 'legitimate use' under Section 6 of the DPDP Act"*

**When I checked,** neither statistic could be traced to any source, so I removed both. The legal claim was also wrong: "legitimate uses" sit in **Section 7**, a closed list that doesn't clearly cover protecting a merchant's promotion budget.

**Why it mattered:** the correction changed the product. Offer Guard now discloses eligibility checks in the brand's offer terms, and uncertain account links never reduce a discount.

**The same pattern elsewhere:** I dropped a coupon-abuse idea after finding existing Shopify apps and Razorpay's own Thirdwatch already do it, and corrected a WhatsApp cost claim against Meta's official guidelines.

## 4. What AI did versus what I decided

| AI did | I decided |
|---|---|
| Critiqued ideas | The problem (incremental margin, not recovery rate) and the merchant focus |
| Ran research and summarised sources | Verified every claim; rejected untraceable statistics |
| Assisted with prototype code and tests | The screens, the merchant journey and every product change after review |
| Suggested features | Removed ones that hurt the product: a shopper "Why no discount?" button (it invites gaming) and policy changes rewriting past decisions (history must stay intact) |
| Not applicable | Primary research: a conversation with a D2C skincare brand's marketing lead |

## 5. Limitations, risks and verification

**Limitations:** all data is simulated, and the AI's estimates are simulated rather than from a trained model; the decision logic, measurements and controls are fully working. Model retraining isn't simulated.

**Risks to validate:** how Razorpay's agent currently picks offers, and whether Thirdwatch's risk score can feed it. My reading of the DPDP Act is a design interpretation, not legal advice.

**Verification:** every external claim was traced to its original source; every figure in the note and video was cross-checked against the live prototype; each prototype version passed automated browser tests; the public link was tested in a private browser window.

*No API keys, credentials, private data or proprietary information are included.*

---

## Addendum: portfolio version (v2)

Added after the challenge, when the prototype was rebuilt as an end-to-end project.

**AI tools:** Claude (Anthropic) in Claude Code, used as a pair programmer for the simulator, model, experiments, tests and dashboard changes.

**What I decided:** what v2 had to prove (does a trained model beat the fixed rules, how much data it needs, where it fails, whether the pilot can detect the effect), the stress-test scenarios, and every product change prompted by the results ([docs/decisions.md](../docs/decisions.md), decisions 9–14).

**How it was verified:** 21 automated tests, including a check that every decision the dashboard computes in JavaScript matches the Python reference engine; every number in the README is read from `reports/results.json`, generated by one command.
