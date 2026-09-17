# Headless stub for MakeHuman's core module.
# The original exposes G, the global application singleton (G.app, G.world,
# G.canvas, etc.). Headlessly there is no Qt application, so G is a null object
# that silently absorbs any attribute access.

class _NullApp:
    """Absorbs G.app.anything without raising AttributeError."""
    def __getattr__(self, name):
        return self
    def __call__(self, *args, **kwargs):
        return self
    def __bool__(self):
        return False

class _Globals:
    app = _NullApp()
    world = []
    canvas = None

G = _Globals()
