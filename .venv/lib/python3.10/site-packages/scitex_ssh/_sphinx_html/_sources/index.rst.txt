.. SciTeX SSH documentation master file

SciTeX SSH - Persistent SSH (Secure Shell) Reverse Tunnel
=============================================================

**SciTeX SSH** manages persistent SSH (Secure Shell) reverse tunnels for NAT (Network Address Translation) traversal, powered by autossh and systemd. It provides three interfaces: Python API (Application Programming Interface), CLI (Command-Line Interface), and MCP (Model Context Protocol) server for AI agents.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   quickstart

.. toctree::
   :maxdepth: 2
   :caption: Architecture

   how-it-works

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/scitex_ssh

Key Features
------------

- **Persistent Tunnels**: autossh-based reverse SSH tunnels that auto-restart on failure
- **systemd Integration**: Each tunnel runs as a managed systemd service that survives reboots
- **Three Interfaces**: Python API, CLI, and MCP server for AI agents
- **Simple API**: Three operations — setup, status, remove
- **Environment Variables**: Configure defaults via ``SCITEX_SSH_*`` environment variables

Architecture Overview
---------------------

.. code-block:: text

    Lab Workstation              Bastion Server           Remote Client
    (behind NAT/firewall)        (public IP)              (laptop)
    ┌─────────────────┐     ┌──────────────────┐     ┌──────────────┐
    │ systemd service  │     │                  │     │              │
    │  └─ autossh ─────┼─────┼─► sshd :{port} ─┼─────┼─ ssh -p PORT │
    │     (daemon)     │     │                  │     │              │
    │ localhost:22     │     │                  │     │              │
    └─────────────────┘     └──────────────────┘     └──────────────┘
       reverse tunnel ──────►         ◄──── SSH connection ────

The lab workstation initiates a **reverse SSH tunnel** to the bastion server. autossh
monitors the connection and re-establishes it on failure. systemd ensures the service
starts on boot and restarts on process crashes. A remote client connects to the bastion
server on the forwarded port, and the connection is routed back through the tunnel.

Quick Example
-------------

Python API:

.. code-block:: python

    import scitex_ssh

    # Set up a tunnel
    result = scitex_ssh.setup(2222, "user@bastion.example.com", "~/.ssh/id_rsa")

    # Check status
    result = scitex_ssh.status()

    # Remove
    result = scitex_ssh.remove(2222)

CLI:

.. code-block:: bash

    scitex-ssh setup -p 2222 -b user@bastion.example.com -s ~/.ssh/id_rsa
    scitex-ssh status
    scitex-ssh remove -p 2222

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
