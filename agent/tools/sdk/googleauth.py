# agent/config/google_auth.py

import os
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from agno.utils.log import logger

# Load environment variables
load_dotenv()


class GoogleAuth:
    """
    Clean Google Calendar Authentication Handler

    Usage:
        auth = GoogleAuth(user_id="123456")
        service = auth.login()  # First time: opens browser, saves token
                               # Next times: loads saved token
    """

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self, user_id: str):
        """
        Initialize Google Auth for a specific user

        Args:
            user_id: Unique identifier for the user (e.g., Telegram user ID)
        """
        self.user_id = user_id

        # Set up file paths
        self.base_dir = os.path.dirname(__file__)
        self.tokens_dir = os.path.join(self.base_dir, 'tokens')
        self.token_path = os.path.join(self.tokens_dir, f'google_token_{user_id}.json')

        # Ensure tokens directory exists
        os.makedirs(self.tokens_dir, exist_ok=True)

        # Get OAuth credentials from environment
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Missing Google OAuth credentials. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env file")

        self.creds = None
        self.service = None

    def login(self):
        """
        Authenticate and return Google Calendar service

        Returns:
            Google Calendar service object

        Raises:
            Exception: If authentication fails
        """
        try:
            # Check if we have valid credentials
            if self._load_existing_token():
                logger.info(f"✅ Loaded existing token for user {self.user_id}")
            else:
                logger.info(f"🔐 Starting OAuth flow for user {self.user_id}")
                self._run_oauth_flow()

            # Create the service
            self.service = build("calendar", "v3", credentials=self.creds)
            logger.info(f"✅ Google Calendar service initialized for user {self.user_id}")
            return self.service

        except Exception as e:
            logger.error(f"❌ Authentication failed for user {self.user_id}: {str(e)}")
            raise Exception(f"Google authentication failed: {str(e)}")

    def _load_existing_token(self) -> bool:
        """
        Try to load existing token from file

        Returns:
            True if token loaded successfully, False otherwise
        """
        if not os.path.exists(self.token_path):
            logger.debug(f"No token file found: {self.token_path}")
            return False

        try:
            # Load credentials from file
            self.creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)

            # Check if credentials are valid
            if not self.creds or not self.creds.valid:
                # Try to refresh if possible
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    logger.info(f"🔄 Refreshing expired token for user {self.user_id}")
                    self.creds.refresh(Request())
                    self._save_token()
                    return True
                else:
                    logger.debug(f"Token invalid or no refresh token available")
                    return False

            return True

        except Exception as e:
            logger.warning(f"Failed to load token: {str(e)}")
            return False

    def _run_oauth_flow(self):
        """
        Run the OAuth2 flow to get new credentials
        """
        try:
            # Create OAuth client configuration from environment variables
            client_config = {
                "installed": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
                }
            }

            # Create OAuth flow
            flow = InstalledAppFlow.from_client_config(client_config, self.SCOPES)

            # Run the flow (opens browser)
            print(f"🌐 Opening browser for Google authentication (user {self.user_id})...")
            self.creds = flow.run_local_server(port=0)

            # Save the token
            self._save_token()
            logger.info(f"✅ New token saved for user {self.user_id}")

        except Exception as e:
            raise Exception(f"OAuth flow failed: {str(e)}")

    def _save_token(self):
        """
        Save credentials to token file
        """
        try:
            with open(self.token_path, 'w') as token_file:
                token_file.write(self.creds.to_json())
            logger.debug(f"Token saved: {self.token_path}")
        except Exception as e:
            logger.error(f"Failed to save token: {str(e)}")
            raise

    def is_authenticated(self) -> bool:
        """
        Check if user is currently authenticated

        Returns:
            True if authenticated, False otherwise
        """
        return self.creds is not None and self.creds.valid

    def logout(self):
        """
        Remove saved token (force re-authentication next time)
        """
        try:
            if os.path.exists(self.token_path):
                os.remove(self.token_path)
                logger.info(f"🗑️ Token removed for user {self.user_id}")
            self.creds = None
            self.service = None
        except Exception as e:
            logger.error(f"Failed to logout: {str(e)}")

    def get_service(self):
        """
        Get the Google Calendar service (must login first)

        Returns:
            Google Calendar service object or None
        """
        if not self.service:
            logger.warning("Not authenticated. Call login() first.")
        return self.service


# Example usage:
if __name__ == "__main__":
    # Test the auth
    auth = GoogleAuth(user_id="test_user")

    try:
        service = auth.login()
        print("✅ Authentication successful!")
        print(f"Authenticated: {auth.is_authenticated()}")

        # Test a simple API call
        calendars = service.calendarList().list().execute()
        print(f"Found {len(calendars.get('items', []))} calendars")

    except Exception as e:
        print(f"❌ Authentication failed: {e}")