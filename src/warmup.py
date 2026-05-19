import httpx
import time
import sys

def warmup():
    print("🔥 Starting Engine Warmup...")
    # Try for 60 seconds to reach the engine
    for i in range(60):
        try:
            response = httpx.post(
                "http://localhost:8000/v1/chat/completions",
                json={
                    "model": "warmup",
                    "messages": [{"role": "user", "content": "1+1"}],
                    "max_tokens": 1
                },
                timeout=5.0
            )
            if response.status_code == 200:
                print("✅ Warmup Complete. Engine is ready for users.")
                return
        except Exception:
            print(f"⏳ Waiting for engine... ({i}/60)")
            time.sleep(2)
    
    print(" Warmup Failed. Engine might be down.")
    sys.exit(1)

if __name__ == "__main__":
    warmup()