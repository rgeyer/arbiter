# Copyright © 2020 R.A. Stern
# SPDX-License-Identifier: LGPL-3.0-or-later

def basic(obj):
    """
    Basic username & password authentication scheme.

    Returns:
        A :py:class:`dict` of credentials including an 'auth' key
        continaing the base64 'basic auth' representation of the data.

    Warning:
        Although username and plaintext password authentication is supported, it
        should not be used outside of a test environment.
    """
    import base64

    return {
        'username': obj['username'],
        'password': obj['password'],
        'auth': base64.b64encode(f"{obj['username']}:{obj['password']}".encode())
    }


def auth_string(obj):
    """
    Base64 'Basic Auth' style credential hash.

    Returns:
        A :py:class:`dict` of credentials including an 'auth' key
        continaing the base64 'basic auth' representation of the data.
    """
    import base64

    u, p = base64.b64decode(obj['credential']).decode().split(':')

    return {
        'username': u,
        'password': p,
        'auth': obj['credential']
    }


def os_env(obj):
    """
    OS environemnt variable scheme.

    Returns:
        A :py:class:`dict` with all values replaced by their respective
        environment variables.
    """
    import os

    return {x: os.environ.get(obj[x]) for x in obj if x != 'type'}
