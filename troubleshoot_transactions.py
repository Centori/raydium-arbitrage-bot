#!/usr/bin/env python3
"""
Solana Transaction Troubleshooter

This utility helps diagnose and fix common transaction issues when using Jupiter API
for swaps and other operations on Solana.
"""

import json
import base64
import asyncio
import requests
import logging
import argparse
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Union, Any, Tuple
import backoff

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Common error codes and their explanations
ERROR_CODES = {
    "0x0": "Success",
    "0x1": "Insufficient funds",
    "0x1771": "Slippage tolerance exceeded (final amount < minimum amount)",
    "0xBC": "Invalid account data",
    "0x7D3": "Computational budget exceeded",
}

# Jupiter API and RPC endpoints
JUPITER_API_URL = "https://quote-api.jup.ag/v6"
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"

@dataclass
class SwapConfig:
    """Configuration for a swap transaction"""
    input_mint: str
    output_mint: str
    amount: float
    slippage_bps: int = 50  # Default 0.5%
    user_public_key: str = None
    rpc_url: str = DEFAULT_RPC_URL
    priority_fee: str = "auto"
    compute_limit: bool = True
    wrap_unwrap_sol: bool = True

@dataclass
class TransactionResult:
    """Result of a transaction execution attempt"""
    success: bool
    signature: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    compute_units_consumed: Optional[int] = None
    compute_units_limit: Optional[int] = None
    blockhash: Optional[str] = None
    fee_lamports: Optional[int] = None
    priority_fee_lamports: Optional[int] = None

class JupiterTransactionTroubleshooter:
    """Utility to troubleshoot and repair common Jupiter transaction issues"""
    
    def __init__(self, rpc_url: str = DEFAULT_RPC_URL):
        self.rpc_url = rpc_url
        self.logger = logging.getLogger("JupiterTroubleshooter")
    
    async def get_quote(self, config: SwapConfig) -> Dict:
        """Get a swap quote from Jupiter API with retry logic"""
        
        @backoff.on_exception(backoff.expo, 
                            (requests.exceptions.RequestException,
                             json.JSONDecodeError),
                            max_tries=3)
        def _get_quote():
            url = f"{JUPITER_API_URL}/quote"
            params = {
                "inputMint": config.input_mint,
                "outputMint": config.output_mint,
                "amount": str(int(config.amount)),
                "slippageBps": config.slippage_bps
            }
            
            self.logger.info(f"Getting quote for {config.amount} {config.input_mint} → {config.output_mint}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
            
        try:
            return _get_quote()
        except Exception as e:
            self.logger.error(f"Error getting Jupiter quote: {str(e)}")
            raise
    
    async def get_swap_transaction(self, config: SwapConfig, quote_response: Dict) -> Dict:
        """Get a swap transaction from Jupiter API with retry logic"""
        
        @backoff.on_exception(backoff.expo, 
                             (requests.exceptions.RequestException,
                              json.JSONDecodeError),
                             max_tries=3)
        def _get_swap_tx():
            url = f"{JUPITER_API_URL}/swap"
            
            body = {
                "quoteResponse": quote_response,
                "userPublicKey": config.user_public_key,
                "dynamicComputeUnitLimit": config.compute_limit,
                "prioritizationFeeLamports": config.priority_fee,
                "wrapAndUnwrapSol": config.wrap_unwrap_sol
            }
            
            self.logger.info("Getting swap transaction")
            response = requests.post(
                url, 
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            response.raise_for_status()
            return response.json()
            
        try:
            return _get_swap_tx()
        except Exception as e:
            self.logger.error(f"Error getting swap transaction: {str(e)}")
            raise
            
    async def simulate_transaction(self, tx_data: Dict) -> TransactionResult:
        """Simulate the transaction using RPC to detect potential issues"""
        try:
            encoded_tx = tx_data.get('swapTransaction')
            if not encoded_tx:
                return TransactionResult(
                    success=False, 
                    error_message="No transaction data found"
                )
                
            # Prepare JSON-RPC request
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "simulateTransaction",
                "params": [
                    encoded_tx, 
                    {
                        "encoding": "base64",
                        "commitment": "processed",
                        "replaceRecentBlockhash": True,
                        "sigVerify": False,
                        "accounts": {
                            "encoding": "base64",
                            "addresses": []
                        }
                    }
                ]
            }
            
            self.logger.info("Simulating transaction")
            response = requests.post(
                self.rpc_url, 
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if "result" in result and "value" in result["result"]:
                value = result["result"]["value"]
                
                if "err" in value and value["err"]:
                    # Parse error information
                    error_info = value["err"]
                    error_code = None
                    error_msg = str(error_info)
                    
                    # Try to extract error code
                    if isinstance(error_info, dict) and "InstructionError" in error_info:
                        if isinstance(error_info["InstructionError"], list) and len(error_info["InstructionError"]) > 1:
                            error_data = error_info["InstructionError"][1]
                            if isinstance(error_data, dict) and "Custom" in error_data:
                                error_code = f"0x{error_data['Custom']:X}"
                    
                    return TransactionResult(
                        success=False,
                        error_code=error_code,
                        error_message=error_msg
                    )
                else:
                    # Extract compute unit information
                    compute_units = None
                    compute_limit = None
                    
                    if "accounts" in value and "logs" in value:
                        for log in value["logs"]:
                            if "consumed" in log and "compute units" in log:
                                # Parse compute units from log
                                parts = log.split()
                                for i, part in enumerate(parts):
                                    if part == "consumed":
                                        compute_units = int(parts[i-1])
                                    if part == "limit" and i > 0:
                                        compute_limit = int(parts[i+1])
                    
                    return TransactionResult(
                        success=True,
                        compute_units_consumed=compute_units,
                        compute_units_limit=compute_limit,
                        blockhash=value.get("unitsConsumed")
                    )
            
            return TransactionResult(
                success=False,
                error_message="Simulation failed with unknown error"
            )
            
        except Exception as e:
            self.logger.error(f"Error simulating transaction: {str(e)}")
            return TransactionResult(
                success=False,
                error_message=f"Simulation request failed: {str(e)}"
            )
    
    def get_error_explanation(self, error_code: str) -> str:
        """Get human-readable explanation for an error code"""
        if not error_code:
            return "Unknown error (no error code provided)"
            
        normalized_code = error_code.lower()
        if normalized_code in ERROR_CODES:
            return ERROR_CODES[normalized_code]
            
        return f"Unknown error code: {error_code}"
    
    async def suggest_fixes(self, result: TransactionResult, config: SwapConfig) -> List[str]:
        """Suggest fixes based on the transaction result and configuration"""
        suggestions = []
        
        # If the transaction was successful in simulation, provide general tips
        if result.success:
            if result.compute_units_consumed:
                compute_efficiency = result.compute_units_consumed / (result.compute_units_limit or 1400000) * 100
                suggestions.append(f"Transaction used {compute_efficiency:.1f}% of compute budget")
                
                if compute_efficiency > 80:
                    suggestions.append("⚠️ High compute usage - consider using dynamicComputeUnitLimit: true")
            
            suggestions.append("✅ Transaction simulation successful")
            suggestions.append("✓ Use skipPreflight: true when submitting to avoid blockhash errors")
            suggestions.append("✓ Use maxRetries: 3 and preflightCommitment: 'processed' for better success rate")
            return suggestions
        
        # For errors, provide specific suggestions
        if result.error_code:
            if result.error_code == "0x1771":  # Slippage exceeded
                current_slippage = config.slippage_bps / 100
                suggestions.append(f"❌ Error: Slippage tolerance exceeded (current: {current_slippage}%)")
                suggestions.append(f"✓ Increase slippage tolerance to {min(current_slippage * 2, 5):.2f}% or higher")
                suggestions.append("✓ Consider using a larger input amount to mitigate price impact")
            
            elif result.error_code == "0x7D3":  # Computational budget exceeded
                suggestions.append("❌ Error: Computational budget exceeded")
                suggestions.append("✓ Use dynamicComputeUnitLimit: true to adjust compute units")
                suggestions.append("✓ Try a simpler route with fewer hops")
            
            elif result.error_code == "0x1":  # Insufficient funds
                suggestions.append("❌ Error: Insufficient funds")
                suggestions.append("✓ Check your wallet balance")
                suggestions.append("✓ Set wrapAndUnwrapSol: true if swapping SOL")
                suggestions.append("✓ Reduce the swap amount to account for transaction fees")
                
            else:
                explanation = self.get_error_explanation(result.error_code)
                suggestions.append(f"❌ Error code: {result.error_code} - {explanation}")
        
        # Generic error fallback
        if not result.error_code and result.error_message:
            if "blockhash" in str(result.error_message).lower():
                suggestions.append("❌ Error: Blockhash issues detected")
                suggestions.append("✓ Use replaceRecentBlockhash: true when submitting")
                suggestions.append("✓ Set skipPreflight: true to avoid client-side blockhash validation")
                suggestions.append("✓ Use commitment: 'processed' for transaction submission")
            else:
                suggestions.append(f"❌ Error: {result.error_message}")
                suggestions.append("✓ Consider increasing prioritizationFeeLamports during congestion")
                
        return suggestions
    
    async def troubleshoot_swap(self, config: SwapConfig) -> Tuple[TransactionResult, List[str]]:
        """Full troubleshooting process for a swap transaction"""
        try:
            # Step 1: Get quote
            quote = await self.get_quote(config)
            
            # Step 2: Get swap transaction
            swap_tx = await self.get_swap_transaction(config, quote)
            
            # Step 3: Simulate transaction
            result = await self.simulate_transaction(swap_tx)
            
            # Step 4: Suggest fixes
            suggestions = await self.suggest_fixes(result, config)
            
            return result, suggestions
            
        except Exception as e:
            self.logger.error(f"Error during troubleshooting process: {str(e)}")
            return TransactionResult(
                success=False,
                error_message=f"Troubleshooting failed: {str(e)}"
            ), [
                f"❌ Error: {str(e)}",
                "✓ Check network connectivity",
                "✓ Verify API endpoints are accessible",
                "✓ Ensure wallet address is valid"
            ]

async def main():
    """Main function to run the troubleshooter"""
    parser = argparse.ArgumentParser(description="Troubleshoot Jupiter swap transactions")
    
    parser.add_argument("--input-mint", required=True, 
                        help="Input token mint address")
    parser.add_argument("--output-mint", required=True, 
                        help="Output token mint address")
    parser.add_argument("--amount", required=True, type=float,
                        help="Amount to swap (in smallest units)")
    parser.add_argument("--wallet", required=True,
                        help="Wallet public key")
    parser.add_argument("--slippage", type=int, default=50,
                        help="Slippage tolerance in basis points (default: 50 = 0.5%)")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL,
                        help=f"Solana RPC URL (default: {DEFAULT_RPC_URL})")
    parser.add_argument("--priority-fee", default="auto",
                        help="Priority fee (default: auto)")
    parser.add_argument("--no-dynamic-cu", action="store_false", dest="dynamic_cu",
                        help="Disable dynamic compute unit limit")
    parser.add_argument("--no-wrap-sol", action="store_false", dest="wrap_sol",
                        help="Disable automatic SOL wrapping/unwrapping")
                        
    args = parser.parse_args()
    
    # Configure swap
    config = SwapConfig(
        input_mint=args.input_mint,
        output_mint=args.output_mint,
        amount=args.amount,
        slippage_bps=args.slippage,
        user_public_key=args.wallet,
        rpc_url=args.rpc_url,
        priority_fee=args.priority_fee,
        compute_limit=args.dynamic_cu,
        wrap_unwrap_sol=args.wrap_sol
    )
    
    # Initialize troubleshooter
    troubleshooter = JupiterTransactionTroubleshooter(rpc_url=args.rpc_url)
    
    print(f"🔍 Troubleshooting swap from {args.input_mint} to {args.output_mint}")
    print(f"Amount: {args.amount}, Slippage: {args.slippage/100}%, Wallet: {args.wallet}")
    
    # Run troubleshooting
    result, suggestions = await troubleshooter.troubleshoot_swap(config)
    
    # Print result
    print("\n=== Troubleshooting Results ===")
    if result.success:
        print("✅ Transaction simulation successful")
    else:
        print(f"❌ Transaction simulation failed")
        if result.error_code:
            print(f"   Error code: {result.error_code}")
        if result.error_message:
            print(f"   Error message: {result.error_message}")
            
    # Print compute units information
    if result.compute_units_consumed:
        print(f"   Compute units used: {result.compute_units_consumed}")
    if result.compute_units_limit:
        print(f"   Compute units limit: {result.compute_units_limit}")
        
    # Print suggestions
    print("\n=== Suggestions ===")
    for i, suggestion in enumerate(suggestions, 1):
        print(f"{i}. {suggestion}")
    
    print("\n=== Common Troubleshooting Tips ===")
    print("• For 0x1771 errors: Increase slippage tolerance or reduce trade size")
    print("• For transaction confirmation timeouts: Increase priority fee")
    print("• For blockhash errors: Use replaceRecentBlockhash: true and skipPreflight: true")
    print("• For SOL wrapping issues: Use wrapAndUnwrapSol: true in API calls")
    print("• During network congestion: Set priority fee to 'auto' with autoMultiplier: 2")

if __name__ == "__main__":
    asyncio.run(main())