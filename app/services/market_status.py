from app.models.market import Market, MarketStatus

ALLOWED_TRANSITIONS: dict[MarketStatus, set[MarketStatus]] = {
    MarketStatus.OPEN: {
        MarketStatus.PENDING_RESOLUTION, MarketStatus.RESOLVED,
        MarketStatus.RESOLVED_YES, MarketStatus.RESOLVED_NO, MarketStatus.CANCELLED,
    },
    MarketStatus.PENDING_RESOLUTION: {
        MarketStatus.OPEN, MarketStatus.RESOLVED,
        MarketStatus.RESOLVED_YES, MarketStatus.RESOLVED_NO, MarketStatus.CANCELLED,
    },
    MarketStatus.CLOSED: {
        MarketStatus.OPEN, MarketStatus.RESOLVED,
        MarketStatus.RESOLVED_YES, MarketStatus.RESOLVED_NO, MarketStatus.CANCELLED,
    },
}


def apply_transition(market: Market, new_status: MarketStatus) -> None:
    if new_status == market.status:
        return  # re-afirmar el mismo estado (PATCH idempotente) no es una transición
    if new_status not in ALLOWED_TRANSITIONS.get(market.status, set()):
        raise ValueError(f"Transición no permitida: {market.status} -> {new_status}")
    market.status = new_status


def demo() -> None:
    m = Market()
    m.status = MarketStatus.OPEN
    apply_transition(m, MarketStatus.OPEN)
    assert m.status == MarketStatus.OPEN
    apply_transition(m, MarketStatus.PENDING_RESOLUTION)
    assert m.status == MarketStatus.PENDING_RESOLUTION
    apply_transition(m, MarketStatus.RESOLVED_YES)
    assert m.status == MarketStatus.RESOLVED_YES
    try:
        apply_transition(m, MarketStatus.OPEN)
    except ValueError:
        pass
    else:
        raise AssertionError("debió rechazar RESOLVED_YES -> OPEN")


if __name__ == "__main__":
    demo()
    print("OK")
