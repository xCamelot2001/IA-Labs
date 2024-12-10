"""
Simulation observation related classes and functions.
"""
from mable.competition.generation import AuctionCargoEvent
from mable.engine import EnginePrePostRunner
from mable.event_management import (
    EventObserver, ArrivalEvent, CargoTransferEvent, TravelEvent, IdleEvent, VesselEvent,
    VesselLocationInformationEvent
)
from mable.metrics import GlobalMetricsCollector


class EventFuelPrintObserver(EventObserver):

    def __init__(self, logger):
        self._logger = logger

    def notify(self, engine, event, data):
        self._logger.info(event)
        if isinstance(event, VesselEvent) and event.performed_time() > 0:
            consumption = MetricsObserver.calculate_consumption(engine, event)
            co2_emissions = event.vessel.get_co2_emissions(consumption)
            cost = event.vessel.get_cost(consumption)
            self._logger.info(f"{event.vessel.name} Fuel consumption<{type(event).__name__.replace('Event', '')}>: "
                              f"{round(consumption, 3)} t,"
                              f" CO2: {round(co2_emissions, 3)} t, Cost: {round(cost, 2)} $")


class TradeDeliveryObserver(EventObserver):
    """
    An observer that logs completed trades.
    """

    def notify(self, engine, event, data):
        if isinstance(event, CargoTransferEvent) and event.is_drop_off:
            company_for_vessel = engine.find_company_for_vessel(event.vessel)
            engine.market_authority.trade_fulfilled(event.trade, company_for_vessel)


class AuctionOutcomeObserver(EventObserver):
    """
    An observer that logs allocated trades.
    """

    def notify(self, engine, event, data):
        if isinstance(event, AuctionCargoEvent):
            engine.market_authority.add_allocation_results(event.allocation_result)


class AuctionOutcomePrintObserver(EventObserver):
    """
    A logger that prints detailed information about the auction outcomes for
    :py:func:`mable.competition.generation.AuctionCargoEvent`.
    """

    def __init__(self, logger):
        self._logger = logger

    def notify(self, engine, event, data):
        if isinstance(event, AuctionCargoEvent):
            trade_allocation_result = {}
            for one_company in event.allocation_result.ledger.keys():
                for one_contract in event.allocation_result.ledger[one_company]:
                    trade_allocation_result[one_contract.trade] = (one_company.name, one_contract.payment)
            unallocated_trades = {trade: None for trade in event.allocation_result.unallocated_trades}
            trade_allocation_result.update(unallocated_trades)
            for one_trade in trade_allocation_result:
                trade_string = (f"'{one_trade.origin_port.name}"
                                f" -> {one_trade.destination_port.name}"
                                f" ({round(one_trade.amount, 2)})'")
                if trade_allocation_result[one_trade] is not None:
                    self._logger.info(f"TRADE ALLOCATION {trade_string}:"
                                      f" To {trade_allocation_result[one_trade][0]}"
                                      f" for {trade_allocation_result[one_trade][1]}.")
                else:
                    self._logger.info(f"TRADE ALLOCATION {trade_string}:"
                                      f" Not allocated.")


class MetricsObserver(EventObserver):

    def __init__(self):
        super().__init__()
        self._metrics = GlobalMetricsCollector()

    @property
    def metrics(self):
        return self._metrics

    @staticmethod
    def _get_event_vessel_status(event):
        if isinstance(event, IdleEvent):
            vessel_status = "idle"
        elif isinstance(event, CargoTransferEvent):
            if event.is_pickup:
                vessel_status = "loading"
            else:
                vessel_status = "unloading"
        elif isinstance(event, TravelEvent):
            if event.is_laden:
                vessel_status = "laden"
            else:
                vessel_status = "ballast"
        else:
            vessel_status = "unknown"
        return vessel_status

    def notify(self, engine, event, data):
        if isinstance(event, VesselEvent) and event.performed_time() > 0:
            consumption = MetricsObserver.calculate_consumption(engine, event)
            self._metrics.add_fuel_consumption(event.vessel, consumption)
            co2_emissions = event.vessel.get_co2_emissions(consumption)
            self._metrics.add_co2_emissions(event.vessel, co2_emissions)
            cost = event.vessel.get_cost(consumption)
            self._metrics.add_cost(event.vessel, cost)
            vessel_status = f"vessel_status_{MetricsObserver._get_event_vessel_status(event)}"
            self._metrics.add_dual_numeric_metric(event.vessel, vessel_status, event.performed_time())
        if isinstance(event, ArrivalEvent) or isinstance(event, VesselLocationInformationEvent):
            self._metrics.add_route_point(event.location.name, event.vessel)

    @staticmethod
    def calculate_consumption(engine, event):
        time = event.performed_time()
        consumption = 0
        if any(isinstance(event, event_type) for event_type in (ArrivalEvent, TravelEvent)) and time > 0:
            distance = event.distance(engine)
            speed = distance / time
            if event.vessel.has_any_load():
                consumption = event.vessel.get_laden_consumption(time, speed)
            else:
                consumption = event.vessel.get_ballast_consumption(time, speed)
        elif isinstance(event, CargoTransferEvent):
            if event.is_pickup:
                consumption = event.vessel.get_loading_consumption(time)
            else:
                consumption = event.vessel.get_unloading_consumption(time)
        elif isinstance(event, IdleEvent):
            consumption = event.vessel.get_idle_consumption(time)
        return consumption


class AuctionMetricsObserver(MetricsObserver):

    def notify(self, engine, event, data):
        super().notify(engine, event, data)
        if isinstance(event, AuctionCargoEvent):
            auction_results = {self._metrics.get_company_id(k): data.action_data[k] for k in data.action_data.keys()}
            self._metrics.add_global_company_list_metric("auction_outcomes", auction_results)


class LogRunner(EnginePrePostRunner):

    def __init__(self, run_logger, message):
        super().__init__()
        self._logger = run_logger
        self._message = message

    def run(self, simulation_engine):
        self._logger.info(self._message)
