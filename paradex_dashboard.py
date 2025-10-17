"""
Paradex Liquidation Dashboard

A real-time dashboard for monitoring liquidations on the Paradex exchange.
"""
import asyncio
import json
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Deque, Any

import pandas as pd
import streamlit as st
import websockets
from streamlit.runtime.scriptrunner import add_script_run_ctx

# Constants
MAX_DATA_POINTS = 1000  # Maximum number of liquidations to keep in memory
PARADEX_WS_URL = "wss://ws.api.prod.paradex.trade/v1"
DB_PATH = "paradex_liquidations.db"

# Global storage for liquidations
liquidations: Deque[Dict[str, Any]] = deque(maxlen=MAX_DATA_POINTS)

# Global connection status (thread-safe)
_connection_status = {"connected": False}

# Streamlit page config
st.set_page_config(
    page_title="Paradex Liquidation Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def set_connection_status(connected: bool):
    """Update connection status (thread-safe)"""
    _connection_status["connected"] = connected

def get_connection_status() -> bool:
    """Get current connection status"""
    return _connection_status["connected"]

def update_connection_display():
    """Update the session state connection status for display"""
    st.session_state.websocket_connected = get_connection_status()

def init_db():
    """Initialize SQLite database and create table if not exists"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS liquidations (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            value REAL NOT NULL,
            time TEXT NOT NULL,
            UNIQUE(timestamp, symbol, side, value)
        )
    """)
    conn.commit()
    conn.close()

def load_liquidations_from_db():
    """Load recent liquidations from database into memory"""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            "SELECT * FROM liquidations ORDER BY timestamp DESC LIMIT ?",
            conn,
            params=(MAX_DATA_POINTS,)
        )
        conn.close()
        
        if not df.empty:
            liquidations.extend(df.to_dict('records'))
            return len(df)
    except Exception as e:
        st.error(f"Error loading liquidations from database: {e}")
    return 0

def save_liquidation_to_db(liquidation: Dict[str, Any]):
    """Save a single liquidation to database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO liquidations 
            (id, timestamp, symbol, side, price, quantity, value, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            liquidation.get('id', ''),
            liquidation.get('timestamp', ''),
            liquidation.get('symbol', ''),
            liquidation.get('side', ''),
            liquidation.get('price', 0.0),
            liquidation.get('quantity', 0.0),
            liquidation.get('value', 0.0),
            liquidation.get('time', '')
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Error saving liquidation to database: {e}")

async def paradex_websocket():
    """Connect to Paradex WebSocket and process trades"""
    while True:
        try:
            set_connection_status(True)
            async with websockets.connect(PARADEX_WS_URL, ping_interval=30, ping_timeout=10, close_timeout=5) as websocket:
                # Subscribe to trades.ALL channel using Paradex JSON-RPC format
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "method": "subscribe",
                    "params": {"channel": "trades.ALL"},
                    "id": 1
                }
                await websocket.send(json.dumps(subscribe_msg))
                while True:
                    message = await websocket.recv()
                    print(f"WS DEBUG: {message}")  # Debug: print all raw messages
                    data = json.loads(message)
                    # Only process trade subscription messages
                    if data.get("method") == "subscription":
                        params = data.get("params", {})
                        channel = params.get("channel", "")
                        if channel == "trades.ALL":
                            trade_data = params.get("data", {})
                            # Terminal color output for trade_type
                            trade_type = trade_data.get('trade_type', '')
                            timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S.%f')[:-3]
                            symbol = trade_data.get('market', '')
                            side = trade_data.get('side', '').upper()
                            price = trade_data.get('price', 0)
                            qty = trade_data.get('size', 0)
                            msg = f"[{timestamp}] {side} {symbol} @ ${float(price):.2f} | Qty: {float(qty):.4f} [{trade_type.upper()}]"
                            if trade_type == "liquidation":
                                print(f"\033[91m{msg}\033[0m")  # Red for liquidation
                            else:
                                print(msg)  # Default color for others
                            process_liquidation(trade_data)
        except (websockets.exceptions.ConnectionClosed, 
                ConnectionRefusedError,
                asyncio.TimeoutError) as e:
            st.error(f"WebSocket connection error: {e}. Reconnecting...")
            set_connection_status(False)
            await asyncio.sleep(5)
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            set_connection_status(False)
            await asyncio.sleep(5)

# Update process_liquidation to handle trade data from trades.ALL

def process_liquidation(data: Dict[str, Any]):
    """Process incoming trade data and add to memory, only for liquidations"""
    try:
        trade_type = data.get('trade_type', '')
        if trade_type != "liquidation":
            return  # Only process liquidation trades
        liquidation = {
            'id': data.get('id', ''),
            'timestamp': data.get('timestamp', ''),
            'symbol': data.get('market', ''),
            'side': data.get('side', '').upper(),
            'price': float(data.get('price', 0)),
            'quantity': float(data.get('size', 0)),
            'value': float(data.get('price', 0)) * float(data.get('size', 0)),
            'trade_type': trade_type,
            'time': datetime.now(timezone.utc).strftime('%H:%M:%S.%f')[:-3]
        }
        liquidations.appendleft(liquidation)
        save_liquidation_to_db(liquidation)
    except Exception as e:
        st.error(f"Error processing trade: {e}")

def get_latest_liquidations(limit: int = 50) -> pd.DataFrame:
    """Get latest liquidations as a DataFrame"""
    if not liquidations:
        return pd.DataFrame()
        
    df = pd.DataFrame(liquidations)
    if not df.empty:
        df = df.head(limit).copy()
        df['value_usd'] = df['value'].apply(lambda x: f"${x:,.2f}")
        df['price_formatted'] = df['price'].apply(lambda x: f"${x:,.2f}")
        df['size'] = df['quantity'].apply(lambda x: f"{x:.4f}")
    return df

def calculate_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate statistics for the dashboard"""
    if df.empty:
        return {
            'total_liquidations': 0,
            'total_volume': 0,
            'avg_size': 0,
            'longs': 0,
            'shorts': 0,
            'top_pairs': []
        }
        
    total_volume = df['value'].sum()
    avg_size = df['value'].mean()
    
    # Count long vs short liquidations
    side_counts = df['side'].value_counts().to_dict()
    
    # Top liquidated pairs
    top_pairs = df['symbol'].value_counts().head(5).to_dict()
    
    return {
        'total_liquidations': len(df),
        'total_volume': total_volume,
        'avg_size': avg_size,
        'longs': side_counts.get('LONG', 0),
        'shorts': side_counts.get('SHORT', 0),
        'top_pairs': [f"{k} ({v})" for k, v in top_pairs.items()]
    }

def start_websocket():
    """Start the WebSocket client in a separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(paradex_websocket())

def main():
    """Main Streamlit app"""
    st.title("Paradex Liquidation Dashboard")
    st.caption("Real-time monitoring of liquidations on Paradex")
    
    # Connection status indicator
    col1, col2 = st.columns([1, 4])
    with col1:
        # Update session state with current connection status
        update_connection_display()
        if st.session_state.get('websocket_connected', False):
            st.success("🟢 Connected to Paradex")
        else:
            st.error("🔴 Disconnected")
    
    # Initialize database and load data
    init_db()
    loaded_count = load_liquidations_from_db()
    
    # Initialize session state for connection status
    if 'websocket_connected' not in st.session_state:
        st.session_state.websocket_connected = False
    
    if loaded_count > 0:
        st.sidebar.success(f"Loaded {loaded_count} liquidations from database")
    
    # Start WebSocket in a separate thread
    if 'websocket_started' not in st.session_state:
        websocket_thread = threading.Thread(target=start_websocket, daemon=True)
        add_script_run_ctx(websocket_thread)
        websocket_thread.start()
        st.session_state.websocket_started = True
    
    # Get latest data
    df = get_latest_liquidations(100)  # Get last 100 liquidations
    
    # Calculate statistics
    stats = calculate_stats(df)
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Liquidations", f"{stats['total_liquidations']:,}")
    with col2:
        st.metric("Total Volume", f"${stats['total_volume']:,.2f}")
    with col3:
        st.metric("Avg. Size", f"${stats['avg_size']:,.2f}")
    with col4:
        st.metric("Long/Short", f"{stats['longs']} / {stats['shorts']}")
    
    # Display top pairs
    st.subheader("Top Liquidated Pairs")
    if stats['top_pairs']:
        st.write(", ".join(stats['top_pairs']))
    else:
        st.info("No liquidation data available yet")
    
    # Data stream display
    st.subheader("Live Data Stream")
    with st.expander("Recent Messages (Last 10)", expanded=False):
        if not liquidations:
            st.info("Waiting for liquidation data...")
        else:
            recent_data = list(liquidations)[:10]
            for i, liq in enumerate(recent_data):
                timestamp = liq.get('time', 'N/A')
                symbol = liq.get('symbol', 'N/A')
                side = liq.get('side', 'N/A')
                price = f"${liq.get('price', 0):.2f}"
                qty = f"{liq.get('quantity', 0):.4f}"
                trade_type = liq.get('trade_type', '')
                msg = f"[{timestamp}] {side} {symbol} @ {price} | Qty: {qty}"
                if trade_type == "liquidation":
                    st.markdown(f"<span style='color:red'>{msg} [LIQUIDATION]</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color:green'>{msg} [{trade_type.upper()}]</span>", unsafe_allow_html=True)
    
    # Display recent liquidations
    st.subheader("Recent Liquidations")
    if not df.empty:
        st.dataframe(
            df[['time', 'symbol', 'side', 'price_formatted', 'size', 'value_usd']],
            column_config={
                'time': 'Time',
                'symbol': 'Pair',
                'side': 'Side',
                'price_formatted': 'Price',
                'size': 'Size',
                'value_usd': 'Value (USD)'
            },
            width='stretch'
        )
    else:
        st.info("Waiting for liquidation data...")
    
    # Auto-refresh every 5 seconds
    time.sleep(5)
    st.rerun()

if __name__ == "__main__":
    main()
