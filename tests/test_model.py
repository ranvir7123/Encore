from encore.domain import DeclineCode
from encore.model import LearnedPolicy, featurize, generate_training_data, train
from encore.simulator import RegimeConfig

R0 = RegimeConfig(salary_days=[1, 7, 15], salary_day_weights=[0.6, 0.3, 0.1],
                  hard_decline_rate=0.08, issuer_down_daily_prob=0.05)


def test_featurize_is_fixed_width_and_numeric():
    v = featurize(DeclineCode.INSUFFICIENT_FUNDS, 100, 1, 49900)
    assert len(v) == 9
    assert all(isinstance(x, float) for x in v)


def test_training_data_has_both_labels():
    # 300x3 seeds: the 200x2 world of the original plan yields only 384 rows (see BROKELOG 2026-08-31)
    X, y = generate_training_data(R0, n_customers=300, seeds=[1, 2, 3])
    assert len(X) == len(y) > 500
    assert 0.02 < sum(y) / len(y) < 0.98  # not degenerate


def test_model_beats_coin_flip_on_holdout_split():
    X, y = generate_training_data(R0, n_customers=300, seeds=[1, 2, 3])
    cut = int(len(X) * 0.8)
    clf = train(X[:cut], y[:cut])
    assert clf.score(X[cut:], y[cut:]) > 0.6


def test_learned_policy_parks_hopeless_low_amounts():
    X, y = generate_training_data(R0, n_customers=200, seeds=[1])
    clf = train(X, y)
    pol = LearnedPolicy(clf, cost_per_attempt_paise=10_000_000)  # absurd cost floor
    from encore.domain import FailedDebit
    from encore.wall import SequenceState
    failed = FailedDebit("cust_0001", "c1", 19900, DeclineCode.INSUFFICIENT_FUNDS, 100)
    state = SequenceState(DeclineCode.INSUFFICIENT_FUNDS, 0, 0, None, False)
    assert pol.propose(failed, state, 100) is None  # everything parks at that cost
