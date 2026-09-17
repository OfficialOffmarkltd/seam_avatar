# Headless stub for MakeHuman's events3d module.
# The original provides the GUI event system (mouse, keyboard, human change
# events). None of these fire in headless operation.

class HumanEvent:
    """Stub. Human change events are not dispatched headlessly."""
    def __init__(self, human, event_type):
        self.human = human
        self.type = event_type
