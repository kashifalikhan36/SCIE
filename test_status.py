import asyncio
import json
import redis.asyncio as redis
from core.config import settings

async def check_status():
    if settings.REDIS_URL:
        r = redis.Redis.from_url(settings.REDIS_URL)
    else:
        r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, password=settings.REDIS_PASSWORD)
        
    print("Checking Redis for meeting offline_8dd60d1b")
    
    for i in range(25):
        val = await r.get("offline_status:offline_8dd60d1b")
        if val:
            data = json.loads(val)
            print(f"Status: {data.get('status')}")
            print(f"Progress: {data.get('progress')}%")
            print(f"Logs: {data.get('logs')[-1] if data.get('logs') else 'None'}")
            print("---")
            if data.get('status') == 'Completed' or str(data.get('status')).startswith('Error'):
                break
        else:
            print("No status found yet...")
        await asyncio.sleep(2)
        
if __name__ == "__main__":
    asyncio.run(check_status())
