#!/usr/bin/env python3
"""Quick test for meme scanner - test full scan."""
import logging
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

print("Testing updated meme scanner...", flush=True)

from meme_scanner import scan_new_tokens, MIN_LIQUIDITY_USD, MAX_NEW_TOKEN_AGE_MINUTES

print(f"Config: MIN_LIQUIDITY=${MIN_LIQUIDITY_USD}, MAX_AGE={MAX_NEW_TOKEN_AGE_MINUTES}min", flush=True)

print("\n=== Full Scan (Solana + Base) ===", flush=True)
signals = scan_new_tokens(["solana", "base"])
print(f"Total signals: {len(signals)}", flush=True)

for s in signals[:10]:
    print(f"\n[{s.level}] {s.name}", flush=True)
    # Print first few lines of message
    lines = s.message.split('\n')[:6]
    for line in lines:
        print(f"  {line}", flush=True)

print("\n\nTest complete.", flush=True)
