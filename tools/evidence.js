/* ---------- evidence ---------- */
function renderEvidence(){
  const R = RESULTS, St = R.strategies, all = St.discount_all, og = St.offer_guard, orc = St.oracle, rb = R.robustness;
  const signed = x => (x >= 0 ? '+' : '−') + money(Math.abs(x));
  const edge = og.exp_net - all.exp_net, saved = 1 - og.exp_disc / all.exp_disc;
  const kp = [
    ['Margin vs discount everyone', signed(edge), 'expected over 8 weeks, holdout included'],
    ['Discount spend', '−' + pct(saved), `${money(og.exp_disc)} vs ${money(all.exp_disc)}`],
    ['Orders vs discount everyone', (og.exp_orders - all.exp_orders >= 0 ? '+' : '−') + Math.abs(Math.round(og.exp_orders - all.exp_orders)), 'the price of the saving'],
    ['Ahead in fresh worlds', `${rb.wins_expected} of ${rb.n}`, `median ${signed(rb.edge_expected[1])}, ${pct(rb.captured[1])} of the ceiling`]
  ];
  document.getElementById('ev-kpis').innerHTML = kp.map(([l, v, d]) => `<div class="card kpi"><div class="label">${l}</div><div class="val">${v}</div><div class="delta">${d}</div></div>`).join('');

  const lad = [['rule_first', '10% on first abandonment only'], ['rule_value', '10% on carts of ₹1,000 or more'], ['discount_all', 'Discount everyone 10%'], ['offer_guard', 'Offer Guard'], ['oracle', 'Perfect foresight (ceiling)']];
  const mx = Math.max(...lad.map(([k]) => St[k].exp_inc_margin));
  document.getElementById('ev-ladder').innerHTML = lad.map(([k, l]) => `<div class="strat-row ${k === 'offer_guard' ? 'og' : ''}"><div class="nm">${l}<small>${money(St[k].exp_disc)} in discounts, ${Math.round(St[k].exp_orders).toLocaleString('en-IN')} orders</small></div><div class="track"><div class="fill ${k === 'offer_guard' ? '' : k === 'oracle' ? 'hold' : 'muted'}" style="width:${Math.max(0, St[k].exp_inc_margin) / mx * 100}%"></div></div><div class="v">${money(St[k].exp_inc_margin)}</div></div>`).join('');

  const L = R.learning_curve, lm = Math.max(...L.map(r => Math.abs(r.edge_holdout)), 1);
  document.getElementById('ev-curve').innerHTML = '<div class="bars">' + L.map(r => `<div class="bar-row"><div class="top"><span>${r.brands} brand${r.brands > 1 ? 's' : ''} <span style="color:var(--muted)">(${r.carts.toLocaleString('en-IN')} carts)</span></span><strong style="color:${r.edge_holdout >= 0 ? 'var(--good)' : 'var(--bad)'}">${signed(r.edge_holdout)}</strong></div><div class="track"><div class="fill ${r.edge_holdout >= 0 ? 'good' : ''}" style="width:${Math.abs(r.edge_holdout) / lm * 100}%;${r.edge_holdout < 0 ? 'background:var(--bad)' : ''}"></div></div></div>`).join('') + '</div>';
  const firstWin = L.find(r => r.edge_holdout > 0 && r.win_rate >= 0.8);
  document.getElementById('ev-curve-take').innerHTML = `<strong>Takeaway:</strong> trained on one brand's own carts, Offer Guard loses money. It needs roughly ${firstWin ? firstWin.brands : 'many'} brands' worth of randomised evidence, which is why it belongs on a payments platform that sees many merchants, not in a single-store plugin.`;

  const sv = R.signal_value, smx = Math.max(...sv.map(v => Math.abs(v.worth)), 1);
  document.getElementById('ev-signals').innerHTML = sv.map(v => `<div class="bar-row"><div class="top"><span>${v.signal}</span><strong>${signed(v.worth)}</strong></div><div class="track"><div class="fill ${v.worth >= 0 ? '' : 'muted'}" style="width:${Math.abs(v.worth) / smx * 100}%"></div></div></div>`).join('');
  const neg = sv.filter(v => v.worth < 0).map(v => v.signal.toLowerCase());
  document.getElementById('ev-signals-take').innerHTML = `<strong>Takeaway:</strong> ${sv[0].signal.toLowerCase()} is worth the most.` + (neg.length ? ` Removing ${neg.join(' or ')} slightly <em>helped</em>: at this data volume those inputs add more noise than signal, a reason to keep collecting evidence before relying on them.` : '');

  const verdict = s => { const d = s.offer_guard - s.discount_all, c = s.oracle - s.discount_all; if (d < 0) return ['b-fail', 'Loses money']; if (c <= 0) return ['b-out', 'Nothing to win']; if (d > 0.25 * c) return ['b-pass', 'Helps']; return ['b-watch', 'Barely helps']; };
  const note = {
    base: 'The world the rest of this dashboard runs on.',
    everyone_responds_alike: 'Nobody is more persuadable than anyone else, so there is nothing to target, yet the model still finds patterns in noise. The holdout and lift-ranking checks are how a team would catch this before scaling.',
    agent_rarely_hears_reason: 'Without the conversation signal most of the edge disappears: asking the shopper why they left is part of the product, not a nice-to-have.',
    thin_margins: 'When margin is thin, a blanket 10% is very expensive, so targeting pays the most. Best first merchants.',
    fat_margins: 'When margin is fat, almost every discount pays for itself and a blanket 10% is hard to beat. Weakest fit.',
    discounts_stop_working: 'Shoppers change mid-way. The safety net sees predictions drift away from outcomes and falls back to reminder-first mode.'
  };
  document.getElementById('ev-stress').innerHTML = '<thead><tr><th>World</th><th class="num">Offer Guard vs discount everyone</th><th class="num">Ceiling vs discount everyone</th><th>Verdict</th><th>What it teaches</th></tr></thead><tbody>' +
    R.stress.map(s => { const [cls, txt] = verdict(s), d = s.offer_guard - s.discount_all; return `<tr><td><strong>${s.label}</strong>${s.tripped_week ? `<br><span class="badge b-cold" style="margin-top:4px">Safety net tripped, week ${s.tripped_week}</span>` : ''}</td><td class="num">${signed(d)}</td><td class="num">${signed(s.oracle - s.discount_all)}</td><td><span class="badge ${cls}">${txt}</span></td><td class="reason">${note[s.scenario] || ''}</td></tr>`; }).join('') + '</tbody>';

  document.getElementById('ev-robust').innerHTML = `<dl class="kv"><dt>Brands simulated</dt><dd>${rb.n}</dd><dt>Offer Guard ahead (expected)</dt><dd>${rb.wins_expected} of ${rb.n}</dd><dt>Offer Guard ahead (realised, with luck)</dt><dd>${rb.wins_realised} of ${rb.n}</dd><dt>Margin vs discount everyone</dt><dd>${signed(rb.edge_expected[1])} median (10th to 90th percentile ${signed(rb.edge_expected[0])} to ${signed(rb.edge_expected[2])})</dd><dt>Discount spend saved</dt><dd>${pct(rb.disc_saved[1])} median</dd><dt>Share of the ceiling captured</dt><dd>${pct(rb.captured[1])} median, before the holdout</dd><dt>False safety-net alarms</dt><dd>${rb.false_alarms} of ${rb.n}</dd></dl>`;

  const P = R.pilot, fmtN = n => n === null ? 'not reachable' : n.toLocaleString('en-IN');
  const weeks = n => Math.max(1, Math.ceil(n * 2 / P.carts_per_week_per_brand));
  document.getElementById('ev-pilot').innerHTML = `<dl class="kv"><dt>Discount spend per cart</dt><dd>${fmtN(P.carts_per_arm_discount)} carts per arm, about ${weeks(P.carts_per_arm_discount)} week(s) for one brand</dd><dt>Margin per cart</dt><dd>${fmtN(P.carts_per_arm_margin)} carts per arm: the gain (${money(P.margin_gain_per_cart)} a cart) is small next to cart-to-cart noise (${money(P.margin_sd)})</dd><dt>Recovery rate within 2 points</dt><dd>${fmtN(P.carts_per_arm_rate)} carts per arm</dd><dt>A 5-brand, 8-week pilot</dt><dd>about ${P.pilot_carts_per_arm['5'].toLocaleString('en-IN')} carts per arm</dd></dl><div class="infobox">The pilot can prove the discount saving within weeks, but not the margin gain. So the pilot plan changed: judge it on discount spend per cart and on holdout-measured lift, report recovery rate with its confidence range as a guardrail, and treat margin as a running estimate.</div>`;

  const B = R.bakeoff;
  const KL = {two_part:'Two-part (chosen)', gbm_single:'Boosted trees', gbm_per_action:'Boosted trees, one per action', logistic:'Logistic regression'};
  document.getElementById('ev-bakeoff').innerHTML = '<thead><tr><th>Model</th><th class="num">Log loss</th><th class="num">Calibration gap</th><th class="num">Lift ranking</th><th class="num">Margin per cart vs discount all</th><th class="num">Same, from hidden truth</th></tr></thead><tbody>' +
    B.rows.map(r => `<tr class="${r.kind === B.chosen ? 'hl' : ''}"><td>${KL[r.kind] || r.kind}</td><td class="num">${r.log_loss.toFixed(4)}</td><td class="num">${(r.cal_gap * 100).toFixed(1)} pts</td><td class="num">${(r.lift_spread * 100).toFixed(1)} ± ${(r.lift_spread_se * 100).toFixed(1)} pts</td><td class="num">${signed(r.edge)} ± ${money(r.edge_se)}</td><td class="num">${signed(r.true_edge)}</td></tr>`).join('') + '</tbody>';
  document.getElementById('ev-bakeoff-take').innerHTML = `<strong>Takeaway:</strong> on ${B.n.toLocaleString('en-IN')} held-out carts the observable margin estimates overlap within their error bars, so the data alone cannot pick a winner. The two-part model was chosen on reasoning instead: trees for the baseline (strongly non-linear, plenty of signal) and a simple model for the lift (small and noisy), giving calibrated estimates and strong lift ranking. The hidden-truth column agrees, but a real team would not have it.`;
}
