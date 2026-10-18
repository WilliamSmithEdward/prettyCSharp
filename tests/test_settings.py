"""Every setting's alternatives, and how bad values are refused."""

import pytest

from prettycsharp import Settings, SettingsError, format_source

from support import check, fmt


def test_defaults_match_the_design() -> None:
    settings = Settings()
    assert settings.max_line_length == 120
    assert settings.indent_size == 4
    assert settings.brace_style == "allman"
    assert settings.chain_break_threshold == 2
    assert settings.namespace_style == "file_scoped_if_supported"


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"max_line_lenght": 80}, "unknown setting 'max_line_lenght'"),
        ({"brace_style": "gnu"}, "brace_style must be one of allman, kr, mixed"),
        ({"indent_size": 0}, "indent_size must be a positive number"),
        ({"align_assignments": "maybe"}, "align_assignments must be true or false"),
        ({"modifier_order": ["public", "sometimes"]}, "unknown modifier 'sometimes'"),
        ({"lang_version": "eleventy"}, "lang_version must be"),
    ],
)
def test_bad_values_are_refused(values: dict[str, object], message: str) -> None:
    with pytest.raises(SettingsError, match=message):
        Settings().with_values(values)


def test_string_values_from_the_command_line_are_converted() -> None:
    settings = Settings().with_values({"max_line_length": "80", "align_assignments": "false", "brace-style": "kr"})
    assert settings.max_line_length == 80
    assert settings.align_assignments is False
    assert settings.brace_style == "kr"


def test_tabs_and_indent_size() -> None:
    assert fmt("class A { void M() { A(); B(); } }", indent_style="tab") == (
        "class A\n{\n\tvoid M()\n\t{\n\t\tA();\n\t\tB();\n\t}\n}\n"
    )
    assert fmt("class A { void M() { A(); B(); } }", indent_size=2) == (
        "class A\n{\n  void M()\n  {\n    A();\n    B();\n  }\n}\n"
    )


def test_line_length() -> None:
    source = "var x = Call(alpha, beta, gamma);\n"
    assert fmt(source, max_line_length=20) == "var x = Call(\n    alpha,\n    beta,\n    gamma\n);\n"
    assert fmt(source, max_line_length=0) == source


def test_end_of_line() -> None:
    assert format_source("class A\n{\n}\n", Settings().with_values({"end_of_line": "crlf"})) == "class A { }\r\n"
    assert format_source("class A\r\n{\r\n}\r\n", Settings().with_values({"end_of_line": "lf"})) == "class A { }\n"


def test_final_newline() -> None:
    assert fmt("class A { }", insert_final_newline=False) == "class A { }"


def test_kr_braces() -> None:
    check(
        """
        class Order { void Ship() { if (IsPaid) { Send(); } else { Hold(); } } }
        """,
        """
        class Order {
            void Ship() {
                if (IsPaid) {
                    Send();
                } else {
                    Hold();
                }
            }
        }
        """,
        brace_style="kr",
        continuation_keywords="same_line",
    )


def test_mixed_braces() -> None:
    check(
        """
        class Order { void Ship() { if (IsPaid) { Send(); } else { Hold(); } } }
        """,
        """
        class Order
        {
            void Ship()
            {
                if (IsPaid) {
                    Send();
                } else {
                    Hold();
                }
            }
        }
        """,
        brace_style="mixed",
        continuation_keywords="same_line",
    )


def test_continuation_keywords_new_line() -> None:
    check(
        "void M() { if (a) { A(); } else { B(); } }\n",
        """
        void M()
        {
            if (a)
            {
                A();
            }
            else
            {
                B();
            }
        }
        """,
        continuation_keywords="new_line",
    )


def test_empty_bodies_allman() -> None:
    check("class A { }\n", "class A\n{\n}\n", empty_bodies="allman")


def test_member_blank_lines_all_and_preserve() -> None:
    source = """
        class C
        {
            int a;
            int b;

            int c;
        }
        """
    assert fmt(source, member_blank_lines="all") == "class C\n{\n    int a;\n\n    int b;\n\n    int c;\n}\n"
    assert fmt(source, member_blank_lines="preserve") == "class C\n{\n    int a;\n    int b;\n\n    int c;\n}\n"


def test_blank_lines_around_blocks_off() -> None:
    check(
        "void M() { A(); if (x) { B(); } C(); }\n",
        """
        void M()
        {
            A();
            if (x)
            {
                B();
            }
            C();
        }
        """,
        blank_lines_around_blocks=False,
    )


def test_argument_wrap_close_on_last_and_fill_and_align() -> None:
    source = "var x = Call(alpha, beta, gamma);\n"
    assert fmt(source, max_line_length=20, argument_wrap="one_per_line_close_on_last") == (
        "var x = Call(\n    alpha,\n    beta,\n    gamma);\n"
    )
    assert fmt(source, max_line_length=24, argument_wrap="fill") == "var x = Call(\n    alpha, beta, gamma);\n"
    assert fmt(source, max_line_length=20, argument_wrap="align") == (
        "var x = Call(alpha,\n             beta,\n             gamma);\n"
    )


def test_chain_break_threshold() -> None:
    source = "var names = users.Select(u => u.Name).ToList();\n"
    assert fmt(source, chain_break_threshold=3) == source
    assert fmt(source, chain_break_threshold=0) == source
    assert fmt(source, chain_break_threshold=0, max_line_length=30) == (
        "var names = users\n    .Select(u => u.Name)\n    .ToList();\n"
    )


def test_expression_body_chain_hang() -> None:
    check(
        "class C { int N => Orders.Where(o => o.IsPaid).Count(); }\n",
        """
        class C
        {
            int N => Orders
                .Where(o => o.IsPaid)
                .Count();
        }
        """,
        expression_body_chain="hang",
    )


def test_binary_wrap_alternatives() -> None:
    source = "var ok = alpha && beta && gamma && delta;\n"
    assert fmt(source, max_line_length=24, binary_wrap="after_operator") == (
        "var ok = alpha &&\n    beta &&\n    gamma &&\n    delta;\n"
    )
    assert fmt(source, max_line_length=24, binary_wrap="before_operator") == (
        "var ok = alpha\n    && beta\n    && gamma\n    && delta;\n"
    )


def test_ternary_wrap_alternatives() -> None:
    assert fmt("var x = a ? b : c;\n", ternary_wrap="always") == "var x = a\n    ? b\n    : c;\n"
    assert fmt("var x = alpha ? beta : gamma;\n", ternary_wrap="after", max_line_length=20) == (
        "var x = alpha ?\n    beta :\n    gamma;\n"
    )


def test_lambda_body_argument() -> None:
    check(
        "orders.ForEach(order => { Validate(order); Send(order); });\n",
        """
        orders.ForEach(
            order =>
            {
                Validate(order);
                Send(order);
            }
        );
        """,
        lambda_body="argument",
    )


def test_initializer_break_threshold_zero_and_simple_lists() -> None:
    assert fmt("var p = new Point { X = 1, Y = 2 };\n", initializer_break_threshold=0) == (
        "var p = new Point { X = 1, Y = 2 };\n"
    )
    assert fmt("var a = new[] { 1, 2 };\n", simple_lists_inline=False) == "var a = new[]\n{\n    1,\n    2\n};\n"


def test_alignment_is_off_by_default_and_each_setting_turns_it_on() -> None:
    source = "var id = order.Id;\nvar customer = order.Customer;\n"
    assert fmt(source) == source
    assert fmt(source, align_assignments=True) == "var id       = order.Id;\nvar customer = order.Customer;\n"
    switch = 'var l = s switch { 1 => "a", 22 => "b" };\n'
    assert fmt(switch) == 'var l = s switch\n{\n    1 => "a",\n    22 => "b"\n};\n'
    assert fmt(switch, align_switch_arms=True) == 'var l = s switch\n{\n    1  => "a",\n    22 => "b"\n};\n'
    assert fmt("enum E { A = 1, Bb = 2 }\n") == "enum E\n{\n    A = 1,\n    Bb = 2\n}\n"
    assert fmt("enum E { A = 1, Bb = 2 }\n", align_enum_values=True) == "enum E\n{\n    A  = 1,\n    Bb = 2\n}\n"


def test_switch_case_indent_and_blank_lines_off() -> None:
    check(
        "void M() { switch (x) { case 1: A(); break; case 2: B(); break; } }\n",
        """
        void M()
        {
            switch (x)
            {
            case 1:
                A();
                break;
            case 2:
                B();
                break;
            }
        }
        """,
        switch_case_indent=False,
        switch_case_blank_lines=False,
    )


def test_namespace_style_block_and_preserve() -> None:
    assert fmt("namespace A;\n\nclass B { }\n", namespace_style="block") == "namespace A\n{\n    class B { }\n}\n"
    assert fmt("namespace A { class B { } }\n", namespace_style="preserve") == "namespace A\n{\n    class B { }\n}\n"


def test_using_order_system_first_and_preserve() -> None:
    source = "using Zeta;\nusing System;\n"
    assert fmt(source, using_order="system_first") == "using System;\nusing Zeta;\n"
    assert fmt(source, using_order="preserve") == source


def test_attributes_preserve() -> None:
    check("class C { [A, B] void M() { } }\n", "class C\n{\n    [A, B]\n    void M() { }\n}\n", attributes="preserve")


def test_modifier_order_preserve_and_custom() -> None:
    assert fmt("class C { static public int X; }\n", modifier_order="preserve") == (
        "class C\n{\n    static public int X;\n}\n"
    )
    assert fmt("class C { public static int X; }\n", modifier_order="static,public") == (
        "class C\n{\n    static public int X;\n}\n"
    )


def test_regions_remove_and_normalize() -> None:
    source = """
        class C
        {
            #region Props
            int a;
            #endregion
        }
        """
    assert fmt(source, regions="remove") == "class C\n{\n    int a;\n}\n"
    assert fmt(source, regions="normalize") == "class C\n{\n    #region Props\n\n    int a;\n\n    #endregion\n}\n"


def test_comment_space_and_wrap_off() -> None:
    long_comment = "// " + " ".join(["word"] * 40)
    assert fmt(f"//x\n{long_comment}\nclass C {{ }}\n", comment_space=False, comment_wrap=False) == (
        f"//x\n{long_comment}\nclass C {{ }}\n"
    )


def test_max_blank_lines_zero() -> None:
    assert fmt("void M() { A();\n\n B(); }\n", max_blank_lines=0) == "void M()\n{\n    A();\n    B();\n}\n"


def test_charset_settings_leave_text_alone_in_the_api() -> None:
    # The byte order mark is the command line's business; the API sees text.
    assert fmt("class A { }\n", charset="utf-8-bom") == "class A { }\n"
