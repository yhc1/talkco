def add_text(original_text, added_text):
    """
    Only add text when isn't empty
    """
    if len(added_text) > 0:
        original_text += added_text
    return original_text
