"""
Classes for shipping companies.
"""

from abc import abstractmethod
import copy
from dataclasses import dataclass
from typing import Hashable, List, Dict, TYPE_CHECKING, TypeVar, Generic

import attrs
from marshmallow import Schema, fields

from mable.simulation_de_serialisation import DataSchema, DataClass, DynamicNestedField
from mable.shipping_market import Trade
from mable.transportation_scheduling import Schedule
from mable.simulation_environment import SimulationEngineAware
from mable.util import JsonAble
from mable.simulation_space.universe import OnJourney

if TYPE_CHECKING:
    from mable.event_management import VesselEvent
    from mable.simulation_space.universe import Location


@dataclass
class CargoCapacity(JsonAble):
    """
    :param cargo_type: The type of cargo.
    :type cargo_type: Hashable
    :param loading_rate: The amount of tonnes (un)loadable in one hour.
    :type loading_rate: float
    :param capacity: The capacity in tonnes (t).
    :type capacity: float
    """
    cargo_type: Hashable
    loading_rate: float
    capacity: float

    def to_json(self):
        return self.__dict__

    @attrs.define
    class Data(DataClass):
        cargo_type: Hashable
        loading_rate: float
        capacity: float

        class Schema(DataSchema):
            cargo_type = fields.Str()
            loading_rate = fields.Float()
            capacity = fields.Float()


class CargoContainer:
    """
    A capacity limited container for cargo.
    """

    def __init__(self, capacity, loading_rate):
        """
        :param capacity: The capacity of the container.
        :type capacity: float
        :param loading_rate: The rate at which the container can be loaded and unloaded.
        :type loading_rate: float
        """
        self._capacity = capacity
        self._loading_rate = loading_rate
        self._amount = 0

    @property
    def capacity(self):
        """
        :return: The capacity of the hold.
        :rtype: float
        """
        return self._capacity

    @property
    def loading_rate(self):
        """
        :return: The rate at which the container can be loaded and unloaded.
        :rtype: float
        """
        return self._loading_rate

    @property
    def amount(self):
        """
        :return: The current amount of cargo.
        :rtype: float
        """
        return self._amount

    @amount.setter
    def amount(self, amount):
        """
        Set the current amount.

        :param amount: The amount.
        :type amount: float
        :raises ValueError: if the amount is negative or exceeds the capacity.
        """
        if amount < 0:
            raise ValueError("not enough cargo in cargo container")
        elif amount > self.capacity:
            raise ValueError(f"not enough capacity in cargo container (capacity: {self._capacity}, amount: {amount})")
        self._amount = amount


class CargoHoldSchema(Schema):
    capacities = fields.List(DynamicNestedField())


class CargoHold:
    """
    A cargo hold for several cargo containers that can be loaded and unloaded.
    """

    def __init__(self, capacities: List[CargoCapacity]):
        """
        Constructor.
        :param capacities: List[CargoCapacity]
            A list of the types, capacities and loading rates of the cargo containers.
        """
        super().__init__()
        self._hold = {}
        for one_capacity in capacities:
            self._hold[one_capacity.cargo_type] = CargoContainer(one_capacity.capacity, one_capacity.loading_rate)

    def available_cargo_types(self):
        """
        A list of the cargo types of the containers in this cargo hold.

        :return: The list of cargo types.
        """
        return list(self._hold.keys())

    def __getitem__(self, cargo_type):
        """
        The cargo container of the specified type.

        :param cargo_type: The type of the cargo container.
        :return: The cargo container
        :rtype: CargoContainer
        """
        return self._hold[cargo_type]

    def get_current_load(self, cargo_type):
        """
        The current amount in the cargo container of the specified type.

        :param cargo_type: The cargo type.
        :type cargo_type: Hashable
        :return: The amount of cargo.
        :rtype: float
        """
        return self[cargo_type].amount

    def is_empty(self):
        """
        Checks if no cargo of any possible types is loaded.
        :return: True if for no cargo type any amount is loaded. Otherwise, False.
        :rtype: bool
        """
        is_empty = True
        all_cargo_types = self.available_cargo_types()
        i = 0
        while is_empty and i < len(all_cargo_types):
            one_cargo_types = all_cargo_types[i]
            if self.get_current_load(one_cargo_types) > 0:
                is_empty = False
            i += 1
        return is_empty

    def get_capacity(self, cargo_type):
        """
        The capacity of the cargo container of the specified type.

        :param cargo_type: The cargo type.
        :type cargo_type: Hashable
        :return: The capacity.
        :rtype: float
        """
        return self[cargo_type].capacity

    def get_loading_rate(self, cargo_type):
        """
        The loading rate of the cargo container of the specified type.

        :param cargo_type: The cargo type.
        :return: The loading rate.
        :rtype: float
        """
        return self[cargo_type].loading_rate

    def _change_cargo_amount(self, cargo_type, amount):
        """
        Changes the amount of cargo in the container of the type. A positive amount constitutes loading and
        a negative amount constitutes unloading.

        :param cargo_type: The cargo type.
        :type cargo_type: Hashable
        :param float amount: The amount to change the current amount by.
        :raises ValueError: if there is no cargo container of the specified type.
        """
        if cargo_type in self._hold:
            self._hold[cargo_type].amount += amount
        else:
            raise ValueError(f"vessel does not carry cargo of type '{cargo_type}'")

    def load_cargo(self, cargo_type, amount):
        """
        Loads the specified amount of cargo in the container of the type.

        :param cargo_type: The cargo type.
        :type cargo_type: Hashable
        :param float amount: The amount to load.
        :raises ValueError: if the amount is negative.
        """
        if amount < 0:
            raise ValueError("a loading amount has to be positive.")
        self._change_cargo_amount(cargo_type, amount)

    def unload_cargo(self, cargo_type, amount):
        """
        Unloads the specified amount of cargo in the container of the type.

        :param cargo_type: The cargo type.
        :type cargo_type: str
        :param float amount: The amount to unload.
        :raises ValueError: if the amount is negative.
        """
        if amount < 0:
            raise ValueError("an unloading amount has to be positive.")
        self._change_cargo_amount(cargo_type, -amount)


class Vessel(SimulationEngineAware):
    """
    A vessel to travel and transport cargo.
    """

    def __init__(self, capacities_and_loading_rates, location, keep_journey_log=True, name=None, company=None):
        """
        :param capacities_and_loading_rates: A list of the types, capacities and loading rates of the cargo containers.
        :type capacities_and_loading_rates: List[CargoCapacity]
        :param location: The location of the vessel at creation.
        :param keep_journey_log: If true the vessel keeps a log of event occurrences that affected the vessel.
        :type keep_journey_log: bool
        :param name: The name of the vessel.
        :type name: str
        :param company: The company that owns the vessel.
        :type company: ShippingCompany[V]
        """
        super().__init__()
        self._cargo_hold = CargoHold(capacities_and_loading_rates)
        self._location = location
        self._schedule = Schedule(self, 0)
        self._keep_journey_log = keep_journey_log
        self._journey_log = []
        self._name = name
        self._company = company

    @attrs.define
    class Data(DataClass):
        capacities_and_loading_rates: List[CargoCapacity.Data]
        location: str | None
        keep_journey_log: bool
        name: str

        class Schema(DataSchema):
            capacities_and_loading_rates = fields.List(DynamicNestedField())
            location = fields.Str(default=None, allow_none=True)
            keep_journey_log = fields.Bool(default=True)
            name = fields.Str(default=None)

    def __repr__(self):
        str_repr = f"<name: {self._name}, location: {self._location}>"
        return str_repr

    def set_engine(self, engine):
        super().set_engine(engine)
        if isinstance(self._location, str):
            self._location = self._engine.world.network.get_port_or_default(self._location, None)
        self._schedule.set_engine(engine)

    @property
    def capacities_and_loading_rates(self):
        """
        A list of :py:class:`CargoCapacity` of the current cargo hold.

        :return: The list.
        :rtype: List[CargoCapacity]
        """
        capacity_list = [
            CargoCapacity(
                cargo_type=one_cargo_type,
                loading_rate=self._cargo_hold.get_loading_rate(one_cargo_type),
                capacity=self._cargo_hold.get_capacity(one_cargo_type)
            )
            for one_cargo_type in self._cargo_hold.available_cargo_types()
        ]
        return capacity_list

    def capacity(self, cargo_type):
        """
        The capacity of the cargo container of the specified type.

        :param cargo_type: The cargo type.
        :type cargo_type: Hashable
        :return: The capacity.
        :rtype: float
        """
        return self._cargo_hold.get_capacity(cargo_type)

    def current_load(self, cargo_type):
        """
        The current amount in the cargo container of the specified type.

        :param cargo_type: The cargo type.
        :type cargo_type: Hashable
        :return: The amount of cargo.
        :rtype: float
        """
        return self._cargo_hold.get_current_load(cargo_type)

    def has_any_load(self):
        """
        Indicates if any of the cargo containers of the hold contain load.

        :return:  True if any one of the cargo container has load and False otherwise.
        :rtype: bool
        """
        has_load = any(self.current_load(one_type) > 0 for one_type in self.loadable_cargo_types())
        return has_load

    def loadable_cargo_types(self):
        """
        Indicates which cargo types can be loaded into the cargo hold.

        :return: List of cargo types.
        :rtype: List[Hashable]
        """
        return self._cargo_hold.available_cargo_types()

    def load_cargo(self, cargo_type, amount):
        """
        **WARNING**: Part of internal simulation logic. Only allowed to be called by the simulation!

        Loads the specified amount of cargo in the container of the type.

        :param cargo_type: The cargo type.
        :type cargo_type: Hashable
        :param float amount: The amount to load.
        :raises ValueError: if the amount is negative.
        """
        self._cargo_hold.load_cargo(cargo_type, amount)

    def unload_cargo(self, cargo_type, amount):
        """
        **WARNING**: Part of internal simulation logic. Only allowed to be called by the simulation!

        Unloads the specified amount of cargo in the container of the type.

        :param cargo_type: The cargo type.
        :type cargo_type: str
        :param float amount: The amount to unload.
        :raises ValueError: if the amount is negative.
        """
        self._cargo_hold.unload_cargo(cargo_type, amount)

    def copy_hold(self):
        """
        Create a deep copy of the current cargo hold.

        :return: The copy of the cargo hold.
        """
        return copy.deepcopy(self._cargo_hold)

    @property
    def schedule(self):
        """
        :return: A copy of the vessel's current schedule.
        :rtype: Schedule
        """
        return self._schedule.copy()

    @property
    def _next_event(self):
        """
        Retrieves, if exists, the next event in schedule without removing it.

        :return: The event.
        """
        return self._schedule.next()

    def has_next_event(self):
        """
        Checks if there is at least one event in the schedule.

        :return: True is there is an event in the schedule and False otherwise.
        :rtype: bool
        """
        return self._next_event is not None

    @property
    def journey_log(self):
        """
        The current log of events pertaining the vessel.

        :return: [VesselEvent]
        """
        return self._journey_log

    def log_journey_log_event(self, log_entry):
        """
        **WARNING**: Part of internal simulation logic. Only allowed to be called by the simulation!

        Log an entry in the journey log.

        :param log_entry: The entry to make
        :type log_entry: VesselEvent
        """
        if self._keep_journey_log:
            self._journey_log.append(log_entry)

    @schedule.setter
    def schedule(self, new_schedule):
        """
        Replace the current schedule with a new schedule. The first event is taken as the current event that is added
        to the event queue and the old next event is removed from the event queue (if either or any exist).
        Does not validate the schedule.

        :param new_schedule: The new schedule.
        """
        if self._next_event is not None:
            self._engine.event_queue.remove(self._next_event)
        self._schedule = new_schedule
        self.start_next_event()

    def event_occurrence(self, event):
        """
        **WARNING**: Part of internal simulation logic. Only allowed to be called by the simulation!

        Informs the vessel about the occurrence of an event. This has to be the vessel's next event.

        :param event: The event.
        :raises ValueError: if the event is not the next event.
        """
        if event == self._next_event:
            self.log_journey_log_event(self._schedule.pop())
            self.start_next_event()
        else:
            raise ValueError(f"event {event} is not the next event of the vessel")

    def start_next_event(self):
        """
        **WARNING**: Part of internal simulation logic. Only allowed to be called by the simulation!

        Starts the next event in schedule. The event is also added to the event queue. However, does not check if
        (if any) preceding next event has occurred nor tidies the event queue of any such event.
        """
        next_event = self._next_event
        if next_event is not None:
            self._engine.event_queue.put(next_event)

    @property
    def location(self):
        """
        :return: The current location.
        :rtype: Location | OnJourney
        """
        return self._location

    @location.setter
    def location(self, location):
        """
        **WARNING**: Part of internal simulation logic. Only allowed to be called by the simulation!

        Change the current location of the vessel.

        :param location: The new location.
        :type location: Location | OnJourney
        """
        self._location = location

    @property
    def name(self):
        """
        :return: The name of the vessel.
        :rtype: str
        """
        return self._name

    @abstractmethod
    def get_travel_time(self, distance, *args, **kwargs):
        """
        Returns the time in hours the vessel requires to traverse the specified distance.

        :param float distance: The distance
        :param args: Positional args for additional arguments in subclasses.
        :param kwargs: Keyword args for additional arguments in subclasses.
        :return: The time
        :rtype: float
        """
        pass

    @abstractmethod
    def get_loading_time(self, cargo_type, amount, *args, **kwargs):
        """
        Returns the time in hours the vessel requires to load the specified amount of the specified cargo.

        :param Hashable cargo_type: The cargo type.
        :param float amount: The amount.
        :param args: Positional args for additional arguments in subclasses.
        :param kwargs: Keyword args for additional arguments in subclasses.
        :return: The time
        :rtype: float
        """
        pass


class SimpleVessel(Vessel):
    """
    A vessel with a fixed travel time.
    """

    def __init__(self, capacities_and_loading_rates, location, speed, keep_journey_log=True, name=None, company=None):
        """
        :param capacities_and_loading_rates: A list of the types, capacities and loading rates of the cargo containers.
        :type capacities_and_loading_rates: List[CargoCapacity]
        :param location: The location of the vessel at creation.
        :param speed: The speed of the vessel.
        :type speed: float
        :param keep_journey_log: If true the vessel keeps a log of event occurrences that affected the vessel.
        :type keep_journey_log: bool
        :param name: The name of the vessel.
        :type name: str
        :param company: The company that owns the vessel.
        :type company: ShippingCompany[V]
        """
        super().__init__(
            capacities_and_loading_rates, location, keep_journey_log=keep_journey_log, name=name, company=company)
        self._speed = speed

    @attrs.define
    class Data(Vessel.Data):
        speed: float

        class Schema(Vessel.Data.Schema):
            speed = fields.Float()

    def __repr__(self):
        str_repr = (f"<name: {self._name}, location: {self._location}, "
                    f"speed: {self._speed}, hold: {self.capacities_and_loading_rates}>")
        return str_repr

    @property
    def speed(self):
        """
        :return: The speed of the vessel.
        :rtype: float
        """
        return self._speed

    def get_travel_time(self, distance, *args, **kwargs):
        """
        The time in hours the vessel requires to traverse the specified distance determined by the vessel's speed.

        :param float distance: The distance
        :param args: Positional args for additional arguments in subclasses.
        :param kwargs: Keyword args for additional arguments in subclasses.
        :return: The time
        :rtype: float
        """
        travel_time = float('inf')
        if distance is not None:
            travel_time = distance/self._speed
        return travel_time

    def get_loading_time(self, cargo_type, amount, *args, **kwargs):
        """
        Returns the time in hours the vessel requires to load the specified amount of the specified cargo based on
        the loading rate of the cargo hold.

        :param cargo_type: The cargo type.
        :type cargo_type: Hashable
        :param amount: The amount.
        :type amount: float
        :param args: Positional args for additional arguments in subclasses.
        :param kwargs: Keyword args for additional arguments in subclasses.
        :return: The time
        :rtype: float
        """
        return amount / self._cargo_hold.get_loading_rate(cargo_type)

    def to_json(self):
        dict_repr = {"capacities_and_loading_rates": self.capacities_and_loading_rates,
                     "location": self.location,
                     "speed": self._speed,
                     "keep_journey_log": self._keep_journey_log,
                     "name": self.name}
        return dict_repr

V = TypeVar('V', bound=Vessel)
class ShippingCompany(SimulationEngineAware, Generic[V]):
    """
    Interface for a shipping company.
    """

    def __init__(self, fleet, name):
        """
        Constructor.
        :param fleet: List of vessels.
        :type fleet: List[V]
        """
        super().__init__()
        self._fleet = fleet
        self._name = name

    @attrs.define
    class Data(DataClass):
        fleet: list[Vessel.Data]
        name: str

        class Schema(DataSchema):
            fleet = fields.List(DynamicNestedField())
            name = fields.Str()

    @classmethod
    def get_class(cls):
        return cls

    def set_engine(self, engine):
        """
        Make the simulation engine know to the company and all its vessels.
        :param engine: SimulationEngine
            The engine.
        """
        super().set_engine(engine)
        for one_vessel in self._fleet:
            one_vessel.set_engine(engine)

    @property
    def fleet(self):
        """
        :return: The vessels of the current fleet.
        :rtype: List[V]
        """
        return self._fleet

    @property
    def name(self):
        return self._name

    @abstractmethod
    def pre_inform(self, *args, **kwargs):
        """
        Inform the shipping company of trades that are available at a future time. No response expected.

        :param args: Positional args for additional arguments in subclasses.
        :param kwargs: Keyword args for additional arguments in subclasses.
        """
        pass

    @abstractmethod
    def inform(self, *args, **kwargs):
        """
        Inform the shipping company of trades that are coming available.
        :param args: Positional args for additional arguments in subclasses.
        :param kwargs: Keyword args for additional arguments in subclasses.
        :return: A response to the information about cargoes, e.g. a list of cargoes the company is interested in.
        """
        pass

    @abstractmethod
    def receive(self, *args, **kwargs):
        """
        An allocation of trades to the shipping company .
        :param args: Positional args for additional arguments in subclasses.
        :param kwargs: Keyword args for additional arguments in subclasses.
        """
        pass


@dataclass
class ScheduleProposal:
    """
    A proposed schedule including a number of trades.

    :param schedules: The proposed schedules indexed by the vessels.
    :type schedules: Dict[Vessel, Schedule]
    :param scheduled_trades: A list of trades that are scheduled within the vessel's schedules.
    :type scheduled_trades: List[Trade]
    """

    schedules: Dict[Vessel, Schedule]
    scheduled_trades: List[Trade]
    costs: Dict[Trade, float]


class SimpleCompany(ShippingCompany[V]):
    """
    A simple company.
    """

    def __init__(self, fleet, name):
        """
        :param fleet: List of vessels.
        :type fleet: List[V]
        :param name: the name of the company
        :type name: str
        """
        super().__init__(fleet, name)
        self._assignments = {}
        self._current_scheduling_proposal = None

    def pre_inform(self, trades, time):
        """
        Inform the shipping company of trades that are available at a future time. No response expected.

        :param trades: The trades coming in the future.
        :type trades: List[Trade]
        :param time: The time when the trades will be allocated.
        :type time: int
        """
        pass

    def inform(self, trades, *args, **kwargs):
        """
        The shipping company tries to schedule the cargoes into the schedules of the fleet. Any trades that fit into
        the vessels' schedules are returned as trades the company can/wants to transport.

        :param trades: The list of trades.
        :type trades: List[Trade]
        :param args: Not used.
        :param kwargs: Not used.
        :return: A response to the information about cargoes, e.g. a list of cargoes the company is interested in.
        """
        proposed_scheduling = self.propose_schedules(trades)
        scheduled_trades = proposed_scheduling.scheduled_trades
        self._current_scheduling_proposal = proposed_scheduling
        return scheduled_trades

    def receive(self, trades, *args, **kwargs):
        """
        Allocate a list of trades to the company. If the trades are all trades that where requested by
        :py:func:`SimpleCompany.inform` the previously generated schedules will be used. Otherwise, new schedules
        will be created.

        :param List[Trade] trades: The list of trades.
        :param args: Not used.
        :param kwargs: Not used.
        """
        if (not (len(trades) == len(self._current_scheduling_proposal.scheduled_trades)
                 and all(one_trade in self._current_scheduling_proposal.scheduled_trades for one_trade in trades))):
            self._current_scheduling_proposal = self.propose_schedules(trades)
        self.apply_schedules(self._current_scheduling_proposal.schedules)
        self._current_scheduling_proposal = None

    def apply_schedules(self, schedules):
        """
        Applies the schedules to the vessels.

        If any schedule is invalid it will not be applied.

        :param schedules: The schedules to apply indexed by the vessels.
        :type schedules: Dict[Vessel, Schedule]
        """
        self._engine.add_new_schedules(self, schedules)

    def propose_schedules(self, trades):
        """
        Tries to generate new schedules based on the vessels' current schedules and the specified trades.
        Trades are attempted to schedule by simply finding the first vessel that can transport the cargo after
        finishing the current schedule.

        :param trades: The trades.
        :type trades: List[Trade]
        :return: The schedule proposals.
        :rtype: ScheduleProposal
        """
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

    def get_arrival_time(self, port, schedule, vessel):
        """
        Calculates the arrival time of the vessel at the port. If the specified schedule has events it is assumed
        that the vessel is in the location of the last event. Otherwise, the vessels current position is used.

        :param port: The port
        :param Schedule | None schedule: The schedule or None
        :param Vessel vessel: The vessel.
        :return: The arrival time
        :rtype: float
        """
        port = self._engine.world.network.get_port_or_default(port, port)
        if schedule is not None and len(schedule) > 0:
            location_before = schedule[-1].location
            if isinstance(location_before, OnJourney):
                location_before = location_before.destination
            finish_time_at_before = schedule.completion_time()
        else:
            location_before = vessel.location
            finish_time_at_before = self._engine.world.current_time
            if isinstance(location_before, OnJourney):
                location_before = self._engine.network.get_journey_location(
                    location_before, vessel, finish_time_at_before)
        travel_distance = self._engine.world.network.get_distance(location_before, port)
        travel_time = vessel.get_travel_time(travel_distance)
        arrival_time = finish_time_at_before + travel_time
        return arrival_time


@attrs.define(kw_only=True)
class Bid:
    """
    A bid for cargo transportation.
    :param amount:
        The amount for which the bidding company is willing to transport the cargo
    :type amount: float
    :param trade:
        The trade the company is diffing for.
    :type trade: Trade
    """
    amount: float
    trade: Trade
    company: ShippingCompany = None
