
from pathlib import Path
import honeyos.companion.personality_reflection_execution as execution

def test_successful_reflection_invokes_promotion_scan():
    source = Path(execution.__file__).read_text(encoding="utf-8")
    assert 'if result.status == "success":' in source
    assert "promote_eligible_candidates(home)" in source
