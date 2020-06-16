# Copyright © 2020 R.A. Stern
# SPDX-License-Identifier: LGPL-3.0-or-later

import atexit
from collections import defaultdict
import datetime
import json
import logging
from logging import StreamHandler
from logging.handlers import RotatingFileHandler
import multiprocessing
import os
import threading
import time
from timeit import default_timer as timer
import traceback

import requests
from requests.structures import CaseInsensitiveDict
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import umsg
from umsg.mixins import LoggingMixin

from arbiter import auth
from arbiter import handlers
from arbiter import registry
from arbiter import exceptions
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
    'BODY_ERROR',
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
BODY_ERROR = """Errors where encountered while processing data:

{errors}
"""

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
    'BASIC': auth.basic
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
    def job_wrapper(func, handler, config, queue):
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

        with multiprocessing.Pool(self.processes) as pool:
            self.log(f"{len(sources)} sources, {self.processes} processes", 'debug')

            for s in sources:
                name = s['resource']

                if s['handler'] in HANDLERS:
                    klass = HANDLERS[s['handler']]

                    self.results[name] = pool.apply_async(self.job_wrapper,
                                         args=(self.handler, klass, s, self.logqueue)
                                     )

            self.wait()
        # pool closed ---


class Process(LoggingMixin):
    """Process management object

    :py:class:`~arbiter.Process` handles the processing of inputs to outputs.

    Args:
        config (dict): Process configuration
        handler (function): Function to use for source processing

    Attributes:
        config (dict): Process configuration.
        files (list): List of generated output files.
        handler (func): Worker function for source processing.
        results (list): Combined result of source processing.
    """
    __slots__ = [
        'config',
        'files',
        'handler',
        'results',
    ]

    def __init__(self, config, handler):
        super().__init__('Process')

        self.config = config
        self.handler = handler
        self.files = list()

    @staticmethod
    def logging_thread(logger, queue):
        umsg.log('Workflow logging enabled', level='debug', logger=logger)

        while True:
            record = queue.get()

            if record is None:
                umsg.log('Workflow logging disabled', level='debug', logger=logger)
                break

            umsg.log(record.message, level=record.levelname, prefix=record.process, logger=logger)

    def notify(self, config, files=None, errors=None):
        for n in config:
            klass = n['handler']

            if klass not in HANDLERS:
                raise UnknownHandlerError(f"Unknown notification handler: {klass}")

            if (not errors and n.get('on_success', False)) or \
            (errors and n.get('on_failure', False)):
                handler = HANDLERS[klass](n, files=files, errors=errors)
            else:
                continue

            if not isinstance(handler, handlers.NotificationHandler):
                raise TypeError(f"Invalid handler type {type(handler)}")

            handler.send()

    def merge_results(self, results):
        data = []

        for r in results:
            data.extend(r)

        return data

    def generate(self, results):
        self.results = self.merge_results(results)
        self.pre()

        for o in self.config['outputs']:
            klass = o['handler']

            try:
                handler = HANDLERS[klass](o, **self.config.get('options', dict()))
            except KeyError:
                raise UnknownHandlerError(f"Unknown output handler: {klass}")

            if isinstance(handler, handlers.NotificationHandler):
                raise TypeError(f"Invalid handler type {type(handler)}")

            handler.set(self.results)

            if isinstance(handler, handlers.FileHandler):
                self.files.append(handler.filename)

                if not o.get('keepfile', False):
                    atexit.register(handler.atexit)

            if 'notifications' in o:
                self.notify(o['notifications'], [handler.filename])

        self.post()

    def run(self):
        self.log('Process initiated')

        # creates a logging thread for queued messages
        log_queue = multiprocessing.Manager().Queue()
        logthread = threading.Thread(target=self.logging_thread,
                                     args=(umsg.get_attr('logger'), log_queue)
                                    )
        logthread.start()

        self.log('Gathering source data')
        workflow = WorkflowJobPool(config=self.config,
                                   handler=self.handler,
                                   logqueue=log_queue
                                  )
        workflow.run()
        results, errors = workflow.get_results()

        # closeout our logging thread
        log_queue.put_nowait(None)
        logthread.join()

        if errors and 'notifications' in self.config:
            self.log('Sending error notifications')
            self.notify(self.config['notifications'], errors=errors)
        else:
            self.log('Generating process output')
            self.generate(results)

            if 'notifications' in self.config:
                self.notify(self.config['notifications'], files=self.files)

    def pre(self):
        pass

    def post(self):
        pass



def unit_cast(value, ufrom, uto, factor, unit_list, precision=False):
    offset = unit_list.index(uto) - unit_list.index(ufrom)
    chg = Decimal(pow(factor, abs(offset)))

    res = value * chg if offset <= 0 else value * (1/chg)

    return round(res, precision) if precision else res.normalize()


def mem_cast(value, unit=None, src=None):
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
    if '{' in input:
        return input.format(
            date=datetime.date.today().strftime(FORMAT_DATE),
            time=datetime.datetime.now().strftime(FORMAT_TIME),
            timestamp=datetime.datetime.now().strftime(FORMAT_TIMESTAMP),
            **kwargs
        )
    else:
        return input


def get_auth(obj):
    if obj['type'].upper() in AUTH:
        return AUTH[obj['type'].upper()](obj)


def init_logging(config):
    global LOG_MODE, LOG_MAXSIZE, LOG_PATH, LOG_FILENAME, LOG_FILEMODE, LOG_ENCODING

    hdlr = None

    if config.get('logging'):
        LOG_MODE = config['logging'].get('mode', 'ERROR')
        LOG_MAXSIZE = config['logging'].get('maxsize', '10M')
        LOG_PATH = config['logging'].get('path', None)
        LOG_FILENAME = config['logging'].get('filename', None)
        LOG_FILEMODE = config['logging'].get('filemode', 'a').lower()
        LOG_ENCODING = config['logging'].get('encoding', None)

        if LOG_PATH and LOG_FILENAME:
            filename = os.path.join(LOG_PATH, LOG_FILENAME)
            hdlr = RotatingFileHandler(filename,
                                       mode=LOG_FILEMODE,
                                       maxBytes=mem_cast(LOG_MAXSIZE, 'B'),
                                       encoding=LOG_ENCODING
                                      )
    if not hdlr:
        hdlr = StreamHandler()

    umsg.init(mode=LOG_MODE)
    umsg.add_handler(hdlr)


def loads(data):
    config = json.loads(data, object_pairs_hook=CaseInsensitiveDict)
    init_logging(config)

    return config


def load(file):
    with open(file, 'r') as fp:
        config = json.load(fp, object_pairs_hook=CaseInsensitiveDict)
        init_logging(config)

        return config
