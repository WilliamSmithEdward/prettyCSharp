"""The rewrites that move or replace tokens, and their limits."""

from prettycsharp import format_source

from support import check, fmt


def test_block_namespace_stays_when_the_file_has_other_top_level_types() -> None:
    check(
        """
        namespace A { class B { } }
        class C { }
        """,
        """
        namespace A
        {
            class B { }
        }

        class C { }
        """,
    )


def test_namespace_style_follows_the_lang_version() -> None:
    source = "namespace A { class B { } }\n"
    assert format_source(source, lang_version=10) == "namespace A;\n\nclass B { }\n"
    assert format_source(source, lang_version=9) == "namespace A\n{\n    class B { }\n}\n"
    assert format_source("namespace A;\n\nclass B { }\n", lang_version=9) == "namespace A\n{\n    class B { }\n}\n"


def test_namespace_comments_survive_the_conversion() -> None:
    check(
        """
        namespace A
        { // opening
            class B { }
            // closing
        }
        """,
        """
        namespace A;

        // opening
        class B { }
        // closing
        """,
    )


def test_using_header_comment_stays_at_the_top() -> None:
    check(
        """
        // Copyright header

        using System;
        using Alpha;
        """,
        """
        // Copyright header

        using Alpha;
        using System;
        """,
    )


def test_global_usings_come_first() -> None:
    check(
        """
        using Beta;
        global using Alpha;
        """,
        """
        global using Alpha;
        using Beta;
        """,
    )


def test_using_order_system_first_grouped() -> None:
    check(
        """
        using Shop.Orders;
        using System.Linq;
        using Newtonsoft.Json;
        using System;
        """,
        """
        using System;
        using System.Linq;

        using Newtonsoft.Json;

        using Shop.Orders;
        """,
        using_order="system_first_grouped",
    )


def test_doc_comment_stays_above_reordered_modifiers() -> None:
    check(
        """
        class C
        {
            /// <summary>Max.</summary>
            static public int Max = 1;
        }
        """,
        """
        class C
        {
            /// <summary>Max.</summary>
            public static int Max = 1;
        }
        """,
    )


def test_partial_stays_last() -> None:
    check("partial public sealed class C { }\n", "public sealed partial class C { }\n")


def test_expression_bodies_for_accessors_constructors_and_operators() -> None:
    check(
        """
        class C
        {
            int _x;
            public int X { get { return _x; } set { _x = value; } }
            public C(int x) { _x = x; }
            public static C operator +(C a, C b) { return a; }
            public void Fail() { throw new InvalidOperationException(); }
        }
        """,
        """
        class C
        {
            int _x;

            public int X
            {
                get => _x;
                set => _x = value;
            }

            public C(int x) => _x = x;

            public static C operator +(C a, C b) => a;

            public void Fail() => throw new InvalidOperationException();
        }
        """,
    )


def test_expression_bodies_block_turns_arrows_into_blocks() -> None:
    check(
        """
        class C
        {
            public int X => _x;
            public void Save() => _repo.Save(this);
            public async Task Run() => await Go();
            public async Task<int> Count() => await Total();
        }
        """,
        """
        class C
        {
            public int X
            {
                get
                {
                    return _x;
                }
            }

            public void Save()
            {
                _repo.Save(this);
            }

            public async Task Run()
            {
                await Go();
            }

            public async Task<int> Count()
            {
                return await Total();
            }
        }
        """,
        expression_bodies="block",
    )


def test_expression_bodies_properties_only() -> None:
    check(
        """
        class C
        {
            public int X { get { return _x; } }
            public int Y() => _y;
        }
        """,
        """
        class C
        {
            public int X => _x;

            public int Y()
            {
                return _y;
            }
        }
        """,
        expression_bodies="properties_only",
    )


def test_iterators_and_multi_statement_bodies_stay_blocks() -> None:
    check(
        """
        class C
        {
            IEnumerable<int> M() { yield return 1; }
            void N() { A(); B(); }
        }
        """,
        """
        class C
        {
            IEnumerable<int> M()
            {
                yield return 1;
            }

            void N()
            {
                A();
                B();
            }
        }
        """,
    )


def test_parentheses_remove_redundant_follows_precedence() -> None:
    check(
        """
        var a = (b * c) + d;
        var e = (f + g) * h;
        var i = (j - k) - l;
        var m = n - (o - p);
        """,
        """
        var a = b * c + d;
        var e = (f + g) * h;
        var i = j - k - l;
        var m = n - (o - p);
        """,
        parentheses="remove_redundant",
    )


def test_parentheses_preserve() -> None:
    check("return (total);\n", "return (total);\n", parentheses="preserve")


def test_parentheses_before_a_generic_lookalike_stay() -> None:
    # Without the first pair, a < b, c > d would read as a generic name.
    check("var x = F((a) < b, c > (d));\n", "var x = F((a) < b, c > d);\n")


def test_braces_always() -> None:
    check(
        """
        void M()
        {
            if (a) Run();
            else if (b) Walk();
            else Stop();
            while (x) Step();
        }
        """,
        """
        void M()
        {
            if (a)
            {
                Run();
            }

            else if (b)
            {
                Walk();
            }

            else
            {
                Stop();
            }

            while (x)
            {
                Step();
            }
        }
        """,
        braces="always",
    )


def test_braces_single_line_only() -> None:
    long_call = "Process(" + ", ".join(f"argument{i}" for i in range(12)) + ")"
    broken = ",\n                    ".join(f"argument{i}" for i in range(12))
    check(
        f"""
        void M()
        {{
            if (a) Run();
            if (b) {long_call};
        }}
        """,
        f"""
        void M()
        {{
            if (a) Run();

            if (b)
            {{
                Process(
                    {broken}
                );
            }}
        }}
        """,
        braces="single_line_only",
    )


def test_trailing_commas_add_when_broken() -> None:
    check(
        "var p = new Point { X = 1, Y = 2 };\n",
        """
        var p = new Point
        {
            X = 1,
            Y = 2,
        };
        """,
        trailing_commas="add",
    )


def test_attributes_combine() -> None:
    check(
        """
        class C
        {
            [A]
            [B(1)]
            void M() { }
        }
        """,
        """
        class C
        {
            [A, B(1)]
            void M() { }
        }
        """,
        attributes="combine",
    )


def test_trailing_comma_comment_moves_to_the_item_before() -> None:
    check(
        """
        var p = new Point
        {
            X = 1,
            Y = 2, // last
        };
        """,
        """
        var p = new Point
        {
            X = 1,
            Y = 2 // last
        };
        """,
    )


def test_verbatim_statements_are_not_rewritten() -> None:
    source = """
        class C
        {
            int M()
            {
                return x switch
                {
                    1 => 2,
        #pragma warning disable CS0001
                    _ => 3
        #pragma warning restore CS0001
                };
            }
        }
        """
    out = fmt(source)
    assert "#pragma warning disable CS0001" in out
    assert "return x switch" in out
