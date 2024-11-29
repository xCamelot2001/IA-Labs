from mable.cargo_bidding import TradingCompany, Bid
from mable.examples import environment, fleets
from mable.transport_operation import ScheduleProposal, Vessel, SimpleVessel
from mable.transportation_scheduling import Schedule
from mable.shipping_market import TimeWindowTrade
from mable.extensions.fuel_emissions import VesselWithEngine
from mable.examples import environment, fleets


class Companyn(TradingCompany):
    def __init__(self, fleet, name):
        """
        Initialize the company with a fleet and a name.
        """
        super().__init__(fleet, name)
        self._future_trades = None
        self._future_auction_time = None
        self._distances = {}
        self.competitor_data = {}
        self.current_schedule = {}
        self.future_trades = []
        self.opponent_data = {}

    def pre_inform(self, trades, time):
        """
        Inform the company of the trades available for bidding.
        """
        self._future_trades = trades
        self._future_auction_time = time
        print(f"Future trades: {trades}, Time: {time}")

    def inform(self, trades, *args, **kwargs):
        """
        Inform the company of the trades available for bidding.
        """
        all_trades = trades + (self._future_trades or [])
        all_trades.sort(key=lambda trade: trade.earliest_pickup or float('inf'))

        bids = []
        for trade in trades:
            best_vessel = min(
                self._fleet,
                key=lambda vessel: self.calculate_cost(vessel, trade)
            )
            cost = self.calculate_cost(best_vessel, trade)
            bid_amount = self.create_bid(cost)
            bids.append(Bid(amount=bid_amount, trade=trade))

        return bids

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        """
        Receive the contracts and update the schedule.
        """
        if auction_ledger:
            for company, won_trades in auction_ledger.items():
                # if company != self.name:
                print(f"Competitor {company} won trades: {won_trades}")

        trades = [contract.trade for contract in contracts]
        scheduling_proposal = self.find_schedules(trades)
        self.current_schedule = scheduling_proposal.schedules

    # def find_contracts(self, trades):
    #     """
    #     Find the best contracts for the company.
    #     """
    #     schedules = {}
    #     scheduled_trades = []
    #     costs = {}


    #     sorted_trades = sorted(
    #         trades,
    #         key=lambda trade: trade.earliest_pickup or float('inf')
    #     )

    #     for trade in sorted_trades:
    #         best_vessel = None
    #         best_schedule = None
    #         min_cost = float("inf")

    #         for vessel in self._fleet:
    #             current_schedule = schedules.get(vessel, vessel.schedule)
    #             new_schedule = current_schedule.copy()

    #             # Try to add the trade to the schedule
    #             new_schedule.add_transportation(trade)
    #             if new_schedule.verify_schedule():
    #                 total_cost = self.calculate_cost(vessel, trade)
    #                 if total_cost < min_cost:
    #                     best_vessel = vessel
    #                     best_schedule = new_schedule
    #                     min_cost = total_cost
    #                     if best_vessel and best_schedule:
    #                         schedules[best_vessel] = best_schedule
    #                         scheduled_trades.append(trade)
    #                         costs[trade] = min_cost

    #     return ScheduleProposal(schedules, scheduled_trades, costs)

    def propose_schedules(self, trades):
        schedules = {}
        scheduled_trades = []
        costs = {}
        
        # Sort trades by earliest pickup time
        sorted_trades = sorted(trades, key=lambda t: t.earliest_pickup)
        
        for current_trade in sorted_trades:
            best_vessel = None
            best_schedule = None
            min_total_cost = float('inf')
            
            for vessel in self._fleet:
                current_schedule = schedules.get(vessel, vessel.schedule)
                new_schedule = current_schedule.copy()
                new_schedule.add_transportation(current_trade)
                
                if new_schedule.verify_schedule():
                    # Calculate cost including idle time
                    cost = self.calculate_cost(vessel, current_trade)
                    
                    # Add a penalty for idle time
                    if len(current_schedule) > 0:
                        last_event = current_schedule[-1]
                        idle_time = current_trade.earliest_pickup - last_event.time
                        idle_cost = vessel.get_cost(vessel.get_idle_consumption(idle_time))
                        total_cost = cost + idle_cost
                    else:
                        total_cost = cost
                    
                    if total_cost < min_total_cost:
                        min_total_cost = total_cost
                        best_vessel = vessel
                        best_schedule = new_schedule
                        
            if best_vessel:
                schedules[best_vessel] = best_schedule
                costs[current_trade] = min_total_cost * 1.5  # Apply profit margin
                scheduled_trades.append(current_trade)
        
        return ScheduleProposal(schedules, scheduled_trades, costs)

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

    # def apply_schedules(self, schedules):
    #     """
    #     Apply the schedules to the vessels.
    #     """
    #     for vessel, schedule in schedules.items():
    #         vessel.schedule = schedule

    def create_bid(self, cost):
        """
        Create a bid for a trade.
        """
        profit_margin = 10
        return cost * (1 + profit_margin)

    def calculate_cost(self, vessel, trade):
        # Get or calculate distance
        distance = self._distances.get((trade.origin_port, trade.destination_port))
        if distance is None:
            distance = self.headquarters.get_network_distance(
                trade.origin_port, trade.destination_port
            )
            self._distances[(trade.origin_port, trade.destination_port)] = distance

        # Calculate arrival time at pickup location
        pickup_arrival_time = self.get_arrival_time(trade.origin_port, vessel.schedule, vessel)
        
        # Calculate idle time before pickup
        pickup_idle_time = max(0, trade.earliest_pickup - pickup_arrival_time)
        
        # Loading time and costs
        loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)
        loading_consumption = vessel.get_loading_consumption(loading_time)
        loading_cost = vessel.get_cost(loading_consumption)

        # Travel time and costs to destination
        travel_time = vessel.get_travel_time(distance)
        travel_consumption = vessel.get_laden_consumption(travel_time, vessel.speed)
        travel_cost = vessel.get_cost(travel_consumption)
        
        # Calculate arrival time at dropoff
        dropoff_arrival_time = pickup_arrival_time + loading_time + travel_time
        dropoff_idle_time = max(0, trade.earliest_drop_off - dropoff_arrival_time)
        # Unloading time and costs
        unloading_time = loading_time  # Assuming unloading takes same time as loading
        unloading_consumption = vessel.get_unloading_consumption(unloading_time)
        unloading_cost = vessel.get_cost(unloading_consumption)

        # Idle time costs
        total_idle_time = pickup_idle_time + dropoff_idle_time
        idle_consumption = vessel.get_idle_consumption(total_idle_time)
        idle_cost = vessel.get_cost(idle_consumption)

        total_cost = loading_cost + unloading_cost + travel_cost + idle_cost

        return total_cost
    
    def idle_time(self, trade, vessel):
        pass

    def find_competing_vessels(self, trade):
        """
        Find the closest vessel to the trade's origin port for each competing company.
        """
        competing_vessels = {}
        for company in self.headquarters.get_companies():
            if company == self:
                continue
            # for every company find the closest vessel to the trade's origin port
            closest_vessel = min(
                company.fleet,
                key=lambda v: self.headquarters.get_network_distance(
                    v.location, trade.origin_port
                ),
            )
            # add the closest vessel to the competing vessels dictionary
            competing_vessels[company] = closest_vessel
        return competing_vessels

    # def calculate_profit(self, trade, contracts=None):
    #     # If contracts are provided, get actual revenue; else, predict revenue
    #     if contracts:
    #         try:
    #             revenue = self.calculate_revenue_from_contract(trade, contracts)
    #         except ValueError:
    #             revenue = trade.amount * 10  # Default revenue assumption if no contract found
    #     else:
    #         # Predict revenue for upcoming trades
    #         revenue = trade.amount * 10  # Example: Assume a unit price of 10 per trade amount

    #     # Calculate the cost using the existing method
    #     cost = self.calculate_total_cost(None, trade)

    #     # Profit is revenue - cost
    #     profit = revenue - cost
    #     return profit

    # def predict_profit(self, trade, contracts):
    #     """
    #     Predict the profit for a given trade using its contract.
    #     """
    #     try:
    #         # Get revenue from the contract
    #         revenue = self.calculate_revenue_from_contract(trade, contracts)

    #         # Calculate cost using existing logic
    #         cost = self.calculate_total_cost(None, trade)

    #         # Profit is revenue - cost
    #         profit = revenue - cost

    # def calculate_revenue_from_contract(self, trade, contracts):
    #     """
    #     Calculate the revenue for a given trade based on its associated contract.
    #     :param trade: The trade object.
    #     :param contracts: A list of Contract objects.
    #     :return: Revenue (payment) for the trade.
    #     """
    #     for contract in contracts:
    #         if contract.trade == trade:
    #             return contract.payment
    #     raise ValueError(f"No contract found for the trade: {trade}")
    #         return profit
    #     except (AttributeError, ValueError) as e:
    #         print(f"Error in predicting profit: {e}")
    #         return None

    # def predict_competitor_profit(self, trade, auction_ledger=None):
    #     # calclate the profit of all the competing vessels
    #     competing_vessels = self.find_competing_vessels(trade)
    #     for company, vessel in competing_vessels.items():
    #         cost = self.predict_cost(vessel, trade)
    #         bid = self.create_bid(cost, len(competing_vessels))
    #         # calculate the profit of the competitor
    #         profit = self.calculate_profit(trade) - bid
    #         self.competitor_data[company] = profit

    #     # competitor_name = "Arch Enemy Ltd."
    #     # competitor_won_contracts = auction_ledger[competitor_name]
    #     # competitor_fleet = [c for c in self.headquarters.get_companies() if c.name == competitor_name].pop().fleet
