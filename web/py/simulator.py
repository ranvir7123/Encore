import random
from dataclasses import dataclass, field

from encore.domain import DAYS_PER_MONTH, HOURS_PER_DAY, DeclineCode, FailedDebit, day_of_month


@dataclass(frozen=True)
class RegimeConfig:
    salary_days: list[int]
    salary_day_weights: list[float]
    hard_decline_rate: float
    issuer_down_daily_prob: float
    uniform_credits: bool = False  # regime R2: destroys the salary-day signal


@dataclass(frozen=True)
class ReplyEvent:
    customer_id: str
    at_hour: int
    text: str


@dataclass
class Customer:
    customer_id: str
    amount_paise: int
    salary_day: int
    balance_paise: int
    daily_spend_paise: int
    billing_day: int
    churn_intent: bool
    revoked: bool = False


REPLY_TEMPLATES = [
    "salary {day} tarikh ko aayegi, tab try karna",
    "please retry after {day}th",
    "cancel karo yeh subscription",
    "band kar do isko",
    "will pay next week",
]


@dataclass
class Portfolio:
    customers: dict[str, Customer]
    regime: RegimeConfig
    rng: random.Random
    issuer_down_hours: set[int] = field(default_factory=set)
    _replies: list[ReplyEvent] = field(default_factory=list)
    balance_history: dict[str, list[int]] = field(default_factory=dict)

    @classmethod
    def generate(cls, n_customers: int, regime: RegimeConfig, seed: int) -> "Portfolio":
        rng = random.Random(seed)
        customers = {}
        for i in range(n_customers):
            cid = f"cust_{i:04d}"
            amount = rng.choice([19900, 29900, 49900, 99900])
            salary_day = rng.choices(regime.salary_days, regime.salary_day_weights)[0]
            customers[cid] = Customer(
                customer_id=cid,
                amount_paise=amount,
                salary_day=salary_day,
                balance_paise=rng.randint(0, 3 * amount),
                daily_spend_paise=rng.randint(1000, 15000),
                billing_day=rng.randint(1, DAYS_PER_MONTH),
                churn_intent=rng.random() < 0.05,
            )
        return cls(customers=customers, regime=regime, rng=rng)

    def _advance_hour(self, h: int) -> None:
        if h % HOURS_PER_DAY == 0:  # once per simulated day
            dom = day_of_month(h)
            if self.rng.random() < self.regime.issuer_down_daily_prob:
                start = h + self.rng.randint(0, 23)
                self.issuer_down_hours.update(range(start, start + self.rng.randint(2, 8)))
            for c in self.customers.values():
                credited = (
                    self.rng.random() < 1 / DAYS_PER_MONTH
                    if self.regime.uniform_credits
                    else dom == c.salary_day
                )
                if credited:
                    c.balance_paise += self.rng.randint(15_00000, 60_00000)  # salary credit
                c.balance_paise = max(0, c.balance_paise - c.daily_spend_paise)
                # one snapshot per customer per simulated day; no RNG consumed here
                self.balance_history.setdefault(c.customer_id, []).append(c.balance_paise)

    def would_succeed(self, customer_id: str, at_hour: int) -> bool:
        c = self.customers[customer_id]
        if c.revoked or c.churn_intent:
            return False
        if at_hour in self.issuer_down_hours:
            return False
        history = self.balance_history.get(customer_id, [])
        day = at_hour // HOURS_PER_DAY
        # use the balance as of at_hour's day when we recorded it; otherwise fall
        # back to the current live balance (keeps far-future/no-history queries
        # consistent with debit(), which always uses the live balance)
        balance = history[day] if history and day < len(history) else c.balance_paise
        return balance >= c.amount_paise

    def debit(self, customer_id: str, at_hour: int) -> DeclineCode | None:
        """Attempt a debit against latent state. None = success (balance deducted)."""
        c = self.customers[customer_id]
        if c.revoked:
            return DeclineCode.MANDATE_REVOKED
        if at_hour in self.issuer_down_hours:
            return DeclineCode.ISSUER_DOWN
        # time-aware balance check, mirroring would_succeed's pattern exactly:
        # use the balance as of at_hour's day when we recorded it; otherwise
        # fall back to the current live balance
        history = self.balance_history.get(customer_id, [])
        day = at_hour // HOURS_PER_DAY
        balance = history[day] if history and day < len(history) else c.balance_paise
        if balance < c.amount_paise:
            return DeclineCode.INSUFFICIENT_FUNDS
        # bookkeeping deduction still comes off the live scalar, not the
        # historical snapshot: eval worlds bill each customer at most once
        # per run (run_cycle(30, ...)), so there's no double-collection path
        # where this scalar/history divergence would matter
        c.balance_paise -= c.amount_paise
        return None

    def run_cycle(self, days: int, cycle_id: str) -> list[FailedDebit]:
        failures: list[FailedDebit] = []
        for h in range(days * HOURS_PER_DAY):
            self._advance_hour(h)
            dom, hod = day_of_month(h), h % HOURS_PER_DAY
            for c in self.customers.values():
                if dom == c.billing_day and hod == 6:  # original execution, once
                    if self.rng.random() < self.regime.hard_decline_rate:
                        c.revoked = True
                    code = self.debit(c.customer_id, h)
                    if code is not None:
                        failures.append(FailedDebit(c.customer_id, cycle_id, c.amount_paise, code, h))
                        # Replies materialize here, tied to the failure itself, not
                        # to any nudge actually being sent -- no shipped policy ever
                        # proposes a NUDGE action. They exist purely to feed the kill
                        # set (a "cancel" reply denies every further retry via the
                        # wall), independent of whether anything nudged the customer.
                        if self.rng.random() < 0.3:  # a minority reply to the eventual nudge
                            tmpl = self.rng.choice(REPLY_TEMPLATES)
                            self._replies.append(ReplyEvent(
                                c.customer_id, h + self.rng.randint(4, 48),
                                tmpl.format(day=c.salary_day),
                            ))
        return failures

    def reply_events(self) -> list[ReplyEvent]:
        return sorted(self._replies, key=lambda r: r.at_hour)
