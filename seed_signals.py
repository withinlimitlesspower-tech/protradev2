#!/usr/bin/env python3
"""
Seed Script for Crypto Trading Signals Database

This script populates the SQLite database with initial demo trading signals
for testing and development purposes. It creates realistic sample data
including various signal types, confidence levels, and historical accuracy.

Usage:
    python seed_signals.py [--force] [--count N]

Options:
    --force     Drop existing data before seeding
    --count N   Number of signals to generate (default: 50)

Requirements:
    - Flask application must be configured with DATABASE_URL
    - SQLite database must exist (created by Flask app initialization)
"""

import argparse
import datetime
import logging
import os
import random
import sqlite3
import sys
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'sqlite:///crypto_signals.db'
)

# Convert SQLAlchemy URL to SQLite path
def get_db_path(db_url: str) -> str:
    """Extract SQLite file path from database URL."""
    if db_url.startswith('sqlite:///'):
        return db_url[10:]
    return db_url

# Sample data for realistic signal generation
CRYPTOCURRENCIES = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
    'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT',
    'LINK/USDT', 'UNI/USDT', 'ATOM/USDT', 'LTC/USDT', 'BCH/USDT'
]

SIGNAL_TYPES = ['BUY', 'SELL']
CONFIDENCE_LEVELS = ['LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH']

SIGNAL_STRATEGIES = [
    'RSI Divergence',
    'MACD Crossover',
    'Moving Average Breakout',
    'Bollinger Band Squeeze',
    'Fibonacci Retracement',
    'Support/Resistance Break',
    'Volume Profile Analysis',
    'Ichimoku Cloud',
    'Elliott Wave Pattern',
    'Order Flow Imbalance'
]

ACCURACY_STATUSES = ['CORRECT', 'INCORRECT', 'PENDING']

# Realistic price ranges for different cryptocurrencies
PRICE_RANGES = {
    'BTC/USDT': (30000, 70000),
    'ETH/USDT': (1500, 4000),
    'BNB/USDT': (200, 600),
    'SOL/USDT': (20, 150),
    'XRP/USDT': (0.3, 1.5),
    'ADA/USDT': (0.2, 1.0),
    'DOGE/USDT': (0.05, 0.3),
    'AVAX/USDT': (10, 50),
    'DOT/USDT': (4, 20),
    'MATIC/USDT': (0.5, 2.5),
    'LINK/USDT': (5, 20),
    'UNI/USDT': (3, 15),
    'ATOM/USDT': (5, 20),
    'LTC/USDT': (50, 200),
    'BCH/USDT': (100, 500)
}


def validate_configuration() -> Tuple[bool, str]:
    """
    Validate that the database configuration is correct.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not DATABASE_URL:
        return False, "DATABASE_URL environment variable is not set"
    
    if not DATABASE_URL.startswith('sqlite:///'):
        return False, f"Unsupported database URL: {DATABASE_URL}"
    
    db_path = get_db_path(DATABASE_URL)
    db_dir = os.path.dirname(db_path) or '.'
    
    if not os.path.exists(db_dir):
        return False, f"Database directory does not exist: {db_dir}"
    
    return True, ""


def create_connection() -> sqlite3.Connection:
    """
    Create and return a database connection.
    
    Returns:
        SQLite connection object
        
    Raises:
        sqlite3.Error: If connection fails
    """
    db_path = get_db_path(DATABASE_URL)
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


def initialize_database(conn: sqlite3.Connection) -> None:
    """
    Create necessary tables if they don't exist.
    
    Args:
        conn: SQLite database connection
    """
    try:
        cursor = conn.cursor()
        
        # Create signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL CHECK(signal_type IN ('BUY', 'SELL')),
                entry_price REAL NOT NULL CHECK(entry_price > 0),
                current_price REAL,
                target_price REAL,
                stop_loss REAL,
                confidence TEXT NOT NULL CHECK(confidence IN ('LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH')),
                strategy TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                accuracy_status TEXT DEFAULT 'PENDING' CHECK(accuracy_status IN ('CORRECT', 'INCORRECT', 'PENDING')),
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_symbol 
            ON signals(symbol)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_timestamp 
            ON signals(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_accuracy 
            ON signals(accuracy_status)
        """)
        
        conn.commit()
        logger.info("Database tables initialized successfully")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database: {e}")
        conn.rollback()
        raise


def clear_existing_data(conn: sqlite3.Connection) -> None:
    """
    Remove all existing signal data from the database.
    
    Args:
        conn: SQLite database connection
    """
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM signals")
        conn.commit()
        logger.info("Existing signal data cleared successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to clear existing data: {e}")
        conn.rollback()
        raise


def generate_signal_data(index: int, total: int) -> Dict:
    """
    Generate realistic signal data for a single trading signal.
    
    Args:
        index: Current signal index (0-based)
        total: Total number of signals to generate
        
    Returns:
        Dictionary containing signal data
    """
    # Select cryptocurrency
    symbol = random.choice(CRYPTOCURRENCIES)
    
    # Generate realistic prices
    price_range = PRICE_RANGES.get(symbol, (1, 100))
    entry_price = round(random.uniform(*price_range), 2)
    
    # Determine signal type and calculate target/stop
    signal_type = random.choice(SIGNAL_TYPES)
    
    if signal_type == 'BUY':
        target_price = round(entry_price * (1 + random.uniform(0.02, 0.15)), 2)
        stop_loss = round(entry_price * (1 - random.uniform(0.01, 0.08)), 2)
    else:  # SELL
        target_price = round(entry_price * (1 - random.uniform(0.02, 0.15)), 2)
        stop_loss = round(entry_price * (1 + random.uniform(0.01, 0.08)), 2)
    
    # Generate current price (may differ from entry for realism)
    current_price = round(entry_price * (1 + random.uniform(-0.05, 0.05)), 2)
    
    # Select confidence level with weighted distribution
    confidence_weights = [0.1, 0.3, 0.4, 0.2]  # LOW, MEDIUM, HIGH, VERY_HIGH
    confidence = random.choices(CONFIDENCE_LEVELS, weights=confidence_weights)[0]
    
    # Select strategy
    strategy = random.choice(SIGNAL_STRATEGIES)
    
    # Generate timestamp (spread over last 30 days)
    days_ago = random.randint(0, 30)
    hours_ago = random.randint(0, 23)
    minutes_ago = random.randint(0, 59)
    
    timestamp = datetime.datetime.now() - datetime.timedelta(
        days=days_ago,
        hours=hours_ago,
        minutes=minutes_ago
    )
    
    # Determine accuracy status (more recent signals are PENDING)
    if days_ago < 7:
        accuracy_status = 'PENDING'
    else:
        accuracy_status = random.choices(
            ACCURACY_STATUSES,
            weights=[0.6, 0.25, 0.15]  # CORRECT, INCORRECT, PENDING
        )[0]
    
    # Generate notes
    notes_templates = [
        f"Strong {signal_type} signal on {symbol} based on {strategy}",
        f"{confidence} confidence {signal_type} setup on {symbol}",
        f"Technical {signal_type} signal with clear risk/reward ratio",
        f"{symbol} showing {strategy} pattern - {signal_type} opportunity",
        f"Conservative {signal_type} entry on {symbol} with tight stop"
    ]
    notes = random.choice(notes_templates)
    
    return {
        'symbol': symbol,
        'signal_type': signal_type,
        'entry_price': entry_price,
        'current_price': current_price,
        'target_price': target_price,
        'stop_loss': stop_loss,
        'confidence': confidence,
        'strategy': strategy,
        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
        'accuracy_status': accuracy_status,
        'notes': notes
    }


def insert_signal(conn: sqlite3.Connection, signal_data: Dict) -> bool:
    """
    Insert a single signal record into the database.
    
    Args:
        conn: SQLite database connection
        signal_data: Dictionary containing signal data
        
    Returns:
        True if successful, False otherwise
    """
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signals (
                symbol, signal_type, entry_price, current_price,
                target_price, stop_loss, confidence, strategy,
                timestamp, accuracy_status, notes
            ) VALUES (
                :symbol, :signal_type, :entry_price, :current_price,
                :target_price, :stop_loss, :confidence, :strategy,
                :timestamp, :accuracy_status, :notes
            )
        """, signal_data)
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to insert signal: {e}")
        return False


def seed_signals(conn: sqlite3.Connection, count: int = 50, force: bool = False) -> int:
    """
    Seed the database with demo trading signals.
    
    Args:
        conn: SQLite database connection
        count: Number of signals to generate (default: 50)
        force: If True, clear existing data before seeding
        
    Returns:
        Number of signals successfully inserted
        
    Raises:
        ValueError: If count is invalid
    """
    if count < 1 or count > 1000:
        raise ValueError(f"Invalid signal count: {count}. Must be between 1 and 1000")
    
    if force:
        clear_existing_data(conn)
    
    successful_inserts = 0
    
    logger.info(f"Generating {count} demo signals...")
    
    for i in range(count):
        try:
            signal_data = generate_signal_data(i, count)
            
            if insert_signal(conn, signal_data):
                successful_inserts += 1
                
                # Log progress every 10 signals
                if (i + 1) % 10 == 0:
                    logger.info(f"Progress: {i + 1}/{count} signals generated")
                    
        except Exception as e:
            logger.error(f"Error generating signal {i + 1}: {e}")
            continue
    
    conn.commit()
    logger.info(f"Successfully inserted {successful_inserts} out of {count} signals")
    
    return successful_inserts


def verify_seeding(conn: sqlite3.Connection) -> Dict:
    """
    Verify the seeding results and return statistics.
    
    Args:
        conn: SQLite database connection
        
    Returns:
        Dictionary containing seeding statistics
    """
    try:
        cursor = conn.cursor()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) as total FROM signals")
        total = cursor.fetchone()['total']
        
        # Get counts by signal type
        cursor.execute("""
            SELECT signal_type, COUNT(*) as count 
            FROM signals 
            GROUP BY signal_type
        """)
        type_counts = {row['signal_type']: row['count'] for row in cursor.fetchall()}
        
        # Get counts by confidence level
        cursor.execute("""
            SELECT confidence, COUNT(*) as count 
            FROM signals 
            GROUP BY confidence
        """)
        confidence_counts = {row['confidence']: row['count'] for row in cursor.fetchall()}
        
        # Get counts by accuracy status
        cursor.execute("""
            SELECT accuracy_status, COUNT(*) as count 
            FROM signals 
            GROUP BY accuracy_status
        """)
        accuracy_counts = {row['accuracy_status']: row['count'] for row in cursor.fetchall()}
        
        # Get date range
        cursor.execute("""
            SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest 
            FROM signals
        """)
        date_range = cursor.fetchone()
        
        return {
            'total_signals': total,
            'by_type': type_counts,
            'by_confidence': confidence_counts,
            'by_accuracy': accuracy_counts,
            'date_range': {
                'earliest': date_range['earliest'],
                'latest': date_range['latest']
            }
        }
        
    except sqlite3.Error as e:
        logger.error(f"Failed to verify seeding: {e}")
        return {}


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description='Seed crypto trading signals database with demo data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python seed_signals.py                    # Seed 50 signals
    python seed_signals.py --count 100        # Seed 100 signals
    python seed_signals.py --force            # Clear and reseed 50 signals
    python seed_signals.py --force --count 200  # Clear and reseed 200 signals
        """
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Drop existing data before seeding'
    )
    
    parser.add_argument(
        '--count',
        type=int,
        default=50,
        help='Number of signals to generate (default: 50, max: 1000)'
    )
    
    return parser.parse_args()


def main() -> int:
    """
    Main entry point for the seeding script.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Parse command line arguments
    args = parse_arguments()
    
    # Validate configuration
    is_valid, error_message = validate_configuration()
    if not is_valid:
        logger.error(f"Configuration error: {error_message}")
        return 1
    
    try:
        # Create database connection
        conn = create_connection()
        
        # Initialize database tables
        initialize_database(conn)
        
        # Seed signals
        inserted_count = seed_signals(
            conn,
            count=args.count,
            force=args.force
        )
        
        if inserted_count == 0:
            logger.warning("No signals were inserted")
            conn.close()
            return 1
        
        # Verify seeding
        stats = verify_seeding(conn)
        
        # Display results
        logger.info("=" * 50)
        logger.info("SEEDING COMPLETE - STATISTICS")
        logger.info("=" * 50)
        logger.info(f"Total signals: {stats.get('total_signals', 0)}")
        logger.info(f"By type: {stats.get('by_type', {})}")
        logger.info(f"By confidence: {stats.get('by_confidence', {})}")
        logger.info(f"By accuracy: {stats.get('by_accuracy', {})}")
        logger.info(f"Date range: {stats.get('date_range', {})}")
        logger.info("=" * 50)
        
        # Close connection
        conn.close()
        
        return 0
        
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())