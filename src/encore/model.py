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
from encore.simulator import Portfolio, RegimeConfig
from encore.wall import SequenceState, WallConfig

SOFT_CODES = [DeclineCode.INSUFFICIENT_FUNDS, DeclineCode.ISSUER_DOWN,
              DeclineCode.GATEWAY_TIMEOUT]


def featurize(decline: DeclineCode, candidate_hour: int, attempt_no: int,
              amount_paise: int, failure_hour: int = 0) -> list[float]:
    onehot = [1.0 if decline == c else 0.0 for c in SOFT_CODES]
    return onehot + [
        float(day_of_month(candidate_hour)),
        float(hour_of_day(candidate_hour)),
        float((candidate_hour - failure_hour) / HOURS_PER_DAY),
        float(attempt_no),
        math.log(amount_paise),
        float(day_of_month(candidate_hour) in (1, 2, 7, 8)),  # near-payday flag
    ]


def _legal_candidates(failure_hour: int, cfg: WallConfig) -> list[int]:
    horizon = range(failure_hour + 1, failure_hour + 10 * HOURS_PER_DAY)
    return [h for h in horizon
            if cfg.window_start_hour <= hour_of_day(h) or hour_of_day(h) < cfg.window_end_hour]


def generate_training_data(regime: RegimeConfig, n_customers: int,
                           seeds: list[int]) -> tuple[list[list[float]], list[int]]:
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
                X.append(featurize(f.decline, h, 1, f.amount_paise, f.at_hour))
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

    def __init__(self, clf, cost_per_attempt_paise: int = 500) -> None:
        self.clf = clf
        self.cost = cost_per_attempt_paise
        self._cfg = WallConfig()

    def propose(self, failed: FailedDebit, state: SequenceState,
                now_hour: int) -> ProposedAction | None:
        if state.retries_attempted >= self._cfg.max_retries_per_cycle:
            return None
        # start past the wall's cooldown so denied proposals don't burn retry budget; the wall still enforces
        start_hour = max(now_hour + 1,
                         (state.last_attempt_hour + self._cfg.cooldown_hours)
                         if state.last_attempt_hour is not None else now_hour + 1)
        candidates = _legal_candidates(start_hour - 1, self._cfg)
        # training labels only exist for attempt_no=1; passing live attempt numbers
        # would query the model out of distribution on a feature it never saw vary
        feats = [featurize(failed.decline, h, 1,
                           failed.amount_paise, failed.at_hour) for h in candidates]
        if not feats:
            return None
        probs = self.clf.predict_proba(feats)[:, 1]
        best = max(range(len(candidates)), key=lambda i: probs[i])
        if probs[best] * failed.amount_paise < self.cost:
            return None  # stopping rule: expected recovery below action cost
        return ProposedAction(ActionKind.RETRY, failed.customer_id, failed.cycle_id,
                              failed.amount_paise, candidates[best],
                              state.retries_attempted + 1)
