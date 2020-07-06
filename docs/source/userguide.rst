.. # Links
.. _SMTP: https://docs.python.org/3/library/smtplib.html#smtplib.SMTP
.. _SMTP_SSL: https://docs.python.org/3/library/smtplib.html#smtplib.SMTP_SSL
.. _starttls: https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.starttls
.. _LMTP: https://docs.python.org/3/library/smtplib.html#smtplib.LMTP
.. _RFC 2732: https://tools.ietf.org/html/rfc2732

==========
User Guide
==========

|

Core Concepts
=============

Processor
---------

The core of arbiter is the :py:class:`~arbiter.Process` class, a multi-processing
orchestrator that collects inputs, performs data manipulation, feeds outputs, and
sends notifications. The processor itself is agnostic to the actual connections,
data, and data translations. All aspects of data handling are the responsibility
of their respective handlers, and inherit from the same :py:class:`~arbiter.handlers.BaseHandler`
object. The processor also takes care of coordinating process logs and error
handling.


Handlers
--------

Handlers perform all the discrete work within a data process flow. This includes
data ingestion, translation, output, notifications, and so forth. In theory any
handler could be used for an input or output, provided it contains the requisite
*get()* and *set()* methods. arbiter broadly defines three logically distinct types
of handlers: :py:class:`~arbiter.handlers.FileHandler`, :py:class:`~arbiter.handlers.ConnectionHandler`, and :py:class:`~arbiter.handlers.NotificationHandler`.

Generally speaking a :py:class:`~arbiter.handlers.FileHandler` should implement
*get()*, *set()*, and *atexit()*; a :py:class:`~arbiter.handlers.ConnectionHandler`
should implement *connect()* and *disconnect()*; and a :py:class:`~arbiter.handlers.NotificationHandler`
should implement *send()*. Each handler type base class will provide interface
stubs for these methods.


Configuration
-------------

arbiter utilizes a structured JSON document consisting of blocks and directives
for all processors. Directives are key-value pairs, while blocks are collections
of directives or other data, represented as JSON objects. There are four block
definitions, of which two are required: *sources* (required), *outputs* (required),
*notifications*, and *logging*. Each block, except *logging*, comprises a list
of one or more handler definitions. The *logging* block consists only of logging
directives.

.. code-block:: JSON
  :force:
  :caption: Configuration document skeleton

  {
    "sources": [...],
    "outputs": [...],
    "notifications": [...],
    "logging": {...}
  }

Handler definition blocks consist of three parts: an *identifier*, *directives*,
and an *options* block. Each handler entry must contain a single identifier called
``handler``, which is a special directive indicating which specific registered
handler will process the config. The identifiers are case-insensitive, and all
custom handler extensions must be registered using the :py:class:`~arbiter.HANDLERS`
registry or an :py:class:`arbiter.exceptions.UnknownHandlerError` will be raised
when the handler is called.

.. code-block:: JSON
  :caption: Handler identifier

  {
    "handler": "<name>"
  }

Handler directives are type level parameters passed to the :py:class:`~arbiter.Process`
indicating how the processor should work with the handler instance. Most handlers
make use of the *resource* and *authentication* directives, though this is
not strictly required as in the case of the :py:class:`~arbiter.handlers.NotificationHandler`.

.. code-block:: JSON
  :caption: Example handler block

  {
    "handler": "<name>",
    "resource": "file://local/path/to/file.ext",
    "authentication": {
        "type": "basic",
        "username": "administrator",
        "password": "insecure"
      }
  }

Handler specific directives are defined in the *options* block. These parameters
are used internally by the handler, and often passed directly to the underlying
third-party library the handler uses. Handlers have flexibility to define any
options required, and to document their use. Some handlers that have complex
interactions with multiple libraries, such as the :py:class:`~arbiter.handlers.EmailHandler`
may have multiple sub-block definitions for each component nested in the *options*
block.

.. code-block:: JSON
   :force:
   :caption: Example sup-blocks in handler options.

   {
     "handler": "email",
     "options": {
       "email": {...},
       "smtp": {...}
     }
   }

Logging Options
^^^^^^^^^^^^^^^

By default arbiter will log to a :py:class:`~logging.StreamHandler`. Alternatively
you may specify a logfile path for output, wherein arbiter will employ a
:py:class:`~logging.handlers.RotatingFileHandler` instead. The following options
are supported:

  :mode: Logging mode as string. One of info, debug, warn, error, critical.
  :maxsize: Maximum filesize before log rotation. Default: 10M.
  :path: Filepath to the desired log. Directory tree must exist.
  :filemode: File write mode. Default: 'a'.
  :encoding: File encoding, if other than UTF-8 is required.

Authentication
--------------

Stored credentials of any kind pose a security risk. arbiter provides multiple
built-in methods for passing simple credentials for testing, and can be extended
to support additional credentialing systems as necessary by handlers. Although
there is no requirement to use the :py:attr:`~arbiter.AUTH` registry for custom
credential handlers, as you may simply read the *authentication* object directly,
the registry allows automatic resolution of any registered authentication scheme
using the :py:func:`~arbiter.get_auth` built-in. This permits users to change
authentication schemes as required, for instance when moving from test to prod,
without requiring code changes, provided you registered a handler.

Built-in authentication providers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:py:attr:`Type:` **AUTH**
  Base64 'Basic Auth' style credential hash.

  Returns a :py:class:`dict` of credentials including an 'auth' key continaing
  the base64 'basic auth' representation of the data.

  .. code-block:: JSON
    :force:
    :caption: AUTH example

    {
      ...,
      "authentication": {
        "type": "auth",
        "credential": "dW5kZXI6d2Vhcg=="
      }
    }

:py:attr:`Type:` **BASIC**
  Basic username & password authentication scheme.

  Returns a :py:class:`dict` of credentials including an 'auth' key continaing
  the base64 'basic auth' representation of the data.

  .. warning::
     Although username and plaintext password authentication is supported, it
     should not be used outside of a test environment.

  .. code-block:: JSON
    :force:
    :caption: BASIC example

    {
      ...,
      "authentication": {
        "type": "basic",
        "username": "bob",
        "password": "dont-do-this"
      }
    }

:py:attr:`Type:` **ENV**
  Credentials are defined by OS level environment variables. The name of the
  variable is given as the value for each field.

  Returns a :py:class:`dict` with all values replaced by their environment variable
  counterpart.

  .. code-block:: JSON
    :force:
    :caption: ENV example

    {
      ...,
      "authentication": {
        "type": "env",
        "username": "APP_USER",
        "token": "APP_TOKEN"
      }
    }

|

Process Objects
===============

.. graphviz:: processor.dot

The :py:class:`~arbiter.Process` class is the workhorse of the arbiter package.
Inputs are pulled in parallel and aggregated using the :py:meth:`~arbiter.Process.merge_results`
method. The combined result set is then sequentially passed to each output handler.
An output handler may have one or more notifiers associated to it, which will
each receive the generated file of the output handler, if any. After all output
handlers are called the global process notifiers are called sequentially, each
receiving the entire list of files generated by all output handlers, if any.

.. class:: Process

   .. attribute:: config

      The process configuration represented as a :py:class:`dict`.

   .. attribute:: results

      Merged results from all inputs as returned by the :py:meth:`merge_results`
      method. The default behavior is to return a :py:class:`list`.

   .. attribute:: files

      A list of files to be sent to the global process notifications handlers.
      After each output handler is called, if the handler has a *filename*
      attribute that is not ``None``, the value will be appended to this list.

   .. method:: Process.__init__(config, worker=None)

      Initialize a :py:class:`Process` instance by loading its JSON configuration
      and initializing configured logging. If `config` is a filepath, the file
      is loaded using :py:func:`~arbiter.load`, otherwise it is expected to be
      a JSON string and loaded using :py:func:`~arbiter.loads`. If `worker` is
      not provided, a generic worker that calls each handler's :py:meth:`~arbiter.handlers.BaseHandler.get`
      method will be provided.

   .. method:: Process.merge_results

      Results from the input handler processes are collected as a list and held
      until all processes are completed. The list of result sets is passed to
      this method for merging into a single result set to be later passed on to
      each output handler. Provided the result sets are well formed by the input
      handlers, the default merge should work for the majority of use cases.
      Where it does not, for example deduplication or collision handling, this
      method should be overloaded as required.

   .. method:: Process.pre

      The pre hook executes after all results are processed, and before the list
      of output handlers is processed.

   .. method:: Process.post

      The post hook executes after all output handlers have been called, before
      the global process notification handlers are processed.

   .. method:: Process.run

      Executes the configured process.

|

Handler Objects
===============

BaseHandler
-----------

All handlers have the following inherited attributes, methods, and directives.
The BaseHandler serves as the foundation of all handler types.

.. note::
   The :py:class:`~arbiter.handlers.BaseHandler` should never be instantiated
   or inherited directly. Instead, utilize one of the categorized handler types
   when building new handlers, and ensure the :py:meth:`__init__` method of the
   subclass calls :py:func:`super`.

:py:attr:`Directives:`
  :authentication:  Authentication block.
  :resource:  Resource definition. Usually an URI.

.. class:: BaseHandler

   Provides configuration loading to all handlers, and establishes the baseline
   attributes.

   :param config: Dictionary of handler configuration data.

   .. attribute:: BaseHandler.config

      The entire handler configuration block, as provided by the calling :py:class:`~arbiter.Process`
      object.

   .. attribute:: BaseHandler.options

      A :py:class:`dictionary` of handler specific keyword options to be passed
      to the handler subroutine. For example, formatting parameters such as `indent`
      for JSON output may be passed this way.

   .. attribute:: BaseHandler.authentication

      The authentication sub-block of the handler configuration definition, if
      present. Otherwise this value is ``None``. This contains all the necessary
      information to authenticate to the resource.

   .. attribute:: BaseHandler.resource

      This represents the full resource definition provided to the handler, after
      substitution parsing has been performed. This will usually correspond to
      an URI, though it is not strictly required.

   .. method:: BaseHandler.atexit()

      Registered with the :py:mod:`atexit` module after the :py:meth:`~arbiter.handlers.BaseHandler.set`
      method is called by the processor.


|

FileHandler
-----------

The :py:class:`~arbiter.handlers.FileHandler` type provides filepath resolution
to all descendent file handlers, and removes files at program termination by
default.

.. class:: FileHandler

   .. attribute:: FileHandler.filename

      For output handlers, this is the output file or file-like resource to be
      written to.

   .. method:: FileHandler.get()

      Data input interface for all handlers. This is called by a :py:class:`~arbiter.Process`
      worker to acquire data from a source.

   .. method:: FileHandler.set(data)

      Data output interface for all handlers. This is called by a :py:class:`~arbiter.Process`
      to write finished data to the handler. A single parameter is required, and
      will be of the data type returned by :py:meth:`~arbiter.Process.merge_results`.

   .. method:: FileHandler.atexit()

      Registered with the :py:mod:`atexit` module to remove the file created for
      output.

|

CsvFile
^^^^^^^

Provides CSV serialization and deserialization utilizing the standard Python CSV
library. By default :py:class:`CsvFile` utilizes the :py:class:`~csv.DictReader`
and :py:class:`~csv.DictWriter` objects.

:py:attr:`Identifier:` **CSV**

.. class:: CsvFile

   :param fieldnames:  Input / output whitelist of fields to filter on. All fields
      are kept if value is ``None``. (Default: ``None``)

   .. method:: CsvFile.__init__(config, **kwargs)

      Sets fields whitelist and initializes handler.

|

JsonFile
^^^^^^^^

Provides JSON serialization and deserialization utilizing the standard Python
JSON library. By default :py:class:`JsonFile` utilizes :py:func:`~json.load`
and :py:func:`~json.dump` functions.

:py:attr:`Identifier:` **JSON**

.. class:: JsonFile

   .. method:: JsonFile.__init__(config, **kwargs)

      JsonFile does not implement any additional attributes or methods.

|

ConnectionHandler
-----------------

:py:class:`~arbiter.handlers.ConnectionHandler` instances are more nuanced than
:py:class:`~arbiter.handlers.FileHandler` instances. Instead of implementing
read/write interfaces, this handler type is intended to be implemented for
direct use within the :py:class:`~arbiter.Process` worker function. A connection
will not in itself execute any action, though it will provide access to resources
through additional external APIs. This might be a well-known REST API, a socket
connection, or other service interface.

.. class:: ConnectionHandler

   .. method:: ConnectionHandler.__init__(config, **kwargs)

      Initializes the handler, stores the authentication sub-block properties,
      and parses the handler resource string for replacement tags.

   .. method:: ConnectionHandler.connect()

      Connection interface to be implemented by sub-classes.

   .. method:: ConnectionHandler.diconnect()

      Disconnection interface to be implemented by sub-classes.

|

HttpHandler
^^^^^^^^^^^

The :py:class:`~arbiter.handlers.HttpHandler` provides additional properties
suitable for HTTP and HTTPS connection implementations. Notably, the `userinfo`
of the URI authority component is explicitly not represented in attributes below,
and although `userinfo` will not be removed from the original resource URI,
credentials should be handled in a more secure manner through the
:py:attr:`~arbiter.handlers.ConnectionHandler.authentication` configuration block.

.. class:: HttpHandler

   .. attribute:: HttpHandler.host

      Location of the resource to be connected to. This could be a registered name,
      or an IP address.

      .. note::
         In accordance with `RFC 2732`_ IPv6 addresses in URLs must be enclosed
         in square brackets. Example: https://[::1]:8080/

   .. attribute:: HttpHandler.path

      Slash (/) separated path segments indicating the resource location upon
      the host.

   .. attribute:: HttpHandler.query

      Query string, if any, used to obtain the desired resource.

   .. attribute:: HttpHandler.secure

      Secure transport indicator. If ``True`` communications will take place over
      an HTTPS connection, otherwise an HTTP connection will be used if ``False``.

      Default: ``False``

   .. attribute:: HttpHandler.port

      Host port to connect to. If the inherited :py:attr:`~arbiter.handlers.ConnectionHandler.resource`
      identifer does not contain a port, `80` will be used for HTTP connections
      and `443` for HTTPS connections by default.

   .. method:: HttpHandler.__init__(config, **kwargs)

      Parses the *resource* string and populates the URL component attributes.

   .. method:: HttpHandler.connect()

      Connection method to be implemented by inheriting sub-classes. Typically
      this will return an connection or session object to the work for making any
      required API calls.

   .. method:: HttpHandler.disconnect()

      Disconnection method to be implemented by inheriting sub-classes, if required.

|

NotificationHandler
-------------------

The base :py:class:`~arbiter.handlers.NotificationHandler` is a special type
handler for relaying secondary information to external systems. This could be
email, SMS messaging, syslog, or other message handling and alerting systems.
All such handlers may be coupled to an output handler, for which they will be
called immediately upon completion of that handler's :py:meth:`~arbiter.handlers.BaseHandler.set`
method with the filepath to the file generated by the output handler if any.
Alternatively, notification handlers may be assigned at the global process level,
where they are called at the end of the process, each receiving the full list of
filepaths for all output handlers if applicable. Notification handlers may also
receive collected error messages, and all must implement the
:py:meth:`~arbiter.handlers.NotificationHandler.send` method.

:py:attr:`Directives:`
  :on_success: Boolean. If ``True`` the notification is executed upon process success.
  :on_failure: Boolean. If ``True`` the notification is executed upon process error.

.. class:: NotificationHandler

   .. attribute:: NotificationHandler.files

      List of all files generated by successful output handlers.

   .. attribute:: NotificationHandler.errors

      List of all errors returned by output handlers.

   .. method:: NotificationHandler.__init__(config, **kwargs)

      Initializes the notification handler, setting the files and error properties
      if applicable.

   .. method:: NotificationHandler.send()

      Notification execution method used by the calling :py:class:`~arbiter.Process`.

|

EmailHandler
^^^^^^^^^^^^

:py:attr:`Identifier:` **email**

Email communications require the construction of the email message itself, as
well as communications with an SMTP server. The :py:class:`~arbiter.handlers.EmailHandler`
handles both tasks, combining them into one process upon :py:meth:`~arbiter.handlers.NotificationHandler.send`.
Email message construction is handled by the Python :py:mod:`email` library, and
SMTP communications is performed by :py:mod:`smtplib`.

Configurable email message header strings:

  - orig-date
  - from
  - sender
  - reply-to
  - to
  - cc
  - bcc
  - subject
  - comments
  - keywords
  - optional-field

Email message options are specified as a sub-block in the standard handler options
block. A `from` header and one of `to`, `cc`, `bcc` are required. All other headers
may be omitted, though a `subject` is strongly recommended. Two additional non-header
fields are supported as well:

:py:attr:`Email Options:`
  :body:  the email message body template
  :body_error:  the email message body template returned upon errors
  :\*\*headers:  Any listed header

.. code-block:: JSON
  :caption: Example email options

  {
     "handler": "email",
     "options": {
       "email": {
         "from": ["no-reply@example.com"],
         "to": ["recipient@example.com"],
         "subject": "Email subject with a timestamp: {timestamp}",
         "body": "This email was generated on {date}.",
         "body_error": "Errors happened: {errors}"
       }
     }
   }

SMTP options are collected as a sub-block under the `SMTP` key. SSL, TLS, and
LMTP are supported through configuration. Python contexts, for SSL and TLS, are
not presently support; a keyfile and certfile must be declared instead.

:py:attr:`SMTP Options:`
  :host:  host identifier. See `SMTP`_ for additional options.
  :ssl:  boolean flag. See `SMTP_SSL`_ for additional options.
  :tls:  boolean flag. See `starttls`_ for additional options.
  :lmtp:  boolean flag. See `LMTP`_ for additional options.
  :authentication:  Authentication block.

.. code-block:: JSON
  :caption: Example SMTP options

  {
     "handler": "email",
     "options": {
       "smtp": {
         "host": "localhost",
         "ssl": true,
         "keyfile": "./location/keyfile",
         "certfile": "./location/certfile"
       }
     }
   }

.. class:: EmailHandler

   .. attribute:: EmailHandler.emailheaders

      A list of email headers which may be modified by the user via configuration
      parameters or passed into the `email` keyword. This list must not be
      edited.

   .. method:: EmailHandler.__init__(config, **kwargs)

      If passing in options directly, Email message options and SMTP options must
      be passed in as a :py:class:`dict` to they keywords `email` and `smtp`
      respectively. All other handler options are passed in as normal.
