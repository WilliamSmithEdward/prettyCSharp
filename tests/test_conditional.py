"""Code that conditional compilation splits, formatted one view at a time."""

import pytest

from prettycsharp import CSharpSyntaxError, FormattingError, format_source
from prettycsharp.conditional import (
    ConditionalError,
    covering_sets,
    evaluate,
    mask,
    restore,
    symbols_in,
)

from support import check


@pytest.mark.parametrize(
    ("condition", "defined", "value"),
    [
        ("DEBUG", set(), False),
        ("DEBUG", {"DEBUG"}, True),
        ("!DEBUG", set(), True),
        ("A && B", {"A"}, False),
        ("A || B", {"B"}, True),
        ("!(A || B) && C", {"C"}, True),
        ("A == B", set(), True),
        ("A != B", {"A"}, True),
        ("true && !false", set(), True),
        ("NET10_0_OR_GREATER", {"NET10_0_OR_GREATER"}, True),
    ],
)
def test_evaluate(condition: str, defined: set[str], value: bool) -> None:
    assert evaluate(condition, defined) is value


def test_unreadable_conditions_are_refused() -> None:
    for condition in ("A &&", "(A", "A B", "A + B"):
        with pytest.raises(ConditionalError):
            evaluate(condition, set())


def test_symbols_in() -> None:
    assert symbols_in("!(NET20 || NET35) && true") == {"NET20", "NET35"}


def test_mask_hides_directives_and_inactive_branches_and_restore_brings_them_back() -> None:
    source = "#if A\nclass B : I\n#else\nclass B\n#endif\n{ }\n"
    masked = mask(source, set())
    assert "class B : I" not in masked.text
    assert "class B\n" in masked.text
    assert restore(masked.text, masked.hidden) == source


def test_mask_follows_define_and_undef() -> None:
    source = "#define A\n#if A\nint a;\n#endif\n#undef A\n#if A\nint b;\n#endif\n"
    text = mask(source, set()).text
    assert "int a;" in text
    assert "int b;" not in text


def test_nested_branches_inside_a_hidden_one_stay_hidden() -> None:
    source = "#if A\n#if B\nint ab;\n#endif\n#else\nint other;\n#endif\n"
    text = mask(source, {"B"}).text
    assert "int ab;" not in text
    assert "int other;" in text


def test_unbalanced_directives() -> None:
    with pytest.raises(ConditionalError):
        mask("#if A\nint a;\n", set())
    with pytest.raises(ConditionalError):
        mask("#endif\n", set())


def test_lost_placeholder_is_an_error() -> None:
    masked = mask("#if A\nint a;\n#endif\nint b;\n", set())
    with pytest.raises(ConditionalError):
        restore("int b;\n", masked.hidden)


def test_covering_sets_reach_every_branch() -> None:
    source = "#if A\nclass C : I\n#elif B\nclass C : J\n#else\nclass C\n#endif\n{ }\n"
    sets = covering_sets(source)
    assert frozenset() in sets
    assert frozenset({"A"}) in sets
    assert frozenset({"B"}) in sets


def test_split_class_header_formats_every_branch() -> None:
    check(
        """
        using System;
        namespace Shop
        {
        #if NET10_0_OR_GREATER
            public sealed class Pool : IAsyncDisposable
        #else
            public sealed class Pool : IDisposable
        #endif
            {
                static public int   Size=3;
        #if NET10_0_OR_GREATER
                public ValueTask DisposeAsync() { return ValueTask.CompletedTask; }
        #else
                public void Dispose() { Close(); }
        #endif
            }
        }
        """,
        """
        using System;

        namespace Shop
        {
        #if NET10_0_OR_GREATER
            public sealed class Pool : IAsyncDisposable
        #else
            public sealed class Pool : IDisposable
        #endif
            {
                public static int Size = 3;

        #if NET10_0_OR_GREATER
                public ValueTask DisposeAsync() => ValueTask.CompletedTask;
        #else
                public void Dispose() => Close();
        #endif
            }
        }
        """,
    )


def test_split_method_signature() -> None:
    check(
        """
        class C
        {
        #if ASYNC
            public async Task<int> Load(int id)
        #else
            public int Load(int id)
        #endif
            {
                var x=id;
                return x;
            }
        }
        """,
        """
        class C
        {
        #if ASYNC
            public async Task<int> Load(int id)
        #else
            public int Load(int id)
        #endif
            {
                var x = id;
                return x;
            }
        }
        """,
    )


def test_usings_do_not_move_across_directives() -> None:
    check(
        """
        using Zeta;
        using Alpha;
        #if NET
        using Net.Only;
        #else
        using Old.Only;
        #endif
        using Gamma;
        using Beta;
        #if NET
        class C : I
        #else
        class C
        #endif
        { }
        """,
        """
        using Alpha;
        using Zeta;
        #if NET
        using Net.Only;
        #else
        using Old.Only;
        #endif
        using Beta;
        using Gamma;

        #if NET
        class C : I
        #else
        class C
        #endif
        { }
        """,
    )


def test_split_code_that_parses_in_no_view_is_still_a_syntax_error() -> None:
    with pytest.raises(CSharpSyntaxError):
        format_source("#if A\nclass {\n#else\nclass {\n#endif\n")


def test_unbalanced_directives_report_the_syntax_error() -> None:
    with pytest.raises(CSharpSyntaxError):
        format_source("#if A\nclass C : I\n#else\nclass C\n{ }\n")


def test_file_ending_in_a_directive_without_a_line_break_parses() -> None:
    assert format_source("class A { }\n#pragma warning restore 618", ) == "class A { }\n#pragma warning restore 618\n"


def test_a_damaged_branch_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    import prettycsharp.conditional as conditional

    real_restore = conditional.restore

    def damaging(text: str, hidden: dict[str, str]) -> str:
        # Pretend formatting turned the hidden branch's base list into another.
        return real_restore(text, hidden).replace("IAsyncDisposable", "IOther")

    monkeypatch.setattr(conditional, "restore", damaging)
    with pytest.raises(FormattingError, match="branch"):
        format_source("#if NET\nclass C : IAsyncDisposable\n#else\nclass C\n#endif\n{ }\n")


def test_comma_before_a_hidden_branch_is_not_a_trailing_comma() -> None:
    check(
        """
        class C
        {
        #if NET
            class D : I
        #else
            class D
        #endif
            {
            }
            static readonly HashSet<Type> Types = new()
            {
                typeof(Guid), typeof(Uri),
        #if DATE_ONLY
                typeof(DateOnly)
        #endif
            };
        }
        """,
        """
        class C
        {
        #if NET
            class D : I
        #else
            class D
        #endif
            { }

            static readonly HashSet<Type> Types = new()
            {
                typeof(Guid),
                typeof(Uri),
        #if DATE_ONLY
                typeof(DateOnly)
        #endif
            };
        }
        """,
    )


def test_property_split_between_arrow_and_accessors_under_block_bodies() -> None:
    check(
        """
        interface I
        {
            bool Ignored
        #if NET8_0_OR_GREATER
                => false;
        #else
            {
                get;
            }
        #endif
        }
        """,
        """
        interface I
        {
            bool Ignored
        #if NET8_0_OR_GREATER
            => false;
        #else
            { get; }
        #endif
        }
        """,
        expression_bodies="block",
    )


def test_directive_after_a_doc_comment_stays_at_column_zero() -> None:
    check(
        """
        static class C
        {
            /// <summary>Humanizes.</summary>
        #if NET6_0_OR_GREATER
            [RequiresDynamicCode("x")]
        #endif
            public static string H(this Enum input) => input.ToString();
        }
        """,
        """
        static class C
        {
            /// <summary>Humanizes.</summary>
        #if NET6_0_OR_GREATER
            [RequiresDynamicCode("x")]
        #endif
            public static string H(this Enum input) => input.ToString();
        }
        """,
        attributes="combine",
    )
