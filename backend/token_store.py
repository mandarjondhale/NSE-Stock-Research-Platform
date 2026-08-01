import os
import sqlite3
import json
import base64
import hashlib
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from dotenv import load_dotenv

# Try to import cryptography
try:
    from cryptography.fernet import Fernet
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

SQLITE_PATH = os.path.join(os.path.dirname(__file__), "broker_connections.db")

def get_encryption_key() -> bytes:
    key = os.environ.get("ENCRYPTION_KEY")
    if key:
        try:
            Fernet(key.encode())
            return key.encode()
        except Exception:
            pass
            
    # Derive key from SUPABASE_KEY or GEMINI_API_KEY
    seed = os.environ.get("SUPABASE_KEY") or os.environ.get("GEMINI_API_KEY") or "fincopilot_default_secret_key_123"
    h = hashlib.sha256(seed.encode()).digest()
    return base64.urlsafe_b64encode(h)

def encrypt(data: Optional[str]) -> Optional[str]:
    if data is None:
        return None
    if not CRYPTOGRAPHY_AVAILABLE:
        key = get_encryption_key().decode()
        xored = "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(data))
        return base64.b64encode(xored.encode()).decode()
        
    key = get_encryption_key()
    f = Fernet(key)
    return f.encrypt(data.encode()).decode()

def decrypt(token: Optional[str]) -> Optional[str]:
    if token is None:
        return None
    try:
        if not CRYPTOGRAPHY_AVAILABLE:
            key = get_encryption_key().decode()
            data = base64.b64decode(token.encode()).decode()
            return "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(data))
            
        key = get_encryption_key()
        f = Fernet(key)
        return f.decrypt(token.encode()).decode()
    except Exception:
        return None

# SQLite Helper Functions
def init_sqlite_db():
    conn = sqlite3.connect(SQLITE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broker_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            broker_name TEXT NOT NULL,
            access_token TEXT,
            refresh_token TEXT,
            api_key TEXT,
            api_secret TEXT,
            client_code TEXT,
            totp_key TEXT,
            expires_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_email, broker_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            buy_price REAL NOT NULL,
            sector TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_email, ticker)
        )
    """)
    conn.commit()
    conn.close()

# Initialize DB on import
init_sqlite_db()

class TokenStore:
    @staticmethod
    def save_connection(
        user_email: str,
        broker_name: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        client_code: Optional[str] = None,
        totp_key: Optional[str] = None,
        expires_at: Optional[str] = None,
        sb_client: Optional[Any] = None
    ) -> bool:
        """
        Saves broker connection tokens/keys.
        Attempts to save to Supabase table 'broker_connections' first.
        Falls back to local SQLite storage.
        All secrets (tokens, api_secret, totp_key) are encrypted.
        """
        broker_name = broker_name.lower().strip()
        
        # Encrypt the sensitive fields
        enc_access_token = encrypt(access_token)
        enc_refresh_token = encrypt(refresh_token)
        enc_api_key = encrypt(api_key) # API key is also considered sensitive
        enc_api_secret = encrypt(api_secret)
        enc_totp_key = encrypt(totp_key)
        
        payload = {
            "user_email": user_email,
            "broker_name": broker_name,
            "access_token": enc_access_token,
            "refresh_token": enc_refresh_token,
            "api_key": enc_api_key,
            "api_secret": enc_api_secret,
            "client_code": client_code,
            "totp_key": enc_totp_key,
            "expires_at": expires_at,
        }
        
        # Try Supabase first
        if sb_client:
            try:
                # Check if connection exists
                existing = sb_client.table("broker_connections") \
                                   .select("*") \
                                   .eq("user_email", user_email) \
                                   .eq("broker_name", broker_name) \
                                   .execute()
                if existing.data:
                    sb_client.table("broker_connections") \
                             .update(payload) \
                             .eq("id", existing.data[0]["id"]) \
                             .execute()
                else:
                    sb_client.table("broker_connections") \
                             .insert(payload) \
                             .execute()
                return True
            except Exception as e:
                print(f"Supabase save failed for broker_connections: {e}. Falling back to SQLite.")
                
        # SQLite fallback
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO broker_connections 
                (user_email, broker_name, access_token, refresh_token, api_key, api_secret, client_code, totp_key, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_email,
                broker_name,
                enc_access_token,
                enc_refresh_token,
                enc_api_key,
                enc_api_secret,
                client_code,
                enc_totp_key,
                expires_at
            ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"SQLite save failed: {e}")
            return False

    @staticmethod
    def get_connection(user_email: str, broker_name: str, sb_client: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves and decrypts broker connection tokens/keys.
        """
        broker_name = broker_name.lower().strip()
        data = None
        
        # Try Supabase first
        if sb_client:
            try:
                res = sb_client.table("broker_connections") \
                               .select("*") \
                               .eq("user_email", user_email) \
                               .eq("broker_name", broker_name) \
                               .execute()
                if res.data:
                    data = res.data[0]
            except Exception as e:
                print(f"Supabase fetch failed for broker_connections: {e}. Checking SQLite.")
                
        # Try SQLite if not found in Supabase
        if not data:
            try:
                conn = sqlite3.connect(SQLITE_PATH)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM broker_connections 
                    WHERE user_email = ? AND broker_name = ?
                """, (user_email, broker_name))
                row = cursor.fetchone()
                if row:
                    data = dict(row)
                conn.close()
            except Exception as e:
                print(f"SQLite fetch failed: {e}")
                
        if not data:
            return None
            
        # Decrypt sensitive fields
        return {
            "user_email": data.get("user_email"),
            "broker_name": data.get("broker_name"),
            "access_token": decrypt(data.get("access_token")),
            "refresh_token": decrypt(data.get("refresh_token")),
            "api_key": decrypt(data.get("api_key")),
            "api_secret": decrypt(data.get("api_secret")),
            "client_code": data.get("client_code"),
            "totp_key": decrypt(data.get("totp_key")),
            "expires_at": data.get("expires_at")
        }

    @staticmethod
    def delete_connection(user_email: str, broker_name: str, sb_client: Optional[Any] = None) -> bool:
        broker_name = broker_name.lower().strip()
        success = False
        
        if sb_client:
            try:
                sb_client.table("broker_connections") \
                         .delete() \
                         .eq("user_email", user_email) \
                         .eq("broker_name", broker_name) \
                         .execute()
                success = True
            except Exception as e:
                print(f"Supabase delete failed: {e}")
                
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM broker_connections 
                WHERE user_email = ? AND broker_name = ?
            """, (user_email, broker_name))
            conn.commit()
            conn.close()
            success = True
        except Exception as e:
            print(f"SQLite delete failed: {e}")
            
        return success

    @staticmethod
    def save_holdings(user_email: str, holdings: list, sb_client: Optional[Any] = None) -> bool:
        """
        Saves user portfolio holdings.
        Saves to Supabase table 'portfolio_holdings' first, falls back to SQLite.
        """
        # Save to Supabase
        if sb_client:
            try:
                # To avoid complex joins, we delete existing and batch insert
                sb_client.table("portfolio_holdings").delete().eq("user_email", user_email).execute()
                if holdings:
                    payload = [
                        {
                            "user_email": user_email,
                            "ticker": h["ticker"].upper().strip(),
                            "shares": float(h["shares"]),
                            "buy_price": float(h["buy_price"]),
                            "sector": h.get("sector", "Unknown")
                        }
                        for h in holdings
                    ]
                    sb_client.table("portfolio_holdings").insert(payload).execute()
                return True
            except Exception as e:
                print(f"Supabase save holdings failed: {e}. Falling back to SQLite.")

        # Save to SQLite
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM portfolio_holdings WHERE user_email = ?", (user_email,))
            for h in holdings:
                cursor.execute("""
                    INSERT OR REPLACE INTO portfolio_holdings (user_email, ticker, shares, buy_price, sector)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    user_email,
                    h["ticker"].upper().strip(),
                    float(h["shares"]),
                    float(h["buy_price"]),
                    h.get("sector", "Unknown")
                ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"SQLite save holdings failed: {e}")
            return False

    @staticmethod
    def get_holdings(user_email: str, sb_client: Optional[Any] = None) -> list:
        """
        Gets user portfolio holdings from Supabase or SQLite.
        """
        # Try Supabase first
        if sb_client:
            try:
                res = sb_client.table("portfolio_holdings").select("*").eq("user_email", user_email).execute()
                if res.data:
                    return [
                        {
                            "ticker": h["ticker"],
                            "shares": h["shares"],
                            "buy_price": h["buy_price"],
                            "sector": h.get("sector", "Unknown")
                        }
                        for h in res.data
                    ]
            except Exception as e:
                print(f"Supabase get holdings failed: {e}. Checking SQLite.")

        # Try SQLite fallback
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM portfolio_holdings WHERE user_email = ?", (user_email,))
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    "ticker": r["ticker"],
                    "shares": r["shares"],
                    "buy_price": r["buy_price"],
                    "sector": r["sector"]
                }
                for r in rows
            ]
        except Exception as e:
            print(f"SQLite get holdings failed: {e}")
            return []

