import asyncio
import json
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import websockets
import hashlib
from collections import deque
import time

# Constants
MAX_DATA_POINTS = 1000  # Maximum number of liquidations to keep in memory
ASTER_WS_URL = "wss://fstream.asterdex.com/ws"
#ASTER_WS_URL = "wss://fstream.binance.com/ws"

# Global storage for liquidations
liquidations = deque(maxlen=MAX_DATA_POINTS)

# Streamlit page config
st.set_page_config(
    page_title="Aster Liquidation Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def process_liquidation(data):
    """Process incoming liquidation data and add to memory"""
    try:
        # Extract relevant data
        event = data.get('e')
        if event != 'forceOrder':
            return
            
        order = data.get('o', {})
        timestamp = pd.Timestamp.utcnow()
        
        # Create unique ID
        hash_input = f"{timestamp}:{order.get('s')}:{order.get('S')}:{order.get('q')}".encode('utf-8')
        liquidation_id = hashlib.md5(hash_input).hexdigest()[:8]
        
        # Calculate notional value
        price = float(order.get('ap', 0))
        quantity = float(order.get('q', 0))
        notional = price * quantity
        
        liquidation = {
            'id': liquidation_id,
            'timestamp': timestamp,
            'symbol': order.get('s', ''),
            'side': order.get('S', ''),
            'price': price,
            'quantity': quantity,
            'value': notional,
            'time': timestamp.strftime('%H:%M:%S')
        }
        
        # Add to memory
        liquidations.append(liquidation)
        
    except Exception as e:
        print(f"Error processing liquidation: {e}")

def get_latest_liquidations():
    """Get latest liquidations as a DataFrame"""
    if not liquidations:
        return pd.DataFrame()
    
    df = pd.DataFrame(liquidations)
    
    # Ensure timestamp is datetime
    if not df.empty and 'timestamp' in df.columns:
        if df['timestamp'].dt.tz is None:
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
        else:
            df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
    
    return df

def calculate_stats(df):
    """Calculate statistics for the dashboard"""
    now = pd.Timestamp.now('UTC')
    
    if df.empty:
        return {
            'total_liquidations': 0,
            'last_hour_liquidations': 0,
            'total_volume': 0,
            'hourly_volume': 0,
            'top_symbol': 'N/A',
            'top_side': 'N/A',
            'avg_trade_size': 0,
            'last_updated': now.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    # Last hour stats
    last_hour = now - pd.Timedelta(hours=1)
    recent_df = df[df['timestamp'] >= last_hour]
    
    return {
        'total_liquidations': len(df),
        'last_hour_liquidations': len(recent_df),
        'total_volume': df['value'].sum(),
        'hourly_volume': recent_df['value'].sum() if not recent_df.empty else 0,
        'top_symbol': df['symbol'].value_counts().idxmax(),
        'top_side': df['side'].value_counts().idxmax(),
        'avg_trade_size': df['value'].mean(),
        'last_updated': now.strftime('%Y-%m-%d %H:%M:%S')
    }

async def aster_websocket():
    """Connect to Aster Dex websocket and process liquidations"""
    subscribe_msg = {
        "method": "SUBSCRIBE",
        "params": ["!forceOrder@arr"],
        "id": 1
    }
    while True:
        try:
            async with websockets.connect(ASTER_WS_URL) as websocket:
                print("Connected to Aster Dex WebSocket")
                # Send subscription message after connecting
                await websocket.send(json.dumps(subscribe_msg))
                print("Subscription message sent for !forceOrder@arr")
                while True:
                    try:
                        message = await websocket.recv()
                        data = json.loads(message)
                        process_liquidation(data)
                    except websockets.exceptions.ConnectionClosed:
                        print("WebSocket connection closed. Reconnecting...")
                        break
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        continue
        except Exception as e:
            print(f"WebSocket error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

def start_websocket():
    """Start the websocket client in a separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(aster_websocket())

# Start websocket in a separate thread
import threading
websocket_thread = threading.Thread(target=start_websocket, daemon=True)
websocket_thread.start()

# Main app
def main():
    # Sidebar with branding
    with st.sidebar:
        st.image("static/logo.svg", width=200)
        st.markdown("### Powered by [Asterdex.com](https://www.asterdex.com/en/referral/183633)")
        st.markdown("""
        <div style="background-color: #1E1E1E; padding: 15px; border-radius: 10px; margin-top: 20px;">
            <p style="margin-bottom: 10px;">💸 Start trading on Aster dex with my referral link:</p>
            <p style="margin-bottom: 10px; font-size: 14px; color: #888;">
                <strong>You receive 5% back</strong> from all fees
            </p>
            <a href="https://www.asterdex.com/en/referral/183633" target="_blank" style="color: #4CAF50; text-decoration: none;">
                https://www.asterdex.com/en/referral/183633
            </a>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("---")

    st.title("📊 Real-time Liquidation Dashboard")
    st.markdown("---")

    # Create placeholders
    stats_placeholder = st.empty()
    chart_placeholder = st.empty()
    table_placeholder = st.empty()

    # Main loop
    while True:
        # Get latest data
        df = get_latest_liquidations()
        
        # Calculate stats
        stats = calculate_stats(df)
        
        # Display stats
        with stats_placeholder.container():
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Liquidations", f"{stats['total_liquidations']:,}")
            with col2:
                st.metric("Last Hour", f"{stats['last_hour_liquidations']:,}")
            with col3:
                st.metric("24h Volume", f"${stats['total_volume']/1e6:.1f}M")
            with col4:
                st.metric("Top Symbol", stats['top_symbol'])
        
        # Display chart if we have data
        if not df.empty:
            with chart_placeholder.container():
                st.subheader("Liquidation Volume by Symbol (Last 100)")
                chart_data = df.tail(100).groupby('symbol')['value'].sum().sort_values(ascending=False)
                st.bar_chart(chart_data)
        
        # Display latest liquidations
        with table_placeholder.container():
            st.subheader("Latest Liquidations")
            if not df.empty:
                # Format the display
                display_df = df[['time', 'symbol', 'side', 'quantity', 'price', 'value']].tail(20)
                display_df.columns = ['Time', 'Symbol', 'Side', 'Quantity', 'Price', 'Value']
                display_df['Value'] = display_df['Value'].apply(lambda x: f"${x:,.2f}")
                display_df['Price'] = display_df['Price'].apply(lambda x: f"${x:,.2f}")
                display_df['Quantity'] = display_df['Quantity'].apply(lambda x: f"{x:,.4f}")
                st.dataframe(display_df, width='stretch', hide_index=True)
            else:
                st.info("Waiting for liquidation data...")
        
        # Small delay to prevent high CPU usage
        time.sleep(1)

if __name__ == "__main__":
    main()
