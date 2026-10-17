"""An opinionated formatter for C#, in the spirit of Prettier."""

from prettycsharp.formatter import format_source
from prettycsharp.parsing import CSharpSyntaxError

__version__ = "1.0.0.dev0"

__all__ = ["CSharpSyntaxError", "__version__", "format_source"]
