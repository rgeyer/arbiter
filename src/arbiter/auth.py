# Copyright © 2020 R.A. Stern
# SPDX-License-Identifier: LGPL-3.0-or-later

def basic(obj):
    import base64

    return base64.b64encode(f"{obj['username']}:{obj['password']}".encode())


def auth_string(obj):
    return obj['credential']
