#!/usr/bin/env python3
"""
Send a single OSC message to a plinth or management node.

Usage:
  python3 send_osc.py <host> <port> <address> [arg1] [arg2] ...

Examples:
  python3 send_osc.py 192.168.1.11 6000 /plinth/1/motor/open
  python3 send_osc.py 192.168.1.11 6000 /plinth/1/led 150
  python3 send_osc.py 192.168.1.100 5010 /plinth/1/button/press 1
"""

import sys
import time
from pythonosc import udp_client

def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2])
    address = sys.argv[3]
    args = []
    
    # Parse arguments
    for arg in sys.argv[4:]:
        try:
            # Try int first
            args.append(int(arg))
        except ValueError:
            try:
                # Try float
                args.append(float(arg))
            except ValueError:
                # String
                args.append(arg)
    
    # Send OSC message
    try:
        client = udp_client.SimpleUDPClient(host, port)
        client.send_message(address, args)
        print(f"[OK] Sent to {host}:{port}")
        print(f"     Address: {address}")
        if args:
            print(f"     Args: {args}")
        time.sleep(0.1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
