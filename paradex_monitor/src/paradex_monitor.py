#!/usr/bin/env python3
"""
Paradex WebSocket Monitor

A simple CLI tool to monitor Paradex WebSocket feeds.
"""
import asyncio
import json
import logging
import socket
from datetime import datetime
from typing import Any, Dict, List, Optional

import websockets
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/paradex_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
PARADEX_WS_URL = "wss://ws.api.prod.paradex.trade/v1"

# Timeout for WebSocket operations in seconds
WEBSOCKET_TIMEOUT = 10

class ParadexWebSocketMonitor:
    """WebSocket client for monitoring Paradex public feeds."""
    
    def __init__(self):
        """Initialize the WebSocket monitor."""
        self.console = Console()
        self.websocket = None
        self.active_subscriptions = set()
        self.running = False
        
    async def connect(self):
        """Establish WebSocket connection to Paradex."""
        try:
            self.console.print(f"🔌 [bold blue]Connecting to Paradex WebSocket at {PARADEX_WS_URL}...[/]")
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    PARADEX_WS_URL,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5
                ),
                timeout=WEBSOCKET_TIMEOUT
            )
            self.console.print("✅ [bold green]Connected to Paradex WebSocket[/]")
            return True
        except asyncio.TimeoutError:
            error_msg = "Connection attempt timed out"
            self.console.print(f"❌ [bold red]{error_msg}[/]")
            logger.error(error_msg)
        except socket.gaierror as e:
            error_msg = f"DNS resolution failed for {PARADEX_WS_URL}. The Paradex API may not be accessible from this environment or the service might be unavailable."
            self.console.print(f"❌ [bold red]{error_msg}[/]")
            self.console.print("💡 [yellow]Possible solutions:[/]")
            self.console.print("   • Check if Paradex API is currently available")
            self.console.print("   • Verify the WebSocket URL in the Paradex documentation")
            self.console.print("   • Try again later if the service is temporarily down")
            logger.error(error_msg, exc_info=True)
        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            self.console.print(f"❌ [bold red]{error_msg}[/]")
            logger.error(error_msg, exc_info=True)
        return False
    
    async def subscribe(self, channels: List[Dict[str, Any]]) -> None:
        """Subscribe to WebSocket channels using Paradex JSON-RPC format.
        
        Args:
            channels: List of channel subscription objects
        """
        if not self.websocket:
            await self.connect()
            
        # Send subscription messages for each channel
        for i, channel in enumerate(channels):
            # Build subscription parameters with correct market_symbol format
            params = {"channel": channel["name"]}
            if "market_symbol" in channel:
                params["market_symbol"] = channel["market_symbol"]
            elif "markets" in channel and channel["markets"]:
                # Handle legacy markets format
                params["market_symbol"] = channel["markets"][0]  # Use first market
            
            subscribe_msg = {
                "jsonrpc": "2.0",
                "method": "subscribe",
                "params": params,
                "id": i + 1
            }
            
            try:
                await self.websocket.send(json.dumps(subscribe_msg))
                self.active_subscriptions.add(channel['name'])
                market_str = f" ({params.get('market_symbol', 'all')})" if 'market_symbol' in params else ""
                self.console.print(f"📡 Subscribed to channel: {channel['name']}{market_str}")
            except Exception as e:
                self.console.print(f"❌ [bold red]Subscription failed for {channel['name']}: {e}[/]")
                logger.error(f"Subscription failed for {channel['name']}: {e}")
    
    async def unsubscribe(self, channels: List[str]) -> None:
        """Unsubscribe from WebSocket channels.
        
        Args:
            channels: List of channel names to unsubscribe from
        """
        if not self.websocket:
            return
            
        # Send unsubscribe messages for each channel
        for i, channel in enumerate(channels):
            # For unsubscribe, we might not need market_symbol, but let's include it for consistency
            # In a real implementation, you'd want to track which specific subscriptions to unsubscribe
            unsubscribe_msg = {
                "jsonrpc": "2.0",
                "method": "unsubscribe",
                "params": {"channel": channel},
                "id": i + 1
            }
            
            try:
                await self.websocket.send(json.dumps(unsubscribe_msg))
                self.active_subscriptions.discard(channel)
                self.console.print(f"📡 Unsubscribed from channel: {channel}")
            except Exception as e:
                self.console.print(f"❌ [bold red]Unsubscription failed for {channel}: {e}[/]")
                logger.error(f"Unsubscription failed for {channel}: {e}")
    
    def format_message(self, message: Dict[str, Any]) -> str:
        """Format WebSocket message for display.
        
        Args:
            message: The message to format
            
        Returns:
            Formatted message string
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Handle subscription responses (actual market data)
        if message.get('method') == 'subscription':
            params = message.get('params', {})
            channel = params.get('channel', 'unknown')
            data = params.get('data', {})
            
            if channel == 'trades':
                return f"[{timestamp}] [green]Trade[/] {data.get('market', '')} - Price: {data.get('price')} {data.get('side', '').upper()} Size: {data.get('size')}"
            elif channel == 'orderbook':
                return f"[{timestamp}] [yellow]OrderBook[/] {data.get('market', '')} - Bids: {len(data.get('bids', []))}, Asks: {len(data.get('asks', []))}"
            elif channel == 'ticker':
                return f"[{timestamp}] [blue]Ticker[/] {data.get('market', '')} - Last: {data.get('last')} 24h Vol: {data.get('volume24h')}"
            else:
                return f"[{timestamp}] [{channel}] {json.dumps(data, indent=2)}"
        
        # Handle error responses
        elif 'error' in message:
            error = message.get('error', {})
            return f"[{timestamp}] [red]Error[/] {error.get('message', 'Unknown error')}"
        
        # Handle subscription confirmations
        elif message.get('method') == 'subscribe' and 'result' in message:
            return f"[{timestamp}] [green]Subscribed[/] to channel"
        
        # Default formatting for other message types (like connection handshake)
        return f"[{timestamp}] {json.dumps(message, indent=2)}"
    
    async def listen(self):
        """Listen for messages from the WebSocket connection."""
        if not self.websocket:
            if not await self.connect():
                return
        
        self.running = True
        self.console.print("👂 [bold green]Listening for messages... (Press Ctrl+C to stop)[/]")
        
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    formatted = self.format_message(data)
                    self.console.print(formatted)
                    logger.debug(f"Received message: {data}")
                except json.JSONDecodeError:
                    self.console.print(f"[red]Failed to decode message: {message}[/]")
                    logger.error(f"Failed to decode message: {message}")
                except Exception as e:
                    self.console.print(f"[red]Error processing message: {e}[/]")
                    logger.error(f"Error processing message: {e}")
                    
        except websockets.exceptions.ConnectionClosed as e:
            self.console.print(f"[yellow]Connection closed: {e}[/]")
            logger.warning(f"Connection closed: {e}")
            self.running = False
            
        except Exception as e:
            self.console.print(f"[red]Error in WebSocket connection: {e}[/]")
            logger.error(f"Error in WebSocket connection: {e}")
            self.running = False
    
    async def close(self):
        """Close the WebSocket connection."""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            self.console.print("👋 [yellow]Disconnected from Paradex WebSocket[/]")

async def main(test_mode: bool = False):
    """Main function to run the Paradex WebSocket monitor."""
    monitor = ParadexWebSocketMonitor()
    
    if test_mode:
        monitor.console.print("🧪 [bold cyan]Running in test mode - simulating Paradex WebSocket data[/]")
        await run_test_mode(monitor)
        return
    
    # Example subscriptions for ALL markets
    subscriptions = [
        {"name": "trades.ALL"}
    ]
    
    try:
        # Connect and subscribe
        if await monitor.connect():
            await monitor.subscribe(subscriptions)
            # Start listening for messages
            await monitor.listen()
    except KeyboardInterrupt:
        pass
    finally:
        await monitor.close()

async def run_test_mode(monitor: ParadexWebSocketMonitor):
    """Run the monitor in test mode with simulated data."""
    import random
    
    monitor.console.print("✅ [bold green]Test mode activated - simulating WebSocket connection[/]")
    
    # Simulate some test messages
    test_messages = [
        {
            "channel": "ticker",
            "data": {
                "market": "BTC-USD",
                "last": "45000.50",
                "volume24h": "1250.75"
            }
        },
        {
            "channel": "trades",
            "data": {
                "market": "BTC-USD",
                "price": "45123.45",
                "size": "0.25",
                "side": "buy"
            }
        },
        {
            "channel": "orderbook",
            "data": {
                "market": "BTC-USD",
                "bids": [["45000.00", "1.5"], ["44950.00", "2.0"]],
                "asks": [["45100.00", "1.2"], ["45150.00", "0.8"]]
            }
        }
    ]
    
    monitor.running = True
    monitor.console.print("👂 [bold green]Simulating message stream... (Press Ctrl+C to stop)[/]")
    
    try:
        for i in range(10):  # Send 10 test messages
            if not monitor.running:
                break
                
            # Pick a random test message
            test_msg = random.choice(test_messages)
            formatted = monitor.format_message(test_msg)
            monitor.console.print(formatted)
            
            await asyncio.sleep(2)  # Wait 2 seconds between messages
            
    except KeyboardInterrupt:
        pass
    finally:
        monitor.console.print("👋 [yellow]Test mode completed[/]")

if __name__ == "__main__":
    import sys
    
    # Check for test mode flag
    test_mode = "--test" in sys.argv or "-t" in sys.argv
    
    if test_mode:
        asyncio.run(main(test_mode=True))
    else:
        asyncio.run(main())
