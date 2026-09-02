import math
import pickle
import random
from pathlib import Path

from sklearn.ensemble import HistGradientBoostingClassifier

from encore.domain import (
    HOURS_PER_DAY,
    ActionKind,
    DeclineCode,
    FailedDebit,
    ProposedAction,
    day_of_month,
    hour_of_day,
)
from encore.policies import cooldown_aware_start, legal_candidate_hours
from encore.simulator import Portfolio, RegimeConfig
from encore.wall import SequenceState, WallConfig

SOFT_CODES = [DeclineCode.INSUFFICIENT_FUNDS, DeclineCode.ISSUER_DOWN,
              DeclineCode.GATEWAY_TIMEOUT]


def featurize(decline: DeclineCode, candidate_hour: int, attempt_no: int,
              amount_paise: int, failure_hour: int = 0,
              payday_flag: bool = True) -> list[float]:
    """Feature vector for one (failure, candidate hour) pair.

    payday_flag toggles the last feature, a hand-written
    `day_of_month in (1, 2, 7, 8)` indicator. That indicator is a HARDCODED
    HUMAN PRIOR, not something the model discovers: it is correct for
    r0_base (salary_days [1, 7, 15], weights [0.6, 0.3, 0.1], so 90% of
    customers are paid on day 1 or 7) and actively wrong for r1_shifted
    (salary_days [3, 10, 25], weights [0.2, 0.3, 0.5], so half are paid on
    day 25). BROKELOG entry 9 records it beating the model under shift.

    Setting payday_flag=False drops it. day_of_month survives either way, so
    payday timing remains *learnable* -- it simply stops being pre-answered.
    Appending it last keeps feature order identical in the default case, so
    a payday_flag=True model is byte-identical to the pre-change one.
    """
    onehot = [1.0 if decline == c else 0.0 for c in SOFT_CODES]
    feats = onehot + [
        float(day_of_month(candidate_hour)),
        float(hour_of_day(candidate_hour)),
        float((candidate_hour - failure_hour) / HOURS_PER_DAY),
        float(attempt_no),
        math.log(amount_paise),
    ]
    if payday_flag:
        feats.append(float(day_of_month(candidate_hour) in (1, 2, 7, 8)))
    return feats


# Moved to policies.py so the horizon-matched baselines search the IDENTICAL
# candidate set this policy does -- see policies.legal_candidate_hours. Alias
# kept so this module's own call sites read unchanged.
_legal_candidates = legal_candidate_hours


def generate_training_data(regime: RegimeConfig, n_customers: int, seeds: list[int],
                           payday_flag: bool = True) -> tuple[list[list[float]], list[int]]:
    X: list[list[float]] = []
    y: list[int] = []
    cfg = WallConfig()
    for seed in seeds:
        p = Portfolio.generate(n_customers, regime, seed=seed)
        failures = p.run_cycle(60, f"train_{seed}")
        rng = random.Random(seed * 7919)
        for f in failures:
            if f.decline not in SOFT_CODES:
                continue
            for h in rng.sample(_legal_candidates(f.at_hour, cfg), 12):
                X.append(featurize(f.decline, h, 1, f.amount_paise, f.at_hour,
                                  payday_flag=payday_flag))
                y.append(int(p.would_succeed(f.customer_id, h)))
    return X, y


def train(X, y) -> HistGradientBoostingClassifier:
    clf = HistGradientBoostingClassifier(random_state=0)
    clf.fit(X, y)
    return clf


def save(clf, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(clf))


def load(path: Path) -> HistGradientBoostingClassifier:
    return pickle.loads(path.read_bytes())


class LearnedPolicy:
    """Chooses WHEN inside the wall; never WHETHER something is allowed."""
    name = "encore_learned"

    def __init__(self, clf, cost_per_attempt_paise: int = 500,
                 payday_flag: bool = True, name: str | None = None,
                 max_hour: int | None = None) -> None:
        self.clf = clf
        self.cost = cost_per_attempt_paise
        self._cfg = WallConfig()
        # exclusive end of the evaluated period; see policies.legal_candidate_hours
        # and BROKELOG 2026-09-02. Must be the SAME bound the control gets, or
        # the horizon match this comparison rests on is broken again.
        self.max_hour = max_hour
        # must match how clf was trained, or inference silently reads a
        # different feature vector than fit() saw
        self.payday_flag = payday_flag
        if name is not None:
            self.name = name

    def propose(self, failed: FailedDebit, state: SequenceState,
                now_hour: int) -> ProposedAction | None:
        if state.retries_attempted >= self._cfg.max_retries_per_cycle:
            return None
        # start past the wall's cooldown so denied proposals don't burn retry budget; the wall still enforces
        start_hour = cooldown_aware_start(state, now_hour, self._cfg)
        candidates = _legal_candidates(start_hour - 1, self._cfg, max_hour=self.max_hour)
        # training labels only exist for attempt_no=1; passing live attempt numbers
        # would query the model out of distribution on a feature it never saw vary
        feats = [featurize(failed.decline, h, 1, failed.amount_paise, failed.at_hour,
                           payday_flag=self.payday_flag) for h in candidates]
        if not feats:
            return None
        probs = self.clf.predict_proba(feats)[:, 1]
        best = max(range(len(candidates)), key=lambda i: probs[i])
        if probs[best] * failed.amount_paise < self.cost:
            return None  # stopping rule: expected recovery below action cost
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, candidates[best],
                              state.retries_attempted + 1)
