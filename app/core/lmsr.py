"""
LMSR (Logarithmic Market Scoring Rule) pricing engine.

Cost function:  C(q) = b * ln(exp(q_yes/b) + exp(q_no/b))
YES price:      p = exp(q_yes/b) / (exp(q_yes/b) + exp(q_no/b))
               = 1 / (1 + exp((q_no - q_yes) / b))

Trade cost:     cost = C(q + delta) - C(q)

The b parameter controls liquidity:
  - Higher b → more liquidity, smaller price impact per trade
  - Maximum loss for market maker = b * ln(2) ≈ 0.693 * b
  - Recommended: b = 100 gives max loss of ~69 PT per market
"""
import math


def _log_sum_exp(q_yes: float, q_no: float, b: float) -> float:
    """Numerically stable log-sum-exp."""
    a = max(q_yes, q_no) / b
    return b * (a + math.log(math.exp(q_yes / b - a) + math.exp(q_no / b - a)))


def cost(q_yes: float, q_no: float, b: float) -> float:
    """LMSR cost function value at current state."""
    return _log_sum_exp(q_yes, q_no, b)


def yes_price(q_yes: float, q_no: float, b: float) -> float:
    """Current YES probability in [0, 1]."""
    # Numerically stable sigmoid
    diff = (q_no - q_yes) / b
    if diff > 500:
        return 0.0
    if diff < -500:
        return 1.0
    return 1.0 / (1.0 + math.exp(diff))


def yes_price_pct(q_yes: float, q_no: float, b: float) -> float:
    """Current YES probability in [0, 100], rounded to 2 decimals."""
    return round(yes_price(q_yes, q_no, b) * 100, 2)


def trade_cost(q_yes: float, q_no: float, b: float, delta_yes: float, delta_no: float) -> float:
    """
    Cost (in points) to buy delta_yes YES shares and delta_no NO shares.
    Positive = user pays points. Negative = user receives points (selling).
    """
    before = cost(q_yes, q_no, b)
    after = cost(q_yes + delta_yes, q_no + delta_no, b)
    return after - before


def shares_for_cost(
    q_yes: float,
    q_no: float,
    b: float,
    points: float,
    buy_yes: bool,
    tolerance: float = 1e-9,
    max_iter: int = 100,
) -> float:
    """
    Binary search: how many shares can you buy with `points` points?
    Returns the number of shares purchasable.
    """
    lo, hi = 0.0, points * 10  # upper bound: can't get more shares than points * 10

    for _ in range(max_iter):
        mid = (lo + hi) / 2
        if buy_yes:
            c = trade_cost(q_yes, q_no, b, mid, 0.0)
        else:
            c = trade_cost(q_yes, q_no, b, 0.0, mid)

        if abs(c - points) < tolerance:
            return mid
        elif c < points:
            lo = mid
        else:
            hi = mid

    return (lo + hi) / 2


def payout_if_yes(position_side: str, shares: float) -> float:
    """Payout when market resolves YES: YES holders get 1 PT/share, NO holders get 0."""
    return shares if position_side == "YES" else 0.0


def payout_if_no(position_side: str, shares: float) -> float:
    """Payout when market resolves NO: NO holders get 1 PT/share, YES holders get 0."""
    return shares if position_side == "NO" else 0.0


def init_q_for_price(target_price: float, b: float) -> tuple[float, float]:
    """
    Return (q_yes, q_no) such that the market starts at target_price probability.
    We fix q_no = 0 and solve: target = 1 / (1 + exp(-q_yes/b))
    => q_yes = b * ln(target / (1 - target))
    """
    if target_price <= 0 or target_price >= 1:
        raise ValueError("target_price must be in (0, 1)")
    q_yes = b * math.log(target_price / (1 - target_price))
    return q_yes, 0.0
