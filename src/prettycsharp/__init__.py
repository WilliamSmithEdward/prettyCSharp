"""An opinionated formatter for C#, in the spirit of Prettier."""

from prettycsharp.formatter import FormattingError, format_source
from prettycsharp.parsing import CSharpSyntaxError
from prettycsharp.settings import Settings, SettingsError

__version__ = "1.0.0"

__all__ = ["CSharpSyntaxError", "FormattingError", "Settings", "SettingsError", "__version__", "format_source"]
