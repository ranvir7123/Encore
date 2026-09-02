from dataclasses import dataclass
from enum import StrEnum


class DeclineCode(StrEnum):
    # Soft declines: retry can help. Modeled on Razorpay's documented payment
    # failure reasons (https://razorpay.com/docs/payments/payments/failed-payments/).
    INSUFFICIENT_FUNDS = "insufficient_funds"
    ISSUER_DOWN = "issuer_down"
    GATEWAY_TIMEOUT = "gateway_timeout"
    # What Razorpay test mode actually reports for a declined card: a generic
    # gateway failure at authorization (error_reason "payment_failed"), even
    # for the documented insufficient-funds test card -- BROKELOG entry 13.
    # Retryable inside the cap, as Razorpay's own T+1/T+2/T+3 treats any
    # failed charge. Never produced by the simulator; never in model.SOFT_CODES.
    GENERIC_DECLINE = "generic_decline"
    # Hard declines: retrying is a compliance violation, not an optimization.
    MANDATE_REVOKED = "mandate_revoked"
    ACCOUNT_CLOSED = "account_closed"
    RISK_DECLINED = "risk_declined"


HARD_DECLINES = frozenset({
    DeclineCode.MANDATE_REVOKED, DeclineCode.ACCOUNT_CLOSED, DeclineCode.RISK_DECLINED,
})


class ActionKind(StrEnum):
    RETRY = "retry"
    NUDGE = "nudge"


@dataclass(frozen=True)
class FailedDebit:
    customer_id: str
    cycle_id: str
    amount_paise: int
    decline: DeclineCode
    at_hour: int


@dataclass(frozen=True)
class ProposedAction:
    kind: ActionKind
    customer_id: str
    cycle_id: str
    amount_paise: int
    execute_at_hour: int
    attempt_no: int


def attempt_id(action: ProposedAction) -> str:
    return f"{action.customer_id}:{action.cycle_id}:{action.kind}:{action.attempt_no}"


HOURS_PER_DAY = 24
DAYS_PER_MONTH = 30  # simulation simplification, stated in README


def hour_of_day(h: int) -> int:
    return h % HOURS_PER_DAY


def day_of_month(h: int) -> int:
    return (h // HOURS_PER_DAY) % DAYS_PER_MONTH + 1
