#!/bin/bash

# Check if node and npm are installed
if ! command -v node &> /dev/null; then
    echo "Node.js is not installed. Please install Node.js."
    exit 1
fi

# Check if ts-node is installed globally
if ! command -v ts-node &> /dev/null; then
    echo "ts-node is not installed globally. Installing it..."
    npm install -g ts-node typescript
fi

# Make sure project dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "Installing project dependencies..."
    npm install
fi

# Run the Glasshot test
echo "Running Glasshot API test..."
export GLASSHOT_API_URL=https://api-new.glasshot.io/v1
npx ts-node test_glasshot.ts