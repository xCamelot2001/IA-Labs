"""
Module of the main engine that runs the simulation (loop).
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from mable.event_management import EventExecutionData
from mable.competition.information import CompanyHeadquarters

if TYPE_CHECKING:
    from mable.event_management import EventObserver, EventQueue
    from event_management import Event
    from mable.shipping_market import Shipping


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
                 pre_run_cmds=None, post_run_cmds=None, output_directory=None, global_agent_timeout=60):
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
        """
        super().__init__()
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

    @property
    def headquarters(self):
        return self._headquarters

    @property
    def global_agent_timeout(self):
        return self._global_agent_timeout

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
