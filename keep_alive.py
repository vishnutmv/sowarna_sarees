import time
import requests
import os
from dotenv import load_dotenv

# We ONLY load dotenv to get the URL. 
# We do NOT import app.py or bot.py to avoid starting any extra bot instances.
load_dotenv()

def keep_render_alive():
    """
    Pings the Sowarna Sarees website every 15 seconds.
    Run this script from an EXTERNAL machine (like your local PC)
    to prevent the Render free tier from sleeping.
    """
    # Replace the URL below if your BASE_URL is different in .env
    url = os.getenv('BASE_URL', 'https://sowarna-sarees.onrender.com')
    
    print(f"🚀 Keep-Alive Service Started")
    print(f"📡 Target: {url}")
    print(f"⏱️ Interval: 15 seconds")
    print("-" * 30)
    
    while True:
        try:
            # We use a simple GET request. 
            # This counts as 'inbound traffic' to Render.
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{timestamp}] ✅ Server is Awake (Status 200)")
            else:
                print(f"⚠️ Warning: Server returned status {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Connection Error: {str(e)}")
            
        # Wait for 15 seconds
        time.sleep(15)

# The function is defined but NOT called.
# To start it, you would add: keep_render_alive()
