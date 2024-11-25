from mable.cargo_bidding import TradingCompany, Bid
from mable.examples import environment, fleets
from mable.transport_operation import ScheduleProposal
from mable.transportation_scheduling import Schedule
from mable.shipping_market import TimeWindowTrade

class MyCompany(TradingCompany):
    def __init__(self, fleet, name):
        super().__init__(fleet, name)
        self._future_trades = None
        self._future_auction_time = None
        self._distances = {}
        self.competitor_data = {}

    def pre_inform(self, trades, time):
        """
        Store future trades information for decision-making and precompute distances.
        """
        self._future_trades = trades
        self._future_auction_time = time
        self.precompute_distances()

    def precompute_distances(self):
        """
        Precompute distances for future trades.
        """
        # Implement distance precomputation logic here
        pass

    def inform(self, trades, *args, **kwargs):
        """
        Propose schedules and generate bids for the given trades.
        """
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        trade_costs = proposed_scheduling.costs

        bids = [Bid(amount=cost, trade=trade) for trade, cost in trade_costs.items()]
        return bids

    def propose_schedules(self, trades):
        """
        Propose schedules for the given trades.
        """
        schedules = {}
        scheduled_trades = []
        costs = {}

        # Sort trades by time windows to prioritize those with tighter deadlines
        sorted_trades = sorted(trades, key=lambda x: x.latest_pickup or float("inf"))

        for current_trade in sorted_trades:
            best_vessel = None
            best_schedule = None
            min_cost = float("inf")

            for vessel in self._fleet:
                # Current schedule for the vessel
                current_schedule = schedules.get(vessel, vessel.schedule)
                new_schedule = current_schedule.copy()

                # Attempt to add the trade to the schedule
                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    # Calculate the cost
                    total_cost = self.calculate_total_cost(vessel, current_trade)

                    # Select the best trade
                    if total_cost < min_cost:
                        best_vessel = vessel
                        best_schedule = new_schedule
                        min_cost = total_cost

            # Assign the best trade to the vessel
            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(current_trade)
                costs[current_trade] = min_cost

        return ScheduleProposal(schedules, scheduled_trades, costs)

    def calculate_total_cost(self, vessel, trade):
        """
        Calculate the total cost of transporting the trade.
        """
        loading_time = vessel.get_loading_time(trade)
        travel_time = self.headquarters.get_network_distance(trade.origin_port, trade.destination_port) / vessel.speed
        unloading_time = vessel.get_unloading_time(trade)
        total_time = loading_time + travel_time + unloading_time

        fuel_consumption = vessel.get_fuel_consumption(total_time)
        cost = fuel_consumption * vessel.fuel_cost
        return cost

    def find_competing_vessels(self, trade):
        """
        Find competing vessels for a given trade.
        """
        competing_vessels = {}
        for company in self.headquarters.get_companies():
            if company == self:
                continue
            closest_vessel = min(company.fleet, key=lambda v: self.headquarters.get_network_distance(v.location, trade.origin_port))
            competing_vessels[company] = closest_vessel
        return competing_vessels

    def create_bid(self, cost, num_competitors):
        """
        Create a bid based on cost and number of competitors.
        """
        return cost * (1 + 0.1 * num_competitors)

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        """
        Process won contracts and schedule transportation for trades.
        """
        trades = [contract.trade for contract in contracts]
        scheduling_proposal = self.find_schedules(trades)
        self.apply_schedules(scheduling_proposal.schedules)

    def find_schedules(self, trades):
        """
        Find schedules for the given trades.
        """
        schedules = {}
        scheduled_trades = []
        costs = {}

        # Sort trades by time windows to prioritize those with tighter deadlines
        sorted_trades = sorted(trades, key=lambda x: x.latest_pickup or float("inf"))

        for current_trade in sorted_trades:
            best_vessel = None
            best_schedule = None
            min_cost = float("inf")

            for vessel in self._fleet:
                # Current schedule for the vessel
                current_schedule = schedules.get(vessel, vessel.schedule)
                new_schedule = current_schedule.copy()

                # Attempt to add the trade to the schedule
                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    # Calculate the cost
                    total_cost = self.calculate_total_cost(vessel, current_trade)

                    # Select the best trade
                    if total_cost < min_cost:
                        best_vessel = vessel
                        best_schedule = new_schedule
                        min_cost = total_cost

            # Assign the best trade to the vessel
            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(current_trade)
                costs[current_trade] = min_cost

        return ScheduleProposal(schedules, scheduled_trades, costs)

    def apply_schedules(self, schedules):
        """
        Apply the given schedules.
        """
        for vessel, schedule in schedules.items():
            vessel.schedule = schedule

    def predict_cost(self, vessel, trade):
        """
        Predict the cost for a competitor's vessel to transport a trade.
        """
        loading_time = vessel.get_loading_time(trade)
        travel_time = self.headquarters.get_network_distance(trade.origin_port, trade.destination_port) / vessel.speed
        unloading_time = vessel.get_unloading_time(trade)
        total_time = loading_time + travel_time + unloading_time

        fuel_consumption = vessel.get_fuel_consumption(total_time)
        cost = fuel_consumption * vessel.fuel_cost
        return cost

if __name__ == "__main__":
    specifications_builder = environment.get_specification_builder(environment_files_path=".")
    fleet = fleets.example_fleet_1()
    specifications_builder.add_company(MyCompany.Data(MyCompany, fleet, "My Company"))
    sim = environment.generate_simulation(specifications_builder)
    sim.run()