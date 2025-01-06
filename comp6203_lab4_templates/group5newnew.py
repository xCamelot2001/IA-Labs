from mable.cargo_bidding import TradingCompany, Bid
from mable.transport_operation import ScheduleProposal
from mable.transportation_scheduling import Schedule
from mable.shipping_market import TimeWindowTrade


class Company5(TradingCompany):
    def __init__(self, fleet, name):
        super().__init__(fleet, name)
        self._future_trades = None
        self._future_auction_time = None
        self._distances = {}
        self.competitor_data = {}
        self.current_schedule = {}
        self.future_trades = []
        self.opponent_data = {}
        self.auction_history = []

    def pre_inform(self, trades, time):
        """
        Inform the company of the trades available for bidding.
        """
        self._future_trades = trades
        self._future_auction_time = time
        print(f"Future trades: {trades}, Time: {time}")

    def create_bid(self, cost, trade, auction_analysis=None):
        """
        Create a bid for a trade, factoring in auction analysis.
        """
        profit_factor = 0.2

        if auction_analysis:
            # Adjust profit factor based on auction trends
            avg_winning_bid = auction_analysis.get("avg_winning_bid", {}).get(trade, cost)
            competition_level = auction_analysis.get("competition_level", {}).get(trade, 1)
            
            # Example logic: Adjust profit factor based on competition
            if competition_level > 2:
                profit_factor += 0.1  # Increase bid aggressiveness
            else:
                profit_factor -= 0.1  # Decrease bid aggressiveness

            # Adjust cost to bid closer to the average winning bid
            cost = min(avg_winning_bid * 1.1, cost)

        return cost * (1 + profit_factor)

    def inform(self, trades, auction_ledger=None, *args, **kwargs):
        """
        Inform the company of the trades available for bidding, considering the auction ledger.
        """
        bids = []
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        self._current_scheduling_proposal = proposed_scheduling

        # Analyze auction outcomes
        auction_analysis = self.analyze_auction_ledger(auction_ledger) if auction_ledger else {}

        trades_and_costs = [
            (x, proposed_scheduling.costs[x]) if x in proposed_scheduling.costs
            else (x, 0)
            for x in scheduled_trades
        ]
        for one_trade, cost in trades_and_costs:
            bid_amount = self.create_bid(cost, one_trade, auction_analysis)
            bids.append(Bid(amount=bid_amount, trade=one_trade))
        return bids

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        """
        Receive contracts and update the schedule while storing auction outcomes.
        """
        if auction_ledger:
            self.auction_history.append(auction_ledger)  # Store auction results
            for company, won_trades in auction_ledger.items():
                if company != self.name:
                    print(f"Competitor {company} won trades: {won_trades}")

        trades = [contract.trade for contract in contracts]
        scheduling_proposal = self.propose_schedules(trades)
        for contract in contracts:
            if contract.trade in scheduling_proposal.scheduled_trades:
                contract.fulfilled = True
        self.current_schedule = contracts

    def analyze_auction_ledger(self, auction_ledger):
        """
        Analyze the auction ledger to extract insights for bidding strategy.
        """
        avg_winning_bid = {}
        competition_level = {}

        for company, trades in auction_ledger.items():
            for trade in trades:
                if trade not in avg_winning_bid:
                    avg_winning_bid[trade] = []
                avg_winning_bid[trade].append(trade.amount)

        # Calculate average winning bids and competition levels
        for trade, bids in avg_winning_bid.items():
            avg_winning_bid[trade] = sum(bids) / len(bids)
            competition_level[trade] = len(bids)

        return {
            "avg_winning_bid": avg_winning_bid,
            "competition_level": competition_level
        }

    def propose_schedules(self, trades):
        """
        Propose schedules for the trades, optimizing for maximum fulfillment and minimum penalties.
        """
        schedules = {}
        scheduled_trades = []
        unassigned_trades = []

        # Step 1: Sort trades by priority (profitability and time constraints)
        trades = sorted(
            trades,
            key=lambda t: (t.amount / max(1, t.time_window[1] - t.time_window[0]), -t.earliest_pickup),
            reverse=True
        )

        # Step 2: Assign trades to vessels
        for current_trade in trades:
            best_vessel = None
            best_schedule = None
            best_score = float('-inf')

            for current_vessel in self._fleet:
                current_schedule = schedules.get(current_vessel, current_vessel.schedule)
                new_schedule = current_schedule.copy()

                # Calculate cost and feasibility
                distance_to_pickup = self.headquarters.get_network_distance(current_vessel.location,
                                                                            current_trade.origin_port)
                travel_time_to_pickup = current_vessel.get_travel_time(distance_to_pickup)
                loading_time = current_vessel.get_loading_time(current_trade.cargo_type, current_trade.amount)
                total_travel_time = travel_time_to_pickup + loading_time

                # Verify time window
                if total_travel_time > current_trade.time_window[1] - current_trade.time_window[0]:
                    continue

                new_schedule.add_transportation(current_trade)
                if new_schedule.verify_schedule():
                    cost = self.calculate_cost(current_vessel, current_trade)

                    # Scoring based on multiple factors
                    score = (
                            current_trade.amount / (cost + 1e-6)  # Higher profitability
                            - total_travel_time * 0.1  # Penalize longer travel times
                            + current_vessel.capacity(current_trade.cargo_type) * 0.01  # Reward larger capacity
                    )

                    if score > best_score:
                        best_score = score
                        best_vessel = current_vessel
                        best_schedule = new_schedule

            # Assign trade to the best vessel
            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(current_trade)
            else:
                unassigned_trades.append(current_trade)

        # Step 3: Return the proposed schedules
        costs = {trade: self.calculate_cost(vessel, trade) for trade in scheduled_trades for vessel in schedules.keys()}
        return ScheduleProposal(schedules, scheduled_trades, costs)

    def calculate_cost(self, vessel, trade):
        """
        Calculate the cost of fulfilling a trade using a specific vessel.
        """
        distance = self._distances.get((trade.origin_port, trade.destination_port), None)
        if distance is None:
            distance = self.headquarters.get_network_distance(
                trade.origin_port, trade.destination_port
            )
            self._distances[(trade.origin_port, trade.destination_port)] = distance

        loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)
        travel_time = vessel.get_travel_time(distance)

        time_penalty = max(0, trade.earliest_drop_off - (trade.time_window[1] - trade.time_window[0]))

        total_cost = (
                vessel.get_cost(vessel.get_loading_consumption(loading_time)) +
                vessel.get_cost(vessel.get_unloading_consumption(loading_time)) +
                vessel.get_cost(vessel.get_laden_consumption(travel_time, vessel.speed)) +
                time_penalty
        )
        return total_cost
