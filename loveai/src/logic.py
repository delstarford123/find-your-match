def manage_context(chat_history, max_messages=5):
    """
    Limits the history sent to the model so the CPU doesn't crash 
    trying to read a massive conversation.
    """
    if len(chat_history) > max_messages:
        return chat_history[-max_messages:]
    return chat_history

def format_system_instruction(user_religion):
    """
    Dynamically changes the AI's personality based on user data.
    """
    base = "You are a supportive AI companion."
    if user_religion == "Christian":
        return base + " Use occasional biblical encouragement in your advice."
    return base