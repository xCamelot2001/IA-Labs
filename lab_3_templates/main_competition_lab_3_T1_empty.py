from mable.cargo_bidding import TradingCompany
from mable.examples import environment, fleets, shipping
from mable.transport_operation import Bid, ScheduleProposal


class MyCompany(TradingCompany):
    def __init__(self, fleet, name):
        super().__init__(fleet, name)
        self._future_trades = None

    def pre_inform(self, trades, time):
        self._future_trades = trades

    def inform(self, trades, *args, **kwargs):
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        self._current_scheduling_proposal = proposed_scheduling
        trades_and_costs = [
            (x, proposed_scheduling.costs[x]) if x in proposed_scheduling.costs
            else (x, 0)
            for x in scheduled_trades]
        bids = [Bid(amount=cost, trade=one_trade) for one_trade, cost in trades_and_costs]
        self._future_trades = None
        return bids

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        trades = [one_contract.trade for one_contract in contracts]
        scheduling_proposal = self.find_schedules(trades)
        rejected_trades = self.apply_schedules(scheduling_proposal.schedules)

    def propose_schedules(self, trades):
        schedules = {}
        costs = {}
        scheduled_trades = []
        j = 0
        while j < len(self._fleet):
            current_vessel = self.fleet[j]
            current_vessel_schedule = schedules.get(current_vessel, current_vessel.schedule)
            new_schedule = current_vessel_schedule.copy()
            i = 0
            trade_options = {}
            while i < len(trades):
                current_trade = trades[i]
                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    total_cost = self.predict_cost(current_vessel, current_trade)
                    # TODO Find the closest future trade
                    # trade_options[current_trade] = ...
                    pass
                i += 1
            if len(trade_options) > 0:
                # TODO Select a trade
                pass
            j += 1
        return ScheduleProposal(schedules, scheduled_trades, costs)

    def predict_cost(self, vessel, trade):
        total_cost = 0
        return total_cost

    def find_schedules(self, trades):
        schedules = {}
        scheduled_trades = []
        i = 0
        while i < len(trades):
            current_trade = trades[i]
            is_assigned = False
            j = 0
            while j < len(self._fleet) and not is_assigned:
                current_vessel = self._fleet[j]
                current_vessel_schedule = schedules.get(current_vessel, current_vessel.schedule)
                new_schedule = current_vessel_schedule.copy()
                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    schedules[current_vessel] = new_schedule
                    scheduled_trades.append(current_trade)
                    is_assigned = True
                j += 1
            i += 1
        return ScheduleProposal(schedules, scheduled_trades, {})


def build_specification():
    specifications_builder = environment.get_specification_builder(fixed_trades=shipping.example_trades_1())
    fleet = fleets.example_fleet_1()
    specifications_builder.add_company(MyCompany.Data(MyCompany, fleet, MyCompany.__name__))
    sim = environment.generate_simulation(
        specifications_builder,
        show_detailed_auction_outcome=True)
    sim.run()


if __name__ == '__main__':
    build_specification()
