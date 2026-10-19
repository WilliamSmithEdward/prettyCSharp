"""The default layout, one DESIGN.md decision per test."""

import pytest

from support import check, fmt


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (";;", "; ; "),
        ("int i=0;;", "int i = 0; ;"),
        (";i<10;", "; i < 10;"),
        (";;i++", "; ; i++"),
        ("int i=0;i<10;", "int i = 0; i < 10;"),
        ("int i=0;;i++", "int i = 0; ; i++"),
        (";i<10;i++", "; i < 10; i++"),
        ("int i=0;i<10;i++", "int i = 0; i < 10; i++"),
        ("int i=0,j=1;;i++,j--", "int i = 0, j = 1; ; i++, j--"),
        ("var start=query[0]=='?'?1:0;;", "var start = query[0] == '?' ? 1 : 0; ;"),
        ("int i=0;/* condition omitted */;", "int i = 0; /* condition omitted */ ;"),
    ],
)
def test_for_header_spacing_with_omitted_clauses(source: str, expected: str) -> None:
    check(f"for({source}){{break;}}", f"for ({expected})\n{{\n    break;\n}}\n")


def test_allman_braces_with_blank_line_before_continuations() -> None:
    check(
        """
        class Order { void Ship() { if (IsPaid) { Send(); } else { Hold(); } } }
        """,
        """
        class Order
        {
            void Ship()
            {
                if (IsPaid)
                {
                    Send();
                }

                else
                {
                    Hold();
                }
            }
        }
        """,
    )


def test_else_if_catch_finally_and_do_while_get_a_blank_line() -> None:
    check(
        """
        void M()
        {
            if (a) { A(); } else if (b) { B(); } else { C(); }
            try { Save(); } catch (IOException ex) { Log(ex); } finally { Close(); }
            do { item = queue.Dequeue(); } while (item != null);
        }
        """,
        """
        void M()
        {
            if (a)
            {
                A();
            }

            else if (b)
            {
                B();
            }

            else
            {
                C();
            }

            try
            {
                Save();
            }

            catch (IOException ex)
            {
                Log(ex);
            }

            finally
            {
                Close();
            }

            do
            {
                item = queue.Dequeue();
            }

            while (item != null);
        }
        """,
    )


def test_four_space_indent() -> None:
    assert fmt("class A{void M(){Run();Stop();}}") == "class A\n{\n    void M()\n    {\n        Run();\n        Stop();\n    }\n}\n"


def test_catch_filter_wraps_logical_pattern_before_expanding_property_pattern() -> None:
    check(
        'try { Run(); } catch (Exception error) when (error is ObjectDisposedException or SocketException '
        'or ArgumentException { ParamName: "socketAddress" }) { Stop(); }',
        'try\n{\n    Run();\n}\n\n'
        'catch (Exception error) when (\n    error is ObjectDisposedException\n'
        '        or SocketException\n        or ArgumentException { ParamName: "socketAddress" }\n)\n{\n    Stop();\n}\n',
    )


def test_broken_pattern_catch_filter_puts_parentheses_on_own_lines() -> None:
    check(
        'try { Run(); } catch (Exception error) when '
        '(error is SocketException or ObjectDisposedException or OperationCanceledException) { }',
        'try\n{\n    Run();\n}\n\ncatch (Exception error) when (\n'
        '    error is SocketException\n        or ObjectDisposedException\n'
        '        or OperationCanceledException\n)\n{ }\n',
        max_line_length=90,
    )


@pytest.mark.parametrize("keyword", ["if", "while"])
def test_broken_pattern_conditions_share_catch_filter_layout(keyword: str) -> None:
    check(
        f'{keyword} (error is SocketException or ObjectDisposedException or OperationCanceledException) {{ Stop(); }}',
        f'{keyword} (\n    error is SocketException\n        or ObjectDisposedException\n'
        '        or OperationCanceledException\n)\n{\n    Stop();\n}\n',
        max_line_length=65,
    )


def test_broken_pattern_do_while_condition_has_own_parenthesis_lines() -> None:
    check(
        'do { Run(); } while (error is SocketException or ObjectDisposedException or OperationCanceledException);',
        'do\n{\n    Run();\n}\n\nwhile (\n    error is SocketException\n'
        '        or ObjectDisposedException\n        or OperationCanceledException\n);\n',
        max_line_length=65,
    )


@pytest.mark.parametrize("keyword", ["if", "while"])
def test_short_pattern_condition_stays_inline(keyword: str) -> None:
    check(f'{keyword} (x is A or B) {{ Run(); }}', f'{keyword} (x is A or B)\n{{\n    Run();\n}}\n')


@pytest.mark.parametrize("keyword", ["if", "while"])
def test_multiline_predicate_condition_uses_own_parenthesis_lines(keyword: str) -> None:
    check(
        f'{keyword} (Predicate(veryLongArgumentName, anotherLongArgumentName)) {{ Run(); }}',
        f'{keyword} (\n    Predicate(\n        veryLongArgumentName,\n'
        '        anotherLongArgumentName\n    )\n)\n{\n    Run();\n}\n',
        max_line_length=50,
    )


@pytest.mark.parametrize("wrap", ["before_operator", "after_operator"])
def test_pattern_conditions_respect_alternative_parenthesis_layout(wrap: str) -> None:
    if wrap == "after_operator":
        pattern = 'error is SocketException or\n    ObjectDisposedException or\n    OperationCanceledException'
    else:
        pattern = 'error is SocketException\n    or ObjectDisposedException\n    or OperationCanceledException'
    check(
        'if (error is SocketException or ObjectDisposedException or OperationCanceledException) { Run(); }',
        f'if ({pattern})\n{{\n    Run();\n}}\n',
        max_line_length=65,
        binary_wrap=wrap,
    )


@pytest.mark.parametrize("style", ["allman", "kr", "mixed"])
def test_broken_property_pattern_respects_brace_style(style: str) -> None:
    separator = "\n" if style == "allman" else " "
    check(
        'var match = value is SomeType { VeryLongProperty: "a rather long value" };',
        f'var match = value is SomeType{separator}'
        '{\n    VeryLongProperty: "a rather long value"\n};\n',
        max_line_length=45,
        brace_style=style,
    )


def test_short_property_pattern_remains_inline() -> None:
    check('var match=value is Type{Id:1};', 'var match = value is Type { Id: 1 };\n')


@pytest.mark.parametrize("operator", ["or", "and"])
@pytest.mark.parametrize("wrap", ["before_operator_paren_own_line", "before_operator", "after_operator"])
def test_long_logical_patterns_wrap(operator: str, wrap: str) -> None:
    if wrap == "after_operator":
        expected = f"var ok = value is LongPatternOne {operator}\n    LongPatternTwo {operator}\n    LongPatternThree;\n"
    else:
        expected = f"var ok = value is LongPatternOne\n    {operator} LongPatternTwo\n    {operator} LongPatternThree;\n"
    check(
        f"var ok = value is LongPatternOne {operator} LongPatternTwo {operator} LongPatternThree;",
        expected,
        max_line_length=50,
        binary_wrap=wrap,
    )


@pytest.mark.parametrize("pattern", ["A or B", "A and B", "A or B and C", "(A or B) and C"])
def test_short_logical_patterns_keep_grouping_and_stay_inline(pattern: str) -> None:
    check(f"var ok=value is {pattern};", f"var ok = value is {pattern};\n")


def test_negated_pattern_chain_and_boolean_tail_share_one_indent() -> None:
    check(
        "var persistent = _status is not 400 and not 408 and not 411 and not 413 and not 414 "
        "and not 500 and not 503 && !_transport.IsDraining && KeepAlive;",
        "var persistent = _status is not 400\n"
        "    and not 408\n    and not 411\n    and not 413\n    and not 414\n"
        "    and not 500\n    and not 503\n    && !_transport.IsDraining\n    && KeepAlive;\n",
    )


def test_call_breaks_one_argument_per_line_with_paren_on_its_own_line() -> None:
    check(
        """
        var invoice = invoiceService.CreateInvoice(customer.Id, order.Lines, DateTime.UtcNow, billingAddress, shippingAddress, discount);
        """,
        """
        var invoice = invoiceService.CreateInvoice(
            customer.Id,
            order.Lines,
            DateTime.UtcNow,
            billingAddress,
            shippingAddress,
            discount
        );
        """,
    )


def test_call_that_fits_stays_on_one_line() -> None:
    check("var invoice = svc.Create(customer.Id, order.Lines);\n", "var invoice = svc.Create(customer.Id, order.Lines);\n")


def test_chain_of_two_calls_always_breaks() -> None:
    check(
        "var names = users.Select(u => u.Name).ToList();\n",
        """
        var names = users
            .Select(u => u.Name)
            .ToList();
        """,
    )


def test_single_call_and_property_chains_stay_on_one_line() -> None:
    check(
        """
        var name = user.GetName();
        var city = order.Customer.Address.City;
        var zip = order.Customer.Address.GetPostalCode();
        """,
        """
        var name = user.GetName();
        var city = order.Customer.Address.City;
        var zip = order.Customer.Address.GetPostalCode();
        """,
    )


def test_properties_before_the_first_call_stay_on_the_receiver_line() -> None:
    check(
        "var total = order.Lines.Where(l => l.IsTaxable).Sum(l => l.Amount);\n",
        """
        var total = order.Lines
            .Where(l => l.IsTaxable)
            .Sum(l => l.Amount);
        """,
    )


def test_broken_chain_after_arrow_moves_to_its_own_line() -> None:
    check(
        """
        class C
        {
            public int PaidCount => Orders.Where(o => o.IsPaid).Count();
        }
        """,
        """
        class C
        {
            public int PaidCount =>
                Orders
                    .Where(o => o.IsPaid)
                    .Count();
        }
        """,
    )


def test_file_scoped_namespace() -> None:
    check(
        """
        using System;
        namespace Shop.Orders
        {
            public class Order { }
        }
        """,
        """
        using System;

        namespace Shop.Orders;

        public class Order { }
        """,
    )


def test_usings_sorted_ordinally_with_static_and_aliases_last() -> None:
    check(
        """
        using Json = Newtonsoft.Json;
        using static System.Math;
        using System;
        using Shop.Orders;
        using Microsoft.Extensions.Logging;
        """,
        """
        using Microsoft.Extensions.Logging;
        using Shop.Orders;
        using System;
        using static System.Math;
        using Json = Newtonsoft.Json;
        """,
    )


def test_fields_grouped_tight_and_blank_lines_around_members_with_bodies() -> None:
    check(
        """
        public class Order
        {
            private readonly int _id;

            private readonly string _name;
            public Order(int id, string name)
            {
                _id = id;
                _name = name;
            }
            public int Id => _id;

            public string Name => _name;
        }
        """,
        """
        public class Order
        {
            private readonly int _id;
            private readonly string _name;

            public Order(int id, string name)
            {
                _id = id;
                _name = name;
            }

            public int Id => _id;
            public string Name => _name;
        }
        """,
    )


def test_block_statements_get_blank_lines_and_plain_ones_keep_the_authors() -> None:
    check(
        """
        void Ship()
        {
            var order = Load();
            // Bail out early
            if (order == null)
            {
                return;
            }
            foreach (var line in order.Lines)
            {
                Reserve(line);
            }
            Send(order);


            Log(order);
        }
        """,
        """
        void Ship()
        {
            var order = Load();

            // Bail out early
            if (order == null)
            {
                return;
            }

            foreach (var line in order.Lines)
            {
                Reserve(line);
            }

            Send(order);

            Log(order);
        }
        """,
    )


def test_braceless_statements_are_left_as_written() -> None:
    check(
        """
        void M()
        {
            if (order == null) return;
            if (order.IsPaid)
                Send(order);
        }
        """,
        """
        void M()
        {
            if (order == null) return;

            if (order.IsPaid)
                Send(order);
        }
        """,
    )


def test_single_expression_members_become_expression_bodied() -> None:
    check(
        """
        class C
        {
            public int Total { get { return Lines.Sum(l => l.Amount); } }
            public string Describe() { return $"Order {Id}"; }
            public void Save() { _repo.Save(this); }
        }
        """,
        """
        class C
        {
            public int Total => Lines.Sum(l => l.Amount);

            public string Describe() => $"Order {Id}";

            public void Save() => _repo.Save(this);
        }
        """,
    )


def test_body_with_a_comment_stays_a_block() -> None:
    check(
        """
        class C
        {
            public void Save()
            {
                // the repository commits
                _repo.Save(this);
            }
        }
        """,
        """
        class C
        {
            public void Save()
            {
                // the repository commits
                _repo.Save(this);
            }
        }
        """,
    )


def test_long_expression_body_breaks_after_the_arrow() -> None:
    check(
        """
        class C
        {
            public decimal TaxableTotal => Lines.Sum(l => l.Amount * l.Quantity * (1 + l.TaxRate) - l.Discount - l.Rebate * 2 + l.Fee);
        }
        """,
        """
        class C
        {
            public decimal TaxableTotal =>
                Lines.Sum(l => l.Amount * l.Quantity * (1 + l.TaxRate) - l.Discount - l.Rebate * 2 + l.Fee);
        }
        """,
    )


def test_trailing_commas_are_removed() -> None:
    check(
        """
        var order = new Order { Id = 42, Customer = customer, };
        enum Status { Pending, Paid, }
        """,
        """
        var order = new Order
        {
            Id = 42,
            Customer = customer
        };

        enum Status
        {
            Pending,
            Paid
        }
        """,
    )


def test_initializer_with_one_member_stays_inline_and_two_break() -> None:
    check(
        """
        var empty = new Order { Id = 42 };
        var point = new Point { X = 1, Y = 2 };
        """,
        """
        var empty = new Order { Id = 42 };
        var point = new Point
        {
            X = 1,
            Y = 2
        };
        """,
    )


def test_simple_value_lists_stay_inline_and_complex_ones_break() -> None:
    check(
        """
        var primes = new List<int> { 2, 3, 5, 7 };
        int[] codes = [200, 404];
        var points = new List<Point> { new Point(0, 0), new Point(1, 1) };
        """,
        """
        var primes = new List<int> { 2, 3, 5, 7 };
        int[] codes = [200, 404];
        var points = new List<Point>
        {
            new Point(0, 0),
            new Point(1, 1)
        };
        """,
    )


def test_line_endings_and_bom_are_kept() -> None:
    from prettycsharp import format_source

    source = "class A\r\n{\r\n}\r\n"
    assert format_source(source) == "class A { }\r\n"


def test_attributes_one_per_line_in_their_own_brackets() -> None:
    check(
        """
        class C
        {
            [HttpGet, Route("orders/{id}")] [Authorize(Roles = "Admin")]
            public IActionResult Get([FromBody] int id) => Ok();
        }
        """,
        """
        class C
        {
            [HttpGet]
            [Route("orders/{id}")]
            [Authorize(Roles = "Admin")]
            public IActionResult Get([FromBody] int id) => Ok();
        }
        """,
    )


def test_regions_are_left_as_written() -> None:
    check(
        """
        class C
        {
            #region Properties
            public int Id { get; set; }
            #endregion
        }
        """,
        """
        class C
        {
            #region Properties
            public int Id { get; set; }
            #endregion
        }
        """,
    )


def test_switch_sections_are_indented_with_blank_lines_between() -> None:
    check(
        """
        void M()
        {
            switch (status) { case Status.Paid: Send(order); break; case Status.Pending: case Status.New: Wait(order); break; default: Hold(order); break; }
        }
        """,
        """
        void M()
        {
            switch (status)
            {
                case Status.Paid:
                    Send(order);
                    break;

                case Status.Pending:
                case Status.New:
                    Wait(order);
                    break;

                default:
                    Hold(order);
                    break;
            }
        }
        """,
    )


def test_nothing_is_padded_into_columns() -> None:
    check(
        """
        var label = status switch { Status.Paid => "Paid", Status.Pending => "Pending", _ => "Unknown" };
        var id   = order.Id;
        var customer = order.Customer;
        public enum Status { Pending   = 0, Paid = 1, Cancelled = 2 }
        """,
        """
        var label = status switch
        {
            Status.Paid => "Paid",
            Status.Pending => "Pending",
            _ => "Unknown"
        };
        var id = order.Id;
        var customer = order.Customer;

        public enum Status
        {
            Pending = 0,
            Paid = 1,
            Cancelled = 2
        }
        """,
    )


@pytest.mark.parametrize("case_indent", [True, False])
@pytest.mark.parametrize("comment", ["// Unknown settings are ignored.", "/* Unknown settings are ignored. */"])
@pytest.mark.parametrize("blank", ["", "\n"])
def test_trailing_switch_comment_aligns_with_statements(case_indent: bool, comment: str, blank: str) -> None:
    label_indent = "    " if case_indent else ""
    statement_indent = label_indent + "    "
    check(
        f"switch(x){{case 9:break;\n{blank}{comment}\n}}",
        f"switch (x)\n{{\n{label_indent}case 9:\n{statement_indent}break;\n"
        f"{blank}{statement_indent}{comment}\n}}\n",
        switch_case_indent=case_indent,
    )


@pytest.mark.parametrize("case_indent", [True, False])
def test_comment_only_switch_keeps_one_indent(case_indent: bool) -> None:
    check(
        "switch(x){\n// No cases yet.\n}",
        "switch (x)\n{\n    // No cases yet.\n}\n",
        switch_case_indent=case_indent,
    )


def test_switch_expression_arms_align_when_turned_on() -> None:
    check(
        """
        var label = status switch { Status.Paid => "Paid", Status.Pending => "Pending", _ => "Unknown" };
        """,
        """
        var label = status switch
        {
            Status.Paid    => "Paid",
            Status.Pending => "Pending",
            _              => "Unknown"
        };
        """,
        align_switch_arms=True,
    )


def test_assignments_and_enum_values_align_when_turned_on() -> None:
    check(
        """
        var id = order.Id;
        var customer = order.Customer;

        var total = order.Total;
        public enum Status { Pending = 0, Paid = 1, Cancelled = 2 }
        """,
        """
        var id       = order.Id;
        var customer = order.Customer;

        var total = order.Total;

        public enum Status
        {
            Pending   = 0,
            Paid      = 1,
            Cancelled = 2
        }
        """,
        align_assignments=True,
        align_enum_values=True,
    )


def test_multi_line_lambda_hangs_off_the_call() -> None:
    check(
        """
        orders.ForEach(order => { Validate(order); Send(order); });
        """,
        """
        orders.ForEach(order =>
        {
            Validate(order);
            Send(order);
        });
        """,
    )


def test_long_condition_breaks_before_operators_with_parens_on_their_own_lines() -> None:
    check(
        """
        void M()
        {
            if (order.IsPaid && order.Lines.Count > 0 && customer.IsActive && !customer.IsBlocked && customer.Region == selectedRegion) { Send(order); }
        }
        """,
        """
        void M()
        {
            if (
                order.IsPaid
                && order.Lines.Count > 0
                && customer.IsActive
                && !customer.IsBlocked
                && customer.Region == selectedRegion
            )
            {
                Send(order);
            }
        }
        """,
    )


def test_long_ternary_breaks_before_question_mark_and_colon() -> None:
    check(
        """
        var shipping = order.Total > FreeShippingThreshold ? 0m : CalculateShipping(order.Weight, order.Destination, order.Carrier);
        """,
        """
        var shipping = order.Total > FreeShippingThreshold
            ? 0m
            : CalculateShipping(order.Weight, order.Destination, order.Carrier);
        """,
    )


def test_comments_get_a_space_and_long_ones_are_rewrapped() -> None:
    long_text = " ".join(["word"] * 40)
    check(
        f"""
        //Bail out early
        //----------
        // {long_text}
        class C {{ }}
        """,
        f"""
        // Bail out early
        //----------
        // {" ".join(["word"] * 23)}
        // {" ".join(["word"] * 17)}
        class C {{ }}
        """,
    )


def test_comment_that_looks_like_code_is_not_rewrapped() -> None:
    line = "// var x = " + "a + " * 30 + "b;"
    check(f"{line}\nclass C {{ }}\n", f"{line}\nclass C {{ }}\n")


def test_modifiers_take_the_dotnet_order() -> None:
    check(
        """
        class C
        {
            static public readonly int Max = 10;
            async override protected Task Run() { await Go(); }
        }
        """,
        """
        class C
        {
            public static readonly int Max = 10;

            protected override async Task Run() => await Go();
        }
        """,
    )


def test_obvious_parentheses_are_removed_and_clarifying_ones_kept() -> None:
    check(
        """
        int M(int a, int b, int c)
        {
            var x = (a * b) + c;
            if ((a > b)) { return (total); }
            return (a);
        }
        """,
        """
        int M(int a, int b, int c)
        {
            var x = (a * b) + c;

            if (a > b)
            {
                return total;
            }

            return a;
        }
        """,
    )


def test_nullable_array_types_stay_tight() -> None:
    source = (
        "void M(params object?[]? values) { }\n"
        "\n"
        "int?[] a = new int?[3];\n"
        "List<string?[]> b = (string?[][])o;\n"
        "var c = x is int?[] d;\n"
        "var e = f ? [1] : [2];\n"
        "var g = h?[i];\n"
    )
    assert fmt(source) == source


def test_empty_collection_moves_to_the_next_line_whole() -> None:
    check(
        "class C { IEnumerable<Entry> Entries(string path, IMimeTypeProvider provider) => []; int[] xs = []; }\n",
        """
        class C
        {
            IEnumerable<Entry> Entries(string path, IMimeTypeProvider provider) =>
                [];

            int[] xs = [];
        }
        """,
        max_line_length=74,
    )


def test_long_empty_constructor_keeps_parentheses_together() -> None:
    check(
        'private readonly ConcurrentDictionary<IPAddress, ConcurrentBag<long>> _failRegexMatches = '
        'new ConcurrentDictionary<IPAddress, ConcurrentBag<long>>();',
        'private readonly ConcurrentDictionary<IPAddress, ConcurrentBag<long>> _failRegexMatches =\n'
        '    new ConcurrentDictionary<IPAddress, ConcurrentBag<long>>();\n',
    )


@pytest.mark.parametrize("wrap", ["one_per_line", "one_per_line_close_on_last", "fill", "align"])
def test_empty_call_parentheses_never_split(wrap: str) -> None:
    check(
        'SomeVeryLongMethodName();', 'SomeVeryLongMethodName();\n',
        max_line_length=12, argument_wrap=wrap,
    )


def test_comments_inside_empty_constructor_are_preserved() -> None:
    source = 'var instance = new Item( // Keep this note.\n);'
    output = fmt(source)
    assert '// Keep this note.\n' in output
    assert fmt(output) == output


def test_spread_elements_are_spaced_and_ranges_are_not() -> None:
    assert fmt("x = [..entries, 1, ..more];\n") == "x = [.. entries, 1, .. more];\n"
    assert fmt("var r = entries[1..] + entries[..2] + entries[..];\n") == (
        "var r = entries[1..] + entries[..2] + entries[..];\n"
    )


@pytest.mark.parametrize("element", ['new HpackField(wire, "")', "GetField()", "wire.Length + 1", "wire"])
@pytest.mark.parametrize("simple_inline", [True, False])
def test_inline_collection_brackets_stay_tight(element: str, simple_inline: bool) -> None:
    check(
        f"Validate([ {element} ]);",
        f"Validate([{element}]);\n",
        simple_lists_inline=simple_inline,
    )


def test_collection_brackets_in_awaited_send_stay_tight() -> None:
    check(
        'await SendAsync([ new Http2Frame(6, 1, 0, frame.Payload) ], token).ConfigureAwait(false);',
        'await SendAsync([new Http2Frame(6, 1, 0, frame.Payload)], token).ConfigureAwait(false);\n',
    )


def test_multiline_collection_argument_has_no_extra_blank_line() -> None:
    check(
        'await SendHeadersAsync([new HpackField(":status", "200"), '
        'new HpackField("content-length", bytes.Length.ToString(CultureInfo.InvariantCulture))], '
        'bytes.Length == 0 || Request.Method == "HEAD", token).ConfigureAwait(false);',
        'await SendHeadersAsync(\n'
        '    [\n'
        '        new HpackField(":status", "200"),\n'
        '        new HpackField("content-length", bytes.Length.ToString(CultureInfo.InvariantCulture))\n'
        '    ],\n'
        '    bytes.Length == 0 || Request.Method == "HEAD",\n'
        '    token\n'
        ').ConfigureAwait(false);\n',
    )


def test_spread_of_call_in_multiline_arguments_keeps_brackets_tight() -> None:
    check(
        '_session = Session.Start([ .. _prefixes.Select(value => new ListenerPrefix(value)) ], '
        '_certificates, TlsPolicy, _native, DeferContinue, Telemetry, _bodyPolicy, _dispatcher);',
        '_session = Session.Start(\n'
        '    [.. _prefixes.Select(value => new ListenerPrefix(value))],\n'
        '    _certificates,\n    TlsPolicy,\n    _native,\n    DeferContinue,\n'
        '    Telemetry,\n    _bodyPolicy,\n    _dispatcher\n);\n',
    )


def test_empty_body_after_a_header_that_spans_lines_gets_its_own_line() -> None:
    # Visual Studio (IDE0055) keeps `{ }` on the header's line only when the
    # header is one line.
    check(
        """
        // Redirects.
        class RedirectModule : ModuleBase
        {
            public RedirectModule(string baseRoute, Uri redirectUrl, Func<IHttpContext, bool>? shouldRedirect, HttpStatusCode statusCode) { }
            public RedirectModule(long alphabetical, long betamaxfactor, long gammaradiation, long deltaforce) : base(alphabetical) { }
            public void Generic<TFirstTypeParameter, TSecondTypeParameter>(TFirstTypeParameter first, TSecondTypeParameter s) where TFirstTypeParameter : class { }
            public RedirectModule(int a) : base() { }
            // Short.
            public void G<T>() where T : class { }
        }
        public abstract class EmptyAbstractWithAVeryLongNameIndeed<TFirstTypeParameter, TSecondTypeParameter> : Base where TFirstTypeParameter : class { }
        """,
        """
        // Redirects.
        class RedirectModule : ModuleBase
        {
            public RedirectModule(
                string baseRoute,
                Uri redirectUrl,
                Func<IHttpContext, bool>? shouldRedirect,
                HttpStatusCode statusCode
            )
            { }

            public RedirectModule(long alphabetical, long betamaxfactor, long gammaradiation, long deltaforce)
                : base(alphabetical)
            { }

            public void Generic<TFirstTypeParameter, TSecondTypeParameter>(TFirstTypeParameter first, TSecondTypeParameter s)
                where TFirstTypeParameter : class
            { }

            public RedirectModule(int a) : base() { }

            // Short.
            public void G<T>() where T : class { }
        }

        public abstract class EmptyAbstractWithAVeryLongNameIndeed<TFirstTypeParameter, TSecondTypeParameter> : Base
            where TFirstTypeParameter : class
        { }
        """,
    )


def test_empty_catch_and_lambda_bodies_after_a_header_that_spans_lines() -> None:
    check(
        """
        void M()
        {
            try { }
            // Ignored.
            catch (Exception error) when (IsRecoverable(error)) { }
            Run((first, second, third) => { });
        }
        """,
        """
        void M()
        {
            try { }

            // Ignored.
            catch (Exception error) when (
                IsRecoverable(error)
            )
            { }

            Run((
                first,
                second,
                third
            ) =>
            { });
        }
        """,
        max_line_length=30,
    )


def test_accessor_list_and_enum_holding_only_a_comment() -> None:
    check(
        "class C { int P {\n// c\n} }\nenum E {\n// c\n}\n",
        """
        class C
        {
            int P
            {
                // c
            }
        }

        enum E
        {
            // c
        }
        """,
    )


def test_auto_properties_and_empty_bodies_stay_on_one_line() -> None:
    check(
        """
        public class Marker
        {
        }
        public class C
        {
            public int Id { get; set; }
            public string Name { get; private set; } = "";
            public void OnLoaded()
            {
            }
        }
        """,
        """
        public class Marker { }

        public class C
        {
            public int Id { get; set; }
            public string Name { get; private set; } = "";

            public void OnLoaded() { }
        }
        """,
    )


def test_tuple_block_lambda_closes_parentheses_on_the_call_line_indent() -> None:
    check(
        '_dataHandlerPairs.Add((data, (ctx, route) => { handler(ctx, route); return Task.CompletedTask; }));',
        '_dataHandlerPairs.Add((data, (ctx, route) =>\n'
        '    {\n        handler(ctx, route);\n        return Task.CompletedTask;\n    }\n));\n',
    )


def test_ordinary_block_lambda_argument_keeps_hugged_parenthesis() -> None:
    check(
        'Run(data, (ctx, route) => { handler(ctx, route); return Task.CompletedTask; });',
        'Run(data, (ctx, route) =>\n'
        '{\n    handler(ctx, route);\n    return Task.CompletedTask;\n});\n',
    )


def test_empty_tuple_lambda_stays_inline() -> None:
    check('Run((data, () => { }));', 'Run((data, () => { }));\n')


def test_object_initializer_hugs_the_last_argument() -> None:
    check(
        """
        services.Add(new Options { Name = "orders", Retries = 3 });
        """,
        """
        services.Add(new Options
        {
            Name = "orders",
            Retries = 3
        });
        """,
    )


def test_trailing_comment_stays_after_its_code() -> None:
    check(
        """
        var a = 1; // one
        Foo(a, // first
            b);
        """,
        """
        var a = 1; // one
        Foo(
            a, // first
            b
        );
        """,
    )


def test_comment_before_closing_brace_keeps_its_own_line() -> None:
    check(
        """
        var list = new List<int>
        {
            1,
            // more to come
        };
        """,
        """
        var list = new List<int>
        {
            1
            // more to come
        };
        """,
    )


def test_preprocessor_branches_keep_their_columns() -> None:
    check(
        """
        class C
        {
        #if DEBUG
            void Log() { Write(); }
        #else
            void Log() { }
        #endif
        }
        """,
        """
        class C
        {
        #if DEBUG
            void Log() => Write();
        #else
            void Log() { }
        #endif
        }
        """,
    )


def test_raw_and_verbatim_strings_are_untouched() -> None:
    check(
        '''
        var json = """
            { "id": 42 }
            """;
        var path = @"C:\\orders\\  ";
        ''',
        '''
        var json = """
            { "id": 42 }
            """;
        var path = @"C:\\orders\\  ";
        ''',
    )


def test_ignore_comment_leaves_the_next_member_untouched() -> None:
    check(
        """
        class C
        {
            // prettycsharp-ignore
            private static readonly int[,] Matrix = {
                { 1, 0 },
                { 0, 1 } };
            int   X;
        }
        """,
        """
        class C
        {
            // prettycsharp-ignore
            private static readonly int[,] Matrix = {
                { 1, 0 },
                { 0, 1 } };
            int X;
        }
        """,
    )


def test_ignore_range_leaves_the_statements_untouched() -> None:
    check(
        """
        void M()
        {
            // prettycsharp-ignore-start
            int  a=1;
            int  b=2;
            // prettycsharp-ignore-end
            int  c=3;
        }
        """,
        """
        void M()
        {
            // prettycsharp-ignore-start
            int  a=1;
            int  b=2;
            // prettycsharp-ignore-end
            int c = 3;
        }
        """,
    )
