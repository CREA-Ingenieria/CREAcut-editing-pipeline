"""Optional local editor for CREAcut projects.

Importing this package never imports Qt.  The pipeline and its command-line
interface therefore remain usable when the optional ``ui`` dependency is not
installed.
"""

from .session import EditorSession, EditorSessionError

__all__ = ["EditorSession", "EditorSessionError"]

