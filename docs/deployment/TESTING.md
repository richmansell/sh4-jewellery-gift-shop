# Testing & Validation Guide

## Overview

This guide provides comprehensive testing procedures to verify the Jewellery Box Interactive system functionality before deployment.

---

## Pre-Integration Testing

### 1. Plinth Unit Testing

#### 1.1 GPIO Read/Write

**Objective:** Verify GPIO pins read/write correctly.

**Test Script:** `tests/test_gpio.py`

```bash
cd /opt/jewellery-box/plinth
python3 ../tests/test_gpio.py
```

**Expected Results:**
- Button GPIO (17) reads as 0 (inactive)
- Maintenance GPIO (27) reads as 0 (inactive)
- LED GPIO (22) PWM set successfully
- Motor pins (23, 24, 25) respond to control signals

#### 1.2 Button Debouncing

**Objective:** Verify button debouncing filters noise.

**Procedure:**
1. Rapidly press and release button 20 times
2. Check logs for clean press/release events
3. Verify no duplicate events during single press

**Expected Results:**
```
Button pressed
Button released (held 0.15s)
Button pressed
Button released (held 0.12s)
...
```

#### 1.3 Motor Control

**Objective:** Verify stepper motor can open and close.

**Procedure:**
1. Send OSC command: `/plinth/1/motor/open`
2. Watch motor step count increase
3. Send OSC command: `/plinth/1/motor/close`
4. Watch motor step count decrease to zero

**Expected Results:**
- 1000 steps to open, 1000 steps to close
- No skipped steps
- Smooth acceleration possible with parameter tuning

#### 1.4 LED PWM

**Objective:** Verify LED brightness control.

**Procedure:**
1. Send `/plinth/1/led 0` → LED off
2. Send `/plinth/1/led 128` → LED 50% brightness
3. Send `/plinth/1/led 255` → LED full brightness

**Expected Results:**
- LED brightness changes smoothly
- No flickering
- Range 0-255 properly mapped to duty cycle

#### 1.5 Maintenance Mode

**Objective:** Verify 4-second hold triggers maintenance mode.

**Procedure:**
1. Hold button for exactly 3 seconds → no action
2. Release button
3. Hold button for exactly 5 seconds → motor opens/closes
4. Verify logging shows maintenance activation

**Expected Results:**
```
Button pressed
Button released (held 3.00s)
Button pressed
Maintenance mode activated (button held 5.00s)
Motor opening
```

---

### 2. Management Node Unit Testing

#### 2.1 OSC Server Listening

**Objective:** Verify management node listens on correct ports.

**Procedure:**
```bash
# From management node
ss -ulnp | grep -E "5000|5001|5002|5010"
```

**Expected Results:**
```
State Recv-Q Send-Q Local Address:Port Peer Address:Port
UNCONN 0      0          0.0.0.0:5000        0.0.0.0:*
UNCONN 0      0          0.0.0.0:5001        0.0.0.0:*
UNCONN 0      0          0.0.0.0:5002        0.0.0.0:*
UNCONN 0      0          0.0.0.0:5010        0.0.0.0:*
```

#### 2.2 Interlock Logic

**Objective:** Verify only one plinth can be active.

**Procedure:**
1. Send button press from plinth 1: `/plinth/1/button/press`
2. Immediately send button press from plinth 2: `/plinth/2/button/press`
3. Verify plinth 2 button is disabled

**Expected Results (in logs):**
```
Received from plinth 1: /plinth/1/button/press
Plinth 1 activated
Sent to plinth 2: /plinth/2/disable

Received from plinth 2: /plinth/2/button/press
Plinth 2 button pressed but plinth 1 is active
```

#### 2.3 HTTP Status Endpoint

**Objective:** Verify status JSON is accessible.

**Procedure:**
```bash
curl http://localhost:3000/status | jq .
```

**Expected Results:**
```json
{
  "timestamp": "2025-12-18T14:30:45.123Z",
  "plinths": [
    {
      "id": 1,
      "connected": false,
      "buttonPressed": false,
      "maintenanceActive": false,
      "motorState": "idle",
      "ledBrightness": 0,
      "enabled": true
    },
    ...
  ],
  "qsys": {
    "connected": false,
    "ip": "192.168.1.200",
    "port": 5011
  },
  "interlock": {
    "activePlinth": null,
    "sequenceActive": false
  }
}
```

#### 2.4 Q-SYS Integration

**Objective:** Verify management node can communicate with Q-SYS.

**Procedure:**
1. Configure Q-SYS to receive on port 5010
2. Send test OSC from management node: `/plinth/1/button/press`
3. Verify Q-SYS receives the message

**Expected Results:**
- Q-SYS Named Control updates with button state
- No packet loss in verbose logging mode

---

## Integration Testing

### 3. End-to-End Button Press Sequence

**Objective:** Verify complete flow from button press to Q-SYS.

**Procedure:**
1. Ensure all three plinths are connected
2. Ensure management node is running
3. Ensure Q-SYS is listening on port 5010
4. Press button on plinth 1
5. Monitor logs on all three systems

**Expected Results:**

**Plinth 1 logs:**
```
Button pressed
Sent /plinth/1/button/press to management node
```

**Management Node logs:**
```
Received from plinth 1: /plinth/1/button/press
Plinth 1 activated
Sent to plinth 1: /plinth/1/led 200
Sent to plinth 2: /plinth/2/disable
Sent to plinth 3: /plinth/3/disable
Forwarded button press from plinth 1 to Q-SYS
```

**Q-SYS logs:**
```
Received OSC: /plinth/1/button/press
Audio/Video playback triggered
```

### 4. Motor Control Flow

**Objective:** Verify motor control from Q-SYS to plinth.

**Procedure:**
1. Plinth 1 button is pressed (plinth is "active")
2. Q-SYS sends `/plinth/1/motor/open`
3. Management node receives and forwards to plinth 1
4. Monitor motor position on plinth

**Expected Results:**

**Management Node logs:**
```
Received from Q-SYS: /plinth/1/motor/open
Sent to plinth 1: /plinth/1/motor/open
```

**Plinth 1 logs:**
```
Received motor open command
Motor opening
[Motor stepping...]
Motor opened
```

### 5. Interlock Under Load

**Objective:** Verify interlock prevents simultaneous activation.

**Procedure:**
1. Press button on plinth 1 (triggers opening)
2. While plinth 1 is opening, rapidly press buttons 2 and 3
3. Release button 1
4. Verify buttons 2 and 3 are now enabled

**Expected Results:**

**Management Node logs:**
```
Plinth 1 activated
Sent to plinth 2: /plinth/2/disable
Sent to plinth 3: /plinth/3/disable

Received from plinth 2: /plinth/2/button/press
Plinth 2 button pressed but plinth 1 is active

[After plinth 1 completes]
Plinth 1 sequence complete
Sent to plinth 2: /plinth/2/enable
Sent to plinth 3: /plinth/3/enable
```

### 6. Network Resilience

**Objective:** Verify system recovers after network interruptions.

**Procedure A – Plinth Disconnect:**
1. Unplug plinth 1 network cable
2. Monitor management node status every 5 seconds
3. Plug plinth 1 back in
4. Verify automatic reconnection within 30 seconds

**Expected Results:**

**Management Node logs:**
```
Plinth 1 heartbeat timeout
Plinth 1 disconnected

[After reconnect]
Plinth 1 reconnected
Plinth 1 connected
```

**Procedure B – Management Node Restart:**
1. Stop management node service
2. Plinths should show connection timeout
3. Start management node
4. Plinths should reconnect

### 7. LED Pulse Feedback

**Objective:** Verify LED provides visual feedback during active sequence.

**Procedure:**
1. Press button on plinth 1
2. Observe LED brightness changes:
   - Inactive: 0 (off)
   - Active during button press: 200 (bright)
   - After release: 0 (off)

**Expected Results:**
- LED pulses smoothly
- No flickering or abrupt changes
- Brightness responds to management node commands

---

## Performance Testing

### 8. Latency Measurement

**Objective:** Measure end-to-end latency from button press to Q-SYS reception.

**Procedure:**
1. Add timestamps to logging at each step
2. Press button on plinth 1
3. Calculate delay:
   - t1: Button physical press (manual marker)
   - t2: Plinth sends OSC
   - t3: Management node receives
   - t4: Management node sends to Q-SYS
   - t5: Q-SYS receives

**Acceptable Results:**
- Total latency < 100 ms (human imperceptible)
- Individual component latencies:
  - Debouncing: ~20 ms
  - OSC transmission: ~5 ms
  - Processing: ~10 ms

### 9. Throughput Testing

**Objective:** Verify system handles rapid button presses.

**Procedure:**
1. Simulate 10 rapid button presses per second for 60 seconds
2. Monitor for packet loss
3. Verify no dropped messages

**Acceptable Results:**
- 0% message loss
- No buffer overflows
- No OSC parsing errors in logs

### 10. Motor Accuracy

**Objective:** Verify motor reaches target positions reliably.

**Procedure:**
1. Send 100 open/close cycles
2. Verify final position is closed (0 steps)
3. Check for position drift

**Acceptable Results:**
- Final position within ±5 steps of target
- No accumulated drift over 100 cycles
- Consistent step timing

---

## Stress Testing

### 11. Extended Runtime

**Objective:** Verify system stability over extended operation.

**Procedure:**
1. Run system for 24 hours
2. Simulate button press every 10 minutes
3. Monitor memory usage and logs

**Acceptable Results:**
- No memory leaks (constant process size)
- No log file growth exceeding capacity
- All services remain running
- No automatic restarts triggered

### 12. Environmental Conditions

**Objective:** Verify system operates in museum environment.

**Test Conditions:**
- Temperature: 18–24°C (normal museum climate)
- Humidity: 40–60% (typical)
- Dust: Museum air (regular dusting)
- Vibration: Visitor movement (minimal)

**Monitoring:**
- Check GPIO readings under vibration
- Verify network stability with interference
- Monitor thermal performance

---

## Checklist

### Pre-Deployment Testing Checklist

- [ ] Plinth GPIO tests pass (all 3 plinths)
- [ ] Button debouncing functional
- [ ] Motor opens/closes correctly
- [ ] LED brightness 0-255 responsive
- [ ] Maintenance mode (4-sec hold) works
- [ ] Management node listening on all ports
- [ ] Interlock prevents dual activation
- [ ] HTTP status endpoint accessible
- [ ] Button press sequence reaches Q-SYS
- [ ] Motor control from Q-SYS works
- [ ] Network disconnect/reconnect graceful
- [ ] LED provides visual feedback
- [ ] Latency < 100 ms
- [ ] No message loss under load
- [ ] Motor accuracy ±5 steps
- [ ] 24-hour stability test passes
- [ ] Environmental conditions tested

### Go/No-Go Decision Criteria

**Go:** All checklist items pass + zero critical bugs  
**No-Go:** Any safety issue, > 5% message loss, latency > 500 ms, memory leak  

---

## Test Utilities

### send_osc.py

Send a single OSC message to a plinth:

```bash
python3 tests/send_osc.py 192.168.1.11 6000 /plinth/1/motor/open
python3 tests/send_osc.py 192.168.1.11 6000 /plinth/1/led 150
```

### monitor_status.py

Poll management node status every N seconds:

```bash
python3 tests/monitor_status.py 192.168.1.100 3000 --interval 5
```

### simulate_button.py

Simulate button presses for testing:

```bash
python3 tests/simulate_button.py 192.168.1.11 6000 --press-duration 0.2 --interval 5
```

---

## References

- **OSC Debugging:** Use Wireshark to capture/analyze OSC packets
  ```bash
  sudo tcpdump -i any -n udp port 5000 -w plinth_traffic.pcap
  ```

- **GPIO Testing:** Use `gpio` command or `gpiod` utilities
  ```bash
  # Read GPIO state
  gpioget gpiochip0 17
  # Set GPIO
  gpioset gpiochip0 22=1
  ```

- **Systemd Debugging:**
  ```bash
  journalctl -u plinth@1.service -n 100
  systemctl status plinth@1.service
  ```

---

**Document Version:** 1.0  
**Last Updated:** 2025-12-18  
**Author:** Development Team
