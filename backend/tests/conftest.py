import os
import tempfile

# Trend-to-Short reads its settings once at import, so pin mock mode + a throwaway data dir before any test
# (including CreatorAi's own) imports the app. No paid API is ever called from tests.
os.environ["T2S_MOCK_MODE"] = "true"
os.environ.setdefault("T2S_DATA_DIR", tempfile.mkdtemp(prefix="t2s-test-"))
