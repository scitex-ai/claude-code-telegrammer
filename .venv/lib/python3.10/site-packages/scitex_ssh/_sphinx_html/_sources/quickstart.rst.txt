Quickstart
==========

Setup a Tunnel (via the ``tunnel`` subcommand group)
-----------------------------------------------------

.. code-block:: bash

    scitex-ssh tunnel setup -p 2222 -b user@bastion.example.com -s ~/.ssh/id_rsa

This creates a systemd service that maintains a persistent reverse SSH (Secure Shell) tunnel.

.. note::

   ``tunnel setup`` and ``tunnel remove`` require **sudo** privileges because they write
   systemd service files to ``/etc/systemd/system/`` and run ``systemctl``.
   You will be prompted for your password.

Check Status
------------

.. code-block:: bash

    scitex-ssh tunnel check-status
    scitex-ssh tunnel check-status -p 2222

Remove a Tunnel
---------------

.. code-block:: bash

    scitex-ssh tunnel remove -p 2222

Python API (Application Programming Interface)
-----------------------------------------------

.. code-block:: python

    import scitex_ssh

    # Setup
    result = scitex_ssh.setup(2222, "user@bastion.example.com", "~/.ssh/id_rsa")
    print(result["success"])  # True

    # Status
    result = scitex_ssh.status(port=2222)

    # Remove
    result = scitex_ssh.remove(2222)
