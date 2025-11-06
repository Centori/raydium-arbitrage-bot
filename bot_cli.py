#!/usr/bin/env python3
import click
import json
import os
from decimal import Decimal
from solders.keypair import Keypair
from api_client import BlockchainAPIClient
from config import Config

class BotCLI:
    def __init__(self):
        self.config = Config()
        self.api_client = BlockchainAPIClient(self.config)

    async def get_balance(self):
        """Get wallet balance"""
        balance = await self.api_client.get_sol_balance()
        return float(balance)

    async def get_token_balances(self):
        """Get all token balances"""
        return await self.api_client.get_token_balances()

    async def get_strategy_stats(self):
        """Get strategy performance stats"""
        return await self.api_client.get_strategy_stats()

    async def update_settings(self, settings):
        """Update bot settings"""
        return await self.api_client.update_settings(settings)

@click.group()
def cli():
    """Raydium Arbitrage Bot CLI"""
    pass

@cli.command()
def balance():
    """Show SOL and token balances"""
    import asyncio
    bot = BotCLI()
    
    async def show_balances():
        # Get SOL balance
        sol_balance = await bot.get_balance()
        click.echo(f"\nSOL Balance: {sol_balance:.4f} SOL")
        
        # Get token balances
        token_balances = await bot.get_token_balances()
        if token_balances:
            click.echo("\nToken Balances:")
            for token in token_balances:
                click.echo(f"  {token['symbol']}: {token['amount']:.4f} "
                         f"(${token['usd_value']:.2f})")
    
    asyncio.run(show_balances())

@cli.command()
def stats():
    """Show bot performance statistics"""
    import asyncio
    bot = BotCLI()
    
    async def show_stats():
        stats = await bot.get_strategy_stats()
        
        click.echo("\nStrategy Performance:")
        click.echo(f"Total Profit: ${stats['total_profit_usd']:.2f}")
        click.echo(f"Total Trades: {stats['total_trades']}")
        click.echo(f"Success Rate: {stats['success_rate']:.1f}%")
        
        click.echo("\nLast 24 Hours:")
        click.echo(f"Profit: ${stats['profit_24h']:.2f}")
        click.echo(f"Trades: {stats['trades_24h']}")
        
        if stats['recent_trades']:
            click.echo("\nRecent Trades:")
            for trade in stats['recent_trades'][:5]:
                click.echo(
                    f"  {trade['timestamp']}: {trade['type']} "
                    f"{trade['token_symbol']} "
                    f"Profit: ${trade['profit_usd']:.2f}"
                )
    
    asyncio.run(show_stats())

@cli.command()
@click.option('--strategy', type=click.Choice(['flash_loan', 'migration', 'both']))
@click.option('--amount', type=float, help='Max trade amount in SOL')
@click.option('--enable/--disable', default=None)
def configure(strategy, amount, enable):
    """Configure bot settings"""
    import asyncio
    bot = BotCLI()
    
    async def update_config():
        settings = {}
        
        if strategy:
            if strategy == 'both':
                settings['enable_flash_loans'] = enable
                settings['enable_migration'] = enable
            elif strategy == 'flash_loan':
                settings['enable_flash_loans'] = enable
            else:
                settings['enable_migration'] = enable
                
        if amount is not None:
            settings['max_trade_size_sol'] = amount
            
        if settings:
            result = await bot.update_settings(settings)
            if result['success']:
                click.echo("\nSettings updated successfully!")
                
                # Show new configuration
                click.echo("\nCurrent Configuration:")
                click.echo(f"Flash Loan Strategy: {'Enabled' if result['config']['enable_flash_loans'] else 'Disabled'}")
                click.echo(f"Migration Strategy: {'Enabled' if result['config']['enable_migration'] else 'Disabled'}")
                click.echo(f"Max Trade Size: {result['config']['max_trade_size_sol']:.3f} SOL")
            else:
                click.echo("\nError updating settings!")
        else:
            click.echo("No settings specified to update!")
    
    asyncio.run(update_config())

@cli.command()
@click.option('--limit', default=10, help='Number of traders to show')
def elite_traders(limit):
    """Show top performing elite traders and their activities"""
    import asyncio
    from solana_elite_tracker import SolanaEliteTracker
    
    async def show_elite_traders():
        tracker = SolanaEliteTracker(bot.config)
        
        # Get top traders
        top_traders = tracker.get_top_traders(limit)
        
        click.echo("\nTop Elite Traders:")
        for i, trader in enumerate(top_traders, 1):
            click.echo(f"\n{i}. Wallet: {trader.wallet_address}")
            click.echo(f"   Win Rate: {trader.win_rate*100:.1f}%")
            click.echo(f"   Total Return: {trader.total_return_pct:.1f}%")
            click.echo(f"   24h Volume: ${float(trader.total_volume_24h):,.2f}")
            click.echo(f"   Performance Score: {trader.performance_score:.2f}")
            click.echo(f"   Active on: {', '.join(trader.trading_program_ids)}")
    
    asyncio.run(show_elite_traders())

@cli.command()
def venues():
    """Show active venue statistics and rankings"""
    import asyncio
    from venue_tracker import VenueTracker
    
    async def show_venues():
        tracker = VenueTracker(bot.config)
        
        # Get venue rankings
        venues = await tracker.get_venue_rankings()
        
        click.echo("\nActive Venues by Liquidity:")
        for venue in venues:
            click.echo(f"\n{venue.name}:")
            click.echo(f"  Total Liquidity: ${float(venue.total_liquidity_usd):,.2f}")
            click.echo(f"  24h Volume: ${float(venue.daily_volume_usd):,.2f}")
            click.echo(f"  Active Pools: {venue.active_pools}")
            click.echo(f"  New Pools (24h): {venue.new_pools_24h}")
            click.echo(f"  Avg Pool Size: ${float(venue.avg_pool_liquidity):,.2f}")
    
    asyncio.run(show_venues())

@cli.command()
def launches():
    """Show recent token launches across venues"""
    import asyncio
    from venue_tracker import VenueTracker
    
    async def show_launches():
        tracker = VenueTracker(bot.config)
        
        # Get recent launches
        launches = await tracker.get_recent_launches()
        
        if not launches:
            click.echo("\nNo recent launches detected")
            return
        
        click.echo("\nRecent Token Launches:")
        for launch in launches:
            click.echo(f"\n{launch.token_name} ({launch.token_symbol}):")
            click.echo(f"  Launch Platform: {launch.launch_platform}")
            click.echo(f"  Initial Liquidity: ${float(launch.initial_liquidity_usd):,.2f}")
            click.echo(f"  Elite Traders: {launch.elite_trader_count}")
            if len(launch.venue_interactions) > 1:
                click.echo("  Cross-venue Activity:")
                for venue, liquidity in launch.venue_interactions.items():
                    click.echo(f"    - {venue}: ${float(liquidity):,.2f}")
    
    asyncio.run(show_launches())

@cli.command()
def liquidity_signals():
    """Show current liquidity signals from elite traders"""
    import asyncio
    from solana_elite_tracker import SolanaEliteTracker
    
    async def show_signals():
        tracker = SolanaEliteTracker(bot.config)
        signals = await tracker._generate_trading_signals()
        
        if not signals:
            click.echo("\nNo significant signals currently")
            return
        
        click.echo("\nCurrent Trading Signals:")
        for signal in signals:
            click.echo(f"\nToken: {signal['token_symbol']}")
            click.echo(f"Elite Traders: {signal['elite_traders']}")
            click.echo(f"Total Liquidity: ${signal['total_liquidity']:,.2f}")
            click.echo(f"Signal Strength: {signal['signal_strength']:.2f}")
            click.echo(f"Age: {int(time.time() - signal['timestamp'])} seconds")
    
    asyncio.run(show_signals())

@cli.command()
def status():
    """Show bot status and active strategies"""
    import asyncio
    bot = BotCLI()
    
    async def show_status():
        status = await bot.api_client.get_bot_status()
        
        click.echo("\nBot Status:")
        click.echo(f"Running: {'Yes' if status['is_running'] else 'No'}")
        click.echo(f"Uptime: {status['uptime']}")
        
        click.echo("\nActive Strategies:")
        if status['active_strategies']['flash_loan']:
            click.echo("- Flash Loan Arbitrage")
        if status['active_strategies']['migration']:
            click.echo("- Migration Strategy")
            
        if status['current_operations']:
            click.echo("\nCurrent Operations:")
            for op in status['current_operations']:
                click.echo(f"- {op['type']}: {op['details']}")
                
        click.echo(f"\nLast Check: {status['last_check_time']}")
        click.echo(f"Next Check: {status['next_check_time']}")
    
    asyncio.run(show_status())

@cli.command()
@click.argument('action', type=click.Choice(['start', 'stop', 'restart']))
def bot(action):
    """Control bot execution (start/stop/restart)"""
    import asyncio
    bot = BotCLI()
    
    async def control_bot():
        result = await bot.api_client.control_bot(action)
        if result['success']:
            click.echo(f"\nBot {action}ed successfully!")
            if action in ['start', 'restart']:
                click.echo(f"PID: {result['pid']}")
        else:
            click.echo(f"\nError {action}ing bot: {result['error']}")
    
    asyncio.run(control_bot())

@cli.command()
def monitor():
    """Monitor bot activity in real-time"""
    import asyncio
    import time
    bot = BotCLI()
    
    async def watch_activity():
        click.echo("\nMonitoring bot activity (Ctrl+C to stop)...")
        try:
            while True:
                status = await bot.api_client.get_bot_status()
                click.clear()
                
                # Show basic status
                click.echo("\nBot Status:")
                click.echo(f"Running: {'Yes' if status['is_running'] else 'No'}")
                click.echo(f"Uptime: {status['uptime']}")
                
                # Show active operations
                if status['current_operations']:
                    click.echo("\nCurrent Operations:")
                    for op in status['current_operations']:
                        click.echo(f"- {op['type']}: {op['details']}")
                
                # Show recent activity
                if status['recent_activity']:
                    click.echo("\nRecent Activity:")
                    for activity in status['recent_activity'][:5]:
                        click.echo(f"- {activity['time']}: {activity['message']}")
                
                await asyncio.sleep(5)  # Update every 5 seconds
                
        except KeyboardInterrupt:
            click.echo("\nStopped monitoring.")
    
    asyncio.run(watch_activity())

if __name__ == '__main__':
    cli()