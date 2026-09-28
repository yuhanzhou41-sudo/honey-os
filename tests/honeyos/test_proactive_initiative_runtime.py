from pathlib import Path

import honeyos.gateway.run as gateway_run


def test_gateway_seeds_personal_initiative_before_existing_reservation_flow():
    source = Path(gateway_run.__file__).read_text(encoding="utf-8")
    function_idx = source.index("def _run_topic_pool_pulse(")
    seed_idx = source.index("seed_personal_initiative_if_due(", function_idx)
    reservation_idx = source.index("reservation =", seed_idx)
    event_idx = source.index("build_proactive_event(reservation, source)", reservation_idx)
    assert function_idx < seed_idx < reservation_idx < event_idx


def test_existing_proactive_delivery_chain_is_still_the_delivery_owner():
    source = Path(gateway_run.__file__).read_text(encoding="utf-8")
    assert "_run_topic_pool_pulse" in source
    assert "build_proactive_event" in source
    assert "_register_proactive_topic_delivery_completion" in source
