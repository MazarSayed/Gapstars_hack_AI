import asyncio
import db

async def test():
    try:
        print("Initializing DB...")
        await db.init_db()
        print("DB initialized successfully.")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
