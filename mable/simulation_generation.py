"""
Module for the generation of simulations and all classes within.
"""

import numpy as np

import mable.instructions as instructions
from mable.simulation_environment import World
from mable.engine import SimulationEngine
from mable.simulation_space.universe import Port, Location
from mable.simulation_space.structure import UnitShippingNetwork
from mable.transport_operation import SimpleCompany, SimpleVessel, CargoCapacity
from mable.shipping_market import StaticShipping, SimpleMarket, Trade
from mable.event_management import ArrivalEvent, CargoTransferEvent, IdleEvent, TravelEvent, EventQueue, \
    VesselLocationInformationEvent, CargoEvent


class SimulationBuilder:
    """
    A unit to translate simulation instructions into a simulation engine.

    The main function to use is :py:func`generate_engine` which should call the function to generate the subunits.
    The functions for the subunits all return self in order to allow easy concatenation of the generation process.
    """

    def __init__(self, class_factory, specifications):
        """
        Constructor.
        :param class_factory: ClassFactory
            The class factory.
        :param specifications:
            Specifications for a simulation.
        """
        super().__init__()
        self._class_factory = class_factory
        self._specifications = instructions.Specifications.init_from_json_string(specifications)
        self._world = None
        self._network = None
        self._companies = None
        self._shipping = None
        self._market = None
        self._random = None

    def generate_engine(self, *args, **kwargs):
        """
        Generates an engine from the specifications by generating all units in turn.
        Order: random, network, world, shipping_companies, shipping(cargo generation), market (shipping allocation).
        :return:
            The simulation engine.
        """
        self.generate_random()\
            .generate_network()\
            .generate_world()\
            .generate_shipping_companies()\
            .generate_shipping()\
            .generate_market()
        simulation_engine = self._class_factory.generate_engine(self._world, self._companies, self._shipping,
                                                                self._market, self._class_factory, *args, **kwargs)
        self.set_engines(simulation_engine, shipping_companies=self._companies,
                         shipping=self._shipping, market=self._market, world=self._world)
        return simulation_engine

    def set_engines(self, engine, *args, **kwargs):
        """
        Makes the engine known to the units constituting the simulation.

        On default called by :py:func:`generate_engine` as the last step.

        All units should be :py:class:`maritime_simulator.util.JsonAble` which is used to set the engine.
        :param engine:
            The simulation engine.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        """
        objects_to_set = [one_arg for one_arg in args]
        objects_to_set.extend([kwargs[key] for key in kwargs.keys()])
        for one_obj in objects_to_set:
            if hasattr(one_obj, '__iter__'):
                self.set_engines(engine, *one_obj)
            else:
                one_obj.set_engine(engine)

    def generate_random(self, *args, **kwargs):
        """
        Generates a random based on the specification information and the class factory's
        :py:func:`ClassFactory.generate_random`.
        :param args:
            Positional args.
            (Most likely no arguments since the args from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :param kwargs:
            Keyword args.
            (Most likely no arguments since the kwargs from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :return:
            self
        """
        args, kwargs = self._specifications.get(instructions.RANDOM_KEY)
        self._random = self._class_factory.generate_random(*args, **kwargs)
        return self

    def generate_world(self, *args, **kwargs):
        """
        Generates the world based on the specification information and the class factory's
        :py:func:`ClassFactory.generate_world`.
        Requires network, event queue and random to be already generated.
        :param args:
            Positional args.
            (Most likely no arguments since the args from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :param kwargs:
            Keyword args.
            (Most likely no arguments since the kwargs from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :return:
            self
        """
        self._world = self._class_factory.generate_world(self._network, self._class_factory.generate_event_queue(),
                                                         self._random)
        return self

    def generate_network(self, *args, **kwargs):
        """
        Generates the network (space) including the ports based on the specification information and the class factory's
        :py:func:`ClassFactory.generate_network` and :py:func:`ClassFactory.generate_port`, respectively.
        :param args:
            Positional args.
            (Most likely no arguments since the args from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :param kwargs:
            Keyword args.
            (Most likely no arguments since the kwargs from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :return:
            self
        """
        args, kwargs = self._specifications.get(instructions.NETWORK_KEY)
        ports_args = kwargs[instructions.PORTS_LIST_KEY]
        ports = []
        for one_ports_args in ports_args:
            if isinstance(one_ports_args, dict):
                one_port = self._class_factory.generate_port(**one_ports_args)
            else:
                one_port = one_ports_args
            ports.append(one_port)
        kwargs[instructions.PORTS_LIST_KEY] = ports
        self._network = self._class_factory.generate_network(*args, **kwargs)
        return self

    def generate_shipping_companies(self, *args, **kwargs):
        """
        Generates the shipping companies including the vessels based on the specification information and the
        class factory's :py:func:`ClassFactory.generate_company` and :py:func:`SimulationFactory.generate_fleet`,
        respectively.
        :param args:
            Positional args.
            (Most likely no arguments since the args from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :param kwargs:
            Keyword args.
            (Most likely no arguments since the kwargs from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :return:
            self
        """
        shipping_company_instructions = self._specifications[instructions.COMPANIES_KEY]
        shipping_companies = []
        name_idx = -1
        for one_company_instructions in shipping_company_instructions:
            name_idx += 1
            one_company_args, one_company_kwargs = one_company_instructions[-1]
            vessels = one_company_args[0]
            # TODO include naming into config generation
            name = f"Company_{name_idx}"
            if "name" in one_company_kwargs:
                name_idx -= 1
                name = one_company_kwargs["name"]
            one_company_fleet = self.generate_fleet(vessels)
            company = self._class_factory.generate_company(one_company_fleet, name)
            shipping_companies.append(company)
        self._companies = shipping_companies
        return self

    def generate_fleet(self, *args, **kwargs):
        """
        Generates the fleet of vessels of one company based on a list of vessel specifications and
        :py:func:`SimulationFactory.generate_vessel`.
        :param args:
            Positional args. The first argument should be a list of vessel instructions.
        :param kwargs:
            Keyword args.
        :return:
            A list of vessels.
        """
        fleet = []
        vessels = args[0]
        for one_vessel_arguments in vessels:
            one_vessel = self.generate_vessel(**one_vessel_arguments)
            fleet.append(one_vessel)
        return fleet

    def generate_vessel(self, *args, **kwargs):
        """
        Generates one vessel using based on class factory's  :py:func:`ClassFactory.generate_vessel`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args. Should include 'location' and 'capacities_and_loading_rates'.
        :return:
            A vessel.
        """
        kwargs["location"] = self._network.get_port_or_default(kwargs["location"], None)
        all_cargo_capacities = []
        for one_cargo_capacity in kwargs["capacities_and_loading_rates"]:
            all_cargo_capacities.append(self._class_factory.generate_cargo_capacity(**one_cargo_capacity))
        kwargs["capacities_and_loading_rates"] = all_cargo_capacities
        return self._class_factory.generate_vessel(**kwargs)

    def generate_shipping(self, *args, **kwargs):
        """
        Generates the shipping (cargo generation) unit based on the specification information and the
        class factory's :py:func:`ClassFactory.generate_shipping`.
        :param args:
            Positional args.
            (Most likely no arguments since the args from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :param kwargs:
            Keyword args.
            (Most likely no arguments since the kwargs from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :return:
            self
        """
        args, _ = self._specifications.get(instructions.SHIPPER_KEY)
        self._shipping = self._class_factory.generate_shipping(*args, class_factory=self._class_factory)
        return self

    def generate_market(self, *args, **kwargs):
        """
        Generates the market (cargo distribution) unit based on the specification information and the
        class factory's :py:func:`ClassFactory.generate_market`.
        :param args:
            Positional args.
            (Most likely no arguments since the args from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :param kwargs:
            Keyword args.
            (Most likely no arguments since the kwargs from the specifications are used. But can be used for further
            instructions from :py:func:`generate_engine`.)
        :return:
            self
        """
        args, kwargs = self._specifications.get(instructions.MARKET_KEY)
        self._market = self._class_factory.generate_market(*args, **kwargs)
        return self


class ClassFactory:
    """
    A class that provides simple functions which return an instance of the required class.

    This class' functions are intended to be overridden to replace the types used to generate the simulation or
    any used or constituting objects within.
    Any function should simply be a call to the class' constructor passing on any positional or keyword arguments:
    def generate_<unit>(*args, **kwargs):
        return <Unit>(*args, **kwargs)
    """

    @staticmethod
    def generate_engine(*args, **kwargs):
        """
        Generates a simulation engine. Default: py:class:`maritime_simulator.engine.SimulationEngine`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The engine.
        """
        return SimulationEngine(*args, **kwargs)

    @staticmethod
    def generate_world(*args, **kwargs):
        """
        Generates a world. Default: py:class:`maritime_simulator.simulation_environment.World`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The world.
        """
        return World(*args, **kwargs)

    @staticmethod
    def generate_network(*args, **kwargs):
        """
        Generates a network (space). Default: py:class:`mable.simulation_space.structure.UnitShippingNetwork`.

        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The network.
        """
        return UnitShippingNetwork(*args, **kwargs)

    @staticmethod
    def generate_port(*args, **kwargs):
        """
        Generates a port. Default: py:class:`mable.simulation_space.universe.Port`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The port.
        """
        return Port(*args, **kwargs)

    @staticmethod
    def generate_location(*args, **kwargs):
        """
        Generates a location. Default: py:class:`mable.simulation_space.universe.Location`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The network.
        """
        return Location(*args, **kwargs)

    # noinspection PyArgumentList
    @staticmethod
    def generate_market(*args, **kwargs):
        """
        Generates a market. Default: py:class:`maritime_simulator.shipping_market.SimpleMarket`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The market.
        """
        return SimpleMarket(*args, **kwargs)

    @staticmethod
    def generate_shipping(*args, **kwargs):
        """
        Generates a shipping (cargo generation) unit.
        Default: py:class:`maritime_simulator.shipping_market.StaticShipping`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The shipping.
        """
        return StaticShipping(*args, **kwargs)

    @staticmethod
    def generate_vessel(*args, **kwargs):
        """
        Generates a vessel. Default: py:class:`maritime_simulator.transport_operation.SimpleVessel`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The vessel.
        """
        return SimpleVessel(*args, **kwargs)

    @staticmethod
    def generate_cargo_capacity(*args, **kwargs):
        """
        Generates a cargo capacity (cargo hold).
        Default: py:class:`maritime_simulator.transport_operation.CargoCapacity`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The cargo capacity.
        """
        return CargoCapacity(*args, **kwargs)

    @staticmethod
    def generate_company(*args, **kwargs):
        """
        Generates a company. Default: py:class:`maritime_simulator.transport_operation.SimpleCompany`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The company.
        """
        return SimpleCompany(*args, **kwargs)

    # noinspection PyArgumentList
    @staticmethod
    def generate_event_queue(*args, **kwargs):
        """
        Generates an event queue. Default: py:class:`maritime_simulator.engine.SimulationEngine`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The event queue.
        """
        return EventQueue(*args, **kwargs)

    @staticmethod
    def generate_random(*args, **kwargs):
        """
        Generate a random. Default: py:class:`random.Random` with provided seed or seed 0 if non is provided.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The random.
        """
        return np.random.RandomState(kwargs.get("seed", 0))

    @staticmethod
    def generate_trade(*args, **kwargs):
        """
        Generates a trade (cargo). Default: py:class:`maritime_simulator.shipping_market.Trade`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The trade.
        """
        return Trade(*args, **kwargs)

    @staticmethod
    def generate_event_arrival(*args, **kwargs):
        """
        Generates an arrival event. Default: py:class:`maritime_simulator.event_management.ArrivalEvent`.

        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The event.
        """
        return ArrivalEvent(*args, **kwargs)

    @staticmethod
    def generate_event_cargo(*args, **kwargs):
        """
        Generates a cargo event. Default: py:class:`maritime_simulator.event_management.CargoEvent`.

        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The event.
        """
        return CargoEvent(*args, **kwargs)

    @staticmethod
    def generate_event_location_info(*args, **kwargs):
        """
        Generates a vessel location information event.
        Default: py:class:`maritime_simulator.event_management.VesselLocationInformationEvent`.
        :param args:
            Positional args.
            - Default see py:func:`maritime_simulator.event_management.VesselLocationInformationEvent.__init__`
                - time: The time of the event
                - vessel: The vessel
                - location: The location of the vessel
        :param kwargs:
            Keyword args.
        :return:
            The event.
        """
        return VesselLocationInformationEvent(*args, **kwargs)

    @staticmethod
    def generate_event_cargo_transfer(*args, **kwargs):
        """
        Generates a cargo transfer event. Default: py:class:`maritime_simulator.event_management.CargoTransferEvent`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The event.
        """
        return CargoTransferEvent(*args, **kwargs)

    @staticmethod
    def generate_event_idling(*args, **kwargs):
        """
        Generates an idling event. Default: py:class:`maritime_simulator.event_management.IdleEvent`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The event.
        """
        return IdleEvent(*args, **kwargs)

    @staticmethod
    def generate_event_travel(*args, **kwargs):
        """
        Generates a travel event. Default: py:class:`maritime_simulator.event_management.TravelEvent`.
        :param args:
            Positional args.
        :param kwargs:
            Keyword args.
        :return:
            The event.
        """
        return TravelEvent(*args, **kwargs)
