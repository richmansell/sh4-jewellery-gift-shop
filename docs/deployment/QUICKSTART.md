# Quick Start Guide

## For Development/Testing (macOS or Linux)

### Prerequisites
- Python 3.7+ and Node.js 14+
- git
- Terminal access

### 1. Clone and Setup

```bash
cd /path/to/jewellery-box
python3 -m venv venv
source venv/bin/activate
pip install python-osc

cd management_node
npm install  # (optional; no external dependencies)
```

### 2. Start Management Node (Development Mode)

```bash
cd management_node
node server.js
# Or with auto-reload
node --watch server.js
```

### 3. Test with Simulated Plinth

In another terminal:

```bash
# Activate venv
source venv/bin/activate

# Run plinth in simulation mode
cd plinth
python3 plinth_controller.py

# This will start in simulation mode (no GPIO available)
```

### 4. Send Test OSC Messages

In a third terminal:

```bash
source venv/bin/activate
python3 tests/send_osc.py localhost 6000 /plinth/1/led 150
python3 tests/send_osc.py localhost 6000 /plinth/1/motor/open
```

### 5. Monitor Status

```bash
# In another terminal
python3 tests/monitor_status.py localhost 3000
```

---

## For Production (Raspberry Pi & Ubuntu)

### Management Node Setup (Ubuntu Server 22.04 LTS)

```bash
# 1. SSH into management node
ssh ubuntu@192.168.10.1

# 2. Clone repository
git clone <repo-url> /tmp/jbox
cd /tmp/jbox

# 3. Install service
sudo cp config/jewellery-box-mgmt.service /etc/systemd/system/
sudo mkdir -p /opt/jewellery-box/management_node
sudo cp -r management_node/* /opt/jewellery-box/management_node/

# 4. Start service
sudo systemctl daemon-reload
sudo systemctl enable jewellery-box-mgmt.service
sudo systemctl start jewellery-box-mgmt.service

# 5. Verify
sudo systemctl status jewellery-box-mgmt.service
curl localhost:3000/status | jq .
```

### Plinth Setup (Raspberry Pi OS)

```bash
# 1. SSH into plinth
ssh pi@192.168.10.11  # (or .12 for Plinth 2, .13 for Plinth 3)

# 2. Clone and install
git clone <repo-url> /tmp/jbox
cd /tmp/jbox

# 3. Install dependencies
pip3 install python-osc

# 4. Install service
sudo cp config/plinth@.service /etc/systemd/system/
sudo mkdir -p /opt/jewellery-box/plinth
sudo cp -r plinth/* /opt/jewellery-box/plinth/
sudo chown -R pi:pi /opt/jewellery-box

# 5. Start service (for plinth ID 1)
sudo systemctl daemon-reload
sudo systemctl enable plinth@1.service
sudo systemctl start plinth@1.service

# 6. Monitor logs
sudo journalctl -u plinth@1.service -f
```

### Repeat for Plinths 2 & 3

```bash
# SSH into plinth 2
ssh pi@192.168.1.12
# ... repeat steps with plinth ID = 2

# SSH into plinth 3
ssh pi@192.168.1.13
# ... repeat steps with plinth ID = 3
```

---

## Verification Checklist

- [ ] Management node running: `curl localhost:3000/status`
- [ ] Plinth 1 service: `sudo systemctl status plinth@1.service`
- [ ] Plinth 2 service: `sudo systemctl status plinth@2.service`
- [ ] Plinth 3 service: `sudo systemctl status plinth@3.service`
- [ ] Plinths connect to mgmt node within 30 seconds
- [ ] Send test OSC: `python3 tests/send_osc.py 192.168.1.100 5010 /plinth/1/button/press`
- [ ] Button presses trigger LED (visual feedback)
- [ ] Motor responds to `/motor/open` and `/motor/close` commands
- [ ] Q-SYS receives button events on port 5010

---

## Common Commands

### Check Status (All Systems)

```bash
# Management node
curl -s http://192.168.1.100:3000/status | jq .

# Plinth 1 logs
ssh pi@192.168.1.11 journalctl -u plinth@1.service -f

# Management node logs
ssh ubuntu@192.168.1.100 journalctl -u jewellery-box-mgmt.service -f
```

### Restart Services

```bash
# Management node
sudo systemctl restart jewellery-box-mgmt.service

# All plinths
for i in 1 2 3; do
  ssh pi@192.168.1.1$i sudo systemctl restart plinth@$i.service
done
```

### Send Commands

```bash
# Enable plinth 1
python3 tests/send_osc.py 192.168.1.100 5010 /plinth/1/enable

# Set LED brightness
python3 tests/send_osc.py 192.168.1.100 5010 /plinth/1/led 200

# Open motor
python3 tests/send_osc.py 192.168.1.100 5010 /plinth/1/motor/open

# Close motor
python3 tests/send_osc.py 192.168.1.100 5010 /plinth/1/motor/close
```

---

## Troubleshooting

### Plinth Not Connecting

1. Check IP address: `ip addr show` (on plinth)
2. Check network: `ping 192.168.1.100` (from plinth)
3. Check service: `systemctl status plinth@1.service`
4. Check logs: `journalctl -u plinth@1.service -n 50`

### Motor Not Moving

1. Check GPIO wiring (see ARCHITECTURE.md)
2. Check service logs for errors
3. Send manual test: `python3 tests/send_osc.py 192.168.1.11 6000 /plinth/1/motor/open`

### Button Not Responding

1. Test GPIO directly: `python3 -c "import RPi.GPIO as GPIO; GPIO.setup(17, GPIO.IN); print(GPIO.input(17))"`
2. Check debouncing logic in logs
3. Verify button is active-low (press = GPIO reads 1)

### High Latency

1. Check network: `ping -c 100 192.168.1.11 | grep avg`
2. Monitor CPU: `top` on management node
3. Check for package loss: `iperf3` test

---

**For detailed deployment instructions, see `DEPLOYMENT.md`**  
**For testing procedures, see `TESTING.md`**  
**For architecture details, see `ARCHITECTURE.md`**
