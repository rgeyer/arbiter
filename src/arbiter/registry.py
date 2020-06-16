# Copyright © 2020 R.A. Stern
# SPDX-License-Identifier: LGPL-3.0-or-later

from arbiter.exceptions import RegistrationError


class Registry:
    __slots__ = [
        '__registry',
        '__required'
    ]

    def __init__(self, required=None, registry=None):
        self.__required = required or []
        self.__registry = registry or {}
        pass

    def __len__(self):
        return len(self.__registry)

    def __getitem__(self, key):
        return self.__registry[key.upper()]

    def __contains__(self, item):
        return True if item.upper() in self.__registry else False

    def __repr__(self):
        return self.__registry.__repr__()

    def __str__(self):
        return self.__registry.__str__()

    def register(self, name, ref):
        if name.upper() in self.__registry:
            raise RegistrationError(f"Name '{name}' is already registered.")
        else:
            self.__registry[name.upper()] = ref

    def unregister(self, name):
        if name.upper() not in self.__required:
            del self.__registry[name.upper()]
        else:
            raise RegistrationError('Unable to remove required entry.')
