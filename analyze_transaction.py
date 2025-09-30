#!/usr/bin/env python3
"""
Jito Transaction Analyzer

This script fetches and analyzes a specific Solana transaction
to extract arbitrage patterns and instruction details.
"""

import json
import requests
import base64
import argparse
import os
from typing import Dict, Any, List, Optional

# Transaction ID to analyze
TRANSACTION_ID = "8e7de0169a8307de3a64ed5b7d265730727248479a72bc73e9bc03f02de13ba4"

# Load RPC endpoint from env or use default
RPC_ENDPOINT = os.getenv("RPC_ENDPOINT", "https://api.mainnet-beta.solana.com")

# Known program IDs
PROGRAM_IDS = {
    "JitoEBftV8P1Bw26ZmUj5byZiot1WJ1Jb6ybGzDUzWM": "Jito MEV",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter v4",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpools",
    "So11111111111111111111111111111111111111112": "SOL Token",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC Token",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT Token",
}

def fetch_transaction(tx_id: str) -> Dict[str, Any]:
    """Fetch transaction details from Solana RPC"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            tx_id,
            {"encoding": "json", "maxSupportedTransactionVersion": 0}
        ]
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    response = requests.post(RPC_ENDPOINT, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch transaction: {response.status_code} {response.text}")
    
    result = response.json()
    if "error" in result:
        raise Exception(f"RPC error: {result['error']}")
    
    return result["result"]

def decode_instruction_data(encoded_data: str) -> bytes:
    """Decode base64 instruction data"""
    try:
        return base64.b64decode(encoded_data)
    except:
        return b''

def analyze_transaction(tx_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze transaction data for arbitrage patterns"""
    if not tx_data:
        return {"error": "No transaction data"}
    
    # Extract basic transaction info
    signature = tx_data.get("transaction", {}).get("signatures", ["Unknown"])[0]
    slot = tx_data.get("slot", 0)
    block_time = tx_data.get("blockTime", 0)
    success = tx_data.get("meta", {}).get("err") is None
    
    # Extract program calls from logs
    logs = tx_data.get("meta", {}).get("logMessages", [])
    program_calls = []
    
    for log in logs:
        if "Program " in log:
            parts = log.split("Program ")
            if len(parts) > 1:
                program_id_part = parts[1].split()[0]
                program_name = PROGRAM_IDS.get(program_id_part, program_id_part[:12] + "...")
                program_calls.append(program_name)
    
    # Extract token information from account keys
    accounts = tx_data.get("transaction", {}).get("message", {}).get("accountKeys", [])
    tokens_involved = []
    
    for account in accounts:
        if account in PROGRAM_IDS and "Token" in PROGRAM_IDS[account]:
            tokens_involved.append(PROGRAM_IDS[account])
    
    # Analyze pre and post balances
    pre_balances = tx_data.get("meta", {}).get("preBalances", [])
    post_balances = tx_data.get("meta", {}).get("postBalances", [])
    
    balance_changes = []
    if pre_balances and post_balances and len(pre_balances) == len(post_balances):
        for i in range(min(5, len(pre_balances))):  # Analyze first few accounts
            change = (post_balances[i] - pre_balances[i]) / 1_000_000_000  # Convert lamports to SOL
            if change != 0:
                balance_changes.append({
                    "account_index": i,
                    "pre_balance": pre_balances[i] / 1_000_000_000,
                    "post_balance": post_balances[i] / 1_000_000_000,
                    "change": change
                })
    
    # Calculate profit
    profit = None
    if balance_changes and balance_changes[0]["change"] != 0:
        profit = balance_changes[0]["change"]
    
    # Analyze instructions
    instructions = tx_data.get("transaction", {}).get("message", {}).get("instructions", [])
    instruction_details = []
    
    for idx, instr in enumerate(instructions):
        program_idx = instr.get("programIdIndex")
        program_id = accounts[program_idx] if program_idx is not None and program_idx < len(accounts) else None
        program_name = PROGRAM_IDS.get(program_id, program_id[:12] + "...") if program_id else "Unknown"
        
        # Decode instruction data
        data = instr.get("data")
        data_hex = None
        
        if data:
            data_bytes = decode_instruction_data(data)
            # First 8 bytes often contain instruction discriminator
            discriminator = data_bytes[:8].hex() if len(data_bytes) >= 8 else None
            data_hex = data_bytes.hex() if data_bytes else None
        
        # Get account addresses for this instruction
        accounts_used = []
        for acc_idx in instr.get("accounts", []):
            if acc_idx < len(accounts):
                acc_address = accounts[acc_idx]
                acc_name = PROGRAM_IDS.get(acc_address, acc_address[:12] + "...")
                accounts_used.append(acc_name)
        
        instruction_details.append({
            "index": idx,
            "program": program_name,
            "discriminator": discriminator,
            "accounts_used": accounts_used[:5]  # Limit to first 5 accounts
        })
    
    # Count swap instructions
    swap_count = sum(1 for log in logs if "Instruction: Swap" in log)
    
    # Detect pattern
    pattern = "Unknown"
    if swap_count >= 3:
        pattern = "Triangular Arbitrage"
    elif swap_count == 2:
        pattern = "Simple Cross-Pool Arbitrage"
    elif "Jupiter" in str(program_calls):
        pattern = "Jupiter Aggregation Arbitrage"
    elif "Orca Whirlpools" in program_calls:
        pattern = "Orca Whirlpools Arbitrage"
    
    # Prepare result
    result = {
        "transaction_id": signature,
        "slot": slot,
        "timestamp": block_time,
        "success": success,
        "pattern": pattern,
        "swap_count": swap_count,
        "profit": profit,
        "programs_involved": program_calls[:10],  # Limit to first 10
        "tokens_involved": tokens_involved,
        "balance_changes": balance_changes,
        "instruction_details": instruction_details
    }
    
    return result

def main():
    parser = argparse.ArgumentParser(description="Analyze a Solana transaction for arbitrage patterns")
    parser.add_argument("--tx-id", default=TRANSACTION_ID, help="Transaction ID to analyze")
    parser.add_argument("--output", default="data/tx_analysis.json", help="Output file path")
    args = parser.parse_args()
    
    try:
        print(f"Fetching transaction {args.tx_id}...")
        tx_data = fetch_transaction(args.tx_id)
        
        print("Analyzing transaction...")
        analysis = analyze_transaction(tx_data)
        
        # Output to terminal
        print("\n===== Transaction Analysis =====")
        print(f"Transaction ID: {analysis['transaction_id']}")
        print(f"Success: {analysis['success']}")
        print(f"Pattern: {analysis['pattern']}")
        print(f"Swap Count: {analysis['swap_count']}")
        
        if analysis.get('profit') is not None:
            print(f"Profit: {analysis['profit']:.6f} SOL")
        
        print("\nPrograms Involved:")
        for program in analysis.get('programs_involved', []):
            print(f"  - {program}")
        
        print("\nTokens Involved:")
        for token in analysis.get('tokens_involved', []):
            print(f"  - {token}")
        
        print("\nBalance Changes:")
        for change in analysis.get('balance_changes', []):
            print(f"  Account {change['account_index']}: {change['change']:.6f} SOL")
        
        print("\nInstructions:")
        for instr in analysis.get('instruction_details', []):
            print(f"  {instr['index']}: {instr['program']} (Discriminator: {instr['discriminator']})")
        
        # Save to file
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, 'w') as f:
            json.dump(analysis, f, indent=2)
        
        print(f"\nDetailed analysis saved to {args.output}")
        
        # Save raw transaction data
        raw_output = f"{os.path.splitext(args.output)[0]}_raw.json"
        with open(raw_output, 'w') as f:
            json.dump(tx_data, f, indent=2)
        
        print(f"Raw transaction data saved to {raw_output}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()