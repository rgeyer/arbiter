# Copyright © 2020 R.A. Stern
# SPDX-License-Identifier: LGPL-3.0-or-later

import csv
import json
import os

from urllib.parse import urlparse
from umsg.mixins import LoggingMixin
import arbiter



class BaseHandler(LoggingMixin):
    """Base handler construct

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
        config (dict): Dictionary of handler specific configuration data.
        options (dict): Dictionary of handler specific keyword options to be
            passed to the handler subroutine.
    """
    __slots__ = [
        'config',
        'options'
    ]

    def __init__(self, config, **kwargs):
        super().__init__()

        self.config = config
        self.options = config.get('options', dict())

        if kwargs:
            for k in kwargs:
                self.options[k] = kwargs[k]

    def get(self):
        pass

    def set(self):
        pass

    def atexit(self):
        pass


class FileHandler(BaseHandler):
    """Base File Handler

    Generic file handler template. Provides filepath resolution to all file
    handlers, and removes files at program termination.

    Attributes:
        filename (str): Resolved filename path.
    """

    __slots__ = [
        'filename'
    ]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)

        resource = arbiter.parse_string(config['resource'])

        if resource.startswith('file:'):
            url = urlparse(resource)
            self.filename = url.path
        else:
            self.filename = resource

    def atexit(self):
        os.remove(self.filename)


class CsvFile(FileHandler):
    """CSV File Handler

    Provides CSV serialization and deserialization utilizing the standard Python
    CSV library. By default :py:class:`CsvFile` utilizes :py:meth:`~csv.DictReader`
    and :py:meth:`~csv.DictWriter` objects.

    Args:
        fields (list): Input whitelist of fields to filter. All fields are kept
            if value is None. (Default: ``None``)

    Attributes:
        fields (list): Input whitelist of fields to filter.
    """
    __slots__ = ['fields']

    def __init__(self, config, **kwargs):
        if 'fields' in kwargs:
            self.fields = kwargs['fields']
            del kwargs['fields']
        else:
            self.fields = None

        super().__init__(config, **kwargs)

    def get(self):
        with open(self.filename, 'r') as fp:
            reader = csv.DictReader(fp, **self.options)

            if self.fields:
                data = []

                for row in reader:
                    for f in row.keys():
                        if f not in self.fields:
                            del row[f]
                    data.append(row)

                return data
            else:
                return [row for row in reader]

    def set(self, data):
        if 'fieldnames' not in self.options:
            self.options['fieldnames'] = data[0].keys()

        self.options['extrasaction'] = 'ignore'

        with open(self.filename, 'w') as fp:
            writer = csv.DictWriter(fp, **self.options)
            writer.writeheader()

            for row in data:
                writer.writerow(row)


class JsonFile(FileHandler):
    """JSON File Handler

    Provides JSON serialization and deserialization utilizing the standard Python
    JSON library. By default :py:class:`JsonFile` utilizes :py:func:`~json.load`
    and :py:func:`~csv.dump` functions.
    """
    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)

    def get(self):
        with open(self.filename, 'r') as fp:
            return json.load(fp, **self.options)

    def set(self, data):
        with open(self.filename, 'w') as fp:
            json.dump(fp, data, **self.options)


class ConnectionHandler(BaseHandler):
    """Base Connection Handler

    Provides URL resolution to all connection handlers.


    """
    __slots__ = [
        'authentication',
        'hostname',
        'path',
        'query',
        'resource',
        'secure'
    ]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)

        self.resource = arbiter.parse_string(config['resource'])
        url = urlparse(self.resource)

        self.hostname = url.netloc
        self.path = url.path
        self.query = url.query
        self.secure = True if url.scheme == 'https' else False
        self.authentication = config.get('authentication', None)

    def connect(self):
        pass

    def disconnect(self):
        pass


class RESTHandler(ConnectionHandler):
    """REST Handler

    Generic REST handler template.
    """

    __slots__ = []

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)


class NotificationHandler(BaseHandler):
    """Notification Handler

    Generic notification handler template.

    Attributes:
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
            self.files = None

        if 'errors' in kwargs:
            self.errors = kwargs['errors']
            del kwargs['errors']
        else:
            self.errors = None

        super().__init__(config, **kwargs)

    def send(self):
        pass


class EmailHandler(NotificationHandler):
    """Email Message Notification Handler

    Sends email message notifications.

    Attributes:
        emailheaders (list): List of email headers a user may specify in the
            config.
        smtp (dict): Dictionary of SMTP options.
    """
    __slots__ = [
        'emailheaders',
        'smtp'
    ]

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)

        self.emailheaders = [
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

        self.smtp = dict()

        if 'smtp' not in self.options:
            self.options['smtp'] = dict()

        self.smtp = {
            'host': self.options['smtp'].get('host', 'localhost'),
            'ssl': self.options['smtp'].get('ssl', False),
            'tls': self.options['smtp'].get('tls', False),
            'lmtp': self.options['smtp'].get('lmtp', False),
            'user': self.options['smtp'].get('username', None),
            'pass': self.options['smtp'].get('password', None)
        }

        if self.options['smtp'].get('authentication', None):
            import base64

            u, p = (base64.b64decode(datamove.get_auth(self.authentication))).decode().split(':')
            self.smtp['user'] = u
            self.smtp['pass'] = p

        for k in self.smtp.keys():
            if k in self.options['smtp']:
                del self.options['smtp'][k]

    def send(self):
        from email.message import EmailMessage
        from email.utils import COMMASPACE
        import mimetypes
        import smtplib

        msg = EmailMessage()

        if self.errors:
            error_msg = '\n\n'.join(errors)

            if 'body_error' not in self.options['email']:
                body = arbiter.BODY_ERROR
            else:
                body = self.options['email']['body_error']

            msg.set_content(arbiter.parse_string(body, errors=error_msg))
        else:
            msg.set_content(arbiter.parse_string(self.options['email']['body']))

        # write headers
        for k in self.options['email']:
            if k in self.emailheaders:
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

        if self.smtp['ssl']:
            klass = smtplib.SMTP_SSL
        elif self.smtp['lmtp']:
            klass = smtplib.LMTP
        else:
            klass = smtplib.SMTP

        with klass(host=self.smtp['host'], **self.options['smtp']) as smtp:
            if self.smtp['tls']:
                smtp.starttls()

            if self.smtp['user'] and self.smtp['pass']:
                smtp.login(self.smtp['user'], self.smtp['pass'])

            smtp.send_message(msg)
