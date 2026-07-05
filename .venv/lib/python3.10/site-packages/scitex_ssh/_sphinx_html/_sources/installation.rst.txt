Installation
============

From PyPI (Python Package Index)
---------------------------------

.. code-block:: bash

    pip install scitex-ssh

Or as part of SciTeX:

.. code-block:: bash

    pip install scitex[ssh]

Prerequisites
-------------

- ``autossh`` installed on the host machine (``sudo apt install autossh``)
- SSH (Secure Shell) key pair for authentication
- A bastion server with SSH access

Development
-----------

.. code-block:: bash

    pip install -e ".[dev]"
