import asyncio
import motor.motor_asyncio

async def main():
    db = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')['SCIE-mg']
    doc = await db.meetings.find_one({'source':'offline_upload'}, sort=[('_id', -1)])
    if doc:
        print("Metadata:", doc.get('extra_data'))
        print("Participants:", doc.get('participants_data'))
        print("Transcript:", doc.get('transcript_data'))
    else:
        print("No document found")

if __name__ == "__main__":
    asyncio.run(main())
