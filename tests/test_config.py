import os
import subprocess
import sys


def test_assistant_can_start_without_system_timezone_database(settings):
    # Windows has no IANA system timezone files. A separate process prevents
    # another test's ZoneInfo cache from hiding a missing tzdata dependency.
    script = """
import sys
from zoneinfo import ZoneInfo
from claims_assistant.agent.runner import Assistant
from claims_assistant.config import Settings
assert ZoneInfo('Asia/Kuala_Lumpur').key == 'Asia/Kuala_Lumpur'
settings = Settings(root=sys.argv[1], runtime_dir=sys.argv[2], _env_file=None)
response = Assistant(settings).respond('I drove 25 km today')
assert response.state.claim.distance_km == 25
assert response.state.claim.expense_date is not None
assert response.state.calculation is None
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(settings.root), str(settings.runtime)],
        env={**os.environ, "PYTHONTZPATH": ""},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
