import requests
import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger("TelegramNotifier")

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, disabled: bool = False):
        self.token = token
        self.chat_id = chat_id
        self.disabled = disabled
        self.base_url = f"https://api.telegram.org/bot{token}"
        
        # Log initialization status
        if self.disabled:
            logger.info("Telegram notifications are disabled")
        elif not token or token == "disabled" or not chat_id or chat_id == "disabled":
            logger.warning("Telegram bot token or chat ID not configured properly")
            self.disabled = True
        else:
            logger.info("Telegram notifier initialized successfully")
            
    def send_message(self, message: str) -> Optional[Dict[str, Any]]:
        """Send a message to the configured Telegram chat"""
        if self.disabled:
            logger.debug(f"Telegram disabled, would have sent: {message}")
            return None
            
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, data=data)
            
            if response.status_code == 200:
                logger.debug("Telegram message sent successfully")
                return response.json()
            else:
                logger.error(f"Failed to send Telegram message: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error sending Telegram message: {str(e)}")
            return None
            
    def send_arbitrage_alert(self, 
                           profit: float, 
                           profit_percentage: float,
                           token_path: list, 
                           route_type: str,
                           executed: bool = False,
                           opportunity: Optional[Dict] = None) -> None:
        """Send an enhanced alert about an arbitrage opportunity with proper token names"""
        
        # Format tokens for display with enhanced metadata
        token_display = []
        
        if opportunity and hasattr(opportunity, 'token_symbol') and hasattr(opportunity, 'token_address'):
            # Enhanced cross-DEX opportunity display
            token_symbol = opportunity.token_symbol or f"TOKEN_{opportunity.token_address[:6]}"
            token_name = getattr(opportunity, 'token_name', 'Unknown Token')
            address_short = f"{opportunity.token_address[:8]}..."
            
            token_display.append(f"{token_symbol} ({address_short})")
            
            # Add venue information for cross-DEX
            if route_type == "cross_dex" and hasattr(opportunity, 'buy_venue'):
                venue_info = f"\n🏪 *Buy on:* {opportunity.buy_venue} at ${opportunity.buy_price:.6f}"
                venue_info += f"\n🏪 *Sell on:* {opportunity.sell_venue} at ${opportunity.sell_price:.6f}"
            else:
                venue_info = ""
        else:
            # Fallback to original logic for backward compatibility
            for token in token_path:
                if isinstance(token, dict):
                    if "symbol" in token and "address" in token:
                        symbol = token['symbol']
                        address_short = f"{token['address'][:8]}..."
                        token_display.append(f"{symbol} ({address_short})")
                    elif "name" in token and "address" in token:
                        name = token['name']
                        address_short = f"{token['address'][:8]}..."
                        token_display.append(f"{name} ({address_short})")
                    else:
                        token_display.append("UNKNOWN")
                elif isinstance(token, str):
                    # Try to format token address
                    if len(token) > 20:  # Looks like an address
                        token_display.append(f"TOKEN_{token[:8]}...")
                    else:
                        token_display.append(token)
                else:
                    token_display.append("UNKNOWN")
            venue_info = ""
        
        # Create enhanced message
        status = "✅ EXECUTED" if executed else "🔍 DETECTED"
        
        # Format route type for better display
        route_display = {
            "cross_dex": "Cross-DEX Arbitrage",
            "triangle": "Triangle Arbitrage", 
            "pair": "Pair Arbitrage",
            "flash_loan": "Flash Loan Arbitrage"
        }.get(route_type, route_type.title())
        
        message = (
            f"*{route_display.upper()} {status}*\n\n"
            f"💰 *Profit:* ${profit:.2f} ({profit_percentage:.2f}%)\n"
            f"🪙 *Token:* {' → '.join(token_display)}\n"
            f"📊 *Type:* {route_display}{venue_info}\n"
            f"⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # Send the message
        self.send_message(message)

    def send_cross_dex_summary(self, opportunities: list) -> None:
        """Send a summary of cross-DEX opportunities found"""
        if not opportunities or self.disabled:
            return
            
        message = f"*📊 CROSS-DEX OPPORTUNITIES SUMMARY*\n\n"
        message += f"Found {len(opportunities)} opportunities:\n\n"
        
        for i, opp in enumerate(opportunities[:5], 1):  # Show top 5
            if hasattr(opp, 'token_symbol') and hasattr(opp, 'profit_percentage'):
                symbol = opp.token_symbol or "UNKNOWN"
                address_short = f"{opp.token_address[:8]}..." if hasattr(opp, 'token_address') else ""
                profit = opp.profit_percentage
                
                message += f"{i}. *{symbol}* ({address_short})\n"
                message += f"   💰 {profit:.2f}% difference\n"
                
                if hasattr(opp, 'buy_venue') and hasattr(opp, 'sell_venue'):
                    message += f"   📈 {opp.buy_venue} → {opp.sell_venue}\n"
                message += "\n"
        
        if len(opportunities) > 5:
            message += f"... and {len(opportunities) - 5} more opportunities\n"
        
        self.send_message(message)

    def send_error(self, error_message: str) -> None:
        """Send an error notification"""
        if self.disabled:
            return
            
        message = f"❌ *ERROR:* {error_message}"
        self.send_message(message)