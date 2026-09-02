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


# --- promise noise (regime R3) -------------------------------------------------
# The digest below was computed on the simulator BEFORE promise_error_days /
# false_promise_rate existed (commit 5e54b3f): seed 100, 200 customers, r0_base,
# every failure's (customer, decline, hour) and every reply's (customer, hour,
# text). If it ever changes, the 18 published eval cells are no longer the
# same worlds and every number in README must be regenerated.
import hashlib

PINNED_PRE_NOISE_DIGEST = "2f57720d28e10d038192ec9d0df19c7405c8fad04d67c9fa92397078d2204e03"


def _digest(regime, seed=100, n=200):
    p = Portfolio.generate(n, regime, seed=seed)
    f = p.run_cycle(30, "snap")
    payload = [(x.customer_id, str(x.decline), x.at_hour) for x in f] + \
              [(r.customer_id, r.at_hour, r.text) for r in p.reply_events()]
    return hashlib.sha256(repr(payload).encode()).hexdigest()


def test_regimes_without_noise_fields_are_byte_identical_to_the_pre_noise_simulator():
    assert _digest(RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05)) == PINNED_PRE_NOISE_DIGEST


def test_noise_fields_change_promised_days_but_nothing_else():
    clean = RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05)
    noisy = RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05,
                         promise_error_days=2, false_promise_rate=0.3)
    a, b = Portfolio.generate(200, clean, seed=100), Portfolio.generate(200, noisy, seed=100)
    fa, fb = a.run_cycle(30, "c"), b.run_cycle(30, "c")
    assert [(x.customer_id, x.at_hour) for x in fa] == [(x.customer_id, x.at_hour) for x in fb]
    ra, rb = a.reply_events(), b.reply_events()
    assert [(r.customer_id, r.at_hour) for r in ra] == [(r.customer_id, r.at_hour) for r in rb]
    assert any(x.text != y.text for x, y in zip(ra, rb, strict=True))
