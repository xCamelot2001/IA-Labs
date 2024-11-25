"""
Event management module.
"""

from abc import abstractmethod
from dataclasses import dataclass, field
import math
from queue import PriorityQueue
from typing import Any, TYPE_CHECKING

from mable.simulation_environment import SimulationEngineAware
from mable.simulation_space import OnJourney

if TYPE_CHECKING:
    from mable.engine import SimulationEngine
    from mable.transport_operation import Vessel
    from mable.simulation_space import Location


class Event:
    """
    One event.
    """

    def __init__(self, time, info=None):
        """
        :param time: The occurrence time of the event.
        :type time: float
        :param info: Some info on the event for logging etc.
        :type info: str
        """
        super().__init__()
        self._time = time
        self.info = info

    @property
    def time(self):
        """
        The time of the occurrence event.

        :return: The time.
        :rtype: float
        """
        return self._time

    def added_to_queue(self, engine):
        """
        Called when the event is added to the queue. Does nothing on default.
        :param engine: Engine
            The simulation engine.
        """
        pass

    def event_action(self, engine):
        """
        Called when the event is happening. This should be at :py:func:`Event.time`. Does nothing on default.
        :param engine: Engine
            The simulation engine.
        """
        pass

    @staticmethod
    def format_time(time):
        """
        Formats a decimal time assumed to be hours in to a string of roughly days and hours.
        After days are determined the remaining hours are round to one decimal place.

        :param time:
            Time in hours.
        :type time: float
        :return: str
            '~<days> day(s) <hours> hour(s)'
        """
        if time >= 0:
            full_days = math.floor(time / 24)
            hours = round(time - 24 * full_days, 1)
            str_time = f"~{full_days} day(s) {hours} hour(s)"
        else:
            str_time = "-"
        return str_time

    def __repr__(self):
        str_repr = (f"Event({type(self).__name__}): time {round(self.time, 3)}[{self.format_time(self.time)}],"
                    f" info: {self.info}.")
        return str_repr

    def __eq__(self, other):
        """
        Two Events are assumed to be equal if their time and info are the same.
        :param other: Event
            Another event.
        :return: bool
            False if any of the event specifying information is different, True otherwise.
        """
        are_same = False
        if (isinstance(other, Event)
                and self.time == other.time
                and self.info == other.info):
            are_same = True
        return are_same


class CargoAnnouncementEvent(Event):
    """
    Announces future cargoes
    """

    def __init__(self, time, cargo_available_time):
        super().__init__(time)
        self._cargo_available_time = cargo_available_time

    def event_action(self, engine):
        """
        Announces the cargoes becoming available at a later time.

        :param engine: SimulationEngine
            The simulation engine.
        :type engine: SimulationEngine
        """
        all_trades = engine.shipping.get_trades(self._cargo_available_time)
        engine.market.inform_future_trades(all_trades, self._cargo_available_time, engine.shipping_companies)
        self.info = f"#Trades: {len(all_trades)}. For time {self.format_time(self._cargo_available_time)}"
        engine.world.event_queue.put(engine.class_factory.generate_event_cargo(self._cargo_available_time))


class CargoEvent(Event):
    """
    An event of appearance of cargoes.
    """

    def __init__(self, time):
        super().__init__(time)

    def event_action(self, engine):
        """
        Collects the cargoes becoming available at the event's time from the shipping object and passes
        them to the market for distribution.

        :param engine: Engine
            The simulation engine.
        """
        all_trades = engine.shipping.get_trades(self.time)
        self.info = f"#Trades: {len(all_trades)}"
        engine.headquarters.get_companies()
        distribution_info = engine.market.distribute_trades(self.time, all_trades, engine.shipping_companies)
        return distribution_info


class DurationEvent(Event):
    """
    An event that has a duration.
    """

    def __init__(self, time):
        """
        Constructor.
        An unstarted event has a start time of -1.
        :param time: float
            The time at which the event happens/ends.
        """
        super().__init__(time)
        self._time_started = -1

    @property
    def time_started(self):
        return self._time_started

    def added_to_queue(self, engine):
        """
        Set start time to current time.

        :param engine: The simulation engine.
        :type engine: SimulationEngine
        """
        if self.time < engine.world.current_time:
            self._time_started = self.time
        else:
            self._time_started = engine.world.current_time

    def has_started(self):
        """
        Indicates if the event has started.

        :return: True if the started time is set and False otherwise.
        :rtype: bool
        """
        return self._time_started >= 0

    def performed_time(self):
        """
        The duration the event took. Is zero as long as the event hasn't started.
        :return: The duration.
        :rtype: float
        """
        time_in_event = 0
        if self.has_started():
            time_in_event = self. time - self._time_started
        return time_in_event

    def __repr__(self):
        str_repr = (f"Event({type(self).__name__}): time {round(self.time, 3)} [{self.format_time(self.time)}],"
                    f" duration: {round(self.performed_time(), 3)} [{self.format_time(self.performed_time())}],"
                    f" info: {self.info}.")
        return str_repr


class VesselEvent(DurationEvent):
    """
    An event that involves a vessel.
    """

    def __init__(self, time, vessel):
        """
        Constructor.
        :param time: The occurrence time of the event.
        :type time: float
        :param vessel: The vessel associated with the event.
        :type vessel: Vessel
        """
        super().__init__(time)
        self._vessel = vessel

    @property
    def vessel(self):
        return self._vessel

    @property
    @abstractmethod
    def location(self):
        """
        The location of the entirety of the event or where the vessel is when the event happens.
        Does not have to ensure that the vessel's current location is returned.
        :return: Location
            The location at event occurrence.
        """
        pass

    @abstractmethod
    def distance(self, engine):
        """
        The distance the vessel crosses between the start and the occurrence of the event.
        :param engine: Engine
            Simulation engine
        :return: float
            The distance.
        """
        pass

    def event_action(self, engine):
        """
        Informs the vessel about the occurrence of the event and updates its location to the location of the
        occurrence, i.e. :py:func:`VesselEvent.location`

        :param engine: The simulation engine.
        :type engine: SimulationEngine
        """
        self._vessel.event_occurrence(self)
        self._vessel.location = self.location

    def __eq__(self, other):
        """
        Two VesselEvents are assumed to be equal if their time, info and vessel are the same.

        :param other: Another event.
        :type other: Event
        :return: False if any of the event specifying information is different, True otherwise.
        :rtype: bool
        """
        are_same = False
        if (isinstance(other, VesselEvent)
                and super().__eq__(other)
                and self._vessel == other.vessel):
            are_same = True
        return are_same


class VesselLocationInformationEvent(VesselEvent):
    """
    An event that informs about the location of a vessel.
    """

    def __init__(self, time, vessel, location):
        """
        Constructor.
        :param time: float
            The time of the event.
        :param vessel: Vessel
            The vessel associated with the event.
        :param location:
            The location of the vessel.
        """
        super().__init__(time, vessel)
        self._location = location
        self.info = f"{self._vessel.name} in {self._location.name}"

    @property
    def location(self):
        """
        The location of the vessel at the specified time.

        :return: Location
            The location at event occurrence.
        """
        return self._location

    def distance(self, engine):
        """
        Always zero since no distance is crossed.
        :param engine: Engine
            Simulation engine
        :return: float
            The distance.
        """
        return 0


class TravelEvent(VesselEvent):

    def __init__(self, time, vessel, origin, destination):
        """
        Constructor for a vessel that performs a journey.
        :param time: float
            The time of the event.
        :param vessel: Vessel
            The vessel associated with the event.
        :param origin: Location
            The location of the vessel when the event starts.
        :param destination: Location
            The location of the vessel when the event occurs.
        """
        super().__init__(time, vessel)
        self._origin = origin
        self._destination = destination
        self._is_laden = False
        self.info = (f"{destination} travel (Vessel [name: {vessel.name}]: "
                     f"{origin}->{destination})")

    @property
    def location(self):
        """
        The destination of the journey.
        :return: Location
            The destination
        """
        return OnJourney(origin=self._origin, destination=self._destination, start_time=self._time_started)

    @property
    def is_laden(self):
        """
        Indicates if the vessel is laden on the voyage.

        Only determined once the event has stated. False beforehand.
        :return: True if laden and False if under ballast.
        """
        return self._is_laden

    def distance(self, engine):
        """
        The distance between origin and destination.
        :param engine: Engine
            Simulation engine.
        :return: float
            The distance.
        """
        return engine.world.network.get_distance(self._origin, self._destination)

    def added_to_queue(self, engine):
        """
        Beside setting the start time the vessel's location is set to be on journey.
        :param engine: Engine
            The simulation engine.
        """
        super().added_to_queue(engine)
        self._vessel.location = OnJourney(self._origin, self._destination, self._time_started)

    def event_action(self, engine):
        """
        Informs the vessel about the occurrence of the event and updates its location to the location of the
        occurrence, i.e. :py:func:`VesselEvent.location`
        :param engine: Engine
            The simulation engine.
        """
        super().event_action(engine)
        self._is_laden = self._vessel.has_any_load()
        self._vessel.location = self.location.destination


class IdleEvent(VesselEvent):
    """
    An event where the vessel is doing nothing.
    """

    def __init__(self, time, vessel, location):
        """
        Constructor.
        :param time: The occurrence time of the event.
        :type time: float
        :param vessel: The vessel associated with the event.
        :type vessel: Vessel
        :param location: The location where the vessel idles.
        :type location: Location
        """
        super().__init__(time, vessel)
        self._location = location
        self.info = f"{location} idling (Vessel [name: {vessel.name}])"

    @property
    def location(self):
        return self._location

    def distance(self, engine):
        """
        Idling passes no distance.
        :param engine: Engine
            Simulation engine.
        :return: float
            0 (Zero)
        """
        return 0

    def __eq__(self, other):
        """
        Two IdleEvents are assumed to be equal if they are equal VesselEvents in the same location.
        :param other: Event
            Another event.
        :return: bool
            False if any of the event specifying information is different, True otherwise.
        """
        are_same = False
        if (isinstance(other, IdleEvent)
                and super().__eq__(other)
                and self._location == other.location):
            are_same = True
        return are_same


class VesselCargoEvent(VesselEvent):
    """
    An event that involves a vessel and a trade.
    """

    def __init__(self, time, vessel, trade, is_pickup):
        """
        Constructor.
        :param time: time: float
            The time of the event.
        :param vessel: Vessel
            The vessel associated with the event.
        :param trade: Trade
            The trade associated with the event.
        :param is_pickup: bool
            Indicate if the event is about the pickup of the cargo at the trade's origin port of the drop-off at the
            trade's destination port.
        """
        super().__init__(time, vessel)
        self._trade = trade
        self._is_pickup = is_pickup
        if is_pickup:
            self.info = (f"{trade.origin_port} pick up (Vessel [name: {vessel.name}], Trade [{trade.cargo_type}, "
                         f"{trade.amount}]: {trade.origin_port}->{trade.destination_port})")
        else:
            self.info = (f"{trade.destination_port} drop off (Vessel [name: {vessel.name}],"
                         f" Trade [{trade.cargo_type}, {trade.amount}]: "
                         f"{trade.origin_port}->{trade.destination_port})")

    @property
    def is_pickup(self):
        """
        Indicate if the event is about the pickup of the cargo at the trade's origin port of the drop-off at the
            trade's destination port.
        :return: bool
            True if event is pickup, False otherwise.
        """
        return self._is_pickup

    @property
    def is_drop_off(self):
        """
        Indicate if the event is about the pickup of the cargo at the trade's origin port of the drop-off at the
            trade's destination port.
        :return: bool
            True if event is drop-off, False otherwise.
        """
        return not self._is_pickup

    @property
    def trade(self):
        """
        :return: Trade
            The trade associated with the event.
        """
        return self._trade

    @property
    def location(self):
        """
        The origin port if it is a pickup and the destination port otherwise.
        :return: Port
            Origin or destination port.
        """
        if self.is_pickup:
            loc = self.trade.origin_port
        else:
            loc = self.trade.destination_port
        return loc

    @abstractmethod
    def distance(self, engine):
        """
        The distance the vessel crosses between the start and the occurrence of the event.
        :param engine: Engine
            Simulation engine
        :return: float
            The distance.
        """
        pass

    def __eq__(self, other):
        """
        Two VesselCargoEvents are assumed to be equal if their trade, time and if it is a pickup or not are the same.
        :param other: Event
            Another event.
        :return: bool
            False if any of the event specifying information is different, True otherwise.
        """
        are_same = False
        if (isinstance(other, VesselCargoEvent)
                and self.time == other.time
                and self._is_pickup == other.is_pickup
                and self._trade == other.trade):
            are_same = True
        return are_same


class ArrivalEvent(VesselCargoEvent):
    """
    An event where a vessel arrives for loading or unloading.
    """

    def distance(self, engine):
        """
        The distance between origin and destination ports.
        :param engine: Engine
            Simulation engine.
        :return: float
            The distance.
        """
        return engine.world.network.get_distance(self.trade.origin_port, self.trade.destination_port)

    def __eq__(self, other):
        """
        :param other: Event
        :return: bool.
            True if ArrivalEvent and equal based on :py:func:`VesselCargoEvent.__eq__`.
        """
        return super().__eq__(other) and isinstance(other, ArrivalEvent)


class CargoTransferEvent(VesselCargoEvent):
    """
    A loading or unloading event.
    """

    def event_action(self, engine):
        super().event_action(engine)
        if self.is_pickup:
            self._vessel.load_cargo(self.trade.cargo_type, self.trade.amount)
        else:
            self._vessel.unload_cargo(self.trade.cargo_type, self.trade.amount)

    def distance(self, engine):
        return 0

    def __eq__(self, other):
        """
        :param other: Event
        :return: bool.
            True if CargoTransferEvent and equal based on :py:func:`VesselCargoEvent.__eq__`.
        """
        return super().__eq__(other) and isinstance(other, CargoTransferEvent)


@dataclass(order=True)
class EventItem:
    """
    Event wrapper for EventQueue.
    """
    time: float
    event: Event = field(compare=False)


class EventQueue(SimulationEngineAware, PriorityQueue):
    """
    Priority Queue for events.
    """

    def __init__(self):
        super().__init__()

    def put(self, event: Event, block=True, timeout=None):
        """
        Adds an event to the queue.
        :param event: Event
            The event.
        :param block:
            See :py:func:`PriorityQueue.put`
        :param timeout:
            See :py:func:`PriorityQueue.put`
        :raises ValueError: if the event's time is infinite.
        """
        if event.time == math.inf:
            raise ValueError("event with infinite deadline")
        event.added_to_queue(self._engine)
        event_item = EventItem(event.time, event)
        super().put(event_item, block, timeout)

    def get(self, block=True, timeout=None):
        """
        Removes and returns the next event from the queue.
        :param block:
            See :py:func:`PriorityQueue.get`
        :param timeout:
            See :py:func:`PriorityQueue.get`
        :return: Event
            The event.
        """
        event_item = super().get(block, timeout)
        event = event_item.event
        return event

    def remove(self, event_s):
        """
        Removes one or more events from the queue.
        :param event_s: Event | [Event]
            The event or a list of events.
        """
        if not isinstance(event_s, list):
            event_s = [event_s]
        for one_event in event_s:
            self.queue.remove(EventItem(one_event.time, one_event))

    def __contains__(self, event):
        """
        Returns if an event that is equal to the passed event is in the queue.
        :param event: Event
            The passed event.
        :return: bool
            True if such an event is in the queue and False otherwise.
        """
        i = 0
        found_event = False
        while i < len(self.queue) and not found_event:
            event_item = self.queue[i]
            if event == event_item:
                found_event = True
            i += 1
        return found_event

    def __getitem__(self, event):
        """
        Returns an event instance from the queue that is similar to the passed event.
        :param event: Event
            The passed event.
        :return: bool
            The event instance from the queue.
        :raises ValueError:
            If no such event is in the queue.
        """
        if event in self.queue:
            return_event = self.queue[event]
        else:
            raise ValueError(event)
        return return_event

    def __iter__(self):
        """
        :return:
            An iterator over the current events.
        """
        return iter(self.queue)


class EventObserver:
    """
    An observer of event occurrences.
    """

    @abstractmethod
    def notify(self, engine, event, data):
        """
        Notify this observer of an event.
        :param engine: Engine
            Simulation engine.
        :param event: Event
            Some event.
        :param data: EventExecutionData
            Additional data in conjunction with the event. E.g. data that was produced or changes that were made.
        """
        pass


@dataclass
class EventExecutionData:
    """
    Data that is associated with an event occurrence.
    :param action_data: Data that is directly associated with the occurrence of the event.
    :type action_data: Any
    :param other_data: Additional data that is related to the event, the event's occurrence or system at
        the time of the event's occurrence.
    :type other_data: Any
    """
    action_data: Any = None
    other_data: Any = None
