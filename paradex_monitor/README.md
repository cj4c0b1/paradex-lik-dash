# Paradex WebSocket Monitor

A simple command-line tool to monitor Paradex WebSocket feeds for real-time market data.

## Features

- Connect to Paradex WebSocket API
- Subscribe to multiple market data channels
- Real-time display of order book, trades, and ticker data
- Colorized console output for better readability
- Logging to file for debugging
- Graceful error handling and reconnection

## Prerequisites

- Python 3.8+
- pip (Python package manager)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd paradex_monitor
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the monitor:
   ```bash
   python -m src.paradex_monitor
   ```

2. The monitor will connect to Paradex WebSocket and subscribe to default channels (BTC-USD orderbook, trades, and ticker).

### Test Mode

If the Paradex API is not accessible from your environment, you can run the monitor in test mode:

```bash
python -m src.paradex_monitor --test
# or
python -m src.paradex_monitor -t
```

Test mode will simulate WebSocket messages to demonstrate the functionality without requiring a live connection.

### Available Commands

- `Ctrl+C` - Stop the monitor and disconnect gracefully

## Troubleshooting

### Connection Issues

If you encounter DNS resolution errors or connection failures:

1. **Check API Availability**: Verify that the Paradex API is currently operational
2. **Network Restrictions**: Some environments may block access to cryptocurrency APIs
3. **Service Status**: Check if Paradex services are experiencing downtime

### Common Error Messages

- **"DNS resolution failed"**: The Paradex API domain may not be accessible from your network
- **"Connection timed out"**: The API might be experiencing high load or temporary issues

### Solutions

1. Try running in test mode to verify the application works: `python -m src.paradex_monitor --test`
2. Check the Paradex status page or social media for service updates
3. Verify your internet connection and firewall settings
4. Try again later if the service is temporarily unavailable

## Configuration

You can modify the default subscriptions in the `main()` function of `src/paradex_monitor.py`:

```python
subscriptions = [
    {"name": "orderbook", "markets": ["BTC-USD"]},
    {"name": "trades", "markets": ["BTC-USD"]},
    {"name": "ticker", "markets": ["BTC-USD"]}
]
```

## Logs

Logs are stored in the `logs/` directory with timestamps for debugging purposes.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
