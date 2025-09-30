from aiohttp import web
import json

# Mock token data
USDC = {
    "symbol": "USDC",
    "name": "USD Coin",
    "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "decimals": 6
}
SOL = {
    "symbol": "SOL", 
    "name": "Wrapped SOL",
    "mint": "So11111111111111111111111111111111111111112",
    "decimals": 9
}

# Mock pools (including both V3 and V4)
MOCK_POOLS = [
    # V3 Pool
    {
        "id": "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2",
        "baseMint": SOL["mint"],
        "quoteMint": USDC["mint"],
        "baseSymbol": SOL["symbol"],
        "quoteSymbol": USDC["symbol"],
        "baseName": SOL["name"],
        "quoteName": USDC["name"],
        "baseDecimals": SOL["decimals"],
        "quoteDecimals": USDC["decimals"],
        "lpMint": "8HoQnePLqPj4M7PUDzfw8e3Ymdwgc7NLGnaTUapubyvu",
        "baseVault": "5tgfd6XgwiXB9otEnzFpXK11m7Q7yZUaAJzWK4oT5UGF",
        "quoteVault": "9r39vqrJuubgafaB6c6yDgxqw9vvyoi8jGwX9e7A6xc3",
        "version": 3,
        "baseAmount": "15000000000",  # 15 SOL
        "quoteAmount": "300000000",  # $300 USDC
        "feeRate": 25  # 0.25%
    },
    # V4 Pool
    {
        "id": "6UmmUiYoBEWsGkk5KTG3G9fK9vhWvVypKvJGfJpesHWm",
        "baseMint": SOL["mint"],
        "quoteMint": USDC["mint"],
        "baseSymbol": SOL["symbol"],
        "quoteSymbol": USDC["symbol"],
        "baseName": SOL["name"],
        "quoteName": USDC["name"],
        "baseDecimals": SOL["decimals"],
        "quoteDecimals": USDC["decimals"],
        "lpMint": "BRCJyvHDFZcCvg5VjKqPHtpZjxR3fjKXqWzMnGDhMmQ1",
        "baseVault": "4BJXYkVAfC9WqFGCwBjz9HHD3N7qkMcnhFqHoT4uRjyY",
        "quoteVault": "B5rYwgFx9MKbVgvWxM3yR2YVfEKVy7BkjZfkQxpmX8P4",
        "version": 4,
        "baseAmount": "18000000000",  # 18 SOL 
        "quoteAmount": "370000000",  # $370 USDC (inflate to create price diff)
        "feeRate": 25  # 0.25%
    }
]

# Wrap response data
def wrap_response(data):
    return {
        "success": True,
        "data": data,
        "timestamp": 0
    }

async def get_all_pools(request):
    return web.json_response(wrap_response(MOCK_POOLS))

async def get_pool(request):
    pool_id = request.match_info['id']
    pool = next((p for p in MOCK_POOLS if p["id"] == pool_id), None)
    if pool:
        return web.json_response(wrap_response(pool))
    return web.json_response({"error": "Pool not found"}, status=404)

async def get_pools_by_mint(request):
    mint = request.match_info['mint']
    pools = [p for p in MOCK_POOLS if p["baseMint"] == mint or p["quoteMint"] == mint]
    return web.json_response(wrap_response(pools))

# Routes and app setup
app = web.Application()
app.router.add_get('/pools', get_all_pools)
app.router.add_get('/pools/info/ids', get_all_pools)
app.router.add_get('/pools/{id}', get_pool)
app.router.add_get('/pools/info/mint/{mint}', get_pools_by_mint)

if __name__ == '__main__':
    web.run_app(app, host='127.0.0.1', port=8545)