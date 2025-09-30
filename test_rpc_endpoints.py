#!/usr/bin/env python3
"""
RPC Endpoint Tester for Solana

This script tests various Solana RPC endpoints for rate limits,
latency, and reliability to find the best one for your arbitrage bot.
"""

import json
import time
import asyncio
import argparse
import statistics
from datetime import datetime
from typing import Dict, List, Any, Tuple
import os
from dotenv import load_dotenv

import aiohttp
import prettytable
from colorama import Fore, Style, init

# Initialize colorama
init()

# Load environment variables
load_dotenv()

# Get API keys from environment
HELIUS_API_KEY = os.getenv('HELIUS_API_KEY', '')
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY', '')

# RPC Endpoints to test
RPC_ENDPOINTS = {
    "Solana Public": "https://api.mainnet-beta.solana.com",
}

# Add Helius if API key exists
if HELIUS_API_KEY:
    RPC_ENDPOINTS["Helius"] = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# Add Alchemy if API key exists
if ALCHEMY_API_KEY:
    RPC_ENDPOINTS["Alchemy"] = f"https://solana-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"

# Add additional public endpoints
RPC_ENDPOINTS.update({
    "GenesysGo": "https://ssc-dao.genesysgo.net",
    "Serum": "https://solana-api.projectserum.com",
    "Triton RPC": "https://free.rpcpool.com",
})

# Request payloads for different test types
TEST_PAYLOADS = {
    "getLatestBlockhash": {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getLatestBlockhash"
    },
    "getBalance": {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": ["vines1vzrYbzLMRdu58ou5XTby4qAqVRLmqo36NKPTg"]  # Random address
    },
    "getBlock": {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBlock",
        "params": [200000000, {"encoding": "json", "maxSupportedTransactionVersion": 0}]
    },
    # Add some advanced methods that might have different rate limits
    "getTokenAccountsByOwner": {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            "vines1vzrYbzLMRdu58ou5XTby4qAqVRLmqo36NKPTg",
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"}
        ]
    },
    "getSignaturesForAddress": {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": ["vines1vzrYbzLMRdu58ou5XTby4qAqVRLmqo36NKPTg", {"limit": 5}]
    }
}


class RPCTester:
    def __init__(self, endpoints: Dict[str, str], test_count: int = 10, batch_size: int = 5, 
                 rate_test: bool = False, rate_test_count: int = 100, rate_test_period: int = 10):
        self.endpoints = endpoints
        self.test_count = test_count
        self.batch_size = batch_size
        self.rate_test = rate_test
        self.rate_test_count = rate_test_count
        self.rate_test_period = rate_test_period
        self.results = {}

    async def test_endpoint(self, name: str, endpoint: str) -> Dict[str, Any]:
        """Test a single RPC endpoint for performance and rate limits"""
        print(f"Testing {Fore.CYAN}{name}{Style.RESET_ALL} ({endpoint})...")
        
        results = {
            "name": name,
            "url": endpoint,
            "success_rate": 0,
            "avg_latency": 0,
            "max_latency": 0,
            "min_latency": 0,
            "rate_limit_hit": False,
            "error_messages": [],
            "api_methods": {},
            "estimated_rate_limit": "Unknown",
            "details": {
                "latencies": [],
                "successes": 0,
                "rate_limit_errors": 0,
                "other_errors": 0
            }
        }
        
        # We'll run sequential tests first for basic latency measurement
        async with aiohttp.ClientSession() as session:
            # Test 1: Sequential requests for basic latency
            print(f"  Running sequential latency test...")
            for i in range(self.test_count):
                start_time = time.time()
                try:
                    async with session.post(
                        endpoint,
                        json=TEST_PAYLOADS["getLatestBlockhash"],
                        headers={"Content-Type": "application/json"},
                        timeout=10
                    ) as response:
                        latency = time.time() - start_time
                        results["details"]["latencies"].append(latency)
                        
                        if response.status == 200:
                            response_data = await response.json()
                            if "result" in response_data:
                                results["details"]["successes"] += 1
                            else:
                                results["details"]["other_errors"] += 1
                                error_msg = f"Error: {response_data.get('error', {}).get('message', 'Unknown')}"
                                if error_msg not in results["error_messages"]:
                                    results["error_messages"].append(error_msg)
                        elif response.status == 429:
                            results["details"]["rate_limit_errors"] += 1
                            results["rate_limit_hit"] = True
                            print(f"  {Fore.RED}Rate limit hit!{Style.RESET_ALL}")
                            break
                        else:
                            results["details"]["other_errors"] += 1
                            error_msg = f"HTTP {response.status}: {await response.text()}"
                            if error_msg not in results["error_messages"]:
                                results["error_messages"].append(error_msg)
                except Exception as e:
                    results["details"]["other_errors"] += 1
                    error_msg = f"Exception: {str(e)}"
                    if error_msg not in results["error_messages"]:
                        results["error_messages"].append(error_msg)
                
                await asyncio.sleep(0.2)  # Small delay between requests
            
            # Test 2: Test different API methods to see if they have different rate limits
            print(f"  Testing different API methods...")
            for method_name, payload in TEST_PAYLOADS.items():
                try:
                    start_time = time.time()
                    async with session.post(
                        endpoint,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=15  # Some methods like getBlock can take longer
                    ) as response:
                        latency = time.time() - start_time
                        success = response.status == 200
                        rate_limited = response.status == 429
                        
                        results["api_methods"][method_name] = {
                            "success": success,
                            "latency": latency,
                            "rate_limited": rate_limited
                        }
                        
                        if rate_limited:
                            print(f"  {Fore.RED}Rate limit hit for {method_name}!{Style.RESET_ALL}")
                except Exception as e:
                    results["api_methods"][method_name] = {
                        "success": False,
                        "latency": 0,
                        "error": str(e)
                    }
                
                await asyncio.sleep(0.5)  # Larger delay between different methods
            
            # Test 3: Parallel request batch to test rate limits
            print(f"  Running parallel rate limit test...")
            try:
                async with asyncio.TaskGroup() as tg:
                    tasks = [
                        tg.create_task(self._make_request(session, endpoint, TEST_PAYLOADS["getBalance"]))
                        for _ in range(self.batch_size)
                    ]
                
                parallel_results = [task.result() for task in tasks]
                rate_limit_count = sum(1 for r in parallel_results if r.get("rate_limited", False))
                
                if rate_limit_count > 0:
                    results["rate_limit_hit"] = True
                    print(f"  {Fore.RED}Rate limit hit during parallel test ({rate_limit_count}/{self.batch_size})!{Style.RESET_ALL}")
            except Exception as e:
                print(f"  {Fore.RED}Error in parallel test: {e}{Style.RESET_ALL}")
            
            # Test 4: Optional rate limit finder - only run if explicitly requested
            if self.rate_test and not results["rate_limit_hit"]:
                print(f"  {Fore.YELLOW}Running rate limit stress test...{Style.RESET_ALL}")
                print(f"  This will make {self.rate_test_count} requests in {self.rate_test_period} seconds.")
                print(f"  Press Ctrl+C to abort.")
                
                # Warning that this might get your IP temporarily banned
                print(f"  {Fore.RED}WARNING: This test may trigger temporary IP blocks from some RPC providers.{Style.RESET_ALL}")
                
                # Sleep to give user a chance to abort
                for i in range(5, 0, -1):
                    print(f"  Starting in {i}...", end="\r")
                    await asyncio.sleep(1)
                print("  Running rate test...                ")
                
                # Run the rate test
                rate_results = await self._find_rate_limit(session, endpoint)
                
                if rate_results["limit_found"]:
                    results["estimated_rate_limit"] = f"{rate_results['max_rate']} req/sec"
                    print(f"  {Fore.GREEN}Estimated rate limit: {results['estimated_rate_limit']}{Style.RESET_ALL}")
                else:
                    results["estimated_rate_limit"] = f">= {rate_results['max_rate']} req/sec"
                    print(f"  {Fore.GREEN}Rate limit not hit - at least {results['estimated_rate_limit']}{Style.RESET_ALL}")
        
        # Calculate statistics if we have any successful requests
        if results["details"]["latencies"]:
            results["avg_latency"] = statistics.mean(results["details"]["latencies"])
            results["max_latency"] = max(results["details"]["latencies"])
            results["min_latency"] = min(results["details"]["latencies"])
        
        # Calculate success rate
        total_requests = self.test_count + self.batch_size
        total_successes = results["details"]["successes"]
        results["success_rate"] = (total_successes / total_requests) * 100
        
        # Print summary
        success_color = Fore.GREEN if results["success_rate"] > 95 else (Fore.YELLOW if results["success_rate"] > 80 else Fore.RED)
        latency_color = Fore.GREEN if results["avg_latency"] < 0.5 else (Fore.YELLOW if results["avg_latency"] < 1.0 else Fore.RED)
        
        print(f"  Success Rate: {success_color}{results['success_rate']:.1f}%{Style.RESET_ALL}")
        print(f"  Avg Latency: {latency_color}{results['avg_latency']*1000:.1f}ms{Style.RESET_ALL}")
        print(f"  Rate Limited: {Fore.RED if results['rate_limit_hit'] else Fore.GREEN}{results['rate_limit_hit']}{Style.RESET_ALL}")
        print(f"  Estimated Rate Limit: {Fore.CYAN}{results['estimated_rate_limit']}{Style.RESET_ALL}")
        print("")
        
        return results

    async def _make_request(self, session, endpoint, payload) -> Dict[str, Any]:
        """Helper to make a single RPC request"""
        try:
            async with session.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            ) as response:
                if response.status == 429:
                    return {"success": False, "rate_limited": True}
                
                data = await response.json()
                return {"success": "result" in data, "rate_limited": False}
        except Exception:
            return {"success": False, "rate_limited": False}
    
    async def _find_rate_limit(self, session, endpoint) -> Dict[str, Any]:
        """Try to find the rate limit by gradually increasing request rate"""
        results = {
            "limit_found": False,
            "max_rate": 0,
            "failed_rate": 0
        }
        
        # Start with a small number of requests per second
        for req_per_sec in [5, 10, 20, 50, 100, 200]:
            delay = 1.0 / req_per_sec
            count = min(req_per_sec * self.rate_test_period, self.rate_test_count)
            
            print(f"  Testing {req_per_sec} requests/sec ({count} requests total)...")
            
            success_count = 0
            rate_limit_hit = False
            
            start_time = time.time()
            for i in range(count):
                if i > 0 and i % req_per_sec == 0:
                    elapsed = time.time() - start_time
                    if elapsed < 1.0:
                        await asyncio.sleep(1.0 - elapsed)
                    start_time = time.time()
                    print(f"  Progress: {i}/{count} requests", end="\r")
                
                try:
                    async with session.post(
                        endpoint,
                        json=TEST_PAYLOADS["getLatestBlockhash"],
                        headers={"Content-Type": "application/json"},
                        timeout=5
                    ) as response:
                        if response.status == 200:
                            success_count += 1
                        elif response.status == 429:
                            rate_limit_hit = True
                            print(f"  {Fore.RED}Rate limit hit at {req_per_sec} req/sec after {i+1} requests{Style.RESET_ALL}")
                            break
                except Exception:
                    pass
                
                if (i+1) % req_per_sec != 0:  # Only sleep between requests (not after each second)
                    await asyncio.sleep(delay)
            
            success_rate = success_count / count * 100 if count > 0 else 0
            print(f"  Result: {success_count}/{count} successful ({success_rate:.1f}%)")
            
            if rate_limit_hit or success_rate < 80:
                results["limit_found"] = True
                results["failed_rate"] = req_per_sec
                break
            else:
                results["max_rate"] = req_per_sec
        
        return results

    async def run_tests(self) -> None:
        """Run tests against all configured endpoints"""
        print(f"{Fore.GREEN}===== Solana RPC Endpoint Performance Test ====={Style.RESET_ALL}")
        print(f"Testing {len(self.endpoints)} endpoints with {self.test_count} sequential requests\n")
        
        results = []
        for name, url in self.endpoints.items():
            result = await self.test_endpoint(name, url)
            results.append(result)
        
        self.results = results
        self._display_results(results)
        
        # Save results to file
        self._save_results(results)

    def _display_results(self, results: List[Dict[str, Any]]) -> None:
        """Display formatted test results"""
        # Sort by success rate (desc) and then latency (asc)
        sorted_results = sorted(
            results, 
            key=lambda x: (-x["success_rate"], x["avg_latency"])
        )
        
        table = prettytable.PrettyTable()
        table.field_names = ["Rank", "Provider", "Success %", "Avg Latency", "Min/Max (ms)", "Rate Limited", "Est. Rate Limit"]
        
        for i, result in enumerate(sorted_results, 1):
            success_color = Fore.GREEN if result["success_rate"] > 95 else (Fore.YELLOW if result["success_rate"] > 80 else Fore.RED)
            latency_color = Fore.GREEN if result["avg_latency"] < 0.5 else (Fore.YELLOW if result["avg_latency"] < 1.0 else Fore.RED)
            rate_limit_color = Fore.RED if result["rate_limit_hit"] else Fore.GREEN
            
            table.add_row([
                f"{i}",
                result["name"],
                f"{success_color}{result['success_rate']:.1f}%{Style.RESET_ALL}",
                f"{latency_color}{result['avg_latency']*1000:.1f}ms{Style.RESET_ALL}",
                f"{result['min_latency']*1000:.1f}/{result['max_latency']*1000:.1f}",
                f"{rate_limit_color}{'Yes' if result['rate_limit_hit'] else 'No'}{Style.RESET_ALL}",
                f"{result['estimated_rate_limit']}"
            ])
        
        print(f"\n{Fore.GREEN}===== Results Summary ====={Style.RESET_ALL}")
        print(table)
        
        # API Method Performance Table
        if any("api_methods" in result and result["api_methods"] for result in results):
            print(f"\n{Fore.GREEN}===== API Method Performance ====={Style.RESET_ALL}")
            method_table = prettytable.PrettyTable()
            method_table.field_names = ["Provider"] + list(TEST_PAYLOADS.keys())
            
            for result in sorted_results:
                row = [result["name"]]
                
                for method in TEST_PAYLOADS.keys():
                    method_result = result.get("api_methods", {}).get(method, {})
                    if method_result:
                        success = method_result.get("success", False)
                        latency = method_result.get("latency", 0)
                        rate_limited = method_result.get("rate_limited", False)
                        
                        status_color = Fore.RED if rate_limited else (Fore.GREEN if success else Fore.YELLOW)
                        latency_str = f"{latency*1000:.1f}ms" if latency else "N/A"
                        
                        cell = f"{status_color}{'✓' if success else ('⚠' if rate_limited else '✗')}{Style.RESET_ALL} {latency_str}"
                        row.append(cell)
                    else:
                        row.append(f"{Fore.YELLOW}?{Style.RESET_ALL}")
                
                method_table.add_row(row)
            
            print(method_table)
        
        # Recommend the best endpoint
        if sorted_results:
            best = sorted_results[0]
            print(f"\n{Fore.GREEN}Recommended RPC endpoint:{Style.RESET_ALL} {best['name']} ({best['url']})")
            print(f"This endpoint had a {best['success_rate']:.1f}% success rate with {best['avg_latency']*1000:.1f}ms average latency.")
            
            if best["rate_limit_hit"]:
                print(f"{Fore.YELLOW}Warning:{Style.RESET_ALL} This endpoint did hit rate limits during testing.")
                
                # Find the best endpoint without rate limits
                for result in sorted_results:
                    if not result["rate_limit_hit"]:
                        print(f"{Fore.GREEN}Alternative without rate limits:{Style.RESET_ALL} {result['name']} ({result['url']})")
                        break
            
            # Config recommendations
            if "helius" in best["url"].lower():
                recommended_config = """
# Add to your .env file:
RPC_ENDPOINT={}
                """.format(best["url"])
                print(f"\n{Fore.CYAN}Recommended config for best performance:{Style.RESET_ALL}")
                print(recommended_config)
        
    def _save_results(self, results: List[Dict[str, Any]]) -> None:
        """Save test results to a JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/rpc_test_results_{timestamp}.json"
        
        # Create data directory if it doesn't exist
        import os
        os.makedirs("data", exist_ok=True)
        
        # Convert results for JSON serialization (remove colorama codes)
        clean_results = []
        for result in results:
            clean_result = {
                "name": result["name"],
                "url": result["url"],
                "success_rate": result["success_rate"],
                "avg_latency_ms": result["avg_latency"] * 1000,
                "min_latency_ms": result["min_latency"] * 1000,
                "max_latency_ms": result["max_latency"] * 1000,
                "rate_limit_hit": result["rate_limit_hit"],
                "estimated_rate_limit": result["estimated_rate_limit"],
                "error_messages": result["error_messages"],
                "api_methods": {
                    method: {
                        "success": data.get("success", False),
                        "latency_ms": data.get("latency", 0) * 1000,
                        "rate_limited": data.get("rate_limited", False)
                    } 
                    for method, data in result.get("api_methods", {}).items()
                },
                "timestamp": datetime.now().isoformat()
            }
            clean_results.append(clean_result)
        
        with open(filename, "w") as f:
            json.dump({"results": clean_results, "timestamp": datetime.now().isoformat()}, f, indent=2)
            
        print(f"\nResults saved to {filename}")


async def main():
    parser = argparse.ArgumentParser(description="Test different Solana RPC endpoints for performance and rate limits")
    parser.add_argument("--count", type=int, default=10, help="Number of sequential requests to test per endpoint")
    parser.add_argument("--batch", type=int, default=5, help="Batch size for parallel requests")
    parser.add_argument("--include-custom", action="store_true", help="Include custom endpoints from config file")
    parser.add_argument("--rate-test", action="store_true", help="Run stress test to find rate limits")
    parser.add_argument("--rate-count", type=int, default=100, help="Number of requests for rate limit test")
    parser.add_argument("--rate-period", type=int, default=10, help="Time period (seconds) for rate limit test")
    args = parser.parse_args()
    
    endpoints = RPC_ENDPOINTS.copy()
    
    # Load custom endpoints from config if flag is set
    if args.include_custom:
        try:
            with open("config.py", "r") as f:
                content = f.read()
                
            import re
            custom_endpoints = re.findall(r'RPC_ENDPOINT["\']?\s*=\s*["\']([^"\']+)["\']', content)
            
            if custom_endpoints:
                for i, endpoint in enumerate(custom_endpoints):
                    if endpoint not in endpoints.values():
                        endpoints[f"Custom {i+1}"] = endpoint
        except Exception as e:
            print(f"Error loading custom endpoints: {e}")
    
    tester = RPCTester(
        endpoints, 
        args.count, 
        args.batch,
        args.rate_test,
        args.rate_count,
        args.rate_period
    )
    await tester.run_tests()


if __name__ == "__main__":
    asyncio.run(main())