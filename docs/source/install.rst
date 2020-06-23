.. # Links
.. _PyPi: http://pypi.org/
.. _repository: https://github.com/rastern/arbiter
.. _setuptools: https://setuptools.readthedocs.io/en/latest/https://setuptools.readthedocs.io/en/latest/


============
Installation
============

Package Install
===============

The simplest and most common way to install *Arbiter* is to utilize the PyPI_
repository to obtain the latest release. The Python command-line package installer
pip will automatically resolve dependencies and install any unmet requirements
provided you have an active internet connection.

.. code-block:: bash

   pip install arbiter

For installations on air gapped or otherwise isolated machines, you will first
need to download all the requisite wheel or source packages to transfer and
install offline. This can be done with pip from a machine that has internet access.

On a machine with internet access:

.. code-block:: bash

  pip download -d ./packages arbiter

On the air gapped machine after transfering and unpacking files:

.. code-block:: bash

  pip install --no-index --find-links ./packages arbiter


Building from Source
====================

Those who wish to, or otherwise are required to build from source *must* be familiar
with Python packaging techniques. *Arbiter* uses the standard Python build procedure
as outlined by Python's official `documentation <https://packaging.python.org/tutorials/packaging-projects/>`_
and standard build tools, chiefly setuptools_. The source code for *Arbiter* is
publicly hosted on GitHub in the official repository_. Additional support for
custom build or alternative package build processes is not available.


Requirements
============

*Arbiter* is designed to work with Python 3.6 and higher. Additionally, the
following packages are required:

- requests >= 2.21.0
- umsg >= 1.0.4
