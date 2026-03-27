# VoxAgent Function Tools

# Placeholder for future integration with VoIP/SIP providers
# and business logic.

async def end_session(call_id: str):
    """Signals the system to finalize the call gracefully."""
    print(f"[TOOL] Ending session: {call_id}")
    return {"status": "success", "action": "hangup"}

async def transfer_to_human(call_id: str, department: str = "support"):
    """Placeholder for SIP transfer logic."""
    print(f"[TOOL] Transferring {call_id} to {department}")
    return {"status": "success", "action": "transfer"}

# Tool Mapping for LLM
TOOLS = [
    {
        "name": "end_session",
        "description": "Call this when the user says goodbye or thanks the agent.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "transfer_to_human",
        "description": "Transfer the caller to a human agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "department": {"type": "string", "enum": ["sales", "support"]}
            }
        }
    }
]
