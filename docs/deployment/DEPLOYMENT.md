# Jewellery Box Interactive - Deployment Guide

## Overview

This guide covers the installation and deployment of the Jewellery Box Interactive system across three plinths, a management node, and integration with Q-SYS.

## Hardware Procurement (Summary)

### Management Node
- **Recommended:** Qotom Q355G4-S02 (fanless, 4×Gigabit LAN, i5-5200U, 8GB RAM, 128GB SSD)
- **Alternative:** Intel NUC 11 Pro + TRENDnet managed switch
- **Rack:** 1U vented shelf, ~200mm depth with cables

### Plinth (×3)
- Raspberry Pi 4 Model B (4 GB)
- Industrial microSD (32 GB, high-endurance)
- NEMA 17 stepper + TMC2209 driver
- 5V/3A power supply
- Button, maintenance switch, LED, enclosure

---

## Network Setup

### IP Addressing

| Device | IP Address | Port(s) |
|--------|-----------|---------|
| Plinth 1 | 192.168.10.11 | 6000 (OSC rx) |
| Plinth 2 | 192.168.10.12 | 6001 (OSC rx) |
| Plinth 3 | 192.168.10.13 | 6002 (OSC rx) |
| Management Node | 192.168.10.1 | 5000-5002 (plinth rx), 5010 (Q-SYS rx), 5011 (Q-SYS tx) |
| Q-SYS Core | 192.168.10.50 | 5010-5011 (OSC) |

**Note:** This is a dedicated control network (192.168.10.0/24) separate from facility network. Gateway is the management node itself (192.168.10.1).

### Static IP Configuration (Ubuntu Server - Management Node)

Edit `/etc/netplan/01-netcfg.yaml`:

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: no
      addresses:
        - 192.168.10.1/24
      gateway4: 192.168.10.1
      nameservers:
        addresses: [1.1.1.1, 8.8.8.8]

    eth1:
      dhcp4: no
      addresses:
        - 192.168.10.2/24

    eth2:
      dhcp4: no
      addresses:
        - 192.168.10.3/24

    eth3:
      dhcp4: no
      addresses:
        - 192.168.10.4/24
```

Apply changes:
```bash
sudo netplan apply
```

### Static IP Configuration (Raspberry Pi OS - Plinth)

Edit `/etc/dhcpcd.conf`:

```
interface eth0
static ip_address=192.168.10.1X/24
static routers=192.168.10.1
static domain_name_servers=1.1.1.1 8.8.8.8
```

Then restart networking:
```bash
sudo systemctl restart dhcpcd
```

**Note:** Replace `1X` with plinth number (11, 12, 13)

---

## Software Installation

### Management Node (Ubuntu Server 22.04 LTS)

#### 1. System Setup

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential git nodejs npm curl wget

# Verify Node.js version (should be >= 14)
node --version
npm --version
```

#### 2. Deploy Management Node Software

```bash
# Create installation directory
sudo mkdir -p /opt/jewellery-box/management_node
cd /opt/jewellery-box/management_node

# Copy or clone the management node code
sudo git clone <repo-url>/management_node .
# OR copy manually from your development machine

# Install dependencies (no npm packages needed; built-in modules only)
# (Optional) npm install

# Set ownership
sudo chown -R root:root /opt/jewellery-box
```

#### 3. Install systemd Service

```bash
sudo cp config/jewellery-box-mgmt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable jewellery-box-mgmt.service
sudo systemctl start jewellery-box-mgmt.service

# Check status
sudo systemctl status jewellery-box-mgmt.service
sudo journalctl -u jewellery-box-mgmt.service -f
```

#### 4. Verify HTTP Status Endpoint

```bash
curl http://localhost:3000/status | jq .
```

---

### Plinth (Raspberry Pi OS Lite)

#### 1. System Setup

```bash
# Connect via SSH
ssh pi@192.168.10.1X  # Replace 1X with 11, 12, or 13 for plinths 1, 2, 3

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3 python3-pip python3-dev \
  git build-essential libssl-dev libffi-dev \
  libgpiozero python3-rpi.gpio

# Install Python OSC library
pip3 install python-osc

# Verify Python version (should be >= 3.7)
python3 --version
```

#### 2. Deploy Plinth Software

```bash
# Create installation directory
sudo mkdir -p /opt/jewellery-box/plinth
cd /opt/jewellery-box/plinth

# Copy plinth code from development machine
scp -r plinth/* pi@192.168.10.1X:/opt/jewellery-box/plinth/  # Replace 1X with plinth IP

# Set ownership and permissions
sudo chown -R pi:pi /opt/jewellery-box
sudo chmod +x /opt/jewellery-box/plinth/plinth_controller.py

# Test run (should show simulation mode if GPIO not available)
python3 /opt/jewellery-box/plinth/plinth_controller.py
# Press Ctrl+C to stop
```

#### 3. Create systemd Service

```bash
# Link the service template (or copy it)
sudo cp config/plinth@.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable for all three plinths (if needed)
# sudo systemctl enable plinth@1.service
# sudo systemctl enable plinth@2.service
# sudo systemctl enable plinth@3.service

# Or enable just this plinth
sudo systemctl enable plinth@1.service

# Start the service
sudo systemctl start plinth@1.service

# Check status
sudo systemctl status plinth@1.service
sudo journalctl -u plinth@1.service -f
```

#### 4. Configure Log Rotation

Create `/etc/logrotate.d/jewellery-box`:

```
/var/log/plinth_*.log {
    daily
    rotate 7
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
}
```

---

## GPIO Wiring Reference (Plinth)

| Function | GPIO | BCM | Usage |
|----------|------|-----|-------|
| Button | GPIO17 | 17 | INPUT (active-low) |
| Maintenance Switch | GPIO27 | 27 | INPUT (active-low) |
| LED (PWM) | GPIO22 | 22 | OUTPUT PWM (0-255) |
| Motor STEP | GPIO23 | 23 | OUTPUT pulse |
| Motor DIR | GPIO24 | 24 | OUTPUT direction |
| Motor ENABLE | GPIO25 | 25 | OUTPUT enable |
| GND | PIN 6, 9, 14, 20, 25, 30, 34, 39 | GND | Ground |
| 5V | PIN 2, 4 | 5V | Power (low-current only) |
| 3V3 | PIN 1, 17 | 3V3 | Power (logic only) |

---

## OSC Protocol Reference

### From Plinth to Management Node

| Address | Args | Example |
|---------|------|---------|
| `/plinth/[1-3]/button/press` | (none) | `/plinth/1/button/press` |
| `/plinth/[1-3]/button/release` | (none) | `/plinth/1/button/release` |
| `/plinth/[1-3]/maintenance` | int (0 or 1) | `/plinth/1/maintenance 1` |

### From Management Node to Plinth

| Address | Args | Example |
|---------|------|---------|
| `/plinth/[1-3]/motor/open` | (none) | `/plinth/1/motor/open` |
| `/plinth/[1-3]/motor/close` | (none) | `/plinth/1/motor/close` |
| `/plinth/[1-3]/led` | int (0-255) | `/plinth/1/led 200` |
| `/plinth/[1-3]/enable` | (none) | `/plinth/1/enable` |
| `/plinth/[1-3]/disable` | (none) | `/plinth/1/disable` |

### From Management Node to Q-SYS (UDP 5010)

| Address | Args |
|---------|------|
| `/plinth/[1-3]/button/press` | int 1 |
| `/plinth/[1-3]/maintenance` | int (0 or 1) |

### From Q-SYS to Management Node (UDP 5011)

| Address | Args |
|---------|------|
| `/plinth/[1-3]/motor/open` | (none) |
| `/plinth/[1-3]/motor/close` | (none) |
| `/system/reset` | (none) |

---

## Testing & Validation

### 1. Network Connectivity

```bash
# From management node, test plinth connectivity
ping 192.168.1.11
ping 192.168.1.12
ping 192.168.1.13

# Check ports (optional, requires nmap)
nmap -p 6000-6002 192.168.1.1{1,2,3}
```

### 2. Management Node Status

```bash
# Check HTTP endpoint
curl http://192.168.1.100:3000/status | jq .

# Check logs
journalctl -u jewellery-box-mgmt.service -n 50
```

### 3. Plinth Connectivity

```bash
# SSH into a plinth
ssh pi@192.168.1.11

# Check service status
sudo systemctl status plinth@1.service

# Check logs
sudo journalctl -u plinth@1.service -n 50

# Test in foreground (if service is stopped)
python3 /opt/jewellery-box/plinth/plinth_controller.py
```

### 4. Button & Motor Testing

Use the test scripts in `/tests/` directory. See `TESTING.md` for details.

---

## Monitoring & Diagnostics

### Remote SSH Access

```bash
# From your development machine
ssh ubuntu@192.168.1.100  # Management node
ssh pi@192.168.1.11       # Plinth 1
```

### Log Aggregation (Optional)

Consider setting up centralized logging:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Graylog
- Syslog server

Configure syslog forwarding in `/etc/rsyslog.d/` if needed.

### Health Checks

Management node runs automatic health checks every 5 seconds:
- Plinth heartbeat timeout: 30 seconds
- Q-SYS heartbeat timeout: 60 seconds
- Alerts logged to `/var/log/jewellery_box_mgmt.log`

---

## Troubleshooting

### Plinth Not Connecting

1. **Check IP configuration:**
   ```bash
   ip addr show  # On plinth
   ```

2. **Test OSC communication:**
   ```bash
   # From management node, send test message
   python3 tests/send_osc.py 192.168.1.11 6000 /plinth/1/led 100
   ```

3. **Check logs:**
   ```bash
   sudo journalctl -u plinth@1.service -f
   ```

### GPIO Errors

- Ensure script runs as `pi` user (for permissions)
- Check GPIO pins are not already in use: `gpio readall`
- Test GPIO directly: `python3 -c "import RPi.GPIO as GPIO; GPIO.setup(17, GPIO.IN)"`

### Network Latency

- Check cable quality (use shielded Cat6a for long runs)
- Monitor packet loss: `ping -c 100 192.168.1.11 | grep loss`
- Q-SYS integration may require OSC/UDP tuning

---

## Maintenance

### Regular Tasks

- **Daily:** Monitor logs for errors
- **Weekly:** Check plinth connectivity via HTTP endpoint
- **Monthly:** Review and rotate logs
- **Quarterly:** Update system packages (carefully)

### Backup

```bash
# Backup configuration
sudo tar -czf jewellery-box-backup-$(date +%Y%m%d).tar.gz \
  /opt/jewellery-box \
  /etc/systemd/system/plinth@.service \
  /etc/systemd/system/jewellery-box-mgmt.service

# Copy to safe location
scp jewellery-box-backup-*.tar.gz user@backup-server:/backups/
```

### Software Updates

```bash
# On management node
cd /opt/jewellery-box/management_node
git pull origin main
sudo systemctl restart jewellery-box-mgmt.service

# On plinth
cd /opt/jewellery-box/plinth
git pull origin main
sudo systemctl restart plinth@1.service
```

---

## References

- [OSC Protocol Spec](http://opensoundcontrol.org/)
- [Raspberry Pi GPIO Documentation](https://www.raspberrypi.org/documentation/usage/gpio/)
- [python-osc Library](https://github.com/attwad/python-osc)
- [systemd Service Unit Documentation](https://www.freedesktop.org/software/systemd/man/systemd.service.html)

---

**Document Version:** 1.0  
**Last Updated:** 2025-12-18  
**Author:** Development Team
