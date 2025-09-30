#!/bin/bash
# Compare bytecode patterns across different arbitrage transactions

echo "===== Arbitrage Bytecode Pattern Analyzer ====="

BUNDLES_DIR="data/bundles"
PATTERN_FILE="data/arbitrage_patterns.json"

# Check if we have any transactions to analyze
INSTRUCTION_FILES=$(find $BUNDLES_DIR -name "arbitrage_instructions_*.json" 2>/dev/null)
if [ -z "$INSTRUCTION_FILES" ]; then
    echo "No instruction files found. Run extract-jito-bundles.sh first to extract arbitrage transactions."
    exit 1
fi

# Count instruction files
NUM_FILES=$(echo "$INSTRUCTION_FILES" | wc -l)
echo "Found $NUM_FILES instruction files for analysis"

# Create bytecode comparison directory
mkdir -p data/bytecode_analysis

# Extract common patterns from instruction data
echo "Extracting bytecode patterns..."

# 1. First 8 bytes (discriminator) patterns
echo "Analyzing instruction discriminators..."
for FILE in $INSTRUCTION_FILES; do
    # Get transaction signature from filename
    TX_SIG=$(basename $FILE | sed 's/arbitrage_instructions_//g' | sed 's/.json//g')
    
    # Extract the first 8 bytes of each instruction's data
    jq -r '.[] | select(.data != null) | .data' $FILE | while read -r DATA; do
        # Decode base64 and take first 8 bytes
        echo $DATA | base64 -d 2>/dev/null | xxd -p -l 8 >> data/bytecode_analysis/all_discriminators.txt
    done
    
    # Record program IDs used
    jq -r '.[] | select(.programIdIndex != null) | .programIdIndex' $FILE >> data/bytecode_analysis/program_indexes.txt
done

# Find most common discriminators
echo "Most common instruction discriminators:"
sort data/bytecode_analysis/all_discriminators.txt | uniq -c | sort -nr | head -10 > data/bytecode_analysis/common_discriminators.txt
cat data/bytecode_analysis/common_discriminators.txt

# 2. Analyze full transaction structures
echo "Analyzing transaction structures..."

# Get the most common transaction paths
echo "Most common program call sequences:"
for FILE in $BUNDLES_DIR/arbitrage_tx_*.json; do
    TX_SIG=$(basename $FILE | sed 's/arbitrage_tx_//g' | sed 's/.json//g')
    
    # Extract program call sequence
    jq -r '.meta.logMessages | map(select(. | contains("Program:"))) | map(. | capture("Program: (?<program>[A-Za-z0-9]{32,44})") | .program) | join(" -> ")' $FILE >> data/bytecode_analysis/program_sequences.txt
done

# Find common program sequences
sort data/bytecode_analysis/program_sequences.txt | uniq -c | sort -nr | head -5 > data/bytecode_analysis/common_program_sequences.txt
cat data/bytecode_analysis/common_program_sequences.txt

# 3. Count most profitable transactions
echo "Extracting profit information..."
for FILE in $BUNDLES_DIR/arbitrage_tx_*.json; do
    TX_SIG=$(basename $FILE | sed 's/arbitrage_tx_//g' | sed 's/.json//g')
    
    # Calculate difference between pre and post balances of first account
    PRE_BALANCE=$(jq -r '.meta.preBalances[0]' $FILE)
    POST_BALANCE=$(jq -r '.meta.postBalances[0]' $FILE)
    
    if [[ ! -z "$PRE_BALANCE" && ! -z "$POST_BALANCE" && "$PRE_BALANCE" != "null" && "$POST_BALANCE" != "null" ]]; then
        PROFIT=$(echo "scale=9; ($POST_BALANCE - $PRE_BALANCE) / 1000000000" | bc)
        echo "$TX_SIG $PROFIT" >> data/bytecode_analysis/profits.txt
    fi
done

# Sort profits and show top 5
echo "Top profitable transactions:"
sort -k2 -nr data/bytecode_analysis/profits.txt | head -5 > data/bytecode_analysis/top_profits.txt
cat data/bytecode_analysis/top_profits.txt

echo "Bytecode analysis complete. Results saved to data/bytecode_analysis/"
echo "Run 'python analyze_bundles.py' for more detailed pattern analysis"