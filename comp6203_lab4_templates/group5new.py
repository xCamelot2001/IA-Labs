from mable.cargo_bidding import TradingCompany, Bid
from mable.transport_operation import ScheduleProposal
from mable.transportation_scheduling import Schedule
from mable.shipping_market import TimeWindowTrade

class Company5(TradingCompany):
    def __init__(self, fleet, name):
        """
        Initialize the company with a fleet and a name.
        """
        super().__init__(fleet, name)
        self._future_trades = None
        self._future_auction_time = None

        # Keep track of distances for repeated look-ups
        self._distances = {}

        # This dictionary will hold data about how each competitor historically bids
        # E.g., { competitor_name: {"payments": [...], "margins": [...], "avg_margin": 1.2, ...}, ... }
        self.competitor_data = {}
        
        # Current scheduling state
        self.current_schedule = {}
        
        # Will hold trades announced in pre_inform
        self.future_trades = []
        
        # We store all competitor/won-trade data from the auction ledger
        self.opponent_data = {}
        
        # We can store historical payment data to feed into a margin model
        self.payment_data = []

    def pre_inform(self, trades, time):
        """
        Inform the company of the trades that will be available for bidding *in the next* auction round.
        """
        self._future_trades = trades
        self._future_auction_time = time
        print(f"Future trades: {trades}, Time: {time}")

    def create_bid(self, cost, trade, auction_ledger=None):
        """
        Create a bid for a trade, using:
          - self payment_data (average or distribution),
          - competitor distances,
          - time window constraints,
          - plus any competitor margin intelligence gleaned from auction_ledger.
        """

        # Base profit factor
        base_profit_factor = 0.2  # your "default" margin above cost

        # 1) Update your competitor model from the auction_ledger
        #    If there's new data about competitor bids, parse it and update self.competitor_data
        if auction_ledger:
            for competitor_name, records in auction_ledger.items():
                # Skip your own ledger
                if competitor_name == self.name:
                    continue

                # Make sure competitor_name is in competitor_data
                if competitor_name not in self.competitor_data:
                    self.competitor_data[competitor_name] = {
                        "payments": [],
                        "margins": [],
                        "avg_margin": 1.0,  # start with neutral margin assumption
                    }

                for record in records:
                    # Each record in 'records' should have a .payment, a .trade, etc., if the competitor won
                    if hasattr(record, "payment") and record.payment is not None:
                        # Store competitor's payment
                        self.competitor_data[competitor_name]["payments"].append(record.payment)
                        
                        # If you have a cost assumption for the competitor, you can guess their margin:
                        # For instance, if you estimate the competitor's cost for that trade,
                        # margin = (payment / estimated_competitor_cost)
                        # We'll do a naive approach that assumes the competitor's cost ~ your cost for demonstration.
                        # In a real model, you'd want something more robust (e.g., competitor's vessel location, etc.).
                        competitor_estimated_cost = cost  # naive assumption
                        if competitor_estimated_cost > 0:
                            comp_margin = record.payment / competitor_estimated_cost
                            self.competitor_data[competitor_name]["margins"].append(comp_margin)

                # Update the competitor's average margin
                margins = self.competitor_data[competitor_name]["margins"]
                if margins:
                    avg_margin = sum(margins) / len(margins)
                    self.competitor_data[competitor_name]["avg_margin"] = avg_margin

        # 2) Use your overall payment_data to influence your base profit factor
        if auction_ledger:
            # If you track *all* winning payments across the entire market:
            for competitor_name, records in auction_ledger.items():
                for record in records:
                    if hasattr(record, "payment") and record.payment is not None:
                        self.payment_data.append(record.payment)

        if self.payment_data:
            avg_payment = sum(self.payment_data) / len(self.payment_data)
            if avg_payment > cost:
                base_profit_factor += 0.1
            else:
                base_profit_factor -= 0.05
        
        # 3) Adjust margin for the presence of strong/weak competitors
        #    If there's a competitor whose average margin is known, we can try to undercut them or stay above them
        strongest_competitor_margin = 0.0
        for c_name, c_data in self.competitor_data.items():
            avg_margin = c_data.get("avg_margin", 1.0)
            # Example: if a competitor often uses a high margin, we can safely raise ours a bit
            # If a competitor uses a low margin, we might want to reduce ours to remain competitive
            if avg_margin > strongest_competitor_margin:
                strongest_competitor_margin = avg_margin
        
        # If we see a competitor that has a high margin, it suggests their bids are typically higher,
        # so we can push our margin up. If we see a competitor with a low margin, we might want to reduce our margin
        if strongest_competitor_margin > 1.3:
            base_profit_factor += 0.1
        elif strongest_competitor_margin < 1.1:
            base_profit_factor -= 0.05

        # 4) Additional adjustments based on your own vessel advantage (e.g., if you are physically close)
        competing_vessels = self.find_competing_vessels(trade)
        closest_distance = min(
            [
                self.headquarters.get_network_distance(v.location, trade.origin_port)
                for v in competing_vessels.values()
            ],
            default=float('inf')
        )
        # If your location is quite close, you can choose to reduce the margin to secure the trade
        if closest_distance > 100:  # i.e., your competitor is far from the origin
            base_profit_factor -= 0.05
        else:
            base_profit_factor += 0.05

        # 5) Adjust margin based on how narrow the time window is
        #    If the window is short, you might charge more because there's more risk
        #    Or you might want to drop your margin a bit to ensure you get it because time is short
        time_window_size = trade.time_window[1] - trade.time_window[0]
        if time_window_size < 100:
            base_profit_factor += 0.1

        # Final: your final bid
        final_bid = cost * (1 + base_profit_factor)
        return final_bid

    def inform(self, trades, *args, **kwargs):
        """
        1. Called right before the actual cargo auctions.
        2. We propose schedules (like in your example).
        3. Then we create bids for those trades based on (scheduled) cost.
        """
        try:

            bids = []
            proposed_scheduling = self.propose_schedules(trades)
            scheduled_trades = proposed_scheduling.scheduled_trades
            self._current_scheduling_proposal = proposed_scheduling

            # If a trade is in your proposed scheduling plan, we have a cost for it
            trades_and_costs = [
                (x, proposed_scheduling.costs[x]) 
                if x in proposed_scheduling.costs else (x, 0)
                for x in scheduled_trades
            ]

            # For each scheduled trade, compute your bid
            for trade, cost in trades_and_costs:
                bid_amount = self.create_bid(
                    cost,
                    trade,
                    auction_ledger=kwargs.get("auction_ledger", None)
                )
                bids.append(Bid(amount=bid_amount, trade=trade))
                
            return bids
        except Exception as e:
            print(f"Error in inform: {e}")
            return []

    def receive(self, contracts, auction_ledger=None, *args, **kwargs):
        """
        Called after the auction has cleared.
        The 'auction_ledger' has details for all companies about
        which trades they won and at what payment.
        """
        # See which competitor got what
        if auction_ledger:
            for competitor_name, won_trades in auction_ledger.items():
                print(f"Competitor {competitor_name} won trades: {won_trades}")

        # Now, for *your* awarded contracts, incorporate them into your schedule
        # so the simulator knows how you plan to fulfill these cargoes
        trades = [contract.trade for contract in contracts]
        scheduling_proposal = self.find_schedules(trades)

        for contract in contracts:
            if contract.trade in scheduling_proposal.scheduled_trades:
                contract.fulfilled = True
        self.current_schedule = contracts
        
        # It's good practice to call `self.apply_schedules(...)` on the final schedule
        # so that MABLE knows how to simulate your vessel movements.
        for vessel, schedule in scheduling_proposal.schedules.items():
            vessel.apply_schedule(schedule)

    def find_competing_vessels(self, current_trade):
        """
        Example method to find the nearest competitor vessel to the origin port
        for each competitor. This can help inform your margin adjustments.
        """
        competing_vessels = {}
        for company in self.headquarters.get_companies():
            if company == self:
                continue  # Skip self
            # For each competitor, find the vessel that is physically closest to the trade's origin
            closest_vessel = min(
                company.fleet,
                key=lambda v: self.headquarters.get_network_distance(v.location, current_trade.origin_port),
            )
            competing_vessels[company] = closest_vessel
        return competing_vessels

    def propose_schedules(self, trades):
        """
        Same (or similar) scheduling logic you already have, returning a ScheduleProposal.
        You can refine it for your own usage.
        """
        schedules = {}
        scheduled_trades = []
        unassigned_trades = []

        # Simple example:  sort trades by some priority measure
        trades = sorted(
            trades,
            key=lambda t: (t.amount / max(1, t.time_window[1] - t.time_window[0])),
            reverse=True
        )

        for current_trade in trades:
            best_vessel = None
            best_schedule = None
            best_score = float('-inf')

            for current_vessel in self._fleet:
                current_schedule = schedules.get(current_vessel, current_vessel.schedule)
                new_schedule = current_schedule.copy()
                new_schedule.add_transportation(current_trade)

                # Check feasibility
                if new_schedule.verify_schedule():
                    cost = self.calculate_cost(current_vessel, current_trade)
                    # Very naive scoring approach
                    score = current_trade.amount / (cost + 1e-6)
                    if score > best_score:
                        best_score = score
                        best_vessel = current_vessel
                        best_schedule = new_schedule

            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(current_trade)
            else:
                unassigned_trades.append(current_trade)

        # If unassigned trades remain, optionally try a second pass
        if unassigned_trades:
            print(f"Unassigned trades: {[t.origin_port.name + ' -> ' + t.destination_port.name for t in unassigned_trades]}")

        # Build cost dictionary
        costs = {}
        for vessel, sch in schedules.items():
            for trade in sch.get_trades():
                costs[trade] = self.calculate_cost(vessel, trade)

        return ScheduleProposal(schedules, scheduled_trades, costs)

    def find_schedules(self, trades):
        """
        A simpler approach that tries to place each trade in a feasible vessel schedule
        with minimal cost. 
        """
        schedules = {}
        scheduled_trades = []
        unassigned_trades = []
        allcost = {}

        for trade in trades:
            best_vessel = None
            best_schedule = None
            min_cost = float("inf")

            for vessel in self._fleet:
                current_schedule = schedules.get(vessel, vessel.schedule)
                new_schedule = current_schedule.copy()
                new_schedule.add_transportation(trade)

                if new_schedule.verify_schedule():
                    cost = self.calculate_cost(vessel, trade)
                    if cost < min_cost:
                        min_cost = cost
                        best_vessel = vessel
                        best_schedule = new_schedule

            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(trade)
                allcost[trade] = min_cost
            else:
                unassigned_trades.append(trade)

        if unassigned_trades:
            print(f"Unassigned trades after second pass: {unassigned_trades}")

        return ScheduleProposal(schedules, scheduled_trades, allcost)

    def calculate_cost(self, vessel, trade):
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
