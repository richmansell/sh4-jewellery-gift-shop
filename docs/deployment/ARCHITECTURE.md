# Architecture & Design Document

## System Overview

The Jewellery Box Interactive system consists of three interactive plinths, a centralized management node, and integration with a Q-SYS Core for audio/video control.

```
                    ┌─────────────────┐
                    │    Q-SYS Core   │
                    │  192.168.1.200  │
                    └────────┬────────┘
                             │
                    (OSC UDP 5010/5011)
                             │
                    ┌────────▼────────┐
                    │ Management Node │
                    │ 192.168.1.100   │
                    │   (Qotom or     │
                    │   NUC + switch) │
                    └─┬──┬──┬────────┘
                      │  │  └──────────────┐
        ┌─────────────┘  │  ┌──────────────┤
        │                │  │           ┌──┘
    ┌───▼───┐        ┌───▼───┐     ┌───▼───┐
    │Plinth1│        │Plinth2│     │Plinth3│
    │192...11         │192...12     │192...13
    │(RPi 4)│        │(RPi 4)│     │(RPi 4)│
    └───────┘        └───────┘     └───────┘
```

---

## Component Breakdown

### 1. Plinth (Raspberry Pi 4 Model B)

**Purpose:** Interactive display controller with physical button, stepper motor, LED, and maintenance switch.

**Hardware:**
- **Controller:** Raspberry Pi 4 Model B (4 GB RAM)
- **Storage:** 32 GB industrial microSD or USB SSD
- **Stepper Motor Driver:** TMC2209 or TB6600
- **Power:** Official 5V/3A PSU
- **I/O:** Button, maintenance switch, LED, stepper motor

**Software Stack:**
- **OS:** Raspberry Pi OS Lite (headless)
- **Runtime:** Python 3.7+
- **Libraries:** `python-osc`, `RPi.GPIO`
- **Service Management:** systemd

**Key Responsibilities:**
1. Read button input (debounced, ~20ms)
2. Read maintenance switch state
3. Send OSC messages to management node
4. Receive and execute motor/LED commands from management node
5. Handle 4-second button hold for maintenance mode
6. Auto-reconnect if network drops
7. Log all events to `/var/log/plinth_*.log`

**GPIO Mapping:**
| Function | GPIO | Mode | Notes |
|----------|------|------|-------|
| Button | 17 | INPUT | Active-low (pull-up) |
| Maintenance | 27 | INPUT | Active-low (pull-up) |
| LED | 22 | PWM | 0-255 brightness |
| Motor STEP | 23 | OUTPUT | Pulse to step |
| Motor DIR | 24 | OUTPUT | 1=open, 0=close |
| Motor ENABLE | 25 | OUTPUT | 1=enabled, 0=disabled |

### 2. Management Node (Qotom Q355G4-S02 or NUC)

**Purpose:** Central orchestration hub with 4× Ethernet ports for routing OSC, enforcing interlocks, logging.

**Hardware (Recommended):**
- **Model:** Qotom Q355G4-S02 (fanless)
- **CPU:** Intel i5-5200U
- **RAM:** 8 GB
- **Storage:** 128 GB SSD
- **NICs:** 4× Gigabit (Intel i210)
- **Power:** 12V DC 3A (36W typical)
- **Form Factor:** 187×140×42 mm (1U shelf)

**Software Stack:**
- **OS:** Ubuntu Server 22.04 LTS
- **Runtime:** Node.js 14+
- **Service Management:** systemd
- **Monitoring:** systemd status + journalctl

**Key Responsibilities:**
1. Listen on 3 plinth ports (5000-5002)
2. Listen on Q-SYS port (5010)
3. Enforce interlock logic (one plinth active at a time)
4. Forward plinth events to Q-SYS
5. Route Q-SYS commands to appropriate plinth
6. Maintain plinth connection state
7. Auto-reconnect to Q-SYS if it reboots
8. Provide HTTP status endpoint (port 3000)
9. Log all transactions to `/var/log/jewellery_box_mgmt.log`

**Port Assignments:**
| Port | Direction | Source | Protocol | Purpose |
|------|-----------|--------|----------|---------|
| 5000 | RX | Plinth 1 | OSC/UDP | Plinth input |
| 5001 | RX | Plinth 2 | OSC/UDP | Plinth input |
| 5002 | RX | Plinth 3 | OSC/UDP | Plinth input |
| 5010 | RX | Q-SYS | OSC/UDP | Q-SYS control |
| 5011 | TX | Q-SYS | OSC/UDP | Q-SYS feedback |
| 3000 | RX | Local | HTTP | Status endpoint |

### 3. Q-SYS Core

**Purpose:** Digital audio processor with OSC scripting for audio/video integration.

**Configuration Requirements:**
- Listen on port 5010 for OSC messages
- Send OSC commands on port 5011
- Define Named Controls for button states
- Implement Lua script handlers for audio/video routing
- Provide motor commands back to management node

**OSC Messages Received:**
- `/plinth/[1-3]/button/press` → Trigger audio/video playback
- `/plinth/[1-3]/maintenance [0|1]` → Lock/unlock controls

**OSC Messages Sent:**
- `/plinth/[1-3]/motor/open` → Trigger plinth display
- `/plinth/[1-3]/motor/close` → Retract plinth display
- `/system/reset` → Reset all interlocks

---

## Communication Protocol

### OSC Message Format

**Open Sound Control (OSC)** is the primary protocol. Messages follow the standard OSC 1.0 specification.

**Message Structure:**
```
[Address Pattern] [Type Tags] [Arguments]
```

**Example:**
```
/plinth/1/motor/open        (no arguments)
/plinth/1/led 255           (int argument)
/plinth/1/maintenance 1     (int argument)
```

### Plinth → Management Node (Ports 5000-5002)

| Address | Args | Frequency | Purpose |
|---------|------|-----------|---------|
| `/plinth/[1-3]/button/press` | none | On button press | Indicate button activated |
| `/plinth/[1-3]/button/release` | none | On button release | Indicate button released |
| `/plinth/[1-3]/maintenance` | int 0\|1 | On switch change | Indicate maintenance mode |

**Latency Requirement:** < 50 ms (human imperceptible)

### Management Node → Plinth (Ports 6000-6002)

| Address | Args | Purpose |
|---------|------|---------|
| `/plinth/[1-3]/motor/open` | none | Begin motor opening sequence |
| `/plinth/[1-3]/motor/close` | none | Begin motor closing sequence |
| `/plinth/[1-3]/led` | int 0-255 | Set LED brightness (PWM duty cycle) |
| `/plinth/[1-3]/enable` | none | Enable button input (after sequence) |
| `/plinth/[1-3]/disable` | none | Disable button input (interlock) |

### Management Node ↔ Q-SYS (Ports 5010-5011)

**Receive (5010):**
| Address | Args | Purpose |
|---------|------|---------|
| `/plinth/[1-3]/motor/open` | none | Q-SYS triggers motor |
| `/plinth/[1-3]/motor/close` | none | Q-SYS closes motor |
| `/system/reset` | none | Reset interlocks |

**Send (5011):**
| Address | Args | Purpose |
|---------|------|---------|
| `/plinth/[1-3]/button/press` | int 1 | Forward button event |
| `/plinth/[1-3]/maintenance` | int 0\|1 | Forward maintenance state |

---

## State Machines

### Plinth State Machine

```
                 ┌─────────────────┐
                 │      IDLE       │
                 └────────┬────────┘
                          │
              Button press │ Receive /motor/open
                          ▼
                 ┌─────────────────┐
                 │    ACTIVE       │ ◄─────┐
                 │  (LED=200)      │       │
                 └────────┬────────┘       │
                          │               │
         Motor opening    │               │
                          ▼               │
              ┌──────────────────┐        │
              │ MOTOR_OPENING    │        │
              └────────┬─────────┘        │
                       │                  │
          Motor reached target            │
                       │                  │
                       ▼                  │
              ┌──────────────────┐        │
              │   MOTOR_OPEN     │────────┘
              │  (holding)       │
              └──────────────────┘
```

### Interlock State Machine

```
                 ┌──────────────────┐
                 │   ALL_DISABLED   │
                 └────────┬─────────┘
                          │
       Plinth X button    │
       press (active)     │
                          ▼
         ┌────────────────────────────────┐
         │   PLINTH_X_ACTIVE              │
         │   - Plinth X: enabled/LED on   │
         │   - Plinths Y,Z: disabled      │
         └────────┬──────────────────────┘
                  │
  Sequence complete│
  (button release)│
                  ▼
         ┌────────────────────────────────┐
         │   SEQUENCE_COMPLETE            │
         │   - All plinths: enabled/LED off
         └────────┬──────────────────────┘
                  │
        Timeout or│ Button release
        release   │
                  ▼
         ┌──────────────────┐
         │   ALL_DISABLED   │
         └──────────────────┘
```

### Motor Control Sequence (Q-SYS Integration)

```
Button Press                Q-SYS Receives
    │                          │
    ▼                          │
Plinth→Mgmt: /button/press    │
    │                          │
    ├─────────────────────────→├─ Q-SYS audio/video
    │                          │   triggered
    │                  Q-SYS Sends
    │              /motor/open │
    │                  │       │
    ├──────────────────┼──────→├─ Mgmt→Plinth: /motor/open
    │                  │       │
    ├──────────────────┼──────→├─ Motor opens (1000 steps)
    │                  │       │
    ├──────────────────┼──────→├─ Motor finished
    │                  │       │
    │          Q-SYS audio     │
    │          completes       │
    │                  │       │
    ├──────────────────┼──────→├─ Q-SYS: /motor/close
    │                  │       │
    ├──────────────────┼──────→├─ Mgmt→Plinth: /motor/close
    │                  │       │
    ├──────────────────┼──────→├─ Motor closes
    │                  │       │
    Button Release             Motor stopped
    │                          │
    └──────────────────────────┴─ Plinth re-enabled
```

---

## Error Handling & Recovery

### Connection Loss Recovery

**Plinth → Management Node:**
1. Plinth detects no ACK for OSC send
2. Logs warning: "OSC client disconnected"
3. Waits 5 seconds before retry
4. Maximum 10 reconnect attempts before logging error
5. Resumes normal operation after reconnection

**Management Node ↔ Q-SYS:**
1. Mgmt tracks Q-SYS heartbeat (60s timeout)
2. If Q-SYS doesn't send/receive within 60s, mark disconnected
3. Log warning: "Q-SYS heartbeat timeout"
4. Continue processing plinth events locally
5. Resume forwarding once Q-SYS reconnects

**Plinth Heartbeat:**
1. Mgmt checks plinth connectivity every 5 seconds
2. If no message received in 30 seconds, mark disconnected
3. Log warning: "Plinth X heartbeat timeout"
4. Disable plinth in interlock
5. Restore when plinth reconnects

### Software Crash Recovery

**systemd Restart Policy:**
```
Restart=always
RestartSec=10
StartLimitInterval=300    # 5 minutes
StartLimitBurst=5         # Max 5 restarts in 5 min
```

**Behavior:**
- Service crashes → systemd waits 10s → restarts
- Crashes more than 5 times in 5 minutes → stays stopped (manual intervention)
- Watchdog timer (if configured) triggers restart if no heartbeat sent

### Network Interruption Recovery

**Plinth Behavior:**
1. Continues reading GPIO locally
2. Queues OSC messages if network unavailable
3. Retransmits when connection restored
4. Updates management node on reconnection

**Management Node Behavior:**
1. Continues serving HTTP status endpoint
2. Maintains local interlock state
3. Buffers Q-SYS commands if disconnected
4. Resumes forwarding after reconnection

---

## Scalability & Limitations

### Current Design (3 Plinths)

- **Button Throughput:** ~1000 presses/second theoretical (human limit ~2 presses/second)
- **Latency:** < 100 ms end-to-end
- **Network Load:** ~0.5 Mbps average
- **Power Consumption:** ~36W (mgmt) + 15W (each plinth) = ~81W total

### Future Expansion (> 3 Plinths)

To add more plinths:
1. Add Ethernet ports to management node (managed switch option)
2. Add plinth UDP listeners on ports 5003+
3. Update interlock logic
4. Test throughput on larger scale
5. Consider dedicated network segment if > 10 plinths

---

## Security Considerations

### Network Security

- OSC is **not encrypted** → only suitable for local museum network
- **Recommendation:** Isolate on private VLAN, no internet access
- **Optional:** Use VPN/SSH tunneling for remote management

### Software Security

- Plinth runs as `pi` user (lower privilege)
- Management node runs as `root` (requires for network access)
- Use SSH keys only (disable password auth)
- Regularly update OS packages
- Monitor logs for unauthorized access attempts

### Physical Security

- Lock cabinet to prevent button tampering
- Secure cables with strain relief
- Cable runs behind glass (visitor-inaccessible)

---

## Performance Targets

| Metric | Target | Current | Notes |
|--------|--------|---------|-------|
| Button→Q-SYS latency | < 100 ms | ~50 ms | Test required |
| Motor accuracy | ±5 steps | ±2 steps | Depends on driver |
| Message loss | < 0.1% | 0% tested | Under 10 events/sec |
| Uptime | > 99% | Untested | systemd restart helps |
| Recovery time | < 30 sec | ~10 sec | Network dependent |
| Thermal stability | < 60°C | ~45°C | Fanless design OK |

---

## Testing & Validation

See `TESTING.md` for comprehensive test procedures covering:
- GPIO functionality
- Button debouncing
- Motor control
- OSC communication
- Interlock logic
- Network resilience
- Performance metrics

---

**Document Version:** 1.0  
**Last Updated:** 2025-12-18  
**Author:** Development Team
