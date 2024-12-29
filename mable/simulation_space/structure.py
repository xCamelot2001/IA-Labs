"""
The space where the simulation and operation takes place including the seas and the ports.
"""
from abc import abstractmethod, ABC
import logging
import math
from typing import Union, List, Dict

import numpy as np

from mable.simulation_environment import SimulationEngineAware
from mable.simulation_space.universe import Location, Port, OnJourney


logger = logging.getLogger(__name__)


class ShippingNetwork(SimulationEngineAware):
    """
    An abstract class for the space of operation.
    """

    def __init__(self):
        super().__init__()

    @staticmethod
    @abstractmethod
    def get_distance(location_one, location_two):
        """
        Returns the distance between two locations.
        :param location_one: Location
            The first location.
        :param location_two: Location
            The second location.
        :return: float
            The distance.
        """
        pass

    @abstractmethod
    def get_port(self, name):
        """
        Returns a port by name.
        :param name: str
            The name of the port.
        :return: Port
            The port by the name.
        """
        pass

    @abstractmethod
    def get_port_or_default(self, name, default=None):
        """
        Returns a port by name or the default value in case no port with the specified name exists.

        :param name: The name of the port.
        :type name: str
        :param default: The default value to return. By default, this is None.
        :type default: Any
        :return: Either the port or whatever is passed to default (None by default).
        :rtype: Union[Port, None]
        """
        pass

    @abstractmethod
    def get_journey_location(self, journey, vessel, current_time):
        """
        Returns the current position of the vessel based on the journey information and the current time.
        :param journey: Journey
            The journey object.
        :param vessel: Vessel
            The vessel that is performing the journey
        :param current_time: float
            The current time.
        :return: Location
            The current location the vessel is in.
        """
        pass

    def get_vessel_location(self, vessel, current_time):
        """
        Returns the location of the vessel assuming the vessel is either in a port or on a journey.
        If the vessel is on a journey the current time is used to determine the vessel's location on the
        journey.

        The method is robust to the vessel having a location by name or Location, i.e. if the vessel's location
        is a port name the port will be determined by the name.
        :param vessel: Vessel
            The vessel.
        :param current_time: float
            The current time.
        :return: Location
            The current location of the vessel.
        """
        if isinstance(vessel.location, OnJourney):
            location = self.get_journey_location(vessel.location, vessel, current_time)
        else:
            location = self.get_port_or_default(vessel.location, vessel.location)
        return location


class NetworkWithPortDict(ShippingNetwork, ABC):
    """
    A space of operation that stores the ports in form of a dictionary.
    """

    def __init__(self, ports=None):
        super().__init__()
        ports = self._create_port_dict(ports)
        self._ports = {}
        if ports is not None:
            self._ports = ports

    @staticmethod
    def _create_port_dict(ports):
        """
        Makes sure that the collection of ports is a dictionary. If the ports are in form of a list
        a dict indexed by the port names is created.

        :param ports: The collection of ports.
        :type ports: Union[Dict[str, Port], List[Port]]
        :return: A dict of ports indexed by the names or the passed in dict.
        :rtype: Dict[str, Port]
        """
        post_dict = ports
        if isinstance(ports, list):
            post_dict = {}
            for one_port in ports:
                post_dict[one_port.name] = one_port
        return post_dict

    @property
    def ports(self):
        return list(self._ports.values())

    def get_port(self, name):
        """
        Returns the port with the name.

        :param name: The name of a port.
        :return: The port instance.
        :rtype: Port
        """
        port = self._ports[name]
        return port

    def get_port_or_default(self, name, default=None):
        """
        Returns a port by name or the default value in case no port with the specified name exists.
        :param name: str
            The name of the port.
        :param default: Any
            The default value to return. By default, this is None.
        :return: default
            Whatever is passed to default or None if nothing is specified.
        """
        try:
            return_value = self._ports[name]
        except KeyError:
            return_value = default
        return return_value


class UnitShippingNetwork(NetworkWithPortDict):
    """
    A space of operation in the [0,1]^2 Euclidian space.
    """

    def __init__(self, ports=None):
        """
        Constructor.
        :param ports: dict | list
            The collection of ports.
        """
        super().__init__(ports)

    def get_distance(self, location_one, location_two):
        """
        Returns the Euclidean distance between two locations.
        :param location_one: Location
            The first location.
        :param location_two: Location
            The second location.
        :return: float
            The Euclidean distance. If the location are outside of [0,1]^2 float('inf') is returned.
        """
        if not isinstance(location_one, Location):
            location_one = self.get_port(location_one)
        if not isinstance(location_two, Location):
            location_two = self.get_port(location_two)
        distance = math.inf
        if all(0 <= coord <= 1 for coord in [location_one.x, location_one.y, location_two.x, location_two.y]):
            x_diff_square = (location_one.x - location_two.x)**2
            y_diff_square = (location_one.y - location_two.y)**2
            distance = np.sqrt(x_diff_square + y_diff_square)
        return distance

    def get_journey_location(self, journey, vessel, current_time):
        """
        Returns the current position of the vessel based on the journey information and the current time.
        If the current time is before the start time the origin is returned. Similarly, if the current time is beyond
        the start time plus the travel time the destination is returned.
        :param journey: Journey
            The journey object.
        :param vessel: Vessel
            The vessel that is performing the journey
        :param current_time: float
            The current time.
        :return: Location
            The current location the vessel is in or one of the endpoints.
        """
        distance = self.get_distance(journey.origin, journey.destination)
        travel_time = vessel.get_travel_time(distance)
        end_time = journey.start_time + travel_time
        if journey.start_time < current_time:
            location = journey.origin
        elif end_time >= current_time:
            location = journey.destination
        else:
            percentage = current_time - journey.start_time/travel_time
            location_x = journey.origin.x + (journey.origin.x - journey.destination.x) * percentage
            location_y = journey.origin.y + (journey.origin.y - journey.destination.y) * percentage
            location = Location(location_x, location_y)
        return location
