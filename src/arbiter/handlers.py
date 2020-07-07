# Copyright © 2020 R.A. Stern
# SPDX-License-Identifier: LGPL-3.0-or-later

import csv
import json
import os

from urllib.parse import urlparse
from umsg.mixins import LoggingMixin
import arbiter



class BaseHandler(LoggingMixin):
    """
    Base handler interface definition. All handlers inherit from this class.
    Each handler must implement input and output methods based on intended use,
    as no distinction is made between inputs and outputs; thus input and output
    handlers must implement the :py:meth:`get` and :py:meth:`set` methods
    respectively. The :py:meth:`atexit` method is called by the system
    for input and output handlers.

    Args:
        config (dict): Dictionary of handler configuration data
        **kwargs: Additional handler specific options. These will override any
            in the `config` options.

    Attributes:
        authentication (dict): Dictionary of authentication data.
        config (dict): Dictionary of handler specific configuration data.
        options (dict): Dictionary of handler specific keyword options to be
            passed to the handler subroutine.
        resource (str): Resource identifier.
    """
    __slots__ = [
        'authentication',
        'config',
        'options',
        'resource'
    ]

    def __init__(self, config, **kwargs):
        super().__init__()

        self.config = config
        self.options = config.get('options', {})
        self.authentication = config.get('authentication', None)
        self.resource = arbiter.parse_string(config.get('resource', None))

        if kwargs:
            for k in kwargs:
                self.options[k] = kwargs[k]


class FileHandler(BaseHandler):
    """
    Generic file handler template. Provides filepath resolution to all file
    handlers, and removes files at program termination.

    Attributes:
        filename (str): Resolved filename path.
    """

    __slots__ = [
        '_options_exclude',
        'filename'
    ]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)

        if self.resource.startswith('file:'):
            url = urlparse(self.resource)
            self.filename = url.path
        else:
            self.filename = self.resource

        self._options_exclude = ['keepfile']

    def _options(self):
        return {k: v for k, v in self.options.items() if k not in self._options_exclude}

    def get(self):
        """Data getter stub, to be implemented by inheriting sub-class."""
        pass

    def set(self):
        """Data setter stub, to be implemented by inheriting sub-class."""
        pass

    def atexit(self):
        """Will attempt to remove the file created at exit."""
        try:
            if not self.options.get('keepfile', False):
                os.remove(self.filename)
        except Exception as e:
            print(e)
            pass


class CsvFile(FileHandler):
    """
    Provides CSV serialization and deserialization utilizing the standard Python
    CSV library. By default :py:class:`CsvFile` utilizes :py:meth:`~csv.DictReader`
    and :py:meth:`~csv.DictWriter` objects.

    Notes:
        v1.1.0 - fields is deprecated, and will be removed in v2.0. Use fieldnames.

    Args:
        fieldnames (list): Input/output whitelist of fields to filter. All fields are kept
            if value is None. (Default: ``None``)
    """
    def __init__(self, config, **kwargs):
        # deprecated - remove in 2.0, for backwards compatibility
        if 'fields' in kwargs:
            kwargs['fieldnames'] = kwargs['fields']
            del kwargs['fields']

        super().__init__(config, **kwargs)

        self._options_exclude.append('fields')

    def get(self):
        """Uses :py:meth:`~csv.DictReader` to import file contents."""
        with open(self.filename, 'r') as fp:
            reader = csv.DictReader(fp, **self._options())

            if self.options['fieldnames']:
                data = []

                for row in reader:
                    for f in row.keys():
                        if f not in self.options['fieldnames']:
                            del row[f]
                    data.append(row)

                return data
            else:
                return [row for row in reader]

    def set(self, data):
        """Uses :py:meth:`~csv.DictWriter` to export file contents."""
        if 'fieldnames' not in self.options:
            self.options['fieldnames'] = data[0].keys()

        # extrasaction is explicitly disabled here
        self.options['extrasaction'] = 'ignore'

        with open(self.filename, 'w') as fp:
            writer = csv.DictWriter(fp, **self._options())
            writer.writeheader()

            for row in data:
                writer.writerow(row)


class JsonFile(FileHandler):
    """
    Provides JSON serialization and deserialization utilizing the standard Python
    JSON library. By default :py:class:`JsonFile` utilizes :py:func:`~json.load`
    and :py:func:`~csv.dump` functions.
    """
    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)

    def get(self):
        """Uses :py:func:`~json.load` to import file contents."""
        with open(self.filename, 'r') as fp:
            return json.load(fp, **self._options())

    def set(self, data):
        """Uses :py:func:`~json.dump` to export file contents."""
        with open(self.filename, 'w') as fp:
            json.dump(data, fp, **self._options())


class ConnectionHandler(BaseHandler):
    """
    Generic connection handler template.
    """

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)

    def connect(self):
        """Connection stub, to be implemented by inheriting sub-class."""
        pass

    def disconnect(self):
        """Disconnection stub, to be implemented by inheriting sub-class."""
        pass


class HttpHandler(ConnectionHandler):
    """
    Handler template for HTTP & HTTPS connections. Provides URL component
    resolution.

    Attributes:
        authority (str): URL authority component
        host (str): Host or IP of the resource
        path (str): Resource host path
        query (str): Query string
        secure (bool): Secure transport flag
        port (int): Connection port on host
    """

    __slots__ = [
        'authority',
        'host',
        'port',
        'path',
        'query',
        'secure'
    ]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)

        url = urlparse(self.resource)

        self.authority = url.netloc
        self.host = url.hostname
        self.path = url.path
        self.query = url.query
        self.secure = True if url.scheme == 'https' else False
        self.port = url.port if url.port else (443 if self.secure else 80)


class NotificationHandler(BaseHandler):
    """
    Generic notification handler template.

    Attributes:
        errors (list): List of error messages collected during processing.
        files (list): List of files which will be sent with the notification.
    """

    __slots__ = [
        'errors',
        'files'
    ]

    def __init__(self, config, **kwargs):
        if 'files' in kwargs:
            self.files = kwargs['files']
            del kwargs['files']
        else:
            self.files = []

        if 'errors' in kwargs:
            self.errors = kwargs['errors']
            del kwargs['errors']
        else:
            self.errors = []

        super().__init__(config, **kwargs)

    def send(self):
        """Notification action stub, to be implemented by inheriting sub-class."""
        pass


class EmailHandler(NotificationHandler):
    """
    Sends email message notifications using an STMP server.
    """
    __slots__ = [
        'default_body_error',
        '_emailheaders',
        '_smtpexclude'
    ]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)

        self.default_body_error = """
        Errors where encountered while processing data:

        {errors}
        """

        self._emailheaders = [
            'orig-date',
            'from',
            'sender',
            'reply-to',
            'to',
            'cc',
            'bcc',
            'subject',
            'comments',
            'keywords',
            'optional-field'
        ]

        self.__smtp_exclude = [
            'host',
            'ssl',
            'tls',
            'lmtp',
            'keyfile',
            'certfile',
            'username',
            'password',
            'authentication'
        ]

        if 'smtp' not in self.options:
            self.options['smtp'] = {
                'host': 'localhost',
                'ssl': False,
                'tls': False,
                'lmtp': False,
                'username': None,
                'password': None
            }

        if self.options['smtp'].get('authentication', None):
            import arbiter
            from arbiter import auth

            try:
                type = self.options['smtp']['authentication']['type']
                auth = arbiter.AUTH[type](self.options['smtp']['authentication'])
                u, p = base64.b64decode(auth).decode().split(':')
                self.options['smtp']['username'] = u
                self.options['smtp']['password'] = p
            except Exception:
                pass

    def __smtp_options(self):
        return {k: v for k, v in self.options['smtp'].items() if k not in self.__smtp_exclude}

    def send(self):
        from email.message import EmailMessage
        from email.utils import COMMASPACE
        import mimetypes
        import smtplib

        msg = EmailMessage()

        if self.errors:
            error_msg = '\n\n'.join(self.errors)

            if 'body_error' not in self.options['email']:
                body = self.default_body_error
            else:
                body = self.options['email']['body_error']

            msg.set_content(arbiter.parse_string(body, errors=error_msg))
        else:
            msg.set_content(arbiter.parse_string(self.options['email']['body']))

        # write headers
        for k in self.options['email']:
            if k in self._emailheaders:
                if isinstance(self.options['email'][k], list):
                    msg[k] = arbiter.parse_string(COMMASPACE.join(self.options['email'][k]))
                else:
                    msg[k] = arbiter.parse_string(self.options['email'][k])

        # attach files
        for file in self.files:
            ctype, encoding = mimetypes.guess_type(file)

            # unknown, treat as binary
            if ctype is None or encoding is not None:
                ctype = 'application/octet-stream'

            maintype, subtype = ctype.split('/', 1)

            with open(file, 'rb') as fp:
                msg.add_attachment(fp.read(),
                               maintype=maintype,
                               subtype=subtype,
                               filename=os.path.basename(file))

        if self.options['smtp']['ssl']:
            klass = smtplib.SMTP_SSL
        elif self.options['smtp']['lmtp']:
            klass = smtplib.LMTP
        else:
            klass = smtplib.SMTP

        with klass(host=self.options['smtp']['host'], **self.__smtp_options()) as smtp:
            if self.options['smtp']['tls']:
                tlsargs = {x: self.options['smtp'][x] for x in self.options['smtp'] if x in ['keyfile', 'certfile']}
                smtp.starttls(**tlsargs)

            if self.options['smtp']['username'] and self.options['smtp']['password']:
                smtp.login(self.options['smtp']['username'], self.options['smtp']['password'])

            smtp.send_message(msg)
