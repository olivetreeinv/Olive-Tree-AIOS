"""
MFS Deal Desk — underwriting engine.

Vendored from Olive Tree AIOS `scripts/deal_analysis.py` (2026-07-28) with one
structural change: THRESHOLDS / BUY_BOX module globals are replaced by an
explicit `criteria` dict so the engine is multi-tenant-safe. The math is
byte-identical to the source — tests/test_parity.py guards against drift.

criteria = {
    "thresholds": {coc_yr3, irr, equity_multiple, dscr, rule_75_pct, min_units},
    "buy_box": {zip: {market, ppu_min, ppu_max}, ...},
}
"""

from types import SimpleNamespace

# ── MFS defaults (from the Multifamily Schooled curriculum / knowledge base) ──

DEFAULT_THRESHOLDS = {
    "coc_yr3":         0.06,   # ≥6% cash-on-cash by year 3-4
    "irr":             0.16,   # ≥16% property (levered) IRR
    "equity_multiple": 1.80,   # ≥1.8x floor (target 2.09x)
    "dscr":            1.25,   # ≥1.25 (fully amortized)
    "rule_75_pct":     0.75,   # all-in ≤ 75% of stabilized value
    "min_units":       5,      # analyze 5+ doors; 15-50 preferred
}

# Default buy box is EMPTY — each member defines their own markets in the
# buy-box wizard. An empty buy box means "no zip restriction" (see score_deal).
DEFAULT_BUY_BOX = {}

# MFS expense fallbacks — proforma column only, used when no OM/T-12 actual exists.
MFS_RM_PER_UNIT       = 750
MFS_TURNOVER_PER_UNIT = 450
MFS_MGMT_PCT          = 0.08
MFS_RESERVES_PER_UNIT = 250

# TN/GA/AL reassess county-wide on a cycle, NOT on sale — proforma taxes are the
# current actual drifted for cycle inflation, never price-scaled.
TAX_INFLATION = 1.03


def default_criteria():
    return {"thresholds": dict(DEFAULT_THRESHOLDS), "buy_box": {}}


def _crit(criteria):
    c = criteria or {}
    thresholds = {**DEFAULT_THRESHOLDS, **(c.get("thresholds") or {})}
    buy_box = c.get("buy_box") or {}
    return thresholds, buy_box


def mfs_expense_ratio_mid(vintage):
    """Midpoint of the MFS vintage expense-ratio band (pre-1980: 45-50%,
    1980-2010: 35-45%, 2010+: 30-40%). Unknown vintage → pre-1980 band."""
    try:
        v = int(vintage) if vintage else 0
    except (TypeError, ValueError):
        v = 0
    return 0.475 if v < 1980 else 0.40 if v < 2010 else 0.35


def mfs_expense_backfill(egi_pf, known_opex, vintage, unsourced):
    """Plug unsourced soft expense lines so total proforma opex lands on the MFS
    vintage-band midpoint. `unsourced` = keys from ('utilities', 'admin',
    'contracts', 'marketing'). Returns {key: annual $}."""
    weights = {"utilities": 0.60, "admin": 0.15, "contracts": 0.15, "marketing": 0.10}
    residual = egi_pf * mfs_expense_ratio_mid(vintage) - known_opex
    if residual <= 0 or not unsourced:
        return {}
    wsum = sum(weights[k] for k in unsourced)
    return {k: round(residual * weights[k] / wsum, 0) for k in unsourced}


# ── Core math ──

def _compute_irr(cash_flows, tol=1e-7, max_iter=200):
    """Newton-Raphson IRR on annual cash flows. Returns None if no convergence."""
    if len(cash_flows) < 2 or cash_flows[0] >= 0:
        return None
    for guess in (0.10, 0.05, 0.20, 0.30, 0.01, -0.05):
        r = guess
        try:
            for _ in range(max_iter):
                npv  = sum(cf / (1 + r) ** t for t, cf in enumerate(cash_flows))
                dnpv = -sum(t * cf / (1 + r) ** (t + 1) for t, cf in enumerate(cash_flows) if t)
                if abs(dnpv) < 1e-12:
                    break
                r2 = r - npv / dnpv
                if abs(r2 - r) < tol:
                    if -0.99 < r2 < 10.0:
                        return r2
                    break
                r = r2
        except (OverflowError, ZeroDivisionError, ValueError):
            continue
    return None


def _pi_payment(loan, rate_annual, amort_years):
    """Monthly P+I payment on a fully-amortizing loan."""
    r = rate_annual / 12
    n = amort_years * 12
    if r == 0 or n == 0:
        return loan / max(n, 1)
    return loan * r * (1 + r) ** n / ((1 + r) ** n - 1)


def _loan_balance(loan, rate_annual, amort_years, months_paid):
    """Remaining balance after `months_paid` P+I payments."""
    r  = rate_annual / 12
    pmt = _pi_payment(loan, rate_annual, amort_years)
    if r == 0:
        return max(0.0, loan - pmt * months_paid)
    return max(0.0, loan * (1 + r) ** months_paid - pmt * ((1 + r) ** months_paid - 1) / r)


def solve_dscr_price(noi, ltv, rate_annual, amort_years, target_dscr=1.25):
    """Back-solve the max defensible purchase price at which Year-1 DSCR equals
    target_dscr, using FULLY-AMORTIZED debt service (banks underwrite amortized,
    not I/O)."""
    if not noi or noi <= 0 or not ltv:
        return None
    annual_ds_target = noi / target_dscr
    monthly_pmt_target = annual_ds_target / 12
    pmt_factor = _pi_payment(1.0, rate_annual, amort_years)
    if pmt_factor <= 0:
        return None
    loan = monthly_pmt_target / pmt_factor
    return loan / ltv


def calculate_metrics(inputs, criteria=None):
    """
    Core underwriting aligned with the MFS Deal Analyzer spreadsheet.

    `inputs` — dict or namespace. Required: asking, units.
    Key defaults (match spreadsheet): ltv=0.70, bridge_rate=0.0675, hold_years=6,
      vacancy_pct=0.10, closing_costs_pct=0.06, io_years=2, amort_years=25
    """
    thresholds, buy_box = _crit(criteria)
    args = SimpleNamespace(**inputs) if isinstance(inputs, dict) else inputs

    asking        = args.asking
    offer         = getattr(args, 'offer', None) or asking
    units         = args.units
    repair        = getattr(args, 'repair', 0) or 0

    ltv           = getattr(args, 'ltv', None) or 0.70
    closing_pct   = getattr(args, 'closing_costs_pct', None) or 0.06
    interest_rate = getattr(args, 'bridge_rate', None) or 0.0675
    io_years      = _default(args, 'io_years', 2)
    amort_years   = _default(args, 'amort_years', 25)
    hold_years    = _default(args, 'hold_years', 6)
    vacancy_pct   = _default(args, 'vacancy_pct', 0.10)
    rent_growth   = _default(args, 'rent_growth', 0.03)
    expense_growth = _default(args, 'expense_growth', 0.02)
    other_income_annual = (getattr(args, 'other_income', 0) or 0)
    selling_costs_pct = 0.05

    current_gpr_mo  = getattr(args, 'current_gpr', None)   # monthly
    market_gpr_mo   = getattr(args, 'market_gpr', None)    # monthly (proforma)
    current_opex_mo = getattr(args, 'current_opex', None)  # monthly
    entry_cap       = getattr(args, 'entry_cap', None)
    exit_cap        = getattr(args, 'exit_cap', None)
    vintage         = getattr(args, 'vintage', None)

    # ── Sources & uses ──
    loan_amount   = offer * ltv
    equity_invest = offer * (1 - ltv) + repair + offer * closing_pct
    all_in        = offer + repair + offer * closing_pct

    # ── Debt service ──
    io_pmt_annual  = loan_amount * interest_rate
    pi_pmt_annual  = _pi_payment(loan_amount, interest_rate, amort_years) * 12

    # ── Annualised rents ──
    current_gpr_annual = (current_gpr_mo * 12) if current_gpr_mo else None
    market_gpr_annual  = (market_gpr_mo * 12)  if market_gpr_mo  else current_gpr_annual
    current_opex_annual = (current_opex_mo * 12) if current_opex_mo else None

    # Spreadsheet: yr1 = current rents, yr2 steps up to proforma rents
    yr1_gpr = current_gpr_annual or market_gpr_annual or 0
    yr2_gpr = market_gpr_annual  or current_gpr_annual or 0

    # Proforma opex baseline (yr1); grows 2%/yr after
    if current_opex_annual:
        proforma_opex = current_opex_annual
    elif yr2_gpr:
        proforma_opex = yr2_gpr * (1 - vacancy_pct) * 0.42  # 42% of EGI (spreadsheet avg)
    else:
        proforma_opex = 0

    # ── Current NOI & entry cap ──
    current_noi_annual = None
    if yr1_gpr and current_opex_annual:
        current_egi = yr1_gpr * (1 - vacancy_pct) + other_income_annual
        current_noi_annual = current_egi - current_opex_annual
    if entry_cap is None and current_noi_annual:
        entry_cap = (current_noi_annual / offer) * 100

    # ── Multi-year NOI & cash flows ──
    annual_noi, annual_cf, annual_ds = [], [], []
    for yr in range(1, hold_years + 1):
        if yr == 1:
            gpr = yr1_gpr
        elif yr == 2:
            gpr = yr2_gpr
        else:
            gpr = yr2_gpr * (1 + rent_growth) ** (yr - 2)
        egi  = gpr * (1 - vacancy_pct) + other_income_annual
        opex = proforma_opex * (1 + expense_growth) ** (yr - 1)
        noi  = egi - opex
        annual_noi.append(noi)
        ds = io_pmt_annual if yr <= io_years else pi_pmt_annual
        annual_ds.append(ds)
        annual_cf.append(noi - ds)

    # ── Exit / sale ──
    if exit_cap is None and entry_cap is not None:
        exit_cap = entry_cap + 0.5   # conservative cap expansion
    sale_price = net_sale_proceeds = loan_at_sale = None
    if exit_cap and exit_cap > 0 and annual_noi:
        sale_price   = annual_noi[-1] / (exit_cap / 100)
        pi_months    = max(0, hold_years - io_years) * 12
        loan_at_sale = _loan_balance(loan_amount, interest_rate, amort_years, pi_months)
        net_sale_proceeds = sale_price * (1 - selling_costs_pct) - loan_at_sale

    # ── Levered cash flows → IRR ──
    levered_cfs = [-equity_invest] + annual_cf[:]
    if net_sale_proceeds is not None:
        levered_cfs[-1] += net_sale_proceeds
    irr_estimate = _compute_irr(levered_cfs)

    # ── Returns ──
    coc_yr1 = annual_cf[0] / equity_invest if equity_invest and annual_cf else None
    coc_yr3 = annual_cf[2] / equity_invest if equity_invest and len(annual_cf) >= 3 else None

    equity_multiple = None
    if equity_invest and net_sale_proceeds is not None:
        total_return = sum(annual_cf) + net_sale_proceeds
        equity_multiple = total_return / equity_invest

    # ── DSCR (year 1) — banks underwrite fully-amortized debt service ──
    dscr_io        = annual_noi[0] / io_pmt_annual if annual_noi and io_pmt_annual else None
    dscr_amortized = annual_noi[0] / pi_pmt_annual if annual_noi and pi_pmt_annual else None
    dscr = dscr_amortized

    # ── Year-1 expense ratio (opex / EGI) ──
    egi_yr1 = (yr1_gpr * (1 - vacancy_pct) + other_income_annual) if yr1_gpr else None
    opex_yr1 = proforma_opex if proforma_opex else None
    expense_ratio = (opex_yr1 / egi_yr1) if (egi_yr1 and opex_yr1) else None

    # ── DSCR 1.25x max defensible offer + rate sweep ──
    noi_for_go = annual_noi[0] if annual_noi else None
    go_price = solve_dscr_price(noi_for_go, ltv, interest_rate, amort_years,
                                target_dscr=thresholds["dscr"])
    sweep_rates = []
    for r in (interest_rate, 0.0575, 0.0625, 0.0675):
        if r not in sweep_rates:
            sweep_rates.append(r)
    go_price_sweep = [
        {"rate": r, "price": solve_dscr_price(noi_for_go, ltv, r, amort_years,
                                              target_dscr=thresholds["dscr"])}
        for r in sweep_rates
    ]

    # ── Stabilized value & 75% rule ──
    stabilized_noi   = annual_noi[0] if annual_noi else None
    stabilized_value = None
    rule_75_ratio = rule_75_pass = None
    if stabilized_noi and exit_cap:
        stabilized_value = stabilized_noi / (exit_cap / 100)
        rule_75_ratio = all_in / stabilized_value
        rule_75_pass  = rule_75_ratio < thresholds["rule_75_pct"]

    # ── 1% rule ──
    ppu = offer / units
    avg_rent_mo = (current_gpr_mo / units) if current_gpr_mo else None
    rule_1pct_ratio = (avg_rent_mo / ppu) if avg_rent_mo else None
    rule_1pct_pass  = (rule_1pct_ratio >= 0.01) if rule_1pct_ratio is not None else None

    # ── 10x NOI rule ──
    rule_10x_noi  = offer / current_noi_annual if current_noi_annual else None
    rule_10x_pass = rule_10x_noi <= 10 if rule_10x_noi is not None else None

    # ── PPU vs buy box ──
    zip_str = str(getattr(args, 'zip', '') or '')
    ppu_in_range = None
    if zip_str in buy_box:
        bb = buy_box[zip_str]
        ppu_in_range = True if bb["ppu_min"] == 0 else (bb["ppu_min"] <= ppu <= bb["ppu_max"])

    return {
        "asking":            asking,
        "offer":             offer,
        "units":             units,
        "ppu":               ppu,
        "repair":            repair,
        "all_in":            all_in,
        "loan_amount":       loan_amount,
        "equity_invested":   equity_invest,
        "io_pmt_annual":     io_pmt_annual,
        "pi_pmt_annual":     pi_pmt_annual,
        "current_noi":       current_noi_annual,
        "stabilized_noi":    stabilized_noi,
        "entry_cap":         entry_cap,
        "exit_cap":          exit_cap,
        "stabilized_value":  stabilized_value,
        "sale_price":        sale_price,
        "loan_at_sale":      loan_at_sale,
        "net_sale_proceeds": net_sale_proceeds,
        "annual_noi":        annual_noi,
        "annual_cf":         annual_cf,
        "annual_ds":         annual_ds,
        "levered_cfs":       levered_cfs,
        "dscr":              dscr,
        "dscr_io":           dscr_io,
        "dscr_amortized":    dscr_amortized,
        "coc_yr1":           coc_yr1,
        "coc_yr3":           coc_yr3,
        "equity_multiple":   equity_multiple,
        "irr_estimate":      irr_estimate,
        "rule_75_ratio":     rule_75_ratio,
        "rule_75_pass":      rule_75_pass,
        "rule_1pct_ratio":   rule_1pct_ratio,
        "rule_1pct_pass":    rule_1pct_pass,
        "rule_10x_noi":      rule_10x_noi,
        "rule_10x_pass":     rule_10x_pass,
        "ppu_in_range":      ppu_in_range,
        "yr1_gpr":           yr1_gpr,
        "yr2_gpr":           yr2_gpr,
        "vintage":           vintage,
        "vacancy_pct":       vacancy_pct,
        "expense_ratio":     expense_ratio,
        "ltv":               ltv,
        "loan_rate":         interest_rate,
        "amort_years":       amort_years,
        "io_years":          io_years,
        "go_price":          go_price,
        "go_price_sweep":    go_price_sweep,
    }


def _default(args, name, default):
    v = getattr(args, name, None)
    return default if v is None else v


def score_deal(metrics, zip_str, criteria=None):
    """Returns (recommendation, passes, fails, warnings).
    recommendation: 'PURSUE_LOI' | 'MORE_INFO' | 'PASS'"""
    thresholds, buy_box = _crit(criteria)
    passes, fails, warnings = [], [], []

    def chk(label, value, threshold, direction="ge"):
        if value is None:
            warnings.append(f"{label}: N/A (missing data)")
            return
        ok = (value >= threshold) if direction == "ge" else (value <= threshold)
        fv = fmt_pct(value)     if value     < 1 else fmt_num(value,     "")
        ft = fmt_pct(threshold) if threshold < 1 else fmt_num(threshold, "")
        entry = f"{label}: {fv} (threshold: {ft})"
        (passes if ok else fails).append(entry)

    # Empty buy box = member hasn't restricted markets → no zip gate.
    if buy_box and zip_str and zip_str not in buy_box:
        fails.append(f"ZIP {zip_str} is outside your buy box")

    units = metrics.get("units")
    sub15_note = None
    if units is not None:
        if units < thresholds["min_units"]:
            fails.append(f"Unit count {units} below analysis floor of {thresholds['min_units']}")
        elif units < 15:
            sub15_note = f"Unit count {units} below 15–50 buy-box preference (OK to analyze)"

    chk("DSCR",             metrics["dscr"],            thresholds["dscr"])
    chk("Cash-on-Cash Yr3", metrics["coc_yr3"],         thresholds["coc_yr3"])
    chk("IRR (est.)",       metrics["irr_estimate"],    thresholds["irr"])
    chk("Equity Multiple",  metrics["equity_multiple"], thresholds["equity_multiple"])

    if metrics["rule_75_pass"] is not None:
        entry = f"75% Rule: {metrics['rule_75_ratio']:.1%} all-in/stabilized (threshold: <75%)"
        (passes if metrics["rule_75_pass"] else fails).append(entry)
    else:
        warnings.append("75% Rule: N/A (need stabilized value estimate)")

    if metrics["rule_1pct_pass"] is not None:
        entry = f"1% Rule: {metrics['rule_1pct_ratio']:.3%} rent/PPU (threshold: ≥1%)"
        (passes if metrics["rule_1pct_pass"] else fails).append(entry)
    else:
        warnings.append("1% Rule: N/A (need rent data)")

    if metrics.get("rule_10x_pass") is not None:
        entry = f"10x NOI Rule: {metrics['rule_10x_noi']:.1f}x offer/NOI (threshold: ≤10x)"
        (passes if metrics["rule_10x_pass"] else warnings).append(entry)

    if metrics["ppu_in_range"] is not None and not metrics["ppu_in_range"]:
        warnings.append(f"Price/unit ${metrics['ppu']:,.0f} outside buy box range for this market")

    # ── Sanity checks (MFS) ──
    try:
        v = int(metrics.get("vintage")) if metrics.get("vintage") else None
    except (TypeError, ValueError):
        v = None

    er = metrics.get("expense_ratio")
    if v is not None and er is not None:
        band = (0.45, 0.55) if v < 1980 else (0.35, 0.45) if v < 2010 else (0.30, 0.40)
        lo, hi = band
        if er < lo:
            warnings.append(f"Expense ratio {er:.1%} below MFS band {lo:.0%}-{hi:.0%} for vintage {v} — broker numbers may be understated")
        elif er > hi:
            warnings.append(f"Expense ratio {er:.1%} above MFS band {lo:.0%}-{hi:.0%} for vintage {v} — verify opex assumptions")

    vac = metrics.get("vacancy_pct")
    if v is not None and v < 1980 and vac is not None and vac < 0.10:
        warnings.append(f"Vacancy input {vac:.0%} below MFS floor: 10% for 1970s product")

    hard_fails = len(fails)
    if hard_fails == 0:
        rec = "PURSUE_LOI"
    elif hard_fails <= 2 and len(warnings) <= 2:
        rec = "MORE_INFO"
    else:
        rec = "PASS"

    if sub15_note:
        warnings.append(sub15_note)

    return rec, passes, fails, warnings


# ── Formatting ──

def fmt_pct(v):
    return f"{v:.1%}" if v is not None else "N/A"


def fmt_num(v, prefix="$"):
    if v is None:
        return "N/A"
    if isinstance(v, float) and abs(v) < 100:
        return f"{v:.2f}x"
    return f"{prefix}{v:,.0f}"


# ── Scorecard, callouts, quick verdict ──

def _light(grade):
    return {"A": "green", "B": "green", "C": "yellow", "D": "red", "F": "red"}.get(grade, "none")


def _grade_economics(irr):
    if irr is None:
        return None
    return "A" if irr >= 0.20 else "B" if irr >= 0.16 else "C" if irr >= 0.12 else "D" if irr >= 0.08 else "F"


def _grade_dscr(d):
    if d is None:
        return None
    return "A" if d >= 1.40 else "B" if d >= 1.25 else "C" if d >= 1.15 else "D" if d >= 1.00 else "F"


def _grade_basis(ppu, bb):
    """Grade price/unit against the market's buy-box band. Open band → N/A."""
    if ppu is None:
        return None, "—"
    if not bb or bb.get("ppu_min", 0) == 0:
        return None, f"${ppu:,.0f}/unit"
    lo, hi = bb["ppu_min"], bb["ppu_max"]
    note = f"${ppu:,.0f}/unit (band ${lo/1000:.0f}–{hi/1000:.0f}K)"
    if ppu <= lo:
        return "A", note
    if ppu <= (lo + hi) / 2:
        return "B", note
    if ppu <= hi:
        return "C", note
    return ("D" if ppu <= hi * 1.2 else "F"), note


def _grade_value_add(metrics):
    cur, pro = metrics.get("yr1_gpr"), metrics.get("yr2_gpr")
    if not cur or not pro or pro <= cur:
        return None, "—"
    gap = (pro - cur) / cur
    note = f"+{gap:.0%} rent lift (current→proforma)"
    return ("A" if gap >= 0.25 else "B" if gap >= 0.15 else "C" if gap >= 0.08 else "D"), note


def _grade_physical(vintage):
    try:
        v = int(vintage) if vintage else None
    except (TypeError, ValueError):
        v = None
    if not v:
        return None, "vintage unknown"
    note = f"built {v}"
    return ("A" if v >= 2000 else "B" if v >= 1990 else "C" if v >= 1980 else "D" if v >= 1970 else "F"), note


def build_scorecard(metrics, inputs, criteria=None):
    """Category letter grades. Returns [(category, grade|None, note), ...]."""
    _, buy_box = _crit(criteria)
    args = SimpleNamespace(**inputs) if isinstance(inputs, dict) else inputs
    irr, em = metrics.get("irr_estimate"), metrics.get("equity_multiple")
    econ_note = f"IRR {fmt_pct(irr)}, EM {em:.2f}x" if em else fmt_pct(irr)
    bb = buy_box.get(str(getattr(args, "zip", "") or ""))
    bg, bnote = _grade_basis(metrics.get("ppu"), bb)
    vg, vnote = _grade_value_add(metrics)
    pg, pnote = _grade_physical(getattr(args, "vintage", None))
    return [
        ("Deal Economics",   _grade_economics(irr),            econ_note),
        ("Basis (PPU)",      bg,                               bnote),
        ("Leverage / DSCR",  _grade_dscr(metrics.get("dscr")), fmt_num(metrics.get("dscr"), "")),
        ("Value-Add Upside", vg,                               vnote),
        ("Physical Risk",    pg,                               pnote),
    ]


def build_callouts(metrics, inputs, criteria=None):
    """The handful of things a coach would flag out loud."""
    thresholds, buy_box = _crit(criteria)
    args = SimpleNamespace(**inputs) if isinstance(inputs, dict) else inputs
    outs = []
    try:
        v = int(getattr(args, "vintage", None)) if getattr(args, "vintage", None) else None
    except (TypeError, ValueError):
        v = None
    if v and v < 1980:
        outs.append(f"Pre-1980 vintage ({v}) → sewer scope, electrical panel, roof age BEFORE any LOI")
    units = metrics.get("units")
    if units and units < 15:
        outs.append(f"{units} units — below 15–50 preference; every vacancy swings occupancy hard")
    d = metrics.get("dscr")
    if d is not None and d < thresholds["dscr"]:
        outs.append(f"DSCR {d:.2f} below {thresholds['dscr']:.2f} — lender will cap leverage")
    if metrics.get("rule_75_pass") is False and metrics.get("rule_75_ratio"):
        outs.append(f"All-in {metrics['rule_75_ratio']:.0%} of stabilized value — thin vs the 75% rule")
    cur, pro = metrics.get("yr1_gpr"), metrics.get("yr2_gpr")
    if cur and pro and pro > cur * 1.12:
        outs.append(f"Rent upside ~{(pro-cur)/cur:.0%} current→proforma — the value-add thesis")
    bb = buy_box.get(str(getattr(args, "zip", "") or ""))
    ppu = metrics.get("ppu")
    if bb and bb.get("ppu_min", 0) > 0 and ppu and ppu > bb["ppu_max"]:
        outs.append(f"Basis ${ppu:,.0f}/unit above the buy-box ceiling ${bb['ppu_max']:,.0f}")
    return outs


def quick_verdict(metrics, rec, inputs, criteria=None):
    """Three traffic-light lines: Basis, Returns, This Deal.
    Returns [(light, label, text), ...] with light in green|yellow|red|none."""
    thresholds, buy_box = _crit(criteria)
    args = SimpleNamespace(**inputs) if isinstance(inputs, dict) else inputs
    pairs = (("dscr", "dscr"), ("coc_yr3", "coc_yr3"),
             ("irr_estimate", "irr"), ("equity_multiple", "equity_multiple"))
    fails = sum(1 for mk, tk in pairs
                if metrics.get(mk) is not None and metrics[mk] < thresholds[tk])
    ret_light = "green" if fails == 0 else "yellow" if fails <= 2 else "red"
    ret_text = "all return floors clear" if fails == 0 else f"{fails} of 4 return floors missed"
    bb = buy_box.get(str(getattr(args, "zip", "") or ""))
    bg, bnote = _grade_basis(metrics.get("ppu"), bb)
    overall = {"PURSUE_LOI": ("green", "GO"), "MORE_INFO": ("yellow", "CONDITIONAL GO"),
               "PASS": ("red", "PASS")}[rec]
    return [
        (_light(bg),  "Basis",     bnote),
        (ret_light,   "Returns",   ret_text),
        (overall[0],  "This Deal", overall[1]),
    ]
