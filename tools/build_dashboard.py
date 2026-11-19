"""Rebuild web/index.html from the challenge prototype (challenge-submission/prototype-v1.html).

The v2 dashboard is the v1 prototype with four changes:
  * carts and model estimates load from web/data.js (written by the pipeline)
  * a new Evidence screen reads web/results.js
  * every decision is re-checked against the Python reference engine on load
  * copy updated where v1 said the estimates were simulated

Keeping it as a scripted patch makes the diff between the challenge version
and the portfolio version easy to review.

    python tools/build_dashboard.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "challenge-submission" / "prototype-v1.html"
OUT = ROOT / "web" / "index.html"
EVIDENCE_JS = Path(__file__).with_name("evidence.js").read_text(encoding="utf8")
EVIDENCE_HTML = Path(__file__).with_name("evidence.html").read_text(encoding="utf8")

PARITY_JS = r"""recompute();
const PARITY = (() => {
  const code = {none:0, small:1, full:2, no_outreach:-1};
  let same = 0, n = 0; const off = [];
  D.forEach(d => { if (d.c.act === undefined) return; n++; const a = d.holdout ? 0 : code[d.action]; if (a === d.c.act) same++; else if (off.length < 5) off.push(d.c.id); });
  const ok = n > 0 && same === n;
  if (!ok) console.warn('Offer Guard engine check: JavaScript and Python decisions differ', off);
  return {ok, same, n, text: ok ? `Every decision this dashboard computes (${n.toLocaleString('en-IN')} carts) matches the Python reference engine exactly.` : `${same.toLocaleString('en-IN')} of ${n.toLocaleString('en-IN')} decisions match the Python reference engine. First mismatches: ${off.join(', ')}.`};
})();
window.OG_PARITY = PARITY;
show('overview');"""

PATCHES = [
    ('<title>Offer Guard prototype</title>',
     '<title>Offer Guard</title>\n<meta name="description" content="Offer Guard: an AI decision layer that gives '
     'cart-recovery discounts only to shoppers they actually persuade. Working demo on simulated data.">'),
    ('<aside class="drawer" id="drawer" hidden aria-label="Cart details" role="dialog" aria-modal="true"></aside>\n\n<script>',
     '<aside class="drawer" id="drawer" hidden aria-label="Cart details" role="dialog" aria-modal="true"></aside>\n'
     '<script src="data.js"></script>\n<script src="results.js"></script>\n<script>'),
    ('<button class="nav-btn" data-view="policy"><span class="dot"></span>Policy</button>',
     '<button class="nav-btn" data-view="policy"><span class="dot"></span>Policy</button>\n'
     '    <button class="nav-btn" data-view="evidence"><span class="dot"></span>Evidence</button>'),
    ('8 weeks of abandoned carts<br>Simulated data</div>',
     '8 weeks of abandoned carts<br>Simulated shoppers, trained model<br>'
     '<a href="https://github.com/rithi-shetty/offer-guard" style="color:#fff">Source and case study ↗</a></div>'),
    ('title="All carts, shoppers and outcomes are simulated">Simulated data</span>',
     'title="Shoppers and outcomes are simulated; the AI model is trained on them">Simulated data</span>'),
    ('<p><strong>Welcome.</strong> This is a working prototype of Offer Guard, running on simulated data for a fictional '
     'skincare brand, Glow &amp; Co.</p>',
     '<p><strong>Welcome.</strong> This is Offer Guard v2. Shoppers are simulated for a fictional skincare brand, '
     'Glow &amp; Co, but every estimate on these screens comes from a trained uplift model, and '
     '<button class="linkbtn" type="button" data-go="evidence">Evidence</button> shows where it works and where it '
     'does not.</p>'),
    ('<span><strong>Model v1</strong></span>', '<span><strong>Model v2 (trained)</strong></span>'),
    ("<dt>Approach</dt><dd>An uplift model: it estimates how much an offer changes each shopper's behaviour, not just "
     "whether they will buy. Trained on outcomes, with the holdout providing the \"no offer\" comparison.</dd>",
     "<dt>Approach</dt><dd>A two-part uplift model. Boosted trees estimate whether the shopper would buy after a plain "
     "reminder; a regularised logistic model estimates how much a 5% or 10% offer adds. It is trained only on carts "
     "where the offer was assigned at random, pooled from comparable brands, so it learns what the offer caused rather "
     "than who happened to get one. A bigger offer can never lower the predicted chance of buying.</dd>"),
    ("<dt>Signals it uses</dt><dd>Cart value and margin; why the shopper left (from the recovery agent's conversation); "
     "30-day history of abandonments, offers received and full-price purchases; confirmed account links and the risk "
     "signal.</dd>",
     "<dt>Signals it uses</dt><dd>Cart value and margin; why the shopper left (from the recovery agent's conversation, "
     "when it heard one); orders with the brand in the last 6 months; 30-day history of abandonments, offers received "
     "and full-price purchases; history from confirmed linked accounts.</dd>"),
    ("<dt>Signals it never uses</dt><dd>Data from other merchants, uncertain account links, or any shopper type label.</dd>",
     "<dt>Signals it never uses</dt><dd>Any shopper's identity or history from another merchant (other brands "
     "contribute only anonymous, randomised cart outcomes to training), the raw risk score, uncertain account links, "
     "or any shopper type label.</dd>\n            <dt>Engine check</dt><dd id=\"mp-parity\"></dd>"),
    ("Model v1, last checked against outcomes on ${new Date(T_END).toLocaleDateString('en-IN', {day:'numeric', "
     "month:'short', year:'numeric'})}. Estimates in this prototype are simulated; the checks and measurements on this "
     "screen are calculated live.",
     "Model v2, trained on ${RESULTS.meta.train_carts.toLocaleString('en-IN')} randomised carts from "
     "${RESULTS.meta.pooled_brands} brands; last checked against outcomes on ${new Date(T_END).toLocaleDateString("
     "'en-IN', {day:'numeric', month:'short', year:'numeric'})}. Shopper outcomes are simulated; the estimates come "
     "from the trained model, and every check on this screen is calculated live."),
    ("trust_new_brand:'New to the brand', waiting_for_offer:'Waiting for an offer'};",
     "trust_new_brand:'New to the brand', waiting_for_offer:'Waiting for an offer', "
     "not_captured:'Not captured (shopper did not say)'};"),
    ("Signals the model used for this cart: cart value and margin, why the shopper left, 30-day history, account "
     "links and the risk signal. Estimates are simulated in this prototype.</p></div>",
     "Signals the model used for this cart: cart value and margin, why the shopper left, orders with the brand, "
     "30-day history and confirmed account links. The risk score itself is never an input.</p></div>"),
    ("text:'Offer Guard earns more margin than discounting everyone or common fixed rules, while spending about half as "
     "much on discounts.'",
     "text:'On the same carts, Offer Guard earns more margin than discounting everyone or common fixed rules, while "
     "spending much less on discounts.'"),
    ("{view:'policy', sel:'#pol-impact', title:'You stay in control', text:'Draft a rule change and preview its "
     "projected effect before applying it. The switch at the top pauses Offer Guard at any time.'}",
     "{view:'policy', sel:'#pol-impact', title:'You stay in control', text:'Draft a rule change and preview its "
     "projected effect before applying it. The switch at the top pauses Offer Guard at any time.'},\n"
     "  {view:'evidence', sel:'#ev-head', title:'Where it works, and where it does not', text:'Stress tests, a "
     "learning curve and a pilot plan built from the same engine. The limits are shown as plainly as the wins.'}"),
    ('<div class="block"><h3>Shopper history (last 30 days)</h3><dl class="kv">',
     '<div class="block"><h3>Shopper history</h3><dl class="kv"><dt>Orders with the brand (6 months)</dt>'
     '<dd>${c.ord}</dd>'),
    ('<dt>Earlier abandoned carts</dt>', '<dt>Earlier abandoned carts (30 days)</dt>'),
    ('<dt>Bought at full price after a reminder</dt><dd>${c.pf}</dd></dl></div>',
     '<dt>Bought at full price after a reminder (30 days)</dt><dd>${c.pf}</dd></dl></div>'),
    ("const TITLES = {overview:'Overview', decisions:'Decisions', model:'AI model', policy:'Policy', "
     "guide:'Demo scenarios'};",
     "const TITLES = {overview:'Overview', decisions:'Decisions', model:'AI model', policy:'Policy', "
     "guide:'Demo scenarios', evidence:'Evidence'};"),
    ("  if (S.view === 'guide') renderGuide();\n}",
     "  if (S.view === 'guide') renderGuide();\n  if (S.view === 'evidence') renderEvidence();\n}"),
    ("  document.getElementById('mp-version').textContent",
     "  document.getElementById('mp-parity').textContent = PARITY.text;\n"
     "  document.getElementById('mp-version').textContent"),
    ('<section id="view-guide" hidden>', EVIDENCE_HTML + '\n<section id="view-guide" hidden>'),
    ("/* ---------- events ---------- */", EVIDENCE_JS + "\n/* ---------- events ---------- */"),
    ("recompute(); show('overview');", PARITY_JS),
]


def build() -> str:
    lines = SRC.read_text(encoding="utf8").split("\n")
    raw = [i for i, line in enumerate(lines) if line.startswith("const RAW = ")]
    assert len(raw) == 1, "expected one embedded data line in the prototype"
    del lines[raw[0]]
    html = "\n".join(lines)
    for old, new in PATCHES:
        if html.count(old) != 1:
            raise SystemExit(f"patch target not found exactly once: {old[:70]!r}")
        html = html.replace(old, new)
    return html


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(build(), encoding="utf8")
    print(f"wrote {OUT.relative_to(ROOT)}")
