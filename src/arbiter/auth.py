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
    OS environment variable scheme.

    Returns:
        A :py:class:`dict` with all values replaced by their respective
        environment variables.
    """
    import os

    return {x: os.environ.get(obj[x]) for x in obj if x != 'type'}

def aws(obj):
    """
    AWS Boto3 Session scheme.

    Returns:
        A :py:class:`dict` of credentials including an 'auth' key
        containing a :py:class:`boto3.session.Session` instance which
        has been authenticated
    """
    import boto3

    retdict = {x: obj[x] for x in obj if x != 'type'}
    session = boto3.Session(
        profile_name=obj['profile'] if 'profile' in obj else None,
        aws_access_key_id=obj['aws_access_key_id'] if 'aws_access_key_id' in obj else None,
        aws_secret_access_key=obj['aws_secret_access_key'] if 'aws_secret_access_key' in obj else None,
        aws_session_token=obj['aws_session_token'] if 'aws_session_token' in obj else None
    )
    if 'role_arn' in obj:
        sts = session.client('sts')

        assumed_role = sts.assume_role(
            RoleArn=obj['role_arn'],
            RoleSessionName='Arbiter'  # Allow the user to name this?
        )

        session = boto3.Session(
            aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
            aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
            aws_session_token=assumed_role['Credentials']['SessionToken']
        )
    retdict['auth'] = session
    return retdict
