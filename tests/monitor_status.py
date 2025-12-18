#!/usr/bin/env python3
"""
Monitor management node status via HTTP endpoint.

Usage:
  python3 monitor_status.py <host> <port> [--interval SECONDS]

Examples:
  python3 monitor_status.py 192.168.1.100 3000
  python3 monitor_status.py 192.168.1.100 3000 --interval 5
"""

import sys
import time
import json
import argparse
from urllib.request import urlopen
from urllib.error import URLError

def get_status(host, port):
    """Fetch status from management node."""
    url = f"http://{host}:{port}/status"
    try:
        with urlopen(url, timeout=5) as response:
            return json.loads(response.read().decode())
    except URLError as e:
        return None
    except json.JSONDecodeError:
        return None

def print_status(status):
    """Pretty-print status."""
    if not status:
        print("[ERROR] Failed to fetch status")
        return
    
    print("\n" + "="*60)
    print(f"Timestamp: {status['timestamp']}")
    print("="*60)
    
    # Plinths
    print("\nPlinths:")
    for p in status['plinths']:
        conn_str = "✓ CONNECTED" if p['connected'] else "✗ DISCONNECTED"
        state_str = f"motor={p['motorState']}, led={p['ledBrightness']}"
        enabled_str = "ENABLED" if p['enabled'] else "DISABLED"
        
        print(f"  Plinth {p['id']}: {conn_str} | {state_str} | {enabled_str}")
        if p['buttonPressed']:
            print(f"            → Button PRESSED")
        if p['maintenanceActive']:
            print(f"            → Maintenance ACTIVE")
    
    # Q-SYS
    q = status['qsys']
    q_conn = "✓ CONNECTED" if q['connected'] else "✗ DISCONNECTED"
    print(f"\nQ-SYS: {q_conn} ({q['ip']}:{q['port']})")
    
    # Interlock
    il = status['interlock']
    if il['activePlinth']:
        print(f"\nInterlock: Plinth {il['activePlinth']} ACTIVE")
    else:
        print(f"\nInterlock: IDLE")
    if il['sequenceActive']:
        print(f"           Sequence in progress")

def main():
    parser = argparse.ArgumentParser(description="Monitor jewellery box system status")
    parser.add_argument('host', help='Management node IP address')
    parser.add_argument('port', type=int, help='HTTP port (usually 3000)')
    parser.add_argument('--interval', type=int, default=2, 
                       help='Polling interval in seconds (default: 2)')
    
    args = parser.parse_args()
    
    print(f"Connecting to {args.host}:{args.port} (polling every {args.interval}s)")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            status = get_status(args.host, args.port)
            print_status(status)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n\nStopped.")

if __name__ == '__main__':
    main()
