# Copyright © 2020 R.A. Stern
# SPDX-License-Identifier: LGPL-3.0-or-later

import atexit
from collections import defaultdict
import datetime
from decimal import Decimal
import json
import logging
from logging import StreamHandler
from logging.handlers import RotatingFileHandler
import multiprocessing
import os
import re
import sys
import threading
import time
from timeit import default_timer as timer
import traceback

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import umsg
from umsg.mixins import LoggingMixin

from arbiter import auth
from arbiter import handlers
from arbiter import registry
from arbiter import exceptions
from arbiter.dict import CaseInsensitiveDict
from .__about__ import (__author__, __copyright__, __description__,
                        __license__, __title__, __version__)



__all__ = [
    '__author__',
    '__copyright__',
    '__description__',
    '__license__',
    '__title__',
    '__version__',
    'FORMAT_DATE',
    'FORMAT_TIME',
    'FORMAT_TIMESTAMP',
    'HANDLERS',
    'AUTH',
    'Process',
    'get_auth',
    'load',
    'loads',
    'mem_cast',
    'parse_string'
]

FORMAT_DATE = '%Y%m%d'
FORMAT_TIME = '%H%M%S'
FORMAT_TIMESTAMP = f"{FORMAT_DATE}{FORMAT_TIME}"

LOG_MODE = logging.ERROR
LOG_MAXSIZE = None
LOG_PATH = None
LOG_FILENAME = None
LOG_FILEMODE = None
LOG_ENCODING = None

__SYSTEM_HANDLERS = ['CSV', 'JSON', 'EMAIL']
__HANDLERS = {
    'CSV': handlers.CsvFile,
    'JSON': handlers.JsonFile,
    'EMAIL': handlers.EmailHandler
}
HANDLERS = registry.Registry(__SYSTEM_HANDLERS, __HANDLERS)

__SYSTEM_AUTH = ['AUTH', 'BASIC']
__AUTH = {
    'AUTH': auth.auth_string,
    'BASIC': auth.basic,
    'ENV': auth.os_env
}
AUTH = registry.Registry(__SYSTEM_AUTH, __AUTH)



class WorkflowJobPool(LoggingMixin):
    __slots__ = [
        'config',
        'handler',
        'logqueue',
        'processes',
        'results',
        'sleep_interval',
        'success',
        'timeout'
    ]

    def __init__(self, config=None, handler=None, processes=None,
                 logqueue=None):
        super().__init__('Workflow')

        self.config = config
        self.success = 0
        self.handler = handler
        self.logqueue = logqueue
        self.sleep_interval = 10
        self.timeout = config.get('process_timeout', 60)
        self.results = defaultdict(lambda: None)

        cpus = multiprocessing.cpu_count()*2 if processes is None else processes
        self.processes = len(config['sources']) if 0 < len(config['sources']) < cpus else cpus

    @staticmethod
    def job_wrapper(func, handler, config, queue, env):
        os.environ = env
        logger = logging.getLogger(__name__+'_worker')
        logger.setLevel(logging.DEBUG)

        # ensure subsequent re-use of the subprocess doesn't duplicate handlers
        if not logger.hasHandlers():
            logger.addHandler(logging.handlers.QueueHandler(queue))

        hdlr = handler(config)

        return func(hdlr, config, logger)

    @property
    def is_complete(self):
        if not self.results:
            return True

        for k in self.results:
            if not self.results[k].ready():
                return False

        return True

    def wait(self):
        start = timer()
        elapsed = 0

        while not self.is_complete and elapsed < self.timeout:
            time.sleep(self.sleep_interval)
            elapsed = int(str(datetime.timedelta(seconds=int(timer() - start)).total_seconds())[:-2])

    def get_results(self):
        results = []
        errors = []

        for k in self.results:
            try:
                msg = None
                res = self.results[k].get()
                results.append(res)
            except multiprocessing.context.TimeoutError:
                msg = f"Workflow timeout exceeded for '{k}'"
            except Exception as e:
                msg = f"Workflow for '{k}' failed"
                self.log(traceback.format_exc(), 'error')

            if msg is not None:
                self.log(msg, level='error')
                errors.append(msg)

        return results, errors

    def run(self, handler=None):
        func = self.handler if handler is None else handler
        sources = self.config['sources']

        with multiprocessing.get_context('spawn').Pool(self.processes) as pool:
            self.log(f"{len(sources)} sources, {self.processes} processes", 'debug')

            for s in sources:
                name = s['resource']

                if s['handler'] in HANDLERS:
                    klass = HANDLERS[s['handler']]

                    self.results[name] = pool.apply_async(self.job_wrapper,
                                         args=(self.handler,
                                               klass,
                                               s,
                                               self.logqueue,
                                               os.environ.copy())
                                     )

            self.wait()
        # pool closed ---


class Process(LoggingMixin):
    """
    Each Process instance handles the processing of inputs, outputs, and
    notifications, as defined in the configuration. The configuration may be
    passed in as a file path or a JSON string. The `worker`, although technically
    optional, is intended to provide input data processing. The function passed
    in will be sent to each new process and provided with the input handler, the
    handler configuration, and a logger object. If no override is provided, the
    process will provide a default worker which calls each input's :py:meth:`~arbiter.handlers.BaseHandler.get`
    method. Because the worker is used for all inputs, it must be capable of
    working with all handlers defined in the config, and any unique requirements
    they may have.

    Args:
        config (path, or string): Process configuration.
        worker (function, optional): Function to use for source processing.
    """
    __slots__ = [
        'config',
        'files',
        'worker',
        'results',
    ]

    def __init__(self, config, worker=None):
        super().__init__('Process')

        try:
            self.config = load(config)
        except FileNotFoundError:
            self.config = loads(config)

        self.__raise_error = self.config.get('raise_error', False)
        self.worker = worker or self.default_worker
        self.results = None
        self.files = None

        init_logging(self.config)

    @staticmethod
    def logging_thread(logger, queue):
        umsg.log('Workflow logging enabled', level='debug', logger=logger)

        while True:
            record = queue.get()

            if record is None:
                umsg.log('Workflow logging disabled', level='debug', logger=logger)
                break

            umsg.log(record.message, level=record.levelname, prefix=record.process, logger=logger)

    @staticmethod
    def default_worker(source, *args):
        try:
            return source.get()
        except Exception:
            return None

    def raise_error(self, msg, exc, exc_info=None):
        if self.__raise_error:
            raise exc(msg)
        else:
            self.log(msg, level='error', exc_info=exc_info)

    def notify(self, config, files=None, errors=None):
        if not files:
            files = []

        if not errors:
            errors = []

        for n in config:
            klass = n['handler']

            if klass not in HANDLERS:
                self.raise_error(f"Unknown handler: {klass}", UnknownHandlerError)

            if (not errors and n.get('on_success', False)) or \
            (errors and n.get('on_failure', False)):
                handler = HANDLERS[klass](n, files=files, errors=errors)
            else:
                continue

            try:
                handler.send()
            except AttributeError:
                self.raise_error(f"Missing required send() method", AttributeError)
            except Exception as e:
                self.log(f"Unable to send notification: {e}")

    def merge_results(self, results):
        """Merges results returned from input handlers into a single result set."""
        data = []

        for r in results:
            data.extend(r)

        return data

    def generate(self, results):
        self.results = self.merge_results(results)
        allerrors = []
        self.pre()

        for o in self.config['outputs']:
            klass = o['handler']
            errors = []
            msg = None
            exc = False

            try:
                handler = HANDLERS[klass](o, **self.config.get('options', {}))
                handler.set(self.results)
                atexit.register(handler.atexit)

                if getattr(handler, 'filename', None):
                    self.files.append(handler.filename)
            except KeyError:
                msg = f"Unknown output handler: {klass}"
                err = UnknownHandlerError
            except AttributeError as e:
                msg = e
                err = AttributeError
            except Exception as e:
                exc = sys.exc_info()
                msg = f"Exception occurred: {e}"
                err = Exception

            if msg:
                self.raise_error(msg, err, exc)
                errors.append(msg)

            # output specific notifications
            if 'notifications' in o:
                self.notify(o['notifications'],
                            files=[handler.filename],
                            errors=errors)

            allerrors.extend(errors)

        self.post()

        return allerrors

    def run(self):
        """Execute the configured process."""
        self.results = []
        self.files = []
        self.log('Process initiated')

        # creates a logging thread for queued messages
        log_queue = multiprocessing.Manager().Queue()
        logthread = threading.Thread(target=self.logging_thread,
                                     args=(umsg.get_attr('logger'), log_queue)
                                    )
        logthread.start()

        self.log('Gathering source data')
        workflow = WorkflowJobPool(config=self.config,
                                   handler=self.worker,
                                   logqueue=log_queue
                                  )
        workflow.run()
        results, errors = workflow.get_results()

        # closeout our logging thread
        log_queue.put_nowait(None)
        logthread.join()

        if not errors:
            self.log('Generating process output')
            errors = self.generate(results)

            if 'notifications' in self.config:
                self.notify(self.config['notifications'],
                            files=self.files,
                            errors=errors)

        if errors and 'notifications' in self.config:
            self.log('Sending error notifications')
            self.notify(self.config['notifications'], errors=errors)

        self.log('Process complete')

    def pre(self):
        pass

    def post(self):
        pass



def unit_cast(value, ufrom, uto, factor, unit_list, precision=False):
    """Generic linear unit conversion routine"""
    offset = unit_list.index(uto) - unit_list.index(ufrom)
    chg = Decimal(pow(factor, abs(offset)))

    res = value * chg if offset <= 0 else value * (1/chg)

    return round(res, precision) if precision else res.normalize()


def mem_cast(value, unit=None, src=None):
    """Memory size (base 2) unit conversion"""
    value = value.replace(' ', '')
    unit = 'G' if not unit else unit[0]
    src = 'B' if not src else src[0]

    if re.match(r'^[\d]+[BKMGTPEZY]{1}[B]?$', value, re.IGNORECASE):
        src = value[-2] if value[-2].isalpha() else value[-1]
        value = value[:-2] if value[-2].isalpha() else value[:-1]
    elif not value.isnumeric():
        raise ValueError(f"'{value}' is not a recognized value")

    return unit_cast(int(value),
                     src.upper(),
                     unit.upper(),
                     1024,
                     ['B', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']
                     )


def parse_string(input, **kwargs):
    """
    String paramter substitution resolver

    Args:
        input (str): Input string to parse.
        **kwargs (dict): Keyword pairs of additional values to substitute.
    """
    if input is not None and '{' in input:
        return input.format(
            date=datetime.date.today().strftime(FORMAT_DATE),
            time=datetime.datetime.now().strftime(FORMAT_TIME),
            timestamp=datetime.datetime.now().strftime(FORMAT_TIMESTAMP),
            **kwargs
        )
    else:
        return input


def get_auth(obj):
    """Resolve authentication handler for a given object"""
    if obj['type'].upper() in AUTH:
        return AUTH[obj['type'].upper()](obj)


def init_logging(config):
    """
    Initialize logging based on configuration

    Either the entire config, or the logging subsection must be passed in. If no
    logging `path` parameter is found a :py:class:`~logging.StreamHandler` will
    be initialized instead. If `path` is found, a :py:class:`~logging.handlers.RotatingFileHandler`
    will be initialized, with a default rotation of 10mb, and `backupCount` of 1.

    Args:
        config (dict): Configuration.
    """
    global LOG_MODE, LOG_MAXSIZE, LOG_PATH, LOG_FILENAME, LOG_FILEMODE, LOG_ENCODING

    hdlr = None
    logging = config.get('logging', config)

    LOG_MODE = logging.get('mode', 'ERROR')
    LOG_MAXSIZE = logging.get('maxsize', '10M')
    LOG_PATH = logging.get('path', None)
    LOG_FILEMODE = logging.get('filemode', 'a+').lower()
    LOG_ENCODING = logging.get('encoding', None)

    if LOG_PATH:
        hdlr = RotatingFileHandler(LOG_PATH,
                                   mode=LOG_FILEMODE,
                                   maxBytes=mem_cast(LOG_MAXSIZE, 'B'),
                                   backupCount=1,
                                   encoding=LOG_ENCODING
                                  )
    if not hdlr:
        hdlr = StreamHandler()

    umsg.init(mode=LOG_MODE)
    umsg.add_handler(hdlr)


def loads(data):
    """
    Loads configuration data from a JSON string

    Args:
        data (str): JSON string to parse.
    """
    return json.loads(data, object_pairs_hook=CaseInsensitiveDict)


def load(file):
    """
    Loads configuration data from a JSON file

    Args:
        file (str): File path to load.
    """
    with open(file, 'r') as fp:
        return json.load(fp, object_pairs_hook=CaseInsensitiveDict)
