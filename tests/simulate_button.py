#!/usr/bin/env python3
"""
Simulate button presses on a plinth for testing.

Usage:
  python3 simulate_button.py <host> <port> [OPTIONS]

Examples:
  python3 simulate_button.py 192.168.1.11 6000
  python3 simulate_button.py 192.168.1.11 6000 --press-duration 0.5 --interval 3 --count 10
"""

import sys
import time
import argparse
from pythonosc import udp_client

def simulate_button_press(client, address, press_duration, interval, count):
    """Simulate button presses."""
    for i in range(count):
        print(f"[{i+1}/{count}] Button press at {time.strftime('%H:%M:%S')}")
        
        # Send button press
        client.send_message(f"{address}/button/press", [1])
        time.sleep(press_duration)
        
        # Send button release
        client.send_message(f"{address}/button/release", [0])
        
        if i < count - 1:
            time.sleep(interval - press_duration)
    
    print(f"\nCompleted {count} button presses")

def main():
    parser = argparse.ArgumentParser(description="Simulate button presses on plinth")
    parser.add_argument('host', help='Plinth IP address')
    parser.add_argument('port', type=int, help='Plinth OSC RX port')
    parser.add_argument('--press-duration', type=float, default=0.2,
                       help='Button press duration in seconds (default: 0.2)')
    parser.add_argument('--interval', type=float, default=3,
                       help='Time between presses in seconds (default: 3)')
    parser.add_argument('--count', type=int, default=5,
                       help='Number of presses to simulate (default: 5)')
    parser.add_argument('--plinth-id', type=int, default=1,
                       help='Plinth ID (default: 1)')
    
    args = parser.parse_args()
    
    if args.press_duration > args.interval:
        print("[ERROR] press-duration cannot be greater than interval")
        sys.exit(1)
    
    try:
        client = udp_client.SimpleUDPClient(args.host, args.port)
        print(f"Connected to {args.host}:{args.port}")
        print(f"Plinth ID: {args.plinth_id}")
        print(f"Press duration: {args.press_duration}s")
        print(f"Interval: {args.interval}s")
        print(f"Count: {args.count}")
        print("-" * 40)
        time.sleep(1)
        
        address = f"/plinth/{args.plinth_id}"
        simulate_button_press(client, address, args.press_duration, args.interval, args.count)
    
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
