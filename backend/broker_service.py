"""
broker_service.py
=================
Handles secure integration with major brokers:
- Zerodha Kite Connect
- Upstox API
- Angel One SmartAPI
- Binance API
- CoinDCX API

Saves credentials encrypted in TokenStore. No mock data fallbacks.
"""

import os
import time
import json
import hmac
import hashlib
import struct
import base64
import logging
import requests
from typing import Dict, List, Optional, Any

from token_store import TokenStore

logger = logging.getLogger("FinCopilot.BrokerService")

# --- Try imports for official SDKs ---
try:
    from kiteconnect import KiteConnect
    KITE_AVAILABLE = True
except ImportError:
    KITE_AVAILABLE = False
    logger.warning("kiteconnect package not found. Zerodha API will fall back to direct HTTP requests or raise exceptions.")


def generate_totp(secret: str) -> str:
    """
    Generates a 6-digit TOTP code from a Google Authenticator Base32 secret key.
    Pure-python implementation with zero external dependencies.
    """
    try:
        secret = secret.replace(" ", "").upper()
        # Add padding if needed
        missing_padding = len(secret) % 8
        if missing_padding:
            secret += "=" * (8 - missing_padding)
            
        key = base64.b32decode(secret, casefold=True)
        # Time counter (30 second intervals)
        counter = struct.pack(">Q", int(time.time() / 30))
        
        # HMAC-SHA1 signature
        mac = hmac.new(key, counter, hashlib.sha1).digest()
        
        # Dynamic truncation
        offset = mac[-1] & 0x0f
        binary = struct.unpack(">I", mac[offset:offset+4])[0] & 0x7fffffff
        
        # 6 digit code
        code = binary % 1000000
        return f"{code:06d}"
    except Exception as e:
        logger.error(f"Error generating TOTP: {e}")
        raise ValueError(f"Invalid TOTP secret key: {e}")


class BrokerService:
    @staticmethod
    def get_login_url(broker: str, redirect_uri: str) -> Dict[str, Any]:
        """
        Generates the redirection URL for broker OAuth login.
        """
        broker = broker.lower().strip()

        # --- ZERODHA ---
        if broker == "zerodha":
            api_key = os.environ.get("ZERODHA_API_KEY")
            if not api_key:
                raise ValueError("ZERODHA_API_KEY is not configured in the environment.")
            
            if KITE_AVAILABLE:
                try:
                    kite = KiteConnect(api_key=api_key)
                    # kite.login_url() returns redirect link to kite.trade
                    login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
                    return {"url": login_url, "is_direct": False, "is_mock": False}
                except Exception as e:
                    logger.error(f"Error generating Kite login URL: {e}")
                    raise RuntimeError(f"Could not generate Zerodha login URL: {str(e)}")
            else:
                login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
                return {"url": login_url, "is_direct": False, "is_mock": False}

        # --- UPSTOX ---
        elif broker == "upstox":
            api_key = os.environ.get("UPSTOX_API_KEY")
            if not api_key:
                raise ValueError("UPSTOX_API_KEY is not configured in the environment.")
            login_url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={api_key}&redirect_uri={redirect_uri}"
            return {"url": login_url, "is_direct": False, "is_mock": False}

        # --- ANGEL ONE ---
        elif broker == "angelone":
            api_key = os.environ.get("ANGEL_ONE_API_KEY")
            if not api_key:
                raise ValueError("ANGEL_ONE_API_KEY is not configured in the environment.")
            # SmartAPI has a publisher login flow
            login_url = f"https://smartapi.angelbroking.com/publisher-login?api_key={api_key}"
            return {"url": login_url, "is_direct": True, "is_mock": False}

        # --- CRYPTO EXCHANGE DIRECT LOGINS ---
        elif broker in ["binance", "coindcx"]:
            return {"is_direct": True, "is_mock": False}

        else:
            raise ValueError(f"Unsupported broker: {broker}")

    @staticmethod
    def handle_callback(broker: str, request_token: str, redirect_uri: str, user_email: str, sb_client: Optional[Any] = None) -> List[Dict]:
        """
        Exchanges callback token/code for access tokens and saves them.
        """
        broker = broker.lower().strip()

        if request_token.startswith("mock_success_token_"):
            raise ValueError("Mock logins are not permitted on this production system. Configure real API credentials.")

        # --- ZERODHA ---
        if broker == "zerodha":
            api_key = os.environ.get("ZERODHA_API_KEY")
            api_secret = os.environ.get("ZERODHA_API_SECRET")
            if not api_key or not api_secret:
                raise ValueError("Zerodha credentials (API Key and Secret) are missing in environment.")
                
            if not KITE_AVAILABLE:
                raise RuntimeError("kiteconnect package is not installed on the system.")
                
            try:
                kite = KiteConnect(api_key=api_key)
                data = kite.generate_session(request_token, api_secret=api_secret)
                access_token = data["access_token"]
                
                # Save connection encrypted
                TokenStore.save_connection(
                    user_email=user_email,
                    broker_name="zerodha",
                    access_token=access_token,
                    api_key=api_key,
                    api_secret=api_secret,
                    sb_client=sb_client
                )
                
                # Fetch holdings
                kite.set_access_token(access_token)
                raw_holdings = kite.holdings()
                return BrokerService._parse_holdings("zerodha", raw_holdings)
            except Exception as e:
                logger.error(f"Zerodha callback exchange failed: {e}")
                raise RuntimeError(f"Zerodha Authentication Failed: {str(e)}")

        # --- UPSTOX ---
        elif broker == "upstox":
            api_key = os.environ.get("UPSTOX_API_KEY")
            api_secret = os.environ.get("UPSTOX_API_SECRET")
            if not api_key or not api_secret:
                raise ValueError("Upstox credentials (API Key and Secret) are missing in environment.")
                
            try:
                # Exchange Authorization Code for Access Token
                url = "https://api.upstox.com/v2/login/authorization/token"
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                data = {
                    "code": request_token,
                    "client_id": api_key,
                    "client_secret": api_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code"
                }
                
                res = requests.post(url, headers=headers, data=data, timeout=10)
                res_data = res.json()
                
                if res.status_code != 200:
                    raise ValueError(res_data.get("errors", [{}])[0].get("message", "Token exchange failed"))
                    
                access_token = res_data["access_token"]
                
                # Save connection encrypted
                TokenStore.save_connection(
                    user_email=user_email,
                    broker_name="upstox",
                    access_token=access_token,
                    api_key=api_key,
                    api_secret=api_secret,
                    sb_client=sb_client
                )
                
                # Fetch holdings
                return BrokerService._fetch_upstox_holdings(access_token)
            except Exception as e:
                logger.error(f"Upstox callback exchange failed: {e}")
                raise RuntimeError(f"Upstox Authentication Failed: {str(e)}")

        else:
            raise ValueError(f"Callback not supported for direct-credential broker: {broker}")

    @staticmethod
    def connect_direct_credentials(broker: str, user_email: str, credentials: dict, sb_client: Optional[Any] = None) -> List[Dict]:
        """
        Validates credentials and connects direct-input brokers.
        """
        broker = broker.lower().strip()

        # --- ANGEL ONE ---
        if broker == "angelone":
            client_code = credentials.get("client_code")
            password = credentials.get("password")
            api_key = credentials.get("api_key")
            totp_key = credentials.get("totp_key")
            
            if not client_code or not password or not api_key or not totp_key:
                raise ValueError("Missing required credentials for Angel One connection.")
                
            try:
                # Generate TOTP code
                totp_code = generate_totp(totp_key)
                
                # Login bypass API
                url = "https://apiconnect.angelone.in/api/v1/user/auth/v1/login/bypass"
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-PrivateKey": api_key,
                    "X-UserType": "USER",
                    "X-SourceID": "WEB",
                    "X-ClientLocalIP": "127.0.0.1",
                    "X-MACAddress": "00:00:00:00:00:00"
                }
                payload = {
                    "clientcode": client_code,
                    "password": password,
                    "totp": totp_code
                }
                
                res = requests.post(url, headers=headers, json=payload, timeout=12)
                res_data = res.json()
                
                if not res_data.get("status", False):
                    raise ValueError(res_data.get("message", "Angel One login failed"))
                    
                jwt_token = res_data["data"]["jwtToken"]
                
                # Save connection encrypted
                TokenStore.save_connection(
                    user_email=user_email,
                    broker_name="angelone",
                    access_token=jwt_token,
                    api_key=api_key,
                    api_secret=password, # Save password securely in api_secret column
                    client_code=client_code,
                    totp_key=totp_key,
                    sb_client=sb_client
                )
                
                # Fetch holdings
                return BrokerService._fetch_angelone_holdings(jwt_token, api_key, client_code)
            except Exception as e:
                logger.error(f"Angel One connection failed: {e}")
                raise RuntimeError(f"Angel One Connection Failed: {str(e)}")

        # --- BINANCE ---
        elif broker == "binance":
            api_key = credentials.get("api_key")
            api_secret = credentials.get("api_secret")
            
            if not api_key or not api_secret:
                raise ValueError("Missing API Key or API Secret for Binance.")
                
            try:
                # Validate by calling Binance account info endpoint
                url = "https://api.binance.com/api/v3/account"
                timestamp = int(time.time() * 1000)
                query_string = f"timestamp={timestamp}"
                signature = hmac.new(api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()
                
                headers = {"X-MBX-APIKEY": api_key}
                res = requests.get(f"{url}?{query_string}&signature={signature}", headers=headers, timeout=10)
                res_data = res.json()
                
                if res.status_code != 200:
                    raise ValueError(res_data.get("msg", "Binance credentials invalid"))
                    
                # Save connection encrypted
                TokenStore.save_connection(
                    user_email=user_email,
                    broker_name="binance",
                    api_key=api_key,
                    api_secret=api_secret,
                    sb_client=sb_client
                )
                
                return BrokerService._parse_binance_balances(res_data.get("balances", []))
            except Exception as e:
                logger.error(f"Binance verification failed: {e}")
                raise RuntimeError(f"Binance Verification Failed: {str(e)}")

        # --- COINDCX ---
        elif broker == "coindcx":
            api_key = credentials.get("api_key")
            api_secret = credentials.get("api_secret")
            
            if not api_key or not api_secret:
                raise ValueError("Missing API Key or API Secret for CoinDCX.")
                
            try:
                # Validate by calling CoinDCX balances endpoint
                url = "https://api.coindcx.com/exchange/v1/users/balances"
                payload = {"timestamp": int(time.time() * 1000)}
                payload_str = json.dumps(payload, separators=(',', ':'))
                
                signature = hmac.new(api_secret.encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha256).hexdigest()
                
                headers = {
                    "Content-Type": "application/json",
                    "X-API-KEY": api_key,
                    "signature": signature
                }
                
                res = requests.post(url, headers=headers, data=payload_str, timeout=10)
                res_data = res.json()
                
                if res.status_code != 200:
                    raise ValueError(res_data.get("message", "CoinDCX credentials invalid"))
                    
                # Save connection encrypted
                TokenStore.save_connection(
                    user_email=user_email,
                    broker_name="coindcx",
                    api_key=api_key,
                    api_secret=api_secret,
                    sb_client=sb_client
                )
                
                return BrokerService._parse_coindcx_balances(res_data)
            except Exception as e:
                logger.error(f"CoinDCX verification failed: {e}")
                raise RuntimeError(f"CoinDCX Verification Failed: {str(e)}")

        else:
            raise ValueError(f"Direct connection not supported for broker: {broker}")

    @staticmethod
    def fetch_holdings(broker: str, user_email: str, sb_client: Optional[Any] = None) -> List[Dict]:
        """
        Fetches holdings for an already linked broker using stored credentials.
        """
        broker = broker.lower().strip()
        conn_data = TokenStore.get_connection(user_email, broker, sb_client)
        if not conn_data:
            raise ValueError(f"No connected credentials found for {broker}. Please link your account.")

        try:
            # --- ZERODHA ---
            if broker == "zerodha":
                if KITE_AVAILABLE:
                    kite = KiteConnect(api_key=conn_data["api_key"])
                    kite.set_access_token(conn_data["access_token"])
                    raw_holdings = kite.holdings()
                    holdings = BrokerService._parse_holdings("zerodha", raw_holdings)
                else:
                    raise RuntimeError("KiteConnect library not installed on backend.")

            # --- UPSTOX ---
            elif broker == "upstox":
                holdings = BrokerService._fetch_upstox_holdings(conn_data["access_token"])

            # --- ANGEL ONE ---
            elif broker == "angelone":
                # Angel One JWT tokens expire quickly. We refresh it by doing a bypass login again
                # since we saved client_code, password, and totp_key.
                client_code = conn_data["client_code"]
                password = conn_data["api_secret"] # we saved password in api_secret
                api_key = conn_data["api_key"]
                totp_key = conn_data["totp_key"]
                
                totp_code = generate_totp(totp_key)
                url = "https://apiconnect.angelone.in/api/v1/user/auth/v1/login/bypass"
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-PrivateKey": api_key,
                    "X-UserType": "USER",
                    "X-SourceID": "WEB",
                    "X-ClientLocalIP": "127.0.0.1",
                    "X-MACAddress": "00:00:00:00:00:00"
                }
                res = requests.post(url, headers=headers, json={
                    "clientcode": client_code,
                    "password": password,
                    "totp": totp_code
                }, timeout=12)
                res_data = res.json()
                if not res_data.get("status", False):
                    raise ValueError("Failed to refresh Angel One session: " + res_data.get("message", ""))
                    
                jwt_token = res_data["data"]["jwtToken"]
                # Save refreshed JWT token
                TokenStore.save_connection(
                    user_email=user_email,
                    broker_name="angelone",
                    access_token=jwt_token,
                    api_key=api_key,
                    api_secret=password,
                    client_code=client_code,
                    totp_key=totp_key,
                    sb_client=sb_client
                )
                holdings = BrokerService._fetch_angelone_holdings(jwt_token, api_key, client_code)

            # --- BINANCE ---
            elif broker == "binance":
                url = "https://api.binance.com/api/v3/account"
                timestamp = int(time.time() * 1000)
                query_string = f"timestamp={timestamp}"
                signature = hmac.new(conn_data["api_secret"].encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()
                
                headers = {"X-MBX-APIKEY": conn_data["api_key"]}
                res = requests.get(f"{url}?{query_string}&signature={signature}", headers=headers, timeout=10)
                res_data = res.json()
                if res.status_code != 200:
                    raise ValueError(res_data.get("msg", "Binance fetch failed"))
                holdings = BrokerService._parse_binance_balances(res_data.get("balances", []))

            # --- COINDCX ---
            elif broker == "coindcx":
                url = "https://api.coindcx.com/exchange/v1/users/balances"
                payload = {"timestamp": int(time.time() * 1000)}
                payload_str = json.dumps(payload, separators=(',', ':'))
                
                signature = hmac.new(conn_data["api_secret"].encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha256).hexdigest()
                headers = {
                    "Content-Type": "application/json",
                    "X-API-KEY": conn_data["api_key"],
                    "signature": signature
                }
                res = requests.post(url, headers=headers, data=payload_str, timeout=10)
                if res.status_code != 200:
                    raise ValueError(res.json().get("message", "CoinDCX fetch failed"))
                holdings = BrokerService._parse_coindcx_balances(res.json())

            else:
                raise ValueError(f"Invalid broker: {broker}")

            # Save fetched holdings in store
            TokenStore.save_holdings(user_email, holdings, sb_client)
            return holdings
        except Exception as e:
            logger.error(f"Error fetching holdings from {broker}: {e}")
            # Fallback: get last saved holdings from local database store
            saved_holdings = TokenStore.get_holdings(user_email, sb_client)
            if saved_holdings:
                logger.info(f"Using cached database holdings for {broker} due to connection error.")
                return saved_holdings
            raise RuntimeError(f"Failed to fetch holdings from {broker}: {str(e)}")

    # --- Private Helpers ---
    @staticmethod
    def _fetch_upstox_holdings(access_token: str) -> List[Dict]:
        url = "https://api.upstox.com/v2/portfolio/long-term-holdings"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res_data = res.json()
        
        if res.status_code != 200:
            raise ValueError(res_data.get("errors", [{}])[0].get("message", "Upstox holdings request failed"))
            
        raw_holdings = res_data.get("data", [])
        return BrokerService._parse_holdings("upstox", raw_holdings)

    @staticmethod
    def _fetch_angelone_holdings(jwt_token: str, api_key: str, client_code: str) -> List[Dict]:
        url = "https://apiconnect.angelone.in/rest/secure/angelbroking/portfolio/v1/getHolding"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-PrivateKey": api_key,
            "X-ClientID": client_code,
            "X-UserType": "USER",
            "X-SourceID": "WEB"
        }
        res = requests.get(url, headers=headers, timeout=12)
        res_data = res.json()
        
        if not res_data.get("status", False):
            raise ValueError(res_data.get("message", "Angel One holdings request failed"))
            
        raw_holdings = res_data.get("data", [])
        return BrokerService._parse_holdings("angelone", raw_holdings)

    @staticmethod
    def _parse_holdings(broker: str, raw_holdings: list) -> List[Dict]:
        holdings = []
        for h in raw_holdings:
            if broker == "zerodha":
                ticker = h.get("tradingsymbol", "")
                shares = float(h.get("quantity", 0) + h.get("t1_quantity", 0))
                buy_price = float(h.get("average_price", 0))
            elif broker == "upstox":
                ticker = h.get("tradingsymbol", "")
                shares = float(h.get("quantity", 0))
                buy_price = float(h.get("average_price", 0))
            elif broker == "angelone":
                ticker = h.get("tradingsymbol", "")
                shares = float(h.get("quantity", 0))
                buy_price = float(h.get("averageprice", 0))
            else:
                continue

            if not ticker or shares <= 0:
                continue

            # Standardize sector name placeholder
            holdings.append({
                "ticker": ticker.upper().strip(),
                "shares": shares,
                "buy_price": buy_price,
                "sector": "Broker Import"
            })
        return holdings

    @staticmethod
    def _parse_binance_balances(balances: list) -> List[Dict]:
        holdings = []
        for b in balances:
            free = float(b.get("free", 0))
            locked = float(b.get("locked", 0))
            total = free + locked
            
            if total <= 0:
                continue
                
            asset = b.get("asset", "").upper().strip()
            # Skip standard fee assets if negligible
            if asset in ["BNB"] and total < 0.001:
                continue
                
            # Get current crypto price in USD first from Binance public ticker
            current_price_inr = 0.0
            if asset == "USDT" or asset == "BUSD":
                current_price_inr = 83.5 # USD to INR conversion
            else:
                try:
                    res = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT", timeout=5)
                    if res.status_code == 200:
                        price_usd = float(res.json().get("price", 0))
                        current_price_inr = price_usd * 83.5 # USD to INR conversion
                except Exception:
                    pass
                    
            holdings.append({
                "ticker": f"{asset}-USD", # Use format compatible with yfinance/tracking
                "shares": total,
                "buy_price": current_price_inr, # Buy price fallback to current if unavailable
                "sector": "Cryptocurrency"
            })
        return holdings

    @staticmethod
    def _parse_coindcx_balances(balances: list) -> List[Dict]:
        holdings = []
        for b in balances:
            qty = float(b.get("balance", 0))
            if qty <= 0:
                continue
                
            asset = b.get("currency", "").upper().strip()
            current_price_inr = 0.0
            
            if asset == "INR":
                current_price_inr = 1.0
            else:
                # Retrieve price from CoinDCX ticker or fallback to standard USDT conversions
                try:
                    res = requests.get("https://api.coindcx.com/exchange/ticker", timeout=5)
                    if res.status_code == 200:
                        # CoinDCX ticker list contains multiple symbols like 'BTCINR'
                        ticker_data = next((t for t in res.json() if t.get("market") == f"{asset}INR"), None)
                        if ticker_data:
                            current_price_inr = float(ticker_data.get("last_price", 0))
                except Exception:
                    pass
                    
            holdings.append({
                "ticker": f"{asset}-INR" if asset != "INR" else "INR",
                "shares": qty,
                "buy_price": current_price_inr,
                "sector": "Cryptocurrency"
            })
        return holdings
