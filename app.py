"""
Flask Backend for AI Crypto Trading Dashboard
Provides routes for chat, signals, voice/file upload, and database operations
"""

import os
import json
import uuid
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

import numpy as np
import pandas as pd
from flask import (
    Flask, 
    request, 
    jsonify, 
    session, 
    send_from_directory,
    make_response
)
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24).hex())
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = Path('uploads')
app.config['DATABASE_PATH'] = Path('database/trading.db')
app.config['ALLOWED_EXTENSIONS'] = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'wav', 'mp3', 'mp4'}

# Ensure directories exist
app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)
app.config['DATABASE_PATH'].parent.mkdir(parents=True, exist_ok=True)

# Initialize CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Database setup
def get_db() -> sqlite3.Connection:
    """Get database connection with row factory"""
    conn = sqlite3.connect(str(app.config['DATABASE_PATH']))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db() -> None:
    """Initialize database with required tables"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Signals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL CHECK(signal_type IN ('BUY', 'SELL', 'NEUTRAL')),
                price REAL NOT NULL,
                confidence REAL DEFAULT 0.0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'EXECUTED', 'EXPIRED', 'CANCELLED')),
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # Chat messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        # Signal accuracy tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signal_accuracy (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                actual_outcome TEXT NOT NULL CHECK(actual_outcome IN ('PROFIT', 'LOSS', 'PENDING')),
                profit_loss REAL DEFAULT 0.0,
                accuracy_score REAL DEFAULT 0.0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE CASCADE
            )
        ''')
        
        # File uploads table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                metadata TEXT DEFAULT '{}'
            )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
        
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        raise
    finally:
        conn.close()

# Initialize database on startup
with app.app_context():
    init_db()

# Helper functions
def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def validate_signal_data(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate signal input data"""
    required_fields = ['symbol', 'signal_type', 'price']
    
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    if data['signal_type'] not in ['BUY', 'SELL', 'NEUTRAL']:
        return False, "Invalid signal_type. Must be BUY, SELL, or NEUTRAL"
    
    try:
        price = float(data['price'])
        if price <= 0:
            return False, "Price must be positive"
    except (ValueError, TypeError):
        return False, "Invalid price value"
    
    return True, None

def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent injection"""
    import html
    return html.escape(text.strip())

# API Routes
@app.route('/api/health', methods=['GET'])
def health_check() -> Dict[str, Any]:
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    })

# Signal routes
@app.route('/api/signals', methods=['GET'])
def get_signals() -> Dict[str, Any]:
    """Get all signals with optional filtering"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get query parameters
        symbol = request.args.get('symbol', '').upper()
        status = request.args.get('status', '').upper()
        limit = min(int(request.args.get('limit', 100)), 1000)
        offset = int(request.args.get('offset', 0))
        
        # Build query
        query = "SELECT * FROM signals WHERE 1=1"
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        signals = [dict(row) for row in cursor.fetchall()]
        
        # Get total count
        count_query = "SELECT COUNT(*) as total FROM signals WHERE 1=1"
        count_params = []
        
        if symbol:
            count_query += " AND symbol = ?"
            count_params.append(symbol)
        
        if status:
            count_query += " AND status = ?"
            count_params.append(status)
        
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['total']
        
        return jsonify({
            'success': True,
            'data': signals,
            'total': total,
            'limit': limit,
            'offset': offset
        })
        
    except Exception as e:
        logger.error(f"Error fetching signals: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/signals', methods=['POST'])
@limiter.limit("10 per minute")
def create_signal() -> Dict[str, Any]:
    """Create a new trading signal"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Validate input
        is_valid, error_msg = validate_signal_data(data)
        if not is_valid:
            return jsonify({'success': False, 'error': error_msg}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Insert signal
        cursor.execute('''
            INSERT INTO signals (symbol, signal_type, price, confidence, metadata)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            sanitize_input(data['symbol'].upper()),
            data['signal_type'],
            float(data['price']),
            float(data.get('confidence', 0.0)),
            json.dumps(data.get('metadata', {}))
        ))
        
        conn.commit()
        signal_id = cursor.lastrowid
        
        logger.info(f"Created signal {signal_id} for {data['symbol']}")
        
        return jsonify({
            'success': True,
            'message': 'Signal created successfully',
            'signal_id': signal_id
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating signal: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/signals/<int:signal_id>', methods=['PUT'])
def update_signal(signal_id: int) -> Dict[str, Any]:
    """Update signal status"""
    try:
        data = request.get_json()
        
        if not data or 'status' not in data:
            return jsonify({'success': False, 'error': 'Status field required'}), 400
        
        valid_statuses = ['ACTIVE', 'EXECUTED', 'EXPIRED', 'CANCELLED']
        if data['status'] not in valid_statuses:
            return jsonify({'success': False, 'error': f'Invalid status. Must be one of {valid_statuses}'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE signals 
            SET status = ?, metadata = json_set(COALESCE(metadata, '{}'), '$.updated_at', ?)
            WHERE id = ?
        ''', (data['status'], datetime.utcnow().isoformat(), signal_id))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Signal not found'}), 404
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'message': f'Signal {signal_id} updated to {data["status"]}'
        })
        
    except Exception as e:
        logger.error(f"Error updating signal {signal_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

# Chat routes
@app.route('/api/chat', methods=['POST'])
@limiter.limit("30 per minute")
def chat_message() -> Dict[str, Any]:
    """Process chat messages and return AI response"""
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({'success': False, 'error': 'Message field required'}), 400
        
        message = sanitize_input(data['message'])
        session_id = data.get('session_id', str(uuid.uuid4()))
        
        # Store user message
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO chat_messages (session_id, role, content)
            VALUES (?, 'user', ?)
        ''', (session_id, message))
        
        # Generate AI response (simulated for now)
        ai_response = generate_ai_response(message, session_id)
        
        # Store AI response
        cursor.execute('''
            INSERT INTO chat_messages (session_id, role, content)
            VALUES (?, 'assistant', ?)
        ''', (session_id, ai_response))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'response': ai_response,
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

def generate_ai_response(message: str, session_id: str) -> str:
    """Generate AI response based on message context"""
    # This is a placeholder - in production, integrate with actual AI model
    message_lower = message.lower()
    
    if 'signal' in message_lower or 'trade' in message_lower:
        return "I can help analyze trading signals. What cryptocurrency are you interested in?"
    elif 'price' in message_lower:
        return "I can provide price analysis. Please specify the cryptocurrency pair (e.g., BTC/USDT)."
    elif 'help' in message_lower:
        return "I can assist with: trading signals, market analysis, portfolio tracking, and answering crypto-related questions."
    else:
        return "I'm your AI trading assistant. How can I help you with your crypto trading today?"

@app.route('/api/chat/history', methods=['GET'])
def get_chat_history() -> Dict[str, Any]:
    """Get chat history for a session"""
    try:
        session_id = request.args.get('session_id')
        limit = min(int(request.args.get('limit', 50)), 500)
        
        if not session_id:
            return jsonify({'success': False, 'error': 'Session ID required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM chat_messages 
            WHERE session_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (session_id, limit))
        
        messages = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'data': messages,
            'total': len(messages)
        })
        
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

# File upload routes
@app.route('/api/upload', methods=['POST'])
@limiter.limit("10 per minute")
def upload_file() -> Dict[str, Any]:
    """Handle file uploads"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'File type not allowed'}), 400
        
        # Secure filename and save
        original_filename = secure_filename(file.filename)
        filename = f"{uuid.uuid4()}_{original_filename}"
        file_path = app.config['UPLOAD_FOLDER'] / filename
        
        file.save(str(file_path))
        file_size = file_path.stat().st_size
        
        # Store file metadata in database
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO file_uploads (filename, original_filename, file_type, file_size, session_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            filename,
            original_filename,
            original_filename.rsplit('.', 1)[1].lower(),
            file_size,
            request.form.get('session_id')
        ))
        
        conn.commit()
        file_id = cursor.lastrowid
        
        logger.info(f"File uploaded: {original_filename} ({file_size} bytes)")
        
        return jsonify({
            'success': True,
            'message': 'File uploaded successfully',
            'file_id': file_id,
            'filename': original_filename,
            'size': file_size
        }), 201
        
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/uploads/<int:file_id>', methods=['GET'])
def get_upload(file_id: int) -> Any:
    """Get uploaded file metadata or download file"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM file_uploads WHERE id = ?', (file_id,))
        file_record = cursor.fetchone()
        
        if not file_record:
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        file_record = dict(file_record)
        
        # Check if download is requested
        if request.args.get('download', 'false').lower() == 'true':
            return send_from_directory(
                str(app.config['UPLOAD_FOLDER']),
                file_record['filename'],
                as_attachment=True,
                download_name=file_record['original_filename']
            )
        
        return jsonify({
            'success': True,
            'data': file_record
        })
        
    except Exception as e:
        logger.error(f"Error fetching file {file_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

# Signal accuracy routes
@app.route('/api/accuracy', methods=['POST'])
def record_accuracy() -> Dict[str, Any]:
    """Record signal accuracy for tracking"""
    try:
        data = request.get_json()
        
        if not data or 'signal_id' not in data:
            return jsonify({'success': False, 'error': 'Signal ID required'}), 400
        
        required_fields = ['signal_id', 'actual_outcome']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing field: {field}'}), 400
        
        if data['actual_outcome'] not in ['PROFIT', 'LOSS', 'PENDING']:
            return jsonify({'success': False, 'error': 'Invalid outcome'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Calculate accuracy score
        accuracy_score = 1.0 if data['actual_outcome'] == 'PROFIT' else 0.0
        
        cursor.execute('''
            INSERT INTO signal_accuracy (signal_id, actual_outcome, profit_loss, accuracy_score)
            VALUES (?, ?, ?, ?)
        ''', (
            data['signal_id'],
            data['actual_outcome'],
            float(data.get('profit_loss', 0.0)),
            accuracy_score
        ))
        
        conn.commit()
        
        # Update signal status if executed
        if data['actual_outcome'] in ['PROFIT', 'LOSS']:
            cursor.execute('''
                UPDATE signals SET status = 'EXECUTED' WHERE id = ?
            ''', (data['signal_id'],))
            conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Accuracy recorded successfully'
        }), 201
        
    except Exception as e:
        logger.error(f"Error recording accuracy: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/accuracy/stats', methods=['GET'])
def get_accuracy_stats() -> Dict[str, Any]:
    """Get accuracy statistics"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Overall statistics
        cursor.execute('''
            SELECT 
                COUNT(*) as total_signals,
                SUM(CASE WHEN actual_outcome = 'PROFIT' THEN 1 ELSE 0 END) as profitable,
                SUM(CASE WHEN actual_outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                AVG(accuracy_score) as avg_accuracy,
                SUM(profit_loss) as total_profit_loss
            FROM signal_accuracy
            WHERE actual_outcome != 'PENDING'
        ''')
        
        stats = dict(cursor.fetchone())
        
        # Per symbol statistics
        cursor.execute('''
            SELECT 
                s.symbol,
                COUNT(*) as total,
                SUM(CASE WHEN sa.actual_outcome = 'PROFIT' THEN 1 ELSE 0 END) as profitable,
                AVG(sa.accuracy_score) as accuracy
            FROM signal_accuracy sa
            JOIN signals s ON sa.signal_id = s.id
            WHERE sa.actual_outcome != 'PENDING'
            GROUP BY s.symbol
        ''')
        
        per_symbol = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'data': {
                'overall': stats,
                'per_symbol': per_symbol
            }
        })
        
    except Exception as e:
        logger.error(f"Error fetching accuracy stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

# Error handlers
@app.errorhandler(404)
def not_found(error: HTTPException) -> Dict[str, Any]:
    """Handle 404 errors"""
    return jsonify({
        'success': False,
        'error': 'Resource not found',
        'status_code': 404
    }), 404

@app.errorhandler(400)
def bad_request(error: HTTPException) -> Dict[str, Any]:
    """Handle 400 errors"""
    return jsonify({
        'success': False,
        'error': 'Bad request',
        'status_code': 400
    }), 400

@app.errorhandler(429)
def ratelimit_handler(error: HTTPException) -> Dict[str, Any]:
    """Handle rate limiting"""
    return jsonify({
        'success': False,
        'error': 'Rate limit exceeded. Please try again later.',
        'status_code': 429
    }), 429

@app.errorhandler(500)
def internal_error(error: HTTPException) -> Dict[str, Any]:
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'success': False,
        'error': 'Internal server error',
        'status_code': 500
    }), 500

# Main entry point
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV', 'production') == 'development'
    
    logger.info(f"Starting Flask server on port {port} (debug={debug})")
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    )