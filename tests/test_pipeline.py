import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_memory():
    from memory import memory
    print("Testing Redis Memory...")
    try:
        memory.create_session("test_call_1", "agent_mvp")
        memory.update_intent("test_call_1", "support")
        sess = memory.get_session("test_call_1")
        print(f"Session data: {sess}")
        assert sess["current_intent"] == "support"
        print("Memory tests passed.\n")
    except Exception as e:
        print(f"Memory test failed: {e}")

async def test_knowledge():
    from knowledge_base import kb
    print("Testing Knowledge Base (RAG)...")
    try:
        res = kb.search("How much does the plan cost?")
        print("Search result:")
        print(res)
        print("Knowledge base tests passed.\n")
    except Exception as e:
        print(f"Knowledge test failed: {e}")

async def test_tools():
    from tools import book_meeting, transfer_to_human
    print("Testing Tools...")
    res = book_meeting("Tomorrow 10 AM", "John Doe")
    print(res)
    res2 = transfer_to_human("Customer frustrated")
    print(res2)
    print("Tool tests passed.\n")

async def test_all():
    await test_memory()
    await test_knowledge()
    await test_tools()
    print("All module tests completed.")

if __name__ == "__main__":
    asyncio.run(test_all())
