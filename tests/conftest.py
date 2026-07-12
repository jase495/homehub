import os
import tempfile

os.environ.setdefault("HOMEHUB_STATE_DIR", tempfile.mkdtemp(prefix="homehub-tests-"))

