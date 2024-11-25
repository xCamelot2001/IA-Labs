"""
Util module including:
- Json encoding
"""

from enum import Enum
import json

from mable.simulation_de_serialisation import DataClass, SimulationSpecification


class JsonAble:
    """
    Ensures that a class is transformable into a json. On default that means an objects __dict__ is json dumped.
    """

    def __init__(self):
        super().__init__()

    def to_json(self):
        """

        :return: Any
            A json encodable object.
        """
        return json.dumps(self.__dict__)


class JsonAbleEncoder(json.JSONEncoder):
    """
    An encoder for settings with :py:class:`JsonAble` classes.
    """

    def default(self, obj):
        """
        If the object is of type :py:class:`JsonAble` the :py:func:`jsonAble.to_json` function is called.
        :param obj: Any
            An object that is either json encodable by default or that is :py:class:`JsonAble`.
        :return:
            The result of :py:func:`jsonAble.to_json` or :py:func:`json.JSONEncoder.default`
        """
        if issubclass(type(obj), JsonAble):
            result = obj.to_json()
        elif issubclass(type(obj), Enum):
            result = obj.value
        elif issubclass(type(obj), DataClass):
            SimulationSpecification.register(obj.current_class.__name__, obj.current_class)
            schema = obj.Schema()
            result = schema.dump(obj)
        else:
            result = json.JSONEncoder.default(self, obj)
        return result
