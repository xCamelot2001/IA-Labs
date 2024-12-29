"""
Module of the main engine that runs the simulation (loop).
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Dict

from loguru import logger

from mable.event_management import EventExecutionData
from mable.competition.information import CompanyHeadquarters, MarketAuthority

if TYPE_CHECKING:
    from mable.event_management import EventObserver, EventQueue
    from event_management import Event
    from mable.shipping_market import Shipping
    from mable.transport_operation import Vessel, Schedule, ShippingCompany
    from mable.shipping_market import AuctionLedger


def pre_run_inform_vessel_locations(simulation_engine):
    for one_company in simulation_engine.shipping_companies:
        for one_vessel in one_company.fleet:
            initial_location_event = (simulation_engine.class_factory
                                      .generate_event_location_info(time=-1, vessel=one_vessel,
                                                                    location=one_vessel.location))
            simulation_engine.notify_event_observer(initial_location_event, None)


def pre_run_place_vessels(simulation_engine):
    ports = simulation_engine.world.network.ports
    for one_company in simulation_engine.shipping_companies:
        for one_vessel in one_company.fleet:
            if one_vessel.location is None:
                random_port_index = simulation_engine.world.random.randint(len(ports))
                random_port = ports[random_port_index]
                one_vessel.location = random_port


class EnginePrePostRunner:
    """
    A framework to run functions before and after engine execution.
    """

    @abstractmethod
    def run(self, simulation_engine):
        pass


class SimulationEngine:
    """
    Main class to run a simulation.
    """

    PRE_RUN_CMDS = [pre_run_place_vessels, pre_run_inform_vessel_locations]
    POST_RUN_CMDS = []

    def __init__(self, world, shipping_companies, cargo_generation, cargo_market, class_factory,
                 pre_run_cmds=None, post_run_cmds=None, output_directory=None, global_agent_timeout=60,
                 info=None):
        """
        Constructor.

        :param world:
            The world environment of the simulation.
        :type world: maritime_simulator.simulation_environment.World
        :param shipping_companies: [maritime_simulator.transport_operation.ShippingCompany]
            The list of companies to operate cargo transportation.
        :param cargo_generation: The cargo generation object.
        :type cargo_generation: Shipping
        :param cargo_market: maritime_simulator.shipping_market.Market
            The cargo distribution object.
        :param class_factory:
            The class generation object.
        :type class_factory: ClassFactory
        :param pre_run_cmds:
            Commands to be executed before the run of the main engine loop. All functions must have one argument
            to which the SimulationEngine passes itself.
            Default list is :py:const:`SimulationEngine.PRE_RUN_CMDS` which is applied when None is passed.
        :param post_run_cmds:
            Commands to be executed after the run of the main engine loop. All functions must have one argument
            to which the SimulationEngine passes itself.
            Default list is :py:const:`SimulationEngine.POST_RUN_CMDS` which is applied when None is passed.
        :param output_directory: The directory for output files. If None, the working directory is used.
        :type output_directory: str | None
        :param global_agent_timeout: The timeout used for agent operations.
        :type global_agent_timeout: int
        :param info: Any information on the type or setting of the simulation.
        :type info: str | dict
        """
        super().__init__()
        self._info = info
        self._event_observer = []
        self._world = world
        self._shipping_companies = shipping_companies
        self._shipping = cargo_generation
        self._market = cargo_market
        self._class_factory = class_factory
        self._pre_run_cmds = pre_run_cmds
        if self._pre_run_cmds is None:
            self._pre_run_cmds = SimulationEngine.PRE_RUN_CMDS
        self._post_run_cmds = post_run_cmds
        if self._post_run_cmds is None:
            self._post_run_cmds = SimulationEngine.POST_RUN_CMDS
        self._output_directory = output_directory
        if output_directory is None:
            self._output_directory = "."
        self._headquarters = CompanyHeadquarters(self)
        self._global_agent_timeout = global_agent_timeout
        self._market_authority = MarketAuthority()
        self._new_schedules = {}

    @property
    def headquarters(self):
        return self._headquarters

    @property
    def global_agent_timeout(self):
        return self._global_agent_timeout

    @property
    def market_authority(self):
        return self._market_authority

    @property
    def info(self):
        return self._info

    def _pre_run(self):
        self._set_up_trades()
        for f in self._pre_run_cmds:
            if isinstance(f, EnginePrePostRunner):
                f.run(self)
            else:
                f(self)

    def _post_run(self):
        for f in self._post_run_cmds:
            if isinstance(f, EnginePrePostRunner):
                f.run(self)
            else:
                f(self)

    def _set_up_trades(self):
        for one_time in self._shipping.get_trading_times():
            one_trading_event = self._class_factory.generate_event_cargo(one_time)
            self._world.event_queue.put(one_trading_event)

    def _process_next_event(self):
        """
        Process the next event in the queue if one exists.
        :return: The next event and the data from its execution.
        :rtype: tuple[Event|None, EventExecutionData|None]
        """
        next_event, data = None, None
        if self._world.do_events_exists():
            next_event = self._world.get_next_event()
            data = EventExecutionData()
            event_action_result = next_event.event_action(self)
            data.action_data = event_action_result
        return next_event, data

    def run(self):
        """
        Run a simulation until no events are left to deal with.

        Start with adding all cargo events into the event queue.
        """
        self._pre_run()
        while self._world.do_events_exists():
            next_event, data = self._process_next_event()
            self.notify_event_observer(next_event, data)
        self._post_run()

    def add_new_schedules(self, company, schedules):
        """
        Adds new vessel schedules to be applied.

        :param company: The company which owns the vessels.
        :type company: ShippingCompany
        :param schedules: The schedules.
        :type schedules: Dict[Vessel, Schedule]
        """
        self._new_schedules[company] = schedules

    def apply_new_schedules(self, distribution_ledger):
        """
        Applies any new existing schedules to the vessels.

        :param distribution_ledger: The outcome of the last auction.
        :type distribution_ledger: AuctionLedger
        """
        while len(self._new_schedules) > 0:
            one_company = next(iter(self._new_schedules.keys()))
            schedules_for_company = self._new_schedules[one_company]
            trades_in_all_schedule = [s.get_scheduled_trades() for s in schedules_for_company.values()]
            trades_in_all_schedule = [t for trades_in_one_schedule in trades_in_all_schedule for t in trades_in_one_schedule]
            if len(set(trades_in_all_schedule)) == len(trades_in_all_schedule):
                for one_vessel in schedules_for_company.keys():
                    schedule_for_vessel = schedules_for_company[one_vessel]
                    if schedule_for_vessel.verify_schedule():
                        trades_previously_awarded_to_company = [c.trade for c in self.market_authority.contracts_per_company.get(one_company, [])]
                        trades_currently_awarded_to_company = [c.trade for c in distribution_ledger.ledger.get(one_company, [])]
                        trades_awarded_to_company = trades_previously_awarded_to_company + trades_currently_awarded_to_company
                        trades_in_schedule = [t for t in schedule_for_vessel.get_scheduled_trades()]
                        all_scheduled_trades_awarded_individually = [
                            t in trades_awarded_to_company for t in trades_in_schedule]
                        all_scheduled_trades_awarded = all(all_scheduled_trades_awarded_individually)
                        if all_scheduled_trades_awarded:
                            one_vessel.schedule = schedule_for_vessel
                        else:
                            logger.warning(f"For company {one_company.name} and vessel {one_vessel.name}"
                                           f" the schedule was rejected since (an) unawarded trade(a) was/were scheduled.")
                    else:
                        logger.warning(f"For company {one_company.name} and vessel {one_vessel.name}"
                                       f" the schedule was rejected:"
                                       f" time constraints satisfied '{schedule_for_vessel.verify_schedule_time()}'"
                                       f" and cargo constraints satisfied '{schedule_for_vessel.verify_schedule_cargo()}'")
            else:
                logger.warning(f"For company {one_company.name}"
                               f" the schedules were rejected due to scheduling the same trade more than once.")
            del self._new_schedules[one_company]

    @property
    def world(self):
        """
        :return: maritime_simulator.simulation_environment.World
            The world environment of the simulation.
        """
        return self._world

    @property
    def event_queue(self):
        """
        :return: The worlds event queue.
        :rtype: EventQueue
        """
        return self._world.event_queue

    @property
    def shipping_companies(self):
        """
        :return: [maritime_simulator.transport_operation.ShippingCompany]
            The list of companies to operate cargo transportation.
        """
        return self._shipping_companies

    def find_company_for_vessel(self, vessel):
        """
        Find the company the vessel belongs to.

        :param vessel: The vessel.
        :type vessel: Vessel
        :return: The company
        """
        company = None
        i = 0
        while i < len(self.shipping_companies) and company is None:
            one_company = self.shipping_companies[i]
            if vessel in one_company.fleet:
                company = one_company
            i += 1
        if company is None:
            raise ValueError(f"No company found for vessel {vessel}")
        return company

    @property
    def shipping(self):
        """
        :return: maritime_simulator.shipping_market.Shipping
            The cargo generation object.
        """
        return self._shipping

    @property
    def market(self):
        """
        :return: maritime_simulator.shipping_market.Market
            The cargo distribution object (the cargo market).
        """
        return self._market

    @property
    def class_factory(self):
        """
        :return: maritime_simulator.simulation_generation.ClassFactory
            The class generation object (the class factory).
        """
        return self._class_factory

    @property
    def output_directory(self):
        return self._output_directory

    def get_event_observers(self):
        """
        Return all current event observers.
        :return: The observers.
        :rtype: list[EventObserver]
        """
        return self._event_observer

    def register_event_observer(self, observer: EventObserver):
        """
        Add an observer to the list of observer that are informed about events occurrences.
        :param observer: maritime_simulator.event_management.EventObserver
            The observer to add.
        """
        self._event_observer.append(observer)

    def unregister_event_observer(self, observer: EventObserver):
        """
        Remove an observer from the list of observer that are informed about events occurrences.
        :param observer: maritime_simulator.event_management.EventObserver
            The observer to remove.
        """
        self._event_observer.remove(observer)

    def notify_event_observer(self, event, data):
        """
        Notify observer about an event that has occurred.
        :param event: Event
            Some event.
        :param data: EventExecutionData
            Additional data in conjunction with the event. E.g. data that was produced or changes that were made.
        """
        for one_observer in self._event_observer:
            one_observer.notify(self, event, data)
