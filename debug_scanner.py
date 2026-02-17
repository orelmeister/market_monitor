#!/usr/bin/env python3
"""Debug the meme scanner step by step."""
import logging
import sys

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger()

print("=== Step 1: Fresh import ===", flush=True)

# Force fresh import by clearing cache
if 'meme_scanner' in sys.modules:
    del sys.modules['meme_scanner']

from meme_scanner import (
    _seen_tokens, 
    get_new_pairs_geckoterminal,
    get_new_pairs,
    parse_pair_to_token,
    scan_new_tokens,
    MIN_LIQUIDITY_USD,
)

print(f"Seen tokens at start: {len(_seen_tokens)}", flush=True)
print(f"MIN_LIQUIDITY_USD: ${MIN_LIQUIDITY_USD}", flush=True)

print("\n=== Step 2: Raw GeckoTerminal pairs ===", flush=True)
pairs = get_new_pairs_geckoterminal("solana", 20)
print(f"GeckoTerminal returned: {len(pairs)} pairs", flush=True)

print("\n=== Step 3: Parse first 5 pairs ===", flush=True)
for i, pair in enumerate(pairs[:5]):
    bt = pair.get("baseToken", {})
    liq = pair.get("liquidity", {}).get("usd", "N/A")
    created = pair.get("pairCreatedAt")
    print(f"  {i+1}. {bt.get('symbol')} ({bt.get('name', 'unknown')[:20]})", flush=True)
    print(f"      Address: {bt.get('address', 'NA')[:30]}...", flush=True)
    print(f"      Liquidity: ${liq}", flush=True)
    print(f"      Created: {created}", flush=True)
    
    # Try to parse it
    token = parse_pair_to_token(pair)
    if token:
        print(f"      -> Parsed OK: {token.symbol}, liq=${token.liquidity_usd}", flush=True)
    else:
        print(f"      -> FAILED TO PARSE", flush=True)

print("\n=== Step 4: Full scan ===", flush=True)
# Clear seen tokens for fresh scan
_seen_tokens.clear()
signals = scan_new_tokens(["solana"])
print(f"Signals generated: {len(signals)}", flush=True)

for sig in signals[:5]:
    print(f"\n[{sig.level}] {sig.name}", flush=True)

print("\n=== Done ===", flush=True)
