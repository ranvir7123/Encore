"""Rails the agent can execute a retry on. The simulated rail answers at once;
the Razorpay rail creates a real test-mode Payment Link and answers "pending"
until a human pays it (or the agent times out)."""
from typing import Literal, Protocol

from encore.domain import ProposedAction, attempt_id
from encore.scheduler import SimulatedRail
from encore.simulator import Portfolio

RailOutcome = Literal["success", "failure", "pending"]


class AgentRail(Protocol):
    name: str

    def execute(self, action: ProposedAction) -> RailOutcome: ...

    def poll(self, action: ProposedAction) -> RailOutcome: ...

    def receipt(self, action: ProposedAction) -> dict: ...


class SimulatedAgentRail:
    name = "simulated"

    def __init__(self, portfolio: Portfolio) -> None:
        self._rail = SimulatedRail(portfolio)

    def execute(self, action: ProposedAction) -> RailOutcome:
        return "success" if self._rail.execute(action) else "failure"

    def poll(self, action: ProposedAction) -> RailOutcome:
        raise RuntimeError("the simulated rail never pends")

    def receipt(self, action: ProposedAction) -> dict:
        return {}


class RazorpayLinkRail:
    name = "razorpay_test_mode"

    def __init__(self, client) -> None:
        self._client = client
        self._links: dict[str, dict] = {}

    def execute(self, action: ProposedAction) -> RailOutcome:
        aid = attempt_id(action)
        # reference_id = attempt_id, so Razorpay's own uniqueness rule backs the
        # local ledger's idempotency; notes carry the customer onto the payment.
        # The description is the checkout page's title. Take 2's operator paid
        # the original link instead of this one (BROKELOG entry 15), so the two
        # pages now say which is which in their first words.
        self._links[aid] = self._client.create_payment_link(
            action.amount_paise, f"PAY THIS ONE - Encore recovery for {action.customer_id} ({aid})",
            aid,
            notes={"customer_id": action.customer_id, "cycle_id": action.cycle_id,
                   "attempt_id": aid})
        return "pending"

    def poll(self, action: ProposedAction) -> RailOutcome:
        aid = attempt_id(action)
        link = self._client.fetch_payment_link(self._links[aid]["id"])
        self._links[aid] = link
        if link["status"] == "paid":
            return "success"
        if link["status"] in ("cancelled", "expired"):
            return "failure"
        return "pending"  # a failed attempt never moves the link off "created"

    def receipt(self, action: ProposedAction) -> dict:
        link = self._links.get(attempt_id(action), {})
        return {"link_id": link.get("id"), "short_url": link.get("short_url"),
                "status": link.get("status")}
