from encore.domain import HARD_DECLINES
from encore.simulator import Portfolio, RegimeConfig

R0 = RegimeConfig(salary_days=[1, 7, 15], salary_day_weights=[0.6, 0.3, 0.1],
                  hard_decline_rate=0.08, issuer_down_daily_prob=0.05)


def test_same_seed_same_world():
    a = Portfolio.generate(200, R0, seed=42).run_cycle(60, "c1")
    b = Portfolio.generate(200, R0, seed=42).run_cycle(60, "c1")
    assert a == b


def test_different_seed_different_world():
    a = Portfolio.generate(200, R0, seed=42).run_cycle(60, "c1")
    b = Portfolio.generate(200, R0, seed=43).run_cycle(60, "c1")
    assert a != b


def test_failures_have_both_hard_and_soft_declines():
    fails = Portfolio.generate(500, R0, seed=7).run_cycle(60, "c1")
    codes = {f.decline for f in fails}
    assert codes & HARD_DECLINES
    assert codes - HARD_DECLINES
    assert len(fails) > 50  # enough events to measure anything


def test_oracle_agrees_with_debit_on_success():
    p = Portfolio.generate(100, R0, seed=9)
    p.run_cycle(30, "c1")
    for cid in list(p.customers)[:20]:
        if p.would_succeed(cid, 999_999):
            assert p.debit(cid, 999_999) is None


# Deliberate divergence: would_succeed is the LABELING oracle (latent churn intent = unrecoverable, so training labels are conservatively pessimistic for ~5% of customers); debit is the mechanical rail every policy is measured by. Bias direction: against the learned policy, never for it. See README limitations.
def test_churn_intent_diverges_oracle_from_debit():
    p = Portfolio.generate(10, R0, seed=1)
    c = p.customers["cust_0000"]
    c.churn_intent = True
    c.revoked = False
    c.balance_paise = c.amount_paise * 2
    at_hour = 100
    assert p.would_succeed(c.customer_id, at_hour) is False
    assert p.debit(c.customer_id, at_hour) is None
