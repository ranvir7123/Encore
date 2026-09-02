"""Where failed debits come from. Two sources, one shape (FailedDebit), so the
agent and the eval harness never care which rail produced a failure."""
from typing import Protocol

from encore.domain import HOURS_PER_DAY, DeclineCode, FailedDebit
from encore.simulator import Portfolio

IST_OFFSET_S = 5 * 3600 + 30 * 60

# Razorpay `error_reason` -> our decline taxonomy. Explicit and short on
# purpose: a reason not in this table is an EXCEPTION the agent reports (parked,
# reason "unmapped_error_reason"), never a guess about whether a retry is legal.
# Strings from razorpay.com/docs/errors/error-reasons. What this account
# ACTUALLY produces (docs/spike-notes.md, A0; BROKELOG entry 13): the
# documented insufficient-funds test card comes back as "payment_failed", the
# generic gateway-authorization failure, so that string maps to the
# retryable GENERIC_DECLINE rather than being dropped as unmapped.
ERROR_REASON_TO_DECLINE: dict[str, DeclineCode] = {
    "insufficient_funds": DeclineCode.INSUFFICIENT_FUNDS,
    "gateway_technical_error": DeclineCode.GATEWAY_TIMEOUT,
    "payment_failed": DeclineCode.GENERIC_DECLINE,
}


def map_error_reason(reason: str | None) -> DeclineCode | None:
    return ERROR_REASON_TO_DECLINE.get(reason or "")


def sim_hour(created_at: int, anchor_ts: int) -> int:
    """Unix timestamp -> simulated hour: whole IST days since the anchor x 24,
    plus the IST hour of day. Hour-of-day is preserved so the wall's 22:00-07:00
    execution window means the same thing on real timestamps as it does in the
    simulator."""
    local, anchor_local = created_at + IST_OFFSET_S, anchor_ts + IST_OFFSET_S
    days = local // 86400 - anchor_local // 86400
    return days * HOURS_PER_DAY + (local % 86400) // 3600


class FailureSource(Protocol):
    def failures(self) -> list[FailedDebit]: ...


class SimulatedFailureSource:
    def __init__(self, portfolio: Portfolio, cycle_id: str, days: int = 30) -> None:
        self._p, self._cycle_id, self._days = portfolio, cycle_id, days

    def failures(self) -> list[FailedDebit]:
        return self._p.run_cycle(self._days, self._cycle_id)


class RazorpayFailureSource:
    """Failed payments from GET /v1/payments in [from_ts, to_ts]. customer_id
    comes from the payment's notes (set on the originating Payment Link and
    carried onto the payment entity -- verified in docs/spike-notes.md, A0),
    else "rzp:<payment_id>" so nothing is silently dropped. Payments whose
    error_reason is not in ERROR_REASON_TO_DECLINE are collected in
    `unmapped` for the agent to park and report, not retried."""

    def __init__(self, client, from_ts: int, to_ts: int, cycle_id: str, anchor_ts: int) -> None:
        self._client, self._from, self._to = client, from_ts, to_ts
        self._cycle_id, self._anchor = cycle_id, anchor_ts
        self.unmapped: list[dict] = []

    def failures(self) -> list[FailedDebit]:
        out: list[FailedDebit] = []
        self.unmapped = []
        for p in self._client.list_payments(self._from, self._to):
            if p.get("status") != "failed":
                continue
            cid = (p.get("notes") or {}).get("customer_id") or f"rzp:{p['id']}"
            code = map_error_reason(p.get("error_reason"))
            if code is None:
                self.unmapped.append({"payment_id": p["id"], "customer_id": cid,
                                      "error_reason": p.get("error_reason"),
                                      "amount_paise": int(p["amount"])})
                continue
            out.append(FailedDebit(cid, self._cycle_id, int(p["amount"]), code,
                                   sim_hour(int(p["created_at"]), self._anchor)))
        return out
