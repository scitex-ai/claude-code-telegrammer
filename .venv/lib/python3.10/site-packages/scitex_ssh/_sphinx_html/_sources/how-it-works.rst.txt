How It Works
============

This page explains the architecture and internals of SciTeX SSH.

.. warning::

   Before setting up reverse tunnels, please check your organization's acceptable
   use policy and network terms of service. Reverse tunnels may bypass institutional
   firewalls or network policies. The authors accept no responsibility for any
   consequences arising from the use of this software.

The Problem: NAT (Network Address Translation) Traversal
---------------------------------------------------------

Machines behind NAT or institutional firewalls **cannot receive incoming connections**.
A standard SSH connection from a remote client to a lab workstation fails because:

1. The workstation has a private IP (e.g., ``192.168.x.x``) that is not routable from the internet.
2. The router/firewall blocks unsolicited incoming connections.
3. Port forwarding on institutional networks is typically not available to researchers.

The Solution: Reverse SSH Tunnels
---------------------------------

A **reverse tunnel** inverts the connection direction. Instead of the client connecting
to the workstation, the workstation connects *outward* to a publicly reachable **bastion
server** and opens a listening port there. When a client connects to that port on the
bastion, the traffic is forwarded back through the existing tunnel to the workstation.

.. code-block:: text

    ┌─────────────────────────────────────────┐
    │  Lab Workstation (behind NAT/firewall)  │
    │                                         │
    │  ┌──────────────────────────────────┐   │
    │  │ systemd service                  │   │
    │  │ autossh-tunnel-{port}.service    │   │
    │  │   ┌──────────────────────────┐   │   │
    │  │   │ autossh                  │   │   │
    │  │   │ (auto-reconnect daemon)  │   │   │
    │  │   └────────────┬─────────────┘   │   │
    │  └────────────────┼─────────────────┘   │
    │                   │                     │
    │  localhost:22 ◄───┘                     │
    │  (SSH server)                           │
    └───────────────────┼─────────────────────┘
                        │
                        │  reverse tunnel
                        │  -R {port}:localhost:22
                        ▼
    ┌──────────────────────────────────────────┐
    │  Bastion Server (public IP)              │
    │                                          │
    │  sshd listening on port {port}           │
    │  forwards to tunnel → workstation:22     │
    └──────────────────────┬───────────────────┘
                           │
                           │  ssh -p {port} bastion-server
                           │
    ┌──────────────────────┴───────────────────┐
    │  Remote Client (researcher laptop)       │
    │                                          │
    │  ssh -p {port} user@bastion-server       │
    │  → routed through tunnel to workstation  │
    └──────────────────────────────────────────┘

Persistence via systemd and autossh
------------------------------------

A plain ``ssh -R`` tunnel breaks when the network drops or the machine reboots.
SciTeX SSH solves this with two layers of persistence:

**Layer 1: autossh (connection-level persistence)**

`autossh <https://www.harding.motd.ca/autossh/>`_ is a program that monitors an SSH
connection and automatically re-establishes it when it detects failure. It uses
``-M 0`` (rely on SSH's built-in ``ServerAliveInterval``/``ServerAliveCountMax``)
and runs as a daemon.

**Layer 2: systemd (process-level persistence)**

Each tunnel is registered as a systemd service unit. This provides:

- **Boot persistence**: ``WantedBy=multi-user.target`` ensures the tunnel starts on boot.
- **Crash recovery**: ``Restart=always`` with ``RestartSec=3`` restarts autossh if it crashes.
- **Standard management**: ``systemctl start/stop/status`` for the tunnel service.

The Service File
~~~~~~~~~~~~~~~~

When you run ``scitex-ssh tunnel setup -p 2222 -b user@bastion -s ~/.ssh/id_rsa``,
the following systemd unit file is created:

**File**: ``/etc/systemd/system/autossh-tunnel-2222.service``

.. code-block:: ini

    [Unit]
    Description=AutoSSH tunnel service
    After=network-online.target
    Wants=network-online.target

    [Service]
    User=<your-username>
    Environment="AUTOSSH_GATETIME=0"
    ExecStart=/usr/bin/autossh -M 0 -N \
        -o "PubkeyAuthentication=yes" \
        -o "PasswordAuthentication=no" \
        -i /home/<user>/.ssh/id_rsa \
        -R 2222:localhost:22 user@bastion
    RestartSec=3
    Restart=always

    [Install]
    WantedBy=multi-user.target

After writing this file, the setup script runs:

.. code-block:: bash

    systemctl daemon-reload
    systemctl enable autossh-tunnel-2222.service
    systemctl restart autossh-tunnel-2222.service

The Three Operations
--------------------

.. list-table::
   :header-rows: 1
   :widths: 15 35 50

   * - Operation
     - What it does
     - Under the hood
   * - **setup**
     - Creates and starts a persistent reverse tunnel
     - Writes systemd unit file → ``daemon-reload`` → ``enable`` → ``start``
   * - **status**
     - Reports whether the tunnel is active
     - Runs ``systemctl status autossh-tunnel-{port}.service``
   * - **remove**
     - Stops and removes the tunnel permanently
     - ``stop`` → ``disable`` → delete unit file → ``daemon-reload``

Each operation is available through all three interfaces:

- **Python**: ``scitex_ssh.setup()``, ``scitex_ssh.status()``, ``scitex_ssh.remove()``
- **CLI**: ``scitex-ssh tunnel setup``, ``scitex-ssh tunnel check-status``, ``scitex-ssh tunnel remove``
- **MCP**: ``tunnel_setup``, ``tunnel_status``, ``tunnel_remove`` tools

Environment Variables
---------------------

To avoid repeating the bastion server and key path on every command, set these
environment variables:

.. list-table::
   :header-rows: 1
   :widths: 35 40 25

   * - Variable
     - Description
     - Example
   * - ``SCITEX_SSH_BASTION_SERVER``
     - Default bastion server address
     - ``user@bastion.example.com``
   * - ``SCITEX_SSH_SECRET_KEY_PATH``
     - Default SSH private key path
     - ``~/.ssh/id_rsa``
   * - ``SCITEX_SSH_DEBUG_MODE``
     - Enable verbose logging (``1``)
     - ``0``

CLI flags always take precedence over environment variables.

Prerequisites
-------------

- **autossh**: Must be installed on the host (``sudo apt install autossh``).
- **SSH key pair**: Public key must be authorized on the bastion server (``~/.ssh/authorized_keys``).
- **Bastion server**: Any machine with a public IP and an SSH server (``sshd``).
  The bastion must have ``GatewayPorts yes`` or ``GatewayPorts clientspecified``
  in ``/etc/ssh/sshd_config`` if you want the forwarded port to be accessible from
  machines other than the bastion itself.
- **sudo access**: Required on the lab workstation to write systemd unit files
  in ``/etc/systemd/system/`` and run ``systemctl``.

Alternative: No-sudo Setup via ~/.bashrc
-----------------------------------------

If you do not have sudo access (e.g., shared HPC nodes, university servers), you
can run autossh directly from your shell profile without systemd. Add to ``~/.bashrc``:

.. code-block:: bash

    # Persistent reverse tunnel without sudo — starts on every login
    # Checks if tunnel is already running before starting
    if ! pgrep -f "autossh.*-R 2222:localhost:22" > /dev/null 2>&1; then
        autossh -M 0 -f -N \
            -o "PubkeyAuthentication=yes" \
            -o "PasswordAuthentication=no" \
            -o "ServerAliveInterval=30" \
            -o "ServerAliveCountMax=3" \
            -i ~/.ssh/id_rsa \
            -R 2222:localhost:22 user@bastion.example.com
    fi

**Trade-offs vs. systemd approach:**

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - Aspect
     - systemd (with sudo)
     - ~/.bashrc (no sudo)
   * - Root access
     - Required
     - Not required
   * - Starts on
     - Boot (no login needed)
     - User login only
   * - Crash recovery
     - systemd restarts automatically
     - autossh reconnects SSH; no restart if autossh itself crashes
   * - Management
     - ``systemctl start/stop/status``
     - ``pgrep`` / ``pkill``

Alternative: Persistent Session (screen, tmux, nohup)
------------------------------------------------------

For long-running sessions where you want the tunnel to survive logout without
sudo or systemd:

.. code-block:: bash

    # Option 1: screen (detaches from terminal)
    screen -dmS tunnel autossh -M 0 -N \
        -o "ServerAliveInterval=30" -o "ServerAliveCountMax=3" \
        -i ~/.ssh/id_rsa -R 2222:localhost:22 user@bastion.example.com

    # Reattach:  screen -r tunnel
    # Kill:      screen -S tunnel -X quit

    # Option 2: tmux
    tmux new-session -d -s tunnel "autossh -M 0 -N \
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -i ~/.ssh/id_rsa -R 2222:localhost:22 user@bastion.example.com"

    # Reattach:  tmux attach -t tunnel
    # Kill:      tmux kill-session -t tunnel

    # Option 3: nohup (simplest)
    nohup autossh -M 0 -N \
        -o "ServerAliveInterval=30" -o "ServerAliveCountMax=3" \
        -i ~/.ssh/id_rsa -R 2222:localhost:22 user@bastion.example.com \
        > /dev/null 2>&1 &

    # Kill:      pkill -f "autossh.*-R 2222:localhost:22"

.. tip::

   To survive reboots without sudo, add the command to a cron ``@reboot`` job:

   .. code-block:: bash

       crontab -e
       # Add this line:
       @reboot autossh -M 0 -f -N -o "ServerAliveInterval=30" -o "ServerAliveCountMax=3" -i ~/.ssh/id_rsa -R 2222:localhost:22 user@bastion.example.com

.. list-table:: Comparison of all approaches
   :header-rows: 1
   :widths: 20 20 20 20 20

   * - Approach
     - Sudo
     - Survives logout
     - Survives reboot
     - Management
   * - systemd (default)
     - Yes
     - Yes
     - Yes
     - ``systemctl``
   * - ~/.bashrc
     - No
     - No (restarts on login)
     - No
     - ``pgrep`` / ``pkill``
   * - screen / tmux / nohup
     - No
     - Yes
     - No (unless cron @reboot)
     - ``screen -r`` / ``tmux attach``
   * - cron @reboot + nohup
     - No
     - Yes
     - Yes
     - ``crontab -e`` / ``pkill``

Alternative: Direct Shell Scripts
---------------------------------

If you have sudo access but prefer not to install Python, use the shell scripts directly:

.. code-block:: bash

    # Download the scripts (one-time)
    curl -o ~/.local/bin/setup-autossh-service.sh \
      https://raw.githubusercontent.com/ywatanabe1989/scitex-ssh/main/src/scitex_ssh/scripts/setup-autossh-service.sh
    curl -o ~/.local/bin/remove-autossh-service.sh \
      https://raw.githubusercontent.com/ywatanabe1989/scitex-ssh/main/src/scitex_ssh/scripts/remove-autossh-service.sh
    chmod +x ~/.local/bin/setup-autossh-service.sh ~/.local/bin/remove-autossh-service.sh

    # Usage (requires sudo for systemd operations)
    setup-autossh-service.sh -p 2222 -b user@bastion.example.com -s ~/.ssh/id_rsa
    remove-autossh-service.sh -p 2222
