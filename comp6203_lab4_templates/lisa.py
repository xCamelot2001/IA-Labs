from mable.cargo_bidding import TradingCompany
from mable.transport_operation import Bid, ScheduleProposal


class Companyn(TradingCompany):
    def __init__(self, fleet, name):
        super().__init__(fleet, name)
        self._future_trades = None
        self._distances = {}

    # Step 1: Pre-Inform Phase
    def pre_inform(self, trades, time):
        """
        Store future trade opportunities for planning.
        """
        self._future_trades = trades

    # Step 2: Inform Phase
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


    # Step 3: Receive Phase
    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        """
        Apply schedules for won contracts and analyze competitors' data.
        """
        trades = [one_contract.trade for one_contract in contracts]
        scheduling_proposal = self.find_schedules(trades)
        _ = self.apply_schedules(scheduling_proposal.schedules)

        # Analyze competitors
        competitor_name = "Arch Enemy Ltd."
        if auction_ledger and competitor_name in auction_ledger:
            competitor_won_contracts = auction_ledger[competitor_name]
            competitor_fleet = [
                c for c in self.headquarters.get_companies() if c.name == competitor_name
            ].pop().fleet
            # Analyze competitor's bid factors
            print(f"Competitor {competitor_name} won {len(competitor_won_contracts)} contracts.")

    def propose_schedules(self, trades):

        schedules = {}
        costs={}
        scheduled_trades = []
        i = 0
        while i < len(trades):
            current_trade = trades[i]
            competing_vessels = self.find_competing_vessels(current_trade)
            if len(competing_vessels) == 0:
                print(f"{current_trade.origin_port.name.split('-')[0]}"
                      f" {current_trade.destination_port.name.split('-')[0]}: No competing vessels found")
            for one_company in competing_vessels:
                distance = self.headquarters.get_network_distance(
                    competing_vessels[one_company].location, current_trade.origin_port)
                print(f"{current_trade.origin_port.name.split('-')[0]}"
                      f" {current_trade.destination_port.name.split('-')[0]}:"
                      f" {one_company.name}'s {competing_vessels[one_company].name}"
                      f" in {competing_vessels[one_company].location.name.split('-')[0]}"
                      f" at {distance} NM")
            is_assigned = False
            j = 0
            while j < len(self._fleet) and not is_assigned:
                current_vessel = self._fleet[j]
                current_vessel_schedule = schedules.get(current_vessel, current_vessel.schedule)
                new_schedule = current_vessel_schedule.copy()
                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    schedules[current_vessel] = new_schedule
                    costs[current_trade] = self.predict_cost(current_vessel, current_trade)
                    scheduled_trades.append(current_trade)
                    is_assigned = True
                j += 1
            i += 1
        return ScheduleProposal(schedules, scheduled_trades, costs)

    # Step 5: Find Competing Vessels
    def find_competing_vessels(self, trade):
        """
        Find the closest competing vessels for a given trade.
        """
        competing_vessels = {}
        for company in self.headquarters.get_companies():
            if company != self:  # Exclude self
                closest_vessel = min(
                    company.fleet,
                    key=lambda v: self.headquarters.get_network_distance(
                        v.location, trade.origin_port
                    ),
                    default=None,
                )
                if closest_vessel:
                    competing_vessels[company] = closest_vessel
        return competing_vessels

    # Step 6: Find Schedules for Won Trades
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

    # Step 7: Predict Costs
    def predict_cost(self, vessel, trade):
        """
        Calculate the cost of a trade for a given vessel.
        """
        distance = self._distances.get((trade.origin_port, trade.destination_port))
        if distance is None:
            distance = self.headquarters.get_network_distance(
                trade.origin_port, trade.destination_port
            )
            self._distances[(trade.origin_port, trade.destination_port)] = distance

        loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)
        loading_consumption = vessel.get_loading_consumption(loading_time)
        loading_cost = vessel.get_cost(loading_consumption)

        unloading_time = loading_time
        unloading_consumption = vessel.get_unloading_consumption(unloading_time)
        unloading_cost = vessel.get_cost(unloading_consumption)

        travel_time = vessel.get_travel_time(distance)
        travel_consumption = vessel.get_laden_consumption(travel_time, vessel.speed)
        travel_cost = vessel.get_cost(travel_consumption)

        total_cost = loading_cost + unloading_cost + travel_cost
        return total_cost