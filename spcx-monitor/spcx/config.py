"""Env + tunables. Everything env-overridable lives here."""
import os

from dotenv import load_dotenv

load_dotenv()

SYMBOL = os.getenv("SPCX_SYMBOL", "SPCX")
IPO_REF_PRICE = float(os.getenv("IPO_REF_PRICE", "135"))

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY", "")
DATABENTO_DATASET = "XNAS.ITCH"
PROBE_TIMEOUT_SEC = float(os.getenv("PROBE_TIMEOUT_SEC", "10"))

IMESSAGE_TO = os.getenv("NOTIFY_IMESSAGE_TO", "")  # uses existing root .env key

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_FROM", "")
TWILIO_TO = os.getenv("TWILIO_TO", "")

DB_PATH = os.getenv("SPCX_DB", "data/spcx.db")

FAST_CANDLE_SEC = 10
SLOW_CANDLE_SEC = 60

# Candle-exhaustion signal
MIN_CANDLES = 20          # warmup before the candle signal scores
ROC_PERIOD = 6            # 6 x 10s candles = 1-minute rate of change
RUN_WINDOW = 30           # candles that define "a run"
RUN_MIN_GAIN = 0.02       # +2% over RUN_WINDOW counts as a run
COMPONENT_MEMORY = 7      # candle-signal components persist over the last N closes...
COMPONENT_DECAY = 0.85    # ...decayed per candle of age, so nearby events stack

# Book-pressure signal (FULL mode only)
BOOK_LEVELS = 10
ASK_WALL_PCT = 0.01       # walls within +1% of last price count as overhead
BOOK_TREND_WINDOW_SEC = 30

# Composite blend (FULL mode); DEGRADED uses candle score only
CANDLE_WEIGHT = 0.6
BOOK_WEIGHT = 0.4

CANDLE_THRESHOLD = float(os.getenv("CANDLE_THRESHOLD", "0.7"))
BOOK_THRESHOLD = float(os.getenv("BOOK_THRESHOLD", "0.7"))
COMPOSITE_ALERT_THRESHOLD = float(os.getenv("ALERT_THRESHOLD", "0.65"))
SIGNAL_COOLDOWN_SEC = float(os.getenv("SIGNAL_COOLDOWN_SEC", "120"))

MILESTONES = [10, 20, 30, 50, 75, 100]  # % gains off IPO_REF_PRICE, fire once each
