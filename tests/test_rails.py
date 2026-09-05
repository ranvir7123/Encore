"""Clock and rails for the agent loop. The clock is injected so wall.py stays
clock-free; the rails give the agent one outcome vocabulary whether a retry
resolves at once (simulated) or waits on a human paying a real link."""
from encore.clock import InstantClock, SimClock
from encore.domain import ActionKind, ProposedAction, attempt_id
from encore.rails import RazorpayLinkRail, SimulatedAgentRail
from encore.simulator import Portfolio, RegimeConfig

R0 = RegimeConfig([1, 7, 15], [0.6, 0.3, 0.1], 0.08, 0.05)


def test_sim_clock_sleeps_proportionally_and_never_goes_backwards():
    slept = []
    clock = SimClock(0.5, sleep=slept.append, monotonic=lambda: 0.0)
    clock.advance_to(10)
    clock.advance_to(4)
    clock.advance_to(12)
    assert slept == [5.0, 1.0] and clock.hour == 12


def test_instant_clock_advances_without_sleeping_and_ticks_monotonic():
    clock = InstantClock()
    clock.advance_to(7)
    assert clock.hour == 7 and clock.monotonic() < clock.monotonic()


def test_simulated_rail_maps_debit_to_sync_outcomes():
    p = Portfolio.generate(50, R0, seed=3)
    failures = p.run_cycle(30, "c")
    rail = SimulatedAgentRail(p)
    outcomes = {rail.execute(ProposedAction(ActionKind.RETRY, f.customer_id, "c", f.amount_paise,
                                            f.at_hour + 72, 1)) for f in failures}
    assert outcomes <= {"success", "failure"} and rail.name == "simulated"


class FakeLinks:
    def __init__(self):
        self.created, self.status = [], "created"

    def create_payment_link(self, amount_paise, description, reference_id, notes=None):
        self.created.append((amount_paise, reference_id, notes))
        return {"id": "plink_x", "status": "created", "short_url": "https://rzp.io/x"}

    def fetch_payment_link(self, link_id):
        return {"id": link_id, "status": self.status, "short_url": "https://rzp.io/x"}


def test_link_rail_pends_then_resolves_on_paid():
    fake = FakeLinks()
    rail = RazorpayLinkRail(fake)
    action = ProposedAction(ActionKind.RETRY, "cust_0001", "live", 19900, 95, 1)
    assert rail.execute(action) == "pending"
    assert fake.created[0][1] == attempt_id(action)
    assert fake.created[0][2]["customer_id"] == "cust_0001"
    assert rail.poll(action) == "pending"
    fake.status = "paid"
    assert rail.poll(action) == "success"
    assert rail.receipt(action) == {"link_id": "plink_x", "short_url": "https://rzp.io/x",
                                    "status": "paid"}
