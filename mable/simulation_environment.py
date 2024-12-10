"""
Classes and functions for the environment in which the simulation takes place.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from event_management import EventQueue
    from mable.engine import SimulationEngine
    from mable.simulation_space.structure import ShippingNetwork


class SimulationEngineAware:
    """
    Helper class to provide a reference to and the setting of the simulation engine.
    """

    def __init__(self):
        super().__init__()
        self._engine = None

    def set_engine(self, engine):
        """
        **WARNING**: Part of internal simulation logic. Only allowed to be called by the simulation!

        Set the simulation engine.

        :param engine: The simulation engine.
        :type engine: SimulationEngine
        """
        self._engine = engine


class World(SimulationEngineAware):
    """
    The overall setting of the simulation including among other things the space/network and the event queue.
    Also keeps track of the current time.
    """

    def __init__(self, network, event_queue, random):
        """
        :param network: The space/network of operation.
        :type network: ShippingNetwork
        :param event_queue: The event queue.
        :type event_queue: EventQueue
        :param random: A random to use wherever randomness is needed.
        """
        super().__init__()
        self._event_queue = event_queue
        self._current_time = 0
        self._network = network
        self._random = random

    @property
    def network(self):
        """
        :return: The space/network of operation.
        :rtype: ShippingNetwork
        """
        return self._network

    @property
    def random(self):
        """
        :return: The random to use wherever randomness is needed.
        """
        return self._random

    @property
    def event_queue(self):
        """
        :return: The event queue.
        :rtype: EventQueue
        """
        return self._event_queue

    def do_events_exists(self):
        """
        Returns if there are events left to deal with.

        :return: True if there are still events and false otherwise.
        :rtype: bool
        """
        are_events_left = True
        if self._event_queue.empty():
            are_events_left = False
        return are_events_left

    def get_next_event(self):
        """
        Removes and return the next event of the queue. Also sets the current time to the time of the
        event occurrence.

        :return: The event.
        """
        next_event = self._event_queue.get()
        self._current_time = next_event.time
        return next_event

    @property
    def current_time(self):
        """
        :return: float
            The current time in the simulation.
        """
        return self._current_time

    def set_engine(self, engine):
        """
        Make the simulation engine know to the world and the event queue.
        :param engine: SimulationEngine
            The engine.
        """
        super().set_engine(engine)
        self._event_queue.set_engine(engine)
