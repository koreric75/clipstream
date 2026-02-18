import os
import pickle
import webbrowser
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

def get_service(client_secret_file, scopes):
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, scopes)
            # Try local server first, fallback to manual if it fails
            try:
                creds = flow.run_local_server(port=8080)
            except Exception as e:
                print(f"Local server failed ({e}), opening browser for manual authorization...")
                auth_url, _ = flow.authorization_url(prompt='consent')
                print(f"\nPlease visit this URL: {auth_url}")
                print("\nAfter authorizing, copy the authorization code and paste it below:")
                auth_code = input("Enter authorization code: ").strip()
                flow.fetch_token(code=auth_code)
                creds = flow.credentials
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    return build("youtube", "v3", credentials=creds)