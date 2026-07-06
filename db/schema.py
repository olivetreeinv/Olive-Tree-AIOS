"""
db/schema.py — SQLAlchemy ORM models for the Olive Tree AIOS.

Tables
------
markets             — 13 active buy-box markets (seeded from references/buy-box.md)
brokers             — broker network (mirrors Google Sheets Brokers List tab)
deals               — deal pipeline (mirrors Google Sheets Deal Sourcing tab)
investors           — LP pipeline (light now; expands with /capital-raise)
investor_commitments — many-to-many soft commits (investor ↔ deal)
meetings            — Fathom-synced calls/meetings (mirrors Google Sheets Meetings tab)
decisions           — append-only policy log (mirrors decisions/log.md)
documents           — wiki/markdown index (path + frontmatter; body stays markdown)

JSON columns (analyzer, scorecard, frontmatter) store flexible document-shaped data.
All other fields are typed columns with UNIQUE / FK constraints for dedup + joins.
"""

from sqlalchemy import (
    Boolean, Column, Float, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Market(Base):
    __tablename__ = "markets"

    zip               = Column(String(10), primary_key=True)
    name              = Column(String(100), nullable=False)
    state             = Column(String(2), nullable=False)
    strategy          = Column(String(300))
    price_per_unit_low  = Column(Integer)   # USD
    price_per_unit_high = Column(Integer)   # USD; NULL = "open" per buy-box
    vintage_target    = Column(String(100))
    composite_score   = Column(Float)       # 0–100 market scorecard; NULL until researched
    scorecard         = Column(Text)        # JSON: 7-criteria scorecard dict
    red_flags         = Column(Text)
    priority          = Column(String(20))  # Active / Watch / Inactive
    last_updated      = Column(String(20))

    deals = relationship("Deal", back_populates="market")


class Broker(Base):
    __tablename__ = "brokers"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    email          = Column(String(200), unique=True)
    name           = Column(String(200))
    brokerage      = Column(String(200))
    phone          = Column(String(50))
    markets_covered = Column(Text)          # comma-separated zips or market names
    specialty      = Column(String(100))
    tier           = Column(String(5))      # A / B / C
    buy_box_sent   = Column(String(20))     # "Yes" / "No" / date string
    deals_sent     = Column(Integer, default=0)
    last_contact   = Column(String(20))
    next_followup  = Column(String(20))
    status         = Column(String(100))    # Active / Dormant / Inactive
    notes          = Column(Text)

    deals    = relationship("Deal", back_populates="broker")
    meetings = relationship("Meeting", back_populates="broker")


class Deal(Base):
    __tablename__ = "deals"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    address         = Column(String(500), unique=True, nullable=False)
    name            = Column(String(300))
    zip             = Column(String(10), ForeignKey("markets.zip"))
    broker_id       = Column(Integer, ForeignKey("brokers.id"))
    units           = Column(Integer)
    vintage         = Column(Integer)           # year built
    asking_price    = Column(Float)
    offer_price     = Column(Float)
    price_per_unit  = Column(Float)
    gpr             = Column(Float)             # gross potential rent (monthly $)
    opex            = Column(Float)             # operating expenses (monthly $)
    noi             = Column(Float)             # net operating income (annual $)
    cap_rate        = Column(Float)             # decimal (0.055 = 5.5%)
    irr             = Column(Float)             # decimal
    dscr            = Column(Float)
    equity_multiple = Column(Float)
    status          = Column(String(50))        # prospect / analyzing / loi-sent / under-contract / closed / dead
    verdict         = Column(String(50))        # PURSUE LOI / MORE INFO NEEDED / PASS
    analyzer        = Column(Text)              # JSON: Deal Analyzer outputs + assumptions
    risks           = Column(Text)
    drive_folder_url = Column(String(500))
    date_found      = Column(String(20))
    last_updated    = Column(String(20))

    market   = relationship("Market", back_populates="deals")
    broker   = relationship("Broker", back_populates="deals")
    investor_commitments = relationship("InvestorCommitment", back_populates="deal")
    meetings = relationship("Meeting", back_populates="deal")


class Investor(Base):
    __tablename__ = "investors"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(200), nullable=False)
    type        = Column(String(50))    # Individual / HNW / Family Office / Institution
    accredited  = Column(Boolean)
    contact     = Column(String(500))   # email and/or phone
    status      = Column(String(50))    # Prospect / Warm Lead / Soft Committed / Funded / Passed
    notes       = Column(Text)

    commitments = relationship("InvestorCommitment", back_populates="investor")


class InvestorCommitment(Base):
    __tablename__ = "investor_commitments"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    investor_id = Column(Integer, ForeignKey("investors.id"), nullable=False)
    deal_id     = Column(Integer, ForeignKey("deals.id"), nullable=False)
    amount      = Column(Float)
    status      = Column(String(50))    # Soft / Funded / Withdrawn

    investor = relationship("Investor", back_populates="commitments")
    deal     = relationship("Deal", back_populates="investor_commitments")


class Meeting(Base):
    __tablename__ = "meetings"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    date         = Column(String(30))
    type         = Column(String(100))      # broker call / investor pitch / market trip / lender meeting
    participants = Column(Text)
    duration     = Column(Integer)          # minutes
    summary      = Column(Text)
    action_items = Column(Text)
    fathom_link  = Column(String(500), unique=True)
    deal_id      = Column(Integer, ForeignKey("deals.id"))
    broker_id    = Column(Integer, ForeignKey("brokers.id"))

    deal   = relationship("Deal", back_populates="meetings")
    broker = relationship("Broker", back_populates="meetings")


class Decision(Base):
    __tablename__ = "decisions"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    date          = Column(String(20), nullable=False)
    title         = Column(String(300), nullable=False)
    decision_text = Column(Text)
    why           = Column(Text)
    alternatives  = Column(Text)
    owner         = Column(String(200))


class LandMarket(Base):
    """Land-wholesaling market screen (mirrors Land Markets tab). Keyed by county+zip."""
    __tablename__ = "land_markets"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    county            = Column(String(50), nullable=False)
    zip               = Column(String(10), nullable=False)
    city              = Column(String(100))
    state             = Column(String(2))
    total_parcels     = Column(Integer)
    vacant_lots       = Column(Integer)
    vacant_oos        = Column(Integer)     # vacant + out-of-state owned
    uniformity        = Column(Float)       # cookie-cutter score 0–1
    median_acres      = Column(Float)
    avg_land_value    = Column(Float)
    builders_active   = Column(String(200))
    go_nogo           = Column(String(10))  # GO / NO-GO / WATCH
    score             = Column(Float)
    notes             = Column(Text)
    date              = Column(String(20))


class LandBuilder(Base):
    """Spec builders / developers buying lots (mirrors Land Builders tab)."""
    __tablename__ = "land_builders"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    name           = Column(String(200))
    company        = Column(String(200))
    phone          = Column(String(50))
    email          = Column(String(200), unique=True)
    markets        = Column(Text)           # comma-separated zips
    lot_size_min   = Column(Float)          # acres
    lot_size_max   = Column(Float)
    price_per_lot  = Column(Float)          # or price/acre, noted in conditions
    volume_per_mo  = Column(Integer)
    conditions     = Column(Text)           # wetlands/slope/utility rules
    close_timeline = Column(String(50))
    tier           = Column(String(5))
    deals_done     = Column(Integer, default=0)
    last_contact   = Column(String(20))
    notes          = Column(Text)

    deals = relationship("LandDeal", back_populates="builder")


class LandSeller(Base):
    """Vacant-lot owners / prospects (mirrors Land Sellers tab). Keyed by parcel id."""
    __tablename__ = "land_sellers"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    parcel_id      = Column(String(60), unique=True, nullable=False)
    situs_address  = Column(String(300))
    zip            = Column(String(10))
    subdivision    = Column(String(200))
    acres          = Column(Float)
    owner_name     = Column(String(300))
    owner_addr     = Column(String(300))    # mailing
    owner_city     = Column(String(120))
    owner_state    = Column(String(2))
    owner_zip      = Column(String(10))
    out_of_state   = Column(Boolean)
    est_land_value = Column(Float)
    offer_price    = Column(Float)
    owner_phone    = Column(String(50))     # skip-traced; blank by default
    builder_target = Column(String(200))
    channel        = Column(String(20))     # mail / call
    call_status    = Column(String(50))
    last_call      = Column(String(20))
    callback_date  = Column(String(20))
    outcome        = Column(String(100))
    notes          = Column(Text)

    deals = relationship("LandDeal", back_populates="seller")


class LandDeal(Base):
    """Land deal pipeline (mirrors Land Deals tab). Keyed by parcel id."""
    __tablename__ = "land_deals"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    parcel_id        = Column(String(60), unique=True, nullable=False)
    situs_address    = Column(String(300))
    seller_id        = Column(Integer, ForeignKey("land_sellers.id"))
    builder_id       = Column(Integer, ForeignKey("land_builders.id"))
    contract_price   = Column(Float)
    assignment_price = Column(Float)
    spread           = Column(Float)
    status           = Column(String(50))   # under-contract / assigned / closing / closed / dead
    feasibility_deadline = Column(String(20))
    deal_killer_check = Column(Text)        # JSON
    title_company    = Column(String(200))
    close_date       = Column(String(20))
    profit           = Column(Float)
    referral_sent    = Column(Boolean, default=False)
    neighbors_called = Column(Boolean, default=False)
    notes            = Column(Text)

    seller  = relationship("LandSeller", back_populates="deals")
    builder = relationship("LandBuilder", back_populates="deals")


# ─────────────────────────────────────────────────────────────────────────────
# Trading Desk tables
# ─────────────────────────────────────────────────────────────────────────────

class TradingThesis(Base):
    """Research-agent output: one ranked thesis per symbol per cycle."""
    __tablename__ = "trading_theses"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    run_id      = Column(String(40), nullable=False, index=True)  # ISO timestamp of cycle
    symbol      = Column(String(20), nullable=False)
    direction   = Column(String(5), nullable=False)   # LONG / SHORT
    conviction  = Column(Float)                        # 0–1 from LLM
    rationale   = Column(Text)
    catalyst    = Column(Text)
    horizon     = Column(String(30))                   # e.g. "intraday" / "swing"
    created_at  = Column(String(30), nullable=False)


class TradingSignal(Base):
    """Quant-agent output: backtest + walk-forward metrics per thesis."""
    __tablename__ = "trading_signals"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    thesis_id       = Column(Integer, ForeignKey("trading_theses.id"), nullable=True)
    symbol          = Column(String(20), nullable=False)
    run_id          = Column(String(40), nullable=False, index=True)
    sharpe          = Column(Float)
    max_drawdown    = Column(Float)    # decimal (0.05 = 5%)
    cagr            = Column(Float)
    win_rate        = Column(Float)
    oos_sharpe      = Column(Float)    # out-of-sample (walk-forward)
    passed_gate     = Column(Boolean)  # True = cleared the quant gate
    strategy_params = Column(Text)     # JSON: indicator params used
    created_at      = Column(String(30), nullable=False)

    thesis = relationship("TradingThesis")


class TradingPosition(Base):
    """Current (and closed) paper positions."""
    __tablename__ = "trading_positions"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    symbol               = Column(String(20), nullable=False)
    side                 = Column(String(5), nullable=False)   # long / short
    qty                  = Column(Float, nullable=False)
    entry_price          = Column(Float)
    stop_price           = Column(Float)                       # current stop (ATR-based or trailing)
    initial_stop_distance = Column(Float)                     # 1R distance at entry; used as trail distance
    high_water_price     = Column(Float)                      # highest/lowest price seen (for trailing)
    entry_time           = Column(String(30))
    exit_price           = Column(Float)
    exit_time            = Column(String(30))
    pnl                  = Column(Float)
    pnl_pct              = Column(Float)
    status               = Column(String(20), default="open")  # open / closed / stopped
    signal_id            = Column(Integer, ForeignKey("trading_signals.id"))
    notes                = Column(Text)

    signal = relationship("TradingSignal")


class TradingOrder(Base):
    """Alpaca paper order log — one row per order submitted."""
    __tablename__ = "trading_orders"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    alpaca_id      = Column(String(60), unique=True)
    symbol         = Column(String(20), nullable=False)
    side           = Column(String(5), nullable=False)
    qty            = Column(Float)
    order_type     = Column(String(20))   # market / limit / stop
    limit_price    = Column(Float)
    stop_price     = Column(Float)
    filled_price   = Column(Float)
    filled_qty     = Column(Float)
    status         = Column(String(30))   # pending / filled / cancelled / rejected
    submitted_at   = Column(String(30))
    filled_at      = Column(String(30))
    position_id    = Column(Integer, ForeignKey("trading_positions.id"))

    position = relationship("TradingPosition")


class TradingEquityCurve(Base):
    """Daily snapshot: portfolio equity vs SPY benchmark."""
    __tablename__ = "trading_equity_curve"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    date            = Column(String(20), unique=True, nullable=False)
    portfolio_equity = Column(Float)
    cash            = Column(Float)
    spy_close       = Column(Float)
    spy_return_pct  = Column(Float)   # SPY cumulative from start
    port_return_pct = Column(Float)   # portfolio cumulative from start
    sharpe_running  = Column(Float)
    max_drawdown    = Column(Float)
    open_positions  = Column(Integer)
    daily_halted    = Column(Boolean, default=False)  # True if −2% halt triggered


class TradingCCPosition(Base):
    """Covered-call book positions — one row per stock lot + its short call."""
    __tablename__ = "trading_cc_positions"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    underlying      = Column(String(20), nullable=False)
    shares_qty      = Column(Integer, default=100)        # always 100-share lots
    avg_cost        = Column(Float)                       # cost basis per share
    option_symbol   = Column(String(30))                  # OCC symbol or NULL (uncovered)
    option_type     = Column(String(5))                   # call / put
    strike          = Column(Float)
    expiry          = Column(String(12))                  # YYYY-MM-DD
    premium_received = Column(Float)                      # total premium collected
    status          = Column(String(20), default="open")  # open / closed / assigned / expired
    opened_at       = Column(String(30))
    closed_at       = Column(String(30))
    realized_pnl    = Column(Float)


class Document(Base):
    """Index of wiki/markdown files. Path is the unique key; body stays on disk."""
    __tablename__ = "documents"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    path         = Column(String(1000), unique=True, nullable=False)
    category     = Column(String(50))   # deals / brokers / markets / mfs-videos / govcon-bids / skills / etc.
    deal_id      = Column(Integer, ForeignKey("deals.id"))
    broker_id    = Column(Integer, ForeignKey("brokers.id"))
    market_zip   = Column(String(10), ForeignKey("markets.zip"))
    frontmatter  = Column(Text)         # JSON: raw YAML frontmatter dict
    last_indexed = Column(String(30))

    deal   = relationship("Deal")
    broker = relationship("Broker")
    market = relationship("Market")


class Chunk(Base):
    """Heading-scoped text chunks for hybrid FTS5 + vector retrieval.

    FTS5 virtual table (chunks_fts) and vec0 virtual table (chunk_vec) are
    created separately via raw SQL in scripts/aios_index.py — SQLAlchemy ORM
    does not model virtual tables.
    """
    __tablename__ = "chunks"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    path         = Column(String(1000), nullable=False, index=True)
    layer        = Column(String(20), nullable=False)   # wiki | reference | memory
    category     = Column(String(50))                   # deals / markets / brokers / etc. (wiki) or None
    heading      = Column(String(500))                  # ## / ### heading text; None = file-level chunk
    frontmatter  = Column(Text)                         # JSON: parsed YAML frontmatter (when present)
    content      = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)   # SHA-256 of content for incremental re-index
    last_indexed = Column(String(30), nullable=False)
