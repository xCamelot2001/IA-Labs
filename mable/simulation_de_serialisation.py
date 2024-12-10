from typing import Type, Dict, Protocol, TypeVar

from marshmallow import Schema, fields, pre_dump, post_load
import attrs


class DataSchema(Schema):

    current_class = fields.Str()

    @pre_dump
    def _pre_dump(self, data, **_):
        if type(data.current_class) is type:
            data.current_class = f"{data.current_class.__name__}"
        return data

    @post_load
    def _post_load(self, data, **_):
        class_name = data["current_class"]
        class_type = SimulationSpecification.get(class_name)
        del data["current_class"]
        obj = class_type(**data)
        return obj


class SchemaProtocol(Protocol):
    Schema: Type[DataSchema]


S = TypeVar('S', bound=SchemaProtocol)


class DataProtocol(Protocol):
    Data: Type[SchemaProtocol]


D = TypeVar('D', bound=DataProtocol)


@attrs.define
class DataClass:
    """
    Parent class for all data classes, i.e. classes that are going to be serialized and deserialised.
    """

    current_class: Type[DataProtocol]


class DynamicNestedField(fields.Field):
    """
    A field that allows to serialize and deserialize nested classes with an inner class 'Data'
    being a descendant of :class:`DataClass` which in turn has an inner class 'Schema' being a
    descendant of :class:`DataSchema`.
    """

    def _serialize(self, value, attr, obj, **kwargs):
        """
        Serialise a nested dataclass using its schema.
        Also registers the class for deserialisation.
        :param value: The object to be serialised.
        :param attr:
        :param obj:
        :param kwargs:
        :return: The serialised object.
        """
        schema = value.Schema()
        if type(value.current_class) is type:
            SimulationSpecification.register(value.current_class.__name__, value.current_class)
        dumped_value = schema.dump(value)
        return dumped_value

    def _deserialize(self, value, attr, data, **kwargs):
        """
        Deserialise a nested dataclass using its schema.
        Relies on the class name being registered.
        :param value:
        :param attr:
        :param data:
        :param kwargs:
        :return:
        """
        class_name = value["current_class"]
        class_type = SimulationSpecification.get(class_name)
        schema = class_type.Data.Schema()
        loaded_value = schema.load(value)
        return loaded_value


class SimulationSpecification:
    """
    A class to hold all specific classes that are part of the export and import to create runnable simulations.
    """
    _class_registry: Dict[str, Type[D]] = {}

    @classmethod
    def register(cls, name, component_cls: Type[D]):
        """
        Register a class under a specified name.
        :param name: The name.
        :type name: str
        :param component_cls: The component class.
        """
        cls._class_registry[name] = component_cls

    @classmethod
    def register_by_type_name(cls, component_cls: Type[D]):
        """
        Register a class under its name, i.e. :attr:`__name__`.
        :param component_cls: The component class.
        :return:
        """
        cls.register(component_cls.__name__, component_cls)

    @classmethod
    def get(cls, name) -> Type[D]:
        """
        Get a class by a specified name.
        :param name: The name.
        :type name: str
        :return: The component class.
        :raises KeyError: If no class is registered under the specified name.
        """
        if name not in cls._class_registry:
            raise ValueError(f"Component '{name}' not registered")
        return cls._class_registry[name]
