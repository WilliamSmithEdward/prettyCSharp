"""The C# printer: from the syntax model to formatted text."""

from __future__ import annotations

from prettycsharp.doc import print_doc
from prettycsharp.printer.declarations import Declarations
from prettycsharp.settings import Settings
from prettycsharp.syntax import SourceFile


class CSharpPrinter(Declarations):
    """Every handler, from the file down to a token."""


def eol_for(settings: Settings, file: SourceFile) -> str:
    return {"lf": "\n", "crlf": "\r\n", "cr": "\r"}.get(settings.end_of_line, file.eol)


def print_file(file: SourceFile, settings: Settings, lang_version: float) -> str:
    printer = CSharpPrinter(settings, file, lang_version)
    doc = printer.print(file.root)
    indent_width = settings.indent_size
    eol = eol_for(settings, file)
    text = print_doc(doc, settings.width, settings.indent_unit, indent_width, eol)
    text = text.lstrip("\r\n")
    if settings.insert_final_newline and text:
        text = text.rstrip("\r\n") + eol
    return text
