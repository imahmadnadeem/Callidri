import asyncio
from agent import agent_loop

async def main():
    try:
        await agent_loop("test-room", "test-call-123")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
