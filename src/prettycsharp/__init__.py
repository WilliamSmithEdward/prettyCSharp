"""An opinionated formatter for C#, in the spirit of Prettier."""

from prettycsharp.formatter import FormatResult, FormattingError, format_details, format_source
from prettycsharp.parsing import CSharpSyntaxError
from prettycsharp.settings import Settings, SettingsError

__version__ = "1.1.9"

__all__ = [
    "CSharpSyntaxError",
    "FormatResult",
    "FormattingError",
    "Settings",
    "SettingsError",
    "__version__",
    "format_details",
    "format_source",
]
