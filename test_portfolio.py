#!/usr/bin/env python3
"""Quick test script for portfolio token monitoring."""

import logging
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)

from meme_scanner import monitor_portfolio_tokens, job_portfolio_tokens
from config import PORTFOLIO_TOKENS

print("=" * 60)
print("Portfolio Token Monitoring Test")
print("=" * 60)

print("\n📋 Configured tokens:")
for token in PORTFOLIO_TOKENS:
    print(f"  • {token['symbol']} ({token['name']}) on {token['chain']}")
    print(f"    Address: {token['address'][:20]}...")

print("\n🔄 Running portfolio check...")
signals = monitor_portfolio_tokens(PORTFOLIO_TOKENS)

print(f"\n📊 Results: {len(signals)} tokens monitored")
print("-" * 60)

for signal in signals:
    print(f"\n[{signal.level}] {signal.name}")
    print(signal.message)
    print("-" * 40)

print("\n✅ Test complete!")
