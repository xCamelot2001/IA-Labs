from mable.cargo_bidding import TradingCompany, Bid
from mable.examples import environment, fleets
from mable.transport_operation import ScheduleProposal
from mable.transportation_scheduling import Schedule


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

    def inform(self, trades, *args, **kwargs):
        """
        Propose schedules and generate bids for the given trades.
        """
        # Get proposed schedules and costs
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        trade_costs = proposed_scheduling.costs

        # Generate bids
        bids = []
        for trade in scheduled_trades:
            cost = trade_costs.get(trade, 0)  # Default to 0 if cost not found
            num_competitors = len(self.find_competing_vessels(trade))
            bid_amount = self.create_bid(cost, num_competitors)
            bids.append(Bid(amount=bid_amount, trade=trade))

        return bids

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        """
        Process won contracts and schedule transportation for trades.
        """
        # Process won contracts
        schedules = self.find_schedules([contract.trade for contract in contracts])
        self.apply_schedules(schedules.schedules)

        # Analyze auction outcomes
        if auction_ledger:
            self.analyze_competitor(auction_ledger)

    def propose_schedules(self, trades):
        """
        Propose schedules for trades by selecting the best vessel based on cost and availability.
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

    def find_schedules(self, trades):
        """
        Find feasible schedules for the given trades, prioritizing trades with tighter deadlines.
        """
        schedules = {}
        scheduled_trades = []

        # Sort trades by time windows to prioritize those with tighter deadlines
        sorted_trades = sorted(trades, key=lambda x: x.latest_pickup or float("inf"))

        for current_trade in sorted_trades:
            best_vessel = None
            best_schedule = None
            min_cost = float("inf")

            for vessel in self._fleet:
                current_schedule = schedules.get(vessel, vessel.schedule)
                new_schedule = current_schedule.copy()

                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    total_cost = self.calculate_total_cost(vessel, current_trade)
                    if total_cost < min_cost:
                        best_vessel = vessel
                        best_schedule = new_schedule
                        min_cost = total_cost

            if best_vessel:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(current_trade)

        return ScheduleProposal(schedules, scheduled_trades, {})

    def analyze_competitor(self, auction_ledger):
        """
        Analyze the auction ledger to gather insights about competitors' bidding behavior.
        """
        for auction in auction_ledger:
            winner = auction.get("winner")
            if winner and winner != self.name:
                trade = auction.get("trade")
                winning_bid = auction.get("winning_bid")
                if winner not in self.competitor_data:
                    self.competitor_data[winner] = []
                self.competitor_data[winner].append((trade, winning_bid))

    def precompute_distances(self):
        """
        Precompute and store distances between current trades and future trades for efficiency.
        """
        if self._future_trades:
            for current_trade in self._future_trades:
                for future_trade in self._future_trades:
                    if current_trade != future_trade:
                        key = (current_trade.destination_port, future_trade.origin_port)
                        if key not in self._distances:
                            self._distances[key] = (
                                self._headquarters.get_network_distance(
                                    current_trade.destination_port,
                                    future_trade.origin_port,
                                )
                            )

    def calculate_total_cost(self, vessel, trade):
        """
        Calculate the total cost of transporting a trade using a given vessel.
        """
        # Calculate the distance between origin and destination ports
        distance = self._headquarters.get_network_distance(trade.origin_port, trade.destination_port)
        
        # Determine the vessel's speed (ensure it's in nautical miles per hour)
        speed = vessel.speed
        
        # Calculate the duration of the voyage in hours
        duration_hours = distance / speed
        
        # Convert duration to days if required by the consumption functions
        duration_days = duration_hours / 24
        
        # Calculate various costs
        ballast_cost = vessel.get_ballast_consumption(duration_hours, speed)
        co2_cost = vessel.get_co2_emission(amount)
        fuel_cost = vessel.get_cost(amount)
        idle_cost = vessel.get_idle_consumption(duration_hours)
        travel_cost = vessel.get_laden_consumption(duration_hours, speed)
        loading_cost = vessel.get_loading_consumption(duration_hours)
        unloading_cost = vessel.get_unloading_consumption(duration_hours)
        
        # Sum all costs to get the total cost
        total_cost = (
            ballast_cost
            + co2_cost
            + fuel_cost
            + idle_cost
            + travel_cost
            + loading_cost
            + unloading_cost
        )
        
        return total_cost
    
    


    def get_insertion_pairs(self, insertion_points):
        """
        Generate all valid pick-up and drop-off index pairs from insertion points.
        """
        for i, idx_pick_up in enumerate(insertion_points):
            for idx_drop_off in insertion_points[i:]:
                yield idx_pick_up, idx_drop_off

    def create_bid(self, cost, num_competitors):
        """
        Create a bid amount based on the cost and number of competitors.
        """
        # If many competitors, lower the profit margin to increase the chances of winning
        profit_margin = max(0.05, 0.1 - (num_competitors * 0.01))
        return cost * (1 + profit_margin)


if __name__ == "__main__":
    specifications_builder = environment.get_specification_builder(
        environment_files_path="."
    )
    fleet = fleets.example_fleet_1()
    specifications_builder.add_company(MyCompany.Data(MyCompany, fleet, "My Company"))
    sim = environment.generate_simulation(specifications_builder)
    sim.run()
