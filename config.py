"""
Configuration module for the AI Crypto Trading Dashboard.

This module provides centralized configuration management for the Flask application,
including database connections, secret keys, and environment-specific settings.
It supports multiple environments (development, testing, production) with secure
defaults and proper validation.

Typical usage example:
    app = Flask(__name__)
    app.config.from_object(Config)
"""

import os
import secrets
from typing import Dict, Optional, Union
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


class ConfigError(Exception):
    """Custom exception for configuration errors."""
    pass


class Config:
    """
    Main configuration class for the Flask application.
    
    This class defines all configuration parameters with secure defaults
    and environment variable overrides. It includes validation for critical
    settings and provides methods for different deployment environments.
    
    Attributes:
        SECRET_KEY: Flask secret key for session management
        SQLALCHEMY_DATABASE_URI: Database connection string
        SQLALCHEMY_TRACK_MODIFICATIONS: SQLAlchemy event tracking flag
        DEBUG: Debug mode flag
        TESTING: Testing mode flag
        ENV: Current environment name
    """
    
    # Flask Core Configuration
    SECRET_KEY: str = os.environ.get(
        'SECRET_KEY',
        secrets.token_hex(32)  # Generate secure random key if not set
    )
    
    # Database Configuration
    # Default to SQLite for development, can be overridden with environment variable
    _default_db_path: str = str(Path(__file__).parent / 'instance' / 'crypto_trading.db')
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        'DATABASE_URL',
        f'sqlite:///{_default_db_path}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    
    # Session Configuration
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = 'Lax'
    
    # Application Configuration
    DEBUG: bool = False
    TESTING: bool = False
    ENV: str = 'production'
    
    # Upload Configuration
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB max upload
    
    # API Configuration
    API_RATE_LIMIT: int = 100  # requests per minute
    API_TIMEOUT: int = 30  # seconds
    
    @classmethod
    def validate(cls) -> None:
        """
        Validate critical configuration parameters.
        
        Raises:
            ConfigError: If any required configuration is invalid or missing
        """
        if not cls.SECRET_KEY or len(cls.SECRET_KEY) < 32:
            raise ConfigError(
                "SECRET_KEY must be at least 32 characters long"
            )
        
        if not cls.SQLALCHEMY_DATABASE_URI:
            raise ConfigError("DATABASE_URL must be configured")
        
        # Validate database URI scheme
        valid_schemes = ['sqlite', 'postgresql', 'mysql', 'mssql']
        scheme = cls.SQLALCHEMY_DATABASE_URI.split('://')[0]
        if scheme not in valid_schemes:
            raise ConfigError(
                f"Invalid database scheme '{scheme}'. Must be one of: {valid_schemes}"
            )
        
        # Ensure instance directory exists for SQLite
        if 'sqlite' in cls.SQLALCHEMY_DATABASE_URI:
            db_path = cls.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')
            if db_path:
                db_dir = Path(db_path).parent
                db_dir.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def init_app(cls, app) -> None:
        """
        Initialize Flask application with configuration.
        
        Args:
            app: Flask application instance
            
        Raises:
            ConfigError: If configuration validation fails
        """
        cls.validate()
        app.config.from_object(cls)
        
        # Set environment-specific configurations
        if cls.ENV == 'development':
            app.config['SESSION_COOKIE_SECURE'] = False
            app.config['DEBUG'] = True
        
        # Log configuration status
        app.logger.info(
            f"Application configured for {cls.ENV} environment"
        )


class DevelopmentConfig(Config):
    """
    Development environment configuration.
    
    Enables debug mode and provides development-friendly defaults.
    """
    
    DEBUG: bool = True
    ENV: str = 'development'
    SESSION_COOKIE_SECURE: bool = False
    
    # Development database (separate from production)
    _dev_db_path: str = str(Path(__file__).parent / 'instance' / 'dev_crypto_trading.db')
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        'DEV_DATABASE_URL',
        f'sqlite:///{_dev_db_path}'
    )


class TestingConfig(Config):
    """
    Testing environment configuration.
    
    Uses in-memory database and enables testing-specific settings.
    """
    
    TESTING: bool = True
    DEBUG: bool = True
    ENV: str = 'testing'
    SESSION_COOKIE_SECURE: bool = False
    
    # Use in-memory SQLite database for tests
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        'TEST_DATABASE_URL',
        'sqlite:///:memory:'
    )
    
    # Disable CSRF for testing
    WTF_CSRF_ENABLED: bool = False


class ProductionConfig(Config):
    """
    Production environment configuration.
    
    Enforces strict security settings and production-ready defaults.
    """
    
    DEBUG: bool = False
    ENV: str = 'production'
    
    @classmethod
    def validate(cls) -> None:
        """
        Extended validation for production environment.
        
        Raises:
            ConfigError: If production requirements are not met
        """
        super().validate()
        
        # Ensure SECRET_KEY is not the default for production
        if cls.SECRET_KEY == Config.SECRET_KEY and not os.environ.get('SECRET_KEY'):
            raise ConfigError(
                "Production environment requires explicit SECRET_KEY configuration"
            )
        
        # Ensure secure session settings
        if not cls.SESSION_COOKIE_SECURE:
            raise ConfigError(
                "Production environment requires SESSION_COOKIE_SECURE=True"
            )


# Configuration dictionary for easy access
config: Dict[str, Config] = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config() -> Config:
    """
    Get the appropriate configuration based on environment.
    
    Returns:
        Config: Configuration class for the current environment
        
    Raises:
        ConfigError: If the environment is not recognized
    """
    env: str = os.environ.get('FLASK_ENV', 'development').lower()
    
    if env not in config:
        raise ConfigError(
            f"Unknown environment '{env}'. Must be one of: {list(config.keys())}"
        )
    
    return config[env]


# Initialize configuration on module import
current_config: Config = get_config()

# Validate configuration on import
try:
    current_config.validate()
except ConfigError as e:
    import logging
    logging.warning(f"Configuration validation warning: {e}")