from pathlib import Path


def test_read_probe_is_read_only() -> None:
    source = Path("scripts/testnet_read_probe.py").read_text(encoding="utf-8")

    assert "get_last_price" in source
    assert "get_tick_size" in source
    assert "list_open_ocos" in source
    assert "cancel_oco" not in source
    assert "place_oco" not in source
    assert "place_market_buy" not in source
