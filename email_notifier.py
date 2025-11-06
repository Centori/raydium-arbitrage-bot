import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger("EmailNotifier")

class EmailNotifier:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.sender_email = os.getenv('SMTP_EMAIL', 'your-bot@gmail.com')  # Set in .env
        self.sender_password = os.getenv('SMTP_PASSWORD', '')  # Set in .env
        self.receiver_email = os.getenv('NOTIFICATION_EMAIL', 'centori1@gmail.com')
        self.enabled = os.getenv('EMAIL_NOTIFICATIONS', 'true').lower() == 'true'
        
    def _format_trade_notification(self, strategy, profit_sol, txn_signature):
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="padding: 20px; background-color: #f8f9fa; border-radius: 5px;">
                <h2 style="color: #28a745;">🎯 Profitable Trade Executed!</h2>
                <p><strong>Strategy:</strong> {strategy}</p>
                <p><strong>Profit:</strong> {profit_sol:.4f} SOL</p>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                <p><strong>Transaction:</strong> <a href="https://solscan.io/tx/{txn_signature}">{txn_signature[:12]}...</a></p>
                <hr>
                <p style="font-size: 12px; color: #6c757d;">
                    SolAssassin MEV Bot<br>
                    This is an automated notification.
                </p>
            </div>
        </body>
        </html>
        """
        return html

    async def send_trade_notification(self, strategy: str, profit_sol: float, txn_signature: str):
        if not self.enabled:
            logger.info(f"Email notifications disabled. Would have sent: {strategy} profit {profit_sol} SOL")
            return

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🎯 SolAssassin Trade: +{profit_sol:.4f} SOL"
            msg['From'] = self.sender_email
            msg['To'] = self.receiver_email

            html_content = self._format_trade_notification(strategy, profit_sol, txn_signature)
            msg.attach(MIMEText(html_content, 'html'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
                
            logger.info(f"Trade notification email sent: {strategy} profit {profit_sol} SOL")
                
        except Exception as e:
            logger.error(f"Failed to send email notification: {str(e)}")

    async def send_daily_summary(self, strategies, total_profit, total_trades):
        if not self.enabled:
            return
            
        try:
            html = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <div style="padding: 20px; background-color: #f8f9fa; border-radius: 5px;">
                    <h2 style="color: #17a2b8;">📊 Daily Trading Summary</h2>
                    <p><strong>Total Profit:</strong> {total_profit:.4f} SOL</p>
                    <p><strong>Total Trades:</strong> {total_trades}</p>
                    <h3>Strategy Breakdown:</h3>
                    <ul>
            """
            
            for strategy, stats in strategies.items():
                html += f"""
                    <li><strong>{strategy}:</strong>
                        <ul>
                            <li>Profit: {stats['profit']:.4f} SOL</li>
                            <li>Trades: {stats['trades']}</li>
                            <li>Success Rate: {stats['success_rate']:.1f}%</li>
                        </ul>
                    </li>
                """
                
            html += """
                    </ul>
                    <hr>
                    <p style="font-size: 12px; color: #6c757d;">
                        SolAssassin MEV Bot<br>
                        Daily report generated automatically.
                    </p>
                </div>
            </body>
            </html>
            """
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"📊 SolAssassin Daily: +{total_profit:.4f} SOL"
            msg['From'] = self.sender_email
            msg['To'] = self.receiver_email
            msg.attach(MIMEText(html, 'html'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
                
            logger.info("Daily summary email sent successfully")
                
        except Exception as e:
            logger.error(f"Failed to send daily summary email: {str(e)}")
    
    async def send_hourly_kol_update(self, 
                                     tokens_monitored: int,
                                     scans_completed: int,
                                     trades_executed: int,
                                     successful_trades: int,
                                     total_pnl_sol: float,
                                     whales_found: int,
                                     runtime_hours: float):
        """Send hourly KOL sniper status"""
        if not self.enabled:
            return
        
        try:
            success_rate = (successful_trades/trades_executed*100) if trades_executed > 0 else 0
            avg_per_trade = (total_pnl_sol/trades_executed) if trades_executed > 0 else 0
            pnl_usd = total_pnl_sol * 200  # Approx $200/SOL
            
            html = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <div style="padding: 20px; background-color: #f8f9fa; border-radius: 5px;">
                    <h2 style="color: #17a2b8;">🎯 KOL Sniper - Hourly Update</h2>
                    
                    <h3>📊 Activity Summary</h3>
                    <ul>
                        <li><strong>Tokens Monitored:</strong> {tokens_monitored}</li>
                        <li><strong>Scans Completed:</strong> {scans_completed}</li>
                        <li><strong>Trades Executed:</strong> {trades_executed}</li>
                        <li><strong>Successful:</strong> {successful_trades}</li>
                        <li><strong>Success Rate:</strong> {success_rate:.1f}%</li>
                    </ul>
                    
                    <h3>💰 Performance</h3>
                    <ul>
                        <li><strong>Total P&L:</strong> {total_pnl_sol:+.4f} SOL (${pnl_usd:+.2f})</li>
                        <li><strong>Avg per Trade:</strong> {avg_per_trade:.4f} SOL</li>
                    </ul>
                    
                    <h3>🐋 Smart Money</h3>
                    <ul>
                        <li><strong>Whales Detected:</strong> {whales_found}</li>
                    </ul>
                    
                    <h3>⏱️ Runtime</h3>
                    <p>{runtime_hours:.1f} hours</p>
                    
                    <hr>
                    <p style="font-size: 12px; color: #6c757d;">
                        KOL Sniper Bot<br>
                        Status: Active ✅<br>
                        Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
                    </p>
                </div>
            </body>
            </html>
            """
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"🎯 KOL Sniper Hourly - {trades_executed} trades, {total_pnl_sol:+.4f} SOL"
            msg['From'] = self.sender_email
            msg['To'] = self.receiver_email
            msg.attach(MIMEText(html, 'html'))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
                
            logger.info("Hourly KOL sniper email sent successfully")
                
        except Exception as e:
            logger.error(f"Failed to send hourly KOL email: {str(e)}")
