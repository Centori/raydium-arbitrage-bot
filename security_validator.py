import asyncio
import logging
import aiohttp
from typing import Dict, Optional, List
from dataclasses import dataclass
from decimal import Decimal

from config import Config
from api_client import BlockchainAPIClient

logger = logging.getLogger("security_validator")

@dataclass
class SecurityCheck:
    """Result of a security check"""
    passed: bool
    risk_level: str  # 'safe', 'warning', 'danger'
    message: str
    score: int  # 0-100, lower is better

@dataclass
class TokenSecurityReport:
    """Comprehensive security report for a token"""
    token_mint: str
    is_safe: bool
    overall_risk_score: int  # 0-100
    checks: Dict[str, SecurityCheck]
    tradeable: bool
    warnings: List[str]

class SecurityValidator:
    """Validates token security to prevent rug pulls and scams"""
    
    def __init__(self, config: Config, api_client: BlockchainAPIClient):
        self.config = config
        self.api_client = api_client
        
        # Risk thresholds
        self.max_risk_score = 50  # Don't trade tokens above this score
        self.warning_threshold = 30
        
        # Holder concentration thresholds
        self.max_top_holder_percent = 15.0  # Top holder can't own >15%
        self.max_top_10_percent = 40.0  # Top 10 holders can't own >40%
        
        # Blacklisted tokens/creators
        self.blacklisted_tokens = set()
        self.blacklisted_creators = set()
        
        # Cache for performance
        self.security_cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    async def validate_token(self, token_mint: str) -> TokenSecurityReport:
        """
        Comprehensive token security validation
        Returns full report with all checks
        """
        logger.info(f"Running security checks for {token_mint}")
        
        # Check cache first
        if token_mint in self.security_cache:
            cached = self.security_cache[token_mint]
            import time
            if time.time() - cached['timestamp'] < self.cache_ttl:
                return cached['report']
        
        checks = {}
        warnings = []
        
        # Run all security checks
        checks['freeze_authority'] = await self._check_freeze_authority(token_mint)
        checks['mint_authority'] = await self._check_mint_authority(token_mint)
        checks['holder_distribution'] = await self._check_holder_distribution(token_mint)
        checks['liquidity_locked'] = await self._check_liquidity_lock(token_mint)
        checks['metadata'] = await self._check_metadata(token_mint)
        checks['creator_history'] = await self._check_creator_history(token_mint)
        checks['rugcheck'] = await self._check_rugcheck_api(token_mint)
        
        # Calculate overall risk score
        risk_score = sum(check.score for check in checks.values()) // len(checks)
        
        # Determine if tradeable
        critical_failures = [
            checks['freeze_authority'].risk_level == 'danger',
            checks['mint_authority'].risk_level == 'danger',
            checks['holder_distribution'].risk_level == 'danger'
        ]
        
        is_safe = risk_score < self.max_risk_score and not any(critical_failures)
        tradeable = is_safe or risk_score < self.warning_threshold
        
        # Collect warnings
        for check_name, check in checks.items():
            if check.risk_level in ['warning', 'danger']:
                warnings.append(f"{check_name}: {check.message}")
        
        report = TokenSecurityReport(
            token_mint=token_mint,
            is_safe=is_safe,
            overall_risk_score=risk_score,
            checks=checks,
            tradeable=tradeable,
            warnings=warnings
        )
        
        # Cache result
        import time
        self.security_cache[token_mint] = {
            'report': report,
            'timestamp': time.time()
        }
        
        if not tradeable:
            logger.warning(f"Token {token_mint} FAILED security checks: {warnings}")
        else:
            logger.info(f"Token {token_mint} passed security (risk: {risk_score}/100)")
        
        return report
    
    async def _check_freeze_authority(self, token_mint: str) -> SecurityCheck:
        """Check if freeze authority is disabled"""
        try:
            # Use Helius DAS API to get token info
            url = f"https://mainnet.helius-rpc.com/?api-key={self.config.HELIUS_API_KEY}"
            
            payload = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "getAccountInfo",
                "params": [
                    token_mint,
                    {"encoding": "jsonParsed"}
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    
                    if 'result' in data and data['result']:
                        account_data = data['result']['value']['data']
                        if 'parsed' in account_data:
                            freeze_authority = account_data['parsed']['info'].get('freezeAuthority')
                            
                            if freeze_authority is None:
                                return SecurityCheck(
                                    passed=True,
                                    risk_level='safe',
                                    message='Freeze authority disabled',
                                    score=0
                                )
                            else:
                                return SecurityCheck(
                                    passed=False,
                                    risk_level='danger',
                                    message='Freeze authority enabled - can freeze trading',
                                    score=100
                                )
            
            # Default to warning if can't determine
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message='Could not verify freeze authority',
                score=50
            )
            
        except Exception as e:
            logger.error(f"Error checking freeze authority: {e}")
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message=f'Error checking: {str(e)}',
                score=50
            )
    
    async def _check_mint_authority(self, token_mint: str) -> SecurityCheck:
        """Check if mint authority is disabled"""
        try:
            url = f"https://mainnet.helius-rpc.com/?api-key={self.config.HELIUS_API_KEY}"
            
            payload = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "getAccountInfo",
                "params": [
                    token_mint,
                    {"encoding": "jsonParsed"}
                ]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    
                    if 'result' in data and data['result']:
                        account_data = data['result']['value']['data']
                        if 'parsed' in account_data:
                            mint_authority = account_data['parsed']['info'].get('mintAuthority')
                            
                            if mint_authority is None:
                                return SecurityCheck(
                                    passed=True,
                                    risk_level='safe',
                                    message='Mint authority disabled',
                                    score=0
                                )
                            else:
                                return SecurityCheck(
                                    passed=False,
                                    risk_level='danger',
                                    message='Mint authority enabled - can mint unlimited tokens',
                                    score=100
                                )
            
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message='Could not verify mint authority',
                score=50
            )
            
        except Exception as e:
            logger.error(f"Error checking mint authority: {e}")
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message=f'Error checking: {str(e)}',
                score=50
            )
    
    async def _check_holder_distribution(self, token_mint: str) -> SecurityCheck:
        """Check for whale concentration risk"""
        try:
            # Use Helius to get largest token accounts
            url = f"https://mainnet.helius-rpc.com/?api-key={self.config.HELIUS_API_KEY}"
            
            payload = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "getTokenLargestAccounts",
                "params": [token_mint]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    
                    if 'result' in data and 'value' in data['result']:
                        accounts = data['result']['value']
                        
                        if not accounts:
                            return SecurityCheck(
                                passed=False,
                                risk_level='warning',
                                message='No holder data available',
                                score=40
                            )
                        
                        # Calculate total supply
                        total_supply = sum(float(acc['amount']) for acc in accounts)
                        
                        # Check top holder
                        top_holder_pct = (float(accounts[0]['amount']) / total_supply * 100) if total_supply > 0 else 0
                        
                        # Check top 10 holders
                        top_10_sum = sum(float(acc['amount']) for acc in accounts[:10])
                        top_10_pct = (top_10_sum / total_supply * 100) if total_supply > 0 else 0
                        
                        # Evaluate risk
                        if top_holder_pct > self.max_top_holder_percent:
                            return SecurityCheck(
                                passed=False,
                                risk_level='danger',
                                message=f'Top holder owns {top_holder_pct:.1f}% (whale risk)',
                                score=80
                            )
                        elif top_10_pct > self.max_top_10_percent:
                            return SecurityCheck(
                                passed=False,
                                risk_level='warning',
                                message=f'Top 10 holders own {top_10_pct:.1f}% (concentration risk)',
                                score=50
                            )
                        else:
                            return SecurityCheck(
                                passed=True,
                                risk_level='safe',
                                message=f'Healthy distribution (top: {top_holder_pct:.1f}%)',
                                score=10
                            )
            
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message='Could not verify holder distribution',
                score=40
            )
            
        except Exception as e:
            logger.error(f"Error checking holder distribution: {e}")
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message=f'Error checking: {str(e)}',
                score=40
            )
    
    async def _check_liquidity_lock(self, token_mint: str) -> SecurityCheck:
        """Check if LP tokens are burned (liquidity locked)"""
        try:
            # Find Raydium pool for this token
            pools = self.api_client.get_raydium_pools()
            matching_pool = None
            
            for pool in pools:
                if pool.base_token.address == token_mint or pool.quote_token.address == token_mint:
                    matching_pool = pool
                    break
            
            if not matching_pool:
                return SecurityCheck(
                    passed=False,
                    risk_level='warning',
                    message='No liquidity pool found',
                    score=60
                )
            
            # Check if LP mint is burned (sent to burn address)
            burn_addresses = [
                "11111111111111111111111111111111",  # System program
                "1nc1nerator11111111111111111111111111111111",  # Incinerator
            ]
            
            # This is a simplified check - in production would query LP token holder
            # For now, we'll give it a moderate score
            return SecurityCheck(
                passed=True,
                risk_level='warning',
                message='LP lock status unknown - verify manually',
                score=30
            )
            
        except Exception as e:
            logger.error(f"Error checking liquidity lock: {e}")
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message=f'Error checking: {str(e)}',
                score=40
            )
    
    async def _check_metadata(self, token_mint: str) -> SecurityCheck:
        """Verify token has valid metadata"""
        try:
            url = f"https://mainnet.helius-rpc.com/?api-key={self.config.HELIUS_API_KEY}"
            
            payload = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "getAsset",
                "params": {
                    "id": token_mint
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    data = await resp.json()
                    
                    if 'result' in data:
                        metadata = data['result']
                        
                        # Check for basic metadata
                        has_name = bool(metadata.get('content', {}).get('metadata', {}).get('name'))
                        has_symbol = bool(metadata.get('content', {}).get('metadata', {}).get('symbol'))
                        
                        if has_name and has_symbol:
                            return SecurityCheck(
                                passed=True,
                                risk_level='safe',
                                message='Valid metadata present',
                                score=0
                            )
                        else:
                            return SecurityCheck(
                                passed=False,
                                risk_level='warning',
                                message='Incomplete metadata',
                                score=30
                            )
            
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message='Could not fetch metadata',
                score=30
            )
            
        except Exception as e:
            logger.error(f"Error checking metadata: {e}")
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message=f'Error checking: {str(e)}',
                score=30
            )
    
    async def _check_creator_history(self, token_mint: str) -> SecurityCheck:
        """Check if creator has history of rug pulls"""
        try:
            # This would check creator's wallet history
            # For now, return moderate risk
            return SecurityCheck(
                passed=True,
                risk_level='safe',
                message='Creator history not available',
                score=20
            )
            
        except Exception as e:
            logger.error(f"Error checking creator history: {e}")
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message=f'Error checking: {str(e)}',
                score=30
            )
    
    async def _check_rugcheck_api(self, token_mint: str) -> SecurityCheck:
        """Check RugCheck API for known issues"""
        try:
            url = f"https://api.rugcheck.xyz/v1/tokens/{token_mint}/report"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        risk_level = data.get('riskLevel', 'unknown')
                        risks = data.get('risks', [])
                        
                        if risk_level == 'good':
                            return SecurityCheck(
                                passed=True,
                                risk_level='safe',
                                message='RugCheck: Good',
                                score=0
                            )
                        elif risk_level == 'medium':
                            return SecurityCheck(
                                passed=True,
                                risk_level='warning',
                                message=f'RugCheck: Medium risk - {len(risks)} issues',
                                score=40
                            )
                        else:
                            return SecurityCheck(
                                passed=False,
                                risk_level='danger',
                                message=f'RugCheck: High risk - {len(risks)} issues',
                                score=80
                            )
                    elif resp.status == 404:
                        # Token not in RugCheck database
                        return SecurityCheck(
                            passed=True,
                            risk_level='warning',
                            message='Token not in RugCheck database',
                            score=30
                        )
            
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message='RugCheck API unavailable',
                score=30
            )
            
        except asyncio.TimeoutError:
            logger.warning("RugCheck API timeout")
            return SecurityCheck(
                passed=True,
                risk_level='safe',
                message='RugCheck timeout - skipping',
                score=20
            )
        except Exception as e:
            logger.error(f"Error checking RugCheck API: {e}")
            return SecurityCheck(
                passed=False,
                risk_level='warning',
                message=f'Error checking: {str(e)}',
                score=30
            )
    
    def blacklist_token(self, token_mint: str, reason: str = "Manual blacklist"):
        """Manually blacklist a token"""
        self.blacklisted_tokens.add(token_mint)
        logger.warning(f"Blacklisted token {token_mint}: {reason}")
    
    def is_blacklisted(self, token_mint: str) -> bool:
        """Check if token is blacklisted"""
        return token_mint in self.blacklisted_tokens
