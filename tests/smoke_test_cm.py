import asyncio
import json
import sys
import os

# Add current directory to path so imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from conversation_manager import ConversationManager
from memory import memory

async def smoke_test():
    cm = ConversationManager()
    call_id = "smoke_test_001"
    agent_id = "agent_smoke"
    
    # Ensure fresh start
    await memory.r.delete(f"call_session:{call_id}")
    await memory.r.delete(f"history:{call_id}")
    
    test_turns = [
        "Hello",
        "What courses do you offer?",
        "How long is the course?",
        "What is the price?",
        "Can I book a demo?",
    ]

    results = []

    for i, text in enumerate(test_turns):
        print(f"\n--- Turn {i+1} ---")
        response = await cm.process_turn(call_id, agent_id, text)

        session = await memory.get_session(call_id)
        current_intent = session.get("current_intent") if session else None

        print(f"User: {text}")
        print(f"Intent: {current_intent}")
        print(f"Assistant: {response}")

        results.append({
            "turn": i+1,
            "input": text,
            "intent": current_intent,
            "response_snippet": response[:100]
        })

    history = await memory.get_history(call_id)
    print(f"\n--- History Check ---")
    print(f"Total messages in history: {len(history)}")

    history_ok = len(history) <= 10
    all_responses_present = all(item["response_snippet"].strip() for item in results)

    print("\n--- FINAL VERIFICATION ---")
    if history_ok:
        print("✅ SUCCESS: History does not exceed 10 messages (5 turns).")
    else:
        print(f"❌ FAILURE: History has {len(history)} messages (> 10).")

    if all_responses_present:
        print("✅ SUCCESS: All scenarios returned a response.")
    else:
        print("❌ FAILURE: One or more scenarios returned an empty response.")

    with open("smoke_test_results.json", "w") as f:
        json.dump({
            "history_count": len(history),
            "history_ok": history_ok,
            "all_responses_present": all_responses_present,
            "turns": results
        }, f, indent=2)

if __name__ == "__main__":
    asyncio.run(smoke_test())
