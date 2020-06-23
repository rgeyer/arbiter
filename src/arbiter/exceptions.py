# Copyright © 2020 R.A. Stern
# SPDX-License-Identifier: LGPL-3.0-or-later

class RegistrationError(Exception):
    """Raised upon :py:class:`~arbiter.registry.register()` failure."""
    pass


class UnknownHandlerError(Exception):
    """Raised when a called handler name is not registerd"""
    pass
