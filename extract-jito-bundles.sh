#!/bin/bash
# Script to extract and analyze successful Jito arbitrage bundles on Solana

echo "===== Extracting Successful Jito Arbitrage Bundles ====="

# Load configuration
source .env 2>/dev/null || echo "Warning: .env file not found, using default RPC"

# Use default RPC if not set in .env
RPC_ENDPOINT=${RPC_ENDPOINT:-"https://api.mainnet-beta.solana.com"}

# Create directory for transaction data
mkdir -p data/bundles

# Known arbitrage program IDs (Jito searchers, MEV bots)
ARBITRAGE_PROGRAM_IDS=(
  "JitoEBftV8P1Bw26ZmUj5byZiot1WJ1Jb6ybGzDUzWM"  # Jito MEV program
  "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"  # Whirlpools Program
  "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB"  # Jupiter Aggregator v4
  "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"  # Jupiter Aggregator v6
  "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" # Raydium AMM Program
)

# Known arbitrageur wallets (examples, you'll need to find actual ones)
ARBITRAGEUR_WALLETS=(
  "JitoEBftV8P1Bw26ZmUj5byZiot1WJ1Jb6ybGzDUzWM"
  # Add wallets you've identified as arbitrageurs
)

echo "Fetching recent confirmed blocks..."

# Get the current slot (block height)
CURRENT_SLOT=$(curl -s -X POST $RPC_ENDPOINT -H "Content-Type: application/json" -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "getSlot",
  "params": [{"commitment": "confirmed"}]
}' | jq -r '.result')

if [ -z "$CURRENT_SLOT" ] || [ "$CURRENT_SLOT" == "null" ]; then
  echo "Failed to get current slot. Please check your RPC endpoint."
  exit 1
fi

echo "Current slot: $CURRENT_SLOT"
BLOCKS_TO_SCAN=10
SLEEP_BETWEEN_REQUESTS=1 # Sleep to avoid rate limiting

echo "Scanning $BLOCKS_TO_SCAN recent blocks for arbitrage transactions..."

for ((i=0; i<$BLOCKS_TO_SCAN; i++)); do
  BLOCK_SLOT=$((CURRENT_SLOT - i))
  echo "Scanning block at slot $BLOCK_SLOT"
  
  # Get block with transactions
  BLOCK_DATA=$(curl -s -X POST $RPC_ENDPOINT -H "Content-Type: application/json" -d "{
    \"jsonrpc\": \"2.0\",
    \"id\": 1,
    \"method\": \"getBlock\",
    \"params\": [$BLOCK_SLOT, {\"encoding\": \"json\", \"maxSupportedTransactionVersion\": 0, \"transactionDetails\": \"full\", \"rewards\": false}]
  }")
  
  # Check if block retrieval was successful
  if echo "$BLOCK_DATA" | jq -e '.error' > /dev/null; then
    echo "Error retrieving block $BLOCK_SLOT: $(echo "$BLOCK_DATA" | jq -r '.error.message')"
    sleep $SLEEP_BETWEEN_REQUESTS
    continue
  fi
  
  # Extract transactions from block
  TRANSACTIONS=$(echo "$BLOCK_DATA" | jq -r '.result.transactions[] | select(.transaction.message.accountKeys != null)')
  
  if [ -z "$TRANSACTIONS" ]; then
    echo "No transactions found in block $BLOCK_SLOT"
    sleep $SLEEP_BETWEEN_REQUESTS
    continue
  fi
  
  # Count transactions for reporting
  TX_COUNT=$(echo "$TRANSACTIONS" | wc -l)
  echo "Found $TX_COUNT transactions in block $BLOCK_SLOT"
  
  # Analyze each transaction for arbitrage patterns
  echo "$TRANSACTIONS" | while read -r TX; do
    # Extract transaction signature
    TX_SIG=$(echo "$TX" | jq -r '.transaction.signatures[0]')
    
    # Check if transaction involves any known arbitrage programs
    for PROGRAM_ID in "${ARBITRAGE_PROGRAM_IDS[@]}"; do
      if echo "$TX" | jq -e ".meta.logMessages | select(. != null) | any(contains(\"Program: $PROGRAM_ID\"))" > /dev/null; then
        echo "Found potential arbitrage transaction: $TX_SIG"
        
        # Check if transaction is successful
        if echo "$TX" | jq -e '.meta.err == null' > /dev/null; then
          echo "Transaction is successful!"
          
          # Check for specific patterns indicating arbitrage
          # 1. Multiple swaps in the same transaction
          SWAP_COUNT=$(echo "$TX" | jq -r '.meta.logMessages | map(select(. | contains("Instruction: Swap"))) | length')
          
          # 2. Same token address appears multiple times (typical in triangular arbitrage)
          TOKEN_ACCOUNTS=$(echo "$TX" | jq -r '.transaction.message.accountKeys[]')
          
          # 3. Check for price impact or arbitrage profit in logs
          PROFIT_INDICATORS=$(echo "$TX" | jq -r '.meta.logMessages | map(select(. | contains("profit") or contains("price") or contains("amount"))) | join(" ")')
          
          if [ "$SWAP_COUNT" -gt 1 ] || [ ! -z "$PROFIT_INDICATORS" ]; then
            echo "Confirmed arbitrage transaction!"
            
            # Save transaction data for analysis
            echo "$TX" > "data/bundles/arbitrage_tx_${TX_SIG}.json"
            
            # Get transaction details with instruction data
            echo "Fetching detailed transaction data..."
            TX_DETAILS=$(curl -s -X POST $RPC_ENDPOINT -H "Content-Type: application/json" -d "{
              \"jsonrpc\": \"2.0\",
              \"id\": 1,
              \"method\": \"getTransaction\",
              \"params\": [\"$TX_SIG\", {\"encoding\": \"base64\", \"maxSupportedTransactionVersion\": 0}]
            }")
            
            echo "$TX_DETAILS" > "data/bundles/arbitrage_tx_details_${TX_SIG}.json"
            
            # Print summary
            echo "Transaction $TX_SIG:"
            echo "- Swap count: $SWAP_COUNT"
            echo "- Programs involved: $(echo "$TX" | jq -r '.meta.logMessages | map(select(. | contains("Program:"))) | map(. | capture("Program: (?<program>[A-Za-z0-9]{32,44})") | .program) | unique | join(", ")')"
            echo "- Saved to data/bundles/arbitrage_tx_${TX_SIG}.json"
            
            # Extract bytecode/instruction data
            INSTRUCTIONS=$(echo "$TX_DETAILS" | jq -r '.result.transaction.message.instructions')
            echo "- Instructions data available: $([ ! -z "$INSTRUCTIONS" ] && echo "Yes" || echo "No")"
            
            if [ ! -z "$INSTRUCTIONS" ]; then
              echo "$INSTRUCTIONS" > "data/bundles/arbitrage_instructions_${TX_SIG}.json"
              echo "- Instruction data saved to data/bundles/arbitrage_instructions_${TX_SIG}.json"
            fi
          fi
        fi
        break
      fi
    done
  done
  
  # Sleep to avoid rate limiting
  sleep $SLEEP_BETWEEN_REQUESTS
done

echo "Scan complete. Check data/bundles/ for extracted transactions."
echo "To analyze a specific transaction, run: solana confirm -v <TRANSACTION_SIGNATURE>"
echo "To analyze all extracted transactions, run: python analyze_bundles.py"