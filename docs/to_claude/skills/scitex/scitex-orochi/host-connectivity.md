---
name: orochi-host-connectivity
description: Machine-specific network configuration for Orochi agents -- SCITEX_OROCHI_HOST values, port accessibility, and known connectivity issues.
---

# Host Connectivity

Each agent machine has different network characteristics that affect how it connects to the Orochi hub running on NAS (192.168.0.102:9559).

## SCITEX_OROCHI_HOST Per Machine

| Machine | Agent | SCITEX_OROCHI_HOST | Reason |
|---------|-------|-------------|--------|
| NAS (192.168.0.102) | nas-agent | `127.0.0.1` | Orochi server runs locally on NAS |
| ywata-note-win (WSL) | master-agent, ywata-note-win-agent | `192.168.0.102` | LAN access to NAS |
| MBA | mba-agent | `192.168.0.102` | LAN access to NAS |
| Spartan HPC | spartan-agent | `orochi.scitex.ai` | External network, no LAN access |

## Orochi Server Location

The Orochi hub runs on NAS as a Docker service. It listens on:
- WebSocket: port 9559
- Dashboard HTTP: port 8559
- Proxied via Cloudflare: `https://orochi.scitex.ai` (WebSocket + HTTP)

## Known Connectivity Issues

### Spartan HPC: WebSocket Port 9559 Blocked

Spartan's university firewall blocks outbound WebSocket connections to port 9559. The `wss://orochi.scitex.ai` proxy (Cloudflare) routes through port 443 which is allowed, but the `mcp_channel.ts` bridge connects directly to `SCITEX_OROCHI_HOST:OROCHI_PORT`, not through the HTTPS proxy.

**Status**: Spartan agent cannot use push mode until `mcp_channel.ts` supports WSS proxy connection. Polling mode works as a fallback (uses HTTP on standard ports).

**Workaround**: Use polling mode for spartan-agent:
```bash
python3 poll-agent.py spartan-agent --model opus --channels "#general,#research" --interval 15
```

### NAS After Hard Reboot

After NAS hard reboot, SSH key changes. Use `nas2.key` instead of `id_rsa`:
```bash
ssh -i ~/.ssh/nas2.key ywatanabe@192.168.0.102
```

Also verify Docker and Orochi service are running:
```bash
ssh nas 'docker ps | grep orochi'
```

### Claude Max Subscription Sharing

Claude Max subscription is shared across all hosts. Running 4+ Opus agents simultaneously consumes quota rapidly (72% in 3.5 days observed). Mitigations:
- Use Haiku for non-critical agents (monitoring, relay, status)
- Reserve Opus for agents that need deep reasoning (research, debugging)
- Monitor agent disconnections -- simultaneous drops usually mean quota exhaustion, not network issues
