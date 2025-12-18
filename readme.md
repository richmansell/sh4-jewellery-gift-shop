# Jewellery Box Interactive – Development Codebase

This repository contains the complete software implementation for the ENBD Pearl Museum jewellery box interactive system, including plinth controllers, management node server, testing utilities, and deployment documentation.

## Quick Navigation

- **[Quick Start Guide](docs/deployment/QUICKSTART.md)** – Get running in 10 minutes
- **[Deployment Guide](docs/deployment/DEPLOYMENT.md)** – Full production setup
- **[Architecture & Design](docs/deployment/ARCHITECTURE.md)** – System design and protocols
- **[Testing & Validation](docs/deployment/TESTING.md)** – Comprehensive test suite

## System Overview
- Three interactive plinths connect to a management node; the management node connects to the Q-SYS Core in the server room.
- All comms are Ethernet-based. OSC over UDP is the primary protocol; TCP/IP is available for Q-SYS if needed.
- Cable runs: three 5 m Cat6 from plinths to management node; one 40 m Cat6a S/FTP from management node to Q-SYS Core.
- Each plinth provides button input, maintenance switch input (glass on/off), LED control, and stepper motor control.

## Critical Correction (Management Node)
- The management node must provide **4 native Ethernet ports** (3 plinths + 1 Q-SYS). Original 2-port hardware (ASUS PN51, Intel NUC, Helix) is insufficient.
- **Option 1 – Recommended:** Qotom Q355G4-S02 (fanless, 4x Intel i210 Gigabit LAN, Intel i5-5200U, 8 GB RAM, 128 GB SSD, 36 W, 187×140×42 mm, fits 1U vented shelf). Total ~$470 with shelf.
- Alternative to Option 1: Protectli Vault VP4650 (i5-8250U, 4 LAN, ~$650).
- **Option 2:** Intel NUC 11 Pro (NUC11TNHi5, 2 LAN) + managed switch (TRENDnet TI-PG541i recommended; Netgear GS305E budget). Total ~$725 (industrial) or ~$585 (budget); ~110 W combined. Use when more CPU or switch diagnostics are required.
- Rack depth requirements: Option 1 needs ~200 mm including cable clearance; Option 2 needs ~160 mm. Both use 1U vented shelf.

## Plinth Hardware (per plinth)
- Controller: Raspberry Pi 4 Model B (4 GB) with industrial microSD (32 GB, high-endurance) or USB boot equivalent.
- Drivers/IO: TMC2209 or TB6600 stepper driver; MOSFET (e.g., IRLZ44N) for LED PWM.
- GPIO mapping:  
  - GPIO17 input – button (debounced)  
  - GPIO27 input – maintenance switch  
  - GPIO22 PWM – LED brightness/pulse  
  - GPIO23/24/25 outputs – stepper STEP/DIR/ENABLE  
  - Ground shared; 5 V only for low-current LED if needed.
- Enclosure: DIN-rail mountable; use screw terminals/JST connectors for motor/button wiring.
- Power: stable 5 V/3 A supply (official PSU or industrial DIN-rail supply).

## Network & Protocol
- Plinth ↔ Management Node: OSC/UDP, ports 5000–5005 (per plinth).
- Management Node ↔ Q-SYS Core: OSC/UDP on 5010 (RX) and 5011 (TX); TCP 1700–1710 optional.
- Example OSC addresses:  
  - From plinth: `/plinth/[1-3]/button/press`, `/plinth/[1-3]/maintenance` (0/1).  
  - To plinth: `/plinth/[1-3]/motor/open|close`, `/plinth/[1-3]/led` (0–255), `/plinth/[1-3]/disable|enable`.  
  - To Q-SYS: forwarded button/maintenance events.  
  - From Q-SYS: motor open/close, `/system/reset`.
- Interlock logic: when one button is active, other plinth buttons/LEDs disable until the sequence completes.

## Software Responsibilities
- **Plinth (Raspberry Pi OS Lite):** Python 3 with `python-osc`, `RPi.GPIO`, `pigpio`. Read inputs, send OSC, drive stepper via STEP/DIR/ENABLE, PWM LEDs, handle maintenance mode (hold button 4s to open/close, stay open in maintenance). Run under `systemd` with watchdog/auto-restart; log events.
- **Management Node (Ubuntu Server recommended):** Configure 4 NICs with static IPs. Listen for plinth OSC, enforce interlocks, log events, forward to Q-SYS, accept Q-SYS commands, and route to plinths. Provide reconnect logic after network or power events. Run as `systemd` service; consider VPN/SSH for remote diagnostics.
- **Q-SYS Core:** Configure Named Controls and Lua/OSC script to receive button/maintenance events, trigger audio/video, send motor commands back, and re-enable plinths after content. Use periodic UDP poll/handler (see Appendix D in the PDF).

## Installation & Timeline (summary)
- Phases (~4–6 weeks total): procurement (2–3 wks) → plinth assembly (2 days) → cabling (3 days) → management node setup (1 day) → Q-SYS integration (2 days) → system testing (2 days) → commissioning (1 day).
- Rack layout: reserve 1U; ensure depth per option; rear ports: 4×RJ45 + power (12 V DC for Qotom; separate supplies for NUC + switch).
- Cabling: Cat6 for plinths, shielded Cat6a for 40 m run to server room; label all four Ethernet lines.

## Testing Checklist (condensed)
- Button press/release OSC correct; maintenance switch state correct.
- Interlock works: active plinth disables other buttons/LEDs until sequence ends.
- LED pulse on active plinth; LEDs off when disabled.
- Motor open/close commands execute and recover after power/network loss.
- Q-SYS receives/returns OSC; system auto-reconnects after Q-SYS reboot.
- Maintenance mode: hold button 4 s to open/close; stays open while in maintenance.
- Power cycle: all services auto-start; network recovers after cable reseat.

## Risk & Mitigations
- SD card wear → use industrial/high-endurance media; keep imaged spares.
- Network cable damage → shielded runs, strain relief, labeled spares.
- Motor/driver failure → quality drivers (TMC2209), keep spares.
- Software crash → `systemd` restart + watchdog; logging/remote monitoring.
- Noise constraints → prefer fanless Qotom (Option 1); TMC2209 for quiet steppers.

## Procurement Guidance (Management Node)
- Order Qotom Q355G4-S02 from Qotom distributors/Amazon/AliExpress; verify: i5-5200U, 4×Gigabit LAN, 8 GB RAM, 128 GB SSD, includes 12 V adapter, 4 LAN ports present.
- Expected price: $400–$470 with shipping; lead time 3–14 days depending on source. Mount on Middle Atlantic U1 vented shelf.
- If choosing Option 2, budget and plan for managed switch power and configuration (VLAN/port-mirroring as needed).

## Next Steps
- Confirm management node option (Qotom recommended) and reserve 1U rack space with required depth.
- Lock network addressing and OSC port assignments; document static IP plan.
- Begin software implementation/testing using the OSC message schema above.
- Prepare `systemd` units, logging, and remote access for plinths and management node.
- Coordinate with Q-SYS integrator to wire OSC/Lua logic to AV cues.
