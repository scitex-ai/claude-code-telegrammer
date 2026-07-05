---
description: |
  [TOPIC] scitex-ssh Installation
  [DETAILS] pip install scitex-ssh; needs system openssh-client + autossh; smoke verify with status.
tags: [scitex-ssh-installation]
---

# Installation

## Standard

```bash
pip install scitex-ssh
```

Pure-Python wrapper. The package shells out to system tools that must
be present on PATH:

| Tool         | Purpose                                          |
|--------------|--------------------------------------------------|
| `ssh`        | Remote exec, copy, attach primitives             |
| `scp`        | `copy_to` / `copy_from`                          |
| `autossh`    | Persistent reconnecting reverse tunnel           |
| `systemctl`  | Install/manage the per-port systemd unit         |

On Debian / Ubuntu:

```bash
sudo apt-get install -y openssh-client autossh
```

On macOS (autossh from Homebrew):

```bash
brew install autossh
```

## Umbrella

```bash
pip install scitex            # also exposes import scitex.tunnel
```

`pip install scitex-ssh` alone does NOT make `import scitex.tunnel`
work — install the umbrella for that form. See
`../../general/02_interface-python-api.md`.

## Verify

```bash
python -c "import scitex_ssh; print(scitex_ssh.__version__, scitex_ssh.AVAILABLE)"
scitex-ssh --help
scitex-ssh tunnel check-status
```

Expected: a version string, `AVAILABLE = True`, then a status table
(possibly empty) listing currently-installed tunnels.

## Notes

- `setup` requires `sudo` to install the systemd unit — it will prompt.
- A per-host SSH allowlist gate (`PolicyError`) blocks tunnels to
  hosts not listed in `~/.scitex/ssh/config.yaml`.
