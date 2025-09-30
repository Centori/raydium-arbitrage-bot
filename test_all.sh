#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}====================================${NC}"
echo -e "${BLUE}    Testing All Blockchain Endpoints${NC}"
echo -e "${BLUE}====================================${NC}"

# Run Python tests for Solana and Raydium
echo -e "\n${BLUE}Running Python Tests (Solana & Raydium)...${NC}"
python3 test_endpoints.py
PYTHON_RESULT=$?

# Run TypeScript tests for Jito
echo -e "\n${BLUE}Running TypeScript Tests (Jito)...${NC}"
npm run test:jito

TS_RESULT=$?

# Check overall results
echo -e "\n${BLUE}====================================${NC}"
echo -e "${BLUE}            Test Summary${NC}"
echo -e "${BLUE}====================================${NC}"

if [ $PYTHON_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Python Tests (Solana & Raydium): PASSED${NC}"
else
    echo -e "${RED}✗ Python Tests (Solana & Raydium): FAILED${NC}"
fi

if [ $TS_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ TypeScript Tests (Jito): PASSED${NC}"
else
    echo -e "${RED}✗ TypeScript Tests (Jito): FAILED${NC}"
fi

# Exit with error if any test suite failed
if [ $PYTHON_RESULT -ne 0 ] || [ $TS_RESULT -ne 0 ]; then
    echo -e "\n${RED}✗ Some tests failed. Check output above for details.${NC}"
    exit 1
fi

echo -e "\n${GREEN}✓ All tests passed successfully!${NC}"
exit 0