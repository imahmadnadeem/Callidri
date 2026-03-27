import asyncio
import aiohttp
import os
import sys

# Add current directory to path to import config
sys.path.append(os.getcwd())
from config import SARVAM_API_KEY

async def diagnose_sarvam():
    print("--- SARVAM TTS DIAGNOSIS ---")
    print(f"API Key present: {'Yes' if SARVAM_API_KEY else 'No'}")
    
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": "Namaste, main Nina hoon. Kya aap mujhe sun sakte hain?",
        "target_language_code": "hi-IN",
        "speaker": "shreya",
        "model": "bulbul:v3"
    }
    
    print(f"Sending request to {url}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                print(f"Response Status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if "audios" in data and len(data["audios"]) > 0:
                        audio_len = len(data["audios"][0])
                        print(f"SUCCESS! Received audio block: {audio_len} base64 chars")
                        print("Pipeline should be working correctly.")
                    else:
                        print("ERROR: Response 200 but no 'audios' field in JSON!")
                        print(f"Response JSON: {data}")
                else:
                    error_text = await response.text()
                    print(f"ERROR: {response.status}")
                    print(f"Details: {error_text}")
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(diagnose_sarvam())
