"""
Classes to create and process simulation instructions.
"""

import json

from mable.util import JsonAbleEncoder


COMPANIES_KEY = "companies"
MARKET_KEY = "market"
SHIPPER_KEY = "shipping"
NETWORK_KEY = "shipping_network"
PORTS_LIST_KEY = "ports"
RANDOM_KEY = "random"
ARGS_KEY = "args"
KWARGS_KEY = "kwargs"


class Specifications:
    """
    A set of instructions that specify the run of a simulation.
    """

    class Builder:
        """
        A builder to create specifications in parts.
        """

        def __init__(self):
            super().__init__()
            self._specifications = {}

        def add_company(self, *args, **kwargs):
            """
            Add instruction for a cargo transportation company.
            :param args:
                Positional args.
            :param kwargs:
                Keyword args.
            """
            if COMPANIES_KEY not in self._specifications:
                self._specifications[COMPANIES_KEY] = []
            company_dict = self._get_args_dict(*args, *kwargs)
            self._specifications[COMPANIES_KEY].append(company_dict)

        def add_cargo_generation(self, *args, **kwargs):
            """
            Add instruction for a cargo generation/shipping object.

            :param args:
                Positional args.
            :param kwargs:
                Keyword args.
            """
            self._add_args(SHIPPER_KEY, *args, **kwargs)

        def add_cargo_distribution(self, *args, **kwargs):
            """
            Add instruction for a cargo distribution/market object.
            :param args:
                Positional args.
            :param kwargs:
                Keyword args.
            """
            self._add_args(MARKET_KEY, *args, **kwargs)

        def add_shipping_network(self, *args, **kwargs):
            """
            Add instruction for a network/operational space object
            :param args:
                Positional args.
            :param kwargs:
                Keyword args.
            """
            self._add_args(NETWORK_KEY, *args, **kwargs)


        def add_random_specifications(self, *args, **kwargs):
            """
            Set the random specifications.

            :param args:
                Positional args.
            :param kwargs:
                Keyword args.
            """
            self._add_args(RANDOM_KEY, *args, **kwargs)

        def _add_args(self, key, *args, **kwargs):
            """
            Add instruction arguments under the specified key.
            :param key:
                The key
            :param args:
                Positional args.
            :param kwargs:
                Keyword args.
            """
            self._specifications[key] = self._get_args_dict(*args, **kwargs)

        @staticmethod
        def _get_args_dict(*args, **kwargs):
            """
            Generate a dict of the positional and keyword args.
            :param args:
                Positional args.
            :param kwargs:
                Keyword args.
            :return: dict
                {:py:const:`ARGS_KEY`: <args>, :py:const:`KWARGS_KEY`: <kwargs>}
            """
            args_dict = {ARGS_KEY: args, KWARGS_KEY: kwargs}
            return args_dict

        def build(self):
            return json.dumps(self._specifications, cls=JsonAbleEncoder, indent=4)

    def __init__(self, specifications):
        self._specifications = specifications

    @classmethod
    def init_from_json_string(cls, specs_string):
        """
        Load and initiated specifications from a json string.
        :param specs_string:
        :return:
        """
        specifications = json.loads(specs_string)
        return cls(specifications)

    def __getitem__(self, key):
        """
        Returns the item under the key. If the key is a tuple the keys will be accessed in order.
        If any key is -1 no key lookup is performed but simply the current part of the specification
        is returned as specifications.
        If the specifications under the key are a list, a list of specifications is returned. Otherwise, a tuple of
        args and kwargs are returned.
        :param key:
            The key
        :return: tuple | list
            As specified.
        """
        sub_specs = self._specifications
        if key != -1:
            if not isinstance(key, tuple):
                key = (key,)
            for sub_key in key:
                sub_specs = sub_specs[sub_key]
        if isinstance(sub_specs, list):
            return_args = [Specifications(s) for s in sub_specs]
        else:
            args = sub_specs[ARGS_KEY]
            kwargs = sub_specs[KWARGS_KEY]
            return_args = (args, kwargs)
        return return_args

    def get(self, key):
        """
        Return the args under the key.
        If the key is not present in the specifications a tuple of an empty list and an empty dict
        are returned, i.e. ([], {}).
        :param key:
            The key.
        :return:
            As specified.
        """
        try:
            return_args = self[key]
        except KeyError:
            return_args = ([], {})
        return return_args

    def __repr__(self):
        return self._specifications.__repr__()
