from mable.cargo_bidding import TradingCompany, Bid
from mable.examples import environment, fleets
from mable.transport_operation import ScheduleProposal, Vessel, SimpleVessel
from mable.transportation_scheduling import Schedule
from mable.shipping_market import TimeWindowTrade
from mable.extensions.fuel_emissions import VesselWithEngine
from mable.examples import environment, fleets
import mable.simulation_space.universe


class Company5(TradingCompany):
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

    def create_bid(self, cost, trade, auction_ledger=None):
        """
        Create a bid for a trade using auction_ledger's payment to compute profit factor.
        """
        profit_factor = 0.2  # 初始利润因子

        # 获取竞争对手的支付信息
        if auction_ledger:
            payment_data = []  # 用于存储过去的支付数据
            for competitor, trades in auction_ledger.items():
                for record in trades:
                    if hasattr(record, 'payment') and record.payment is not None:
                        payment_data.append(record.payment)

            # 如果存在历史支付记录，计算平均支付金额
            if payment_data:
                avg_payment = sum(payment_data) / len(payment_data)
                if avg_payment > cost:  # 如果平均支付金额高于当前成本
                    profit_factor += 0.1  # 提高利润因子
                else:  # 平均支付金额低于当前成本
                    profit_factor -= 0.05  # 降低利润因子，增加中标机会

        # 考虑竞争对手船只的距离
        competing_vessels = self.find_competing_vessels(trade)
        closest_distance = min(
            [self.headquarters.get_network_distance(v.location, trade.origin_port) for v in competing_vessels.values()],
            default=float('inf')
        )
        if closest_distance < 50:  # 如果竞争对手船只距离小于50海里
            profit_factor += 0.1  # 提高利润因子，避免低价竞争

        # 考虑时间窗口的紧迫性
        if trade.time_window[1] - trade.time_window[0] < 100:
            profit_factor += 0.05

        # 计算最终竞标金额
        bid_amount = cost * (1 + profit_factor)
        return bid_amount

    def inform(self, trades, *args, **kwargs):
        """
        Inform the company of the trades available for bidding.
        """
        bids=[]
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        self._current_scheduling_proposal = proposed_scheduling
        trades_and_costs = [
            (x, proposed_scheduling.costs[x]) if x in proposed_scheduling.costs
            else (x, 0)
            for x in scheduled_trades]
        for x in scheduled_trades:
            bid_amount = self.create_bid(proposed_scheduling.costs[x], x)
            bids = [Bid(amount=bid_amount, trade=one_trade) for one_trade, cost in trades_and_costs]
            #self._future_trades = None

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
        for contract in contracts:
            print(f"contract.trade{contract.trade}")
            print(f"scheduled_trades{scheduling_proposal.scheduled_trades}")
            if contract.trade in scheduling_proposal.scheduled_trades:
                contract.fulfilled = True
        self.current_schedule = contracts



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
    def find_competing_vessels(self, current_trade):
        """
        Find the closest vessel to the trade's origin port for each competing company.
        """
        competing_vessels = {}

        for company in self.headquarters.get_companies():
            if company == self:
                continue
            # for every company find the closest vessel to the trade's origin port
            print(f"nidejiandui:{company.fleet}")
            print(f"nidetrade:{current_trade}")
            closest_vessel = min(
                company.fleet,
                key=lambda v: self.headquarters.get_network_distance(
                    v.location,current_trade.origin_port
                ),
            )
            # add the closest vessel to the competing vessels dictionary
            competing_vessels[company] = closest_vessel
        return competing_vessels

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

        # Step 3: Attempt to reassign unassigned trades
        for trade in unassigned_trades[:]:
            for vessel in self._fleet:
                current_schedule = schedules.get(vessel, vessel.schedule)
                new_schedule = current_schedule.copy()

                distance_to_pickup = self.headquarters.get_network_distance(vessel.location, trade.origin_port)
                travel_time_to_pickup = vessel.get_travel_time(distance_to_pickup)
                loading_time = vessel.get_loading_time(trade.cargo_type, trade.amount)

                # Check time window again
                if travel_time_to_pickup + loading_time > trade.time_window[1] - trade.time_window[0]:
                    continue

                new_schedule.add_transportation(trade)
                if new_schedule.verify_schedule():
                    schedules[vessel] = new_schedule
                    scheduled_trades.append(trade)
                    unassigned_trades.remove(trade)
                    break

        # Step 4: Log unassigned trades
        if unassigned_trades:
            print(
                f"Unassigned trades: {[trade.origin_port.name + ' -> ' + trade.destination_port.name for trade in unassigned_trades]}")

        # Step 5: Return the proposed schedules
        costs = {trade: self.calculate_cost(vessel, trade) for trade in scheduled_trades for vessel in schedules.keys()}
        return ScheduleProposal(schedules, scheduled_trades, costs)

    def find_schedules(self, trades):
        """
        Find schedules for a list of trades by assigning them to vessels in the fleet.

        :param trades: List of trades (contracts) to schedule.
        :return: ScheduleProposal containing schedules, scheduled trades, and costs.
        """
        schedules = {}
        scheduled_trades = []
        unassigned_trades = []
        allcost = []


        # Step 1: Sort trades by priority (e.g., profit margin and earliest pickup time)
        #trades = sorted(trades, key=lambda t: (t.amount / self.calculate_cost(vessel, t), -t.earliest_pickup), reverse=True)

        # Step 2: Iterate over each trade and try to assign to the best vessel
        for current_trade in trades:
            best_vessel = None
            best_schedule = None
            min_cost = float("inf")

            # Step 3: Try to assign the trade to each vessel and calculate the cost
            for current_vessel in self._fleet:
                current_vessel_schedule = schedules.get(current_vessel, current_vessel.schedule)
                new_schedule = current_vessel_schedule.copy()
                new_schedule.add_transportation(current_trade)

                if new_schedule.verify_schedule():
                    # Calculate the cost of this schedule
                    cost = self.calculate_cost(current_vessel, current_trade)
                    if cost < min_cost:
                        min_cost = cost
                        best_vessel = current_vessel
                        best_schedule = new_schedule

            # Step 4: Assign the trade to the best vessel if found
            if best_vessel and best_schedule:
                schedules[best_vessel] = best_schedule
                scheduled_trades.append(current_trade)
                allcost.append(min_cost)  # Record the minimum cost
            else:
                # If no suitable vessel is found, record the trade as unassigned
                unassigned_trades.append(current_trade)

        # Step 5: Log unassigned trades for debugging
        if unassigned_trades:
            print(
                f"Unassigned trades: {[trade.origin_port.name + ' -> ' + trade.destination_port.name for trade in unassigned_trades]}")

        # Step 6: Return the scheduling proposal
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

        # 增加违约成本
        time_penalty = max(0, trade.earliest_drop_off - (trade.time_window[1] - trade.time_window[0]))

        total_cost = (
                vessel.get_cost(vessel.get_loading_consumption(loading_time)) +
                vessel.get_cost(vessel.get_unloading_consumption(loading_time)) +
                vessel.get_cost(vessel.get_laden_consumption(travel_time, vessel.speed)) +
                time_penalty  # 违约时间的高额惩罚
        )
        return total_cost





