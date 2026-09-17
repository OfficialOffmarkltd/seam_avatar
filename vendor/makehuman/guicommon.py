# Headless stub for MakeHuman's guicommon module.
# The original provides GUI widget base classes (Action for undo/redo, Object
# for scene nodes). None of these are needed in the headless deformation path.

class Action:
    """Stub base class. Undo/redo actions are not used headlessly."""
    def __init__(self, description=""):
        self.description = description
    def do(self): return True
    def undo(self): return True

class Object:
    """Stub base class for MakeHuman scene objects."""
    def __init__(self, *args, **kwargs): pass
