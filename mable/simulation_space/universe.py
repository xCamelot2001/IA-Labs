import attrs

from mable.util import JsonAble


class Location:
    """
    A location in the operational space.
    """

    def __init__(self, x, y, name=None):
        """
        :param x: The x coordinate of the location.
        :type x: float
        :param y: The y coordinate of the location.
        :type y: float
        :param name: An optional name of the location.
        :type name: str
        """
        super().__init__()
        self._x = x
        self._y = y
        self._name = name

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y

    @property
    def name(self):
        return self._name

    def __repr__(self):
        str_repr = f"Location<({self._x}, {self._y})>"
        return str_repr

    def __eq__(self, other):
        are_equal = False
        if isinstance(other, Location):
            if (
                    self.name == other.name
                    and self.x == other.x
                    and self.y == other.y):
                are_equal = True
        return are_equal

    def __hash__(self):
        return hash((self.name, self._x, self._y))


class Port(Location, JsonAble):
    """
    A port, i.e. a location in the operational space at which cargo gets exchanged.
    """

    def __init__(self, name, x, y):
        """
        :param name: The name of the port.
        :type name: str
        :param x: The x coordinate of the port.
        :type x: float
        :param y: The y coordinate of the port.
        :type y: float
        """
        super().__init__(x, y, name)

    def __repr__(self):
        str_repr = f"Port<{self.name} ({self.x}, {self.y})>"
        return str_repr

    def to_json(self):
        return self.__dict__


@attrs.define(repr=False)
class OnJourney:
    """
    An indicator that a vessel is in transit, i.e. performing a journey.

    :param origin: The start location of the journey.
    :type origin: Location
    :param destination: The end location of the journey.
    :type destination: Location
    :param start_time: The time at which the journey started, i.e. the time the vessel left origin.
    :type start_time: float
    """
    origin: Location
    destination: Location
    start_time: float

    def __repr__(self):
        str_repr = f"OnJourney<{self.origin} -> {self.destination} (start {self.start_time})>"
        return str_repr
