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


def test_payday_flag_false_drops_exactly_one_feature():
    """The de-biased variant must differ from the default by the hardcoded
    (1, 2, 7, 8) indicator ALONE -- day_of_month has to survive, or the model
    is not merely de-biased, it is blinded to timing entirely."""
    full = featurize(DeclineCode.INSUFFICIENT_FUNDS, 100, 1, 49900, payday_flag=True)
    lean = featurize(DeclineCode.INSUFFICIENT_FUNDS, 100, 1, 49900, payday_flag=False)
    assert len(full) == len(lean) + 1
    assert full[:-1] == lean  # identical prefix: only the last feature is dropped


def test_payday_flag_default_is_backward_compatible():
    """Default must stay byte-identical to the pre-BROKELOG-9 feature vector,
    so the flagged model's published numbers remain reproducible."""
    from encore.domain import day_of_month
    v = featurize(DeclineCode.INSUFFICIENT_FUNDS, 100, 1, 49900)
    assert v == featurize(DeclineCode.INSUFFICIENT_FUNDS, 100, 1, 49900, payday_flag=True)
    assert v[-1] == float(day_of_month(100) in (1, 2, 7, 8))
