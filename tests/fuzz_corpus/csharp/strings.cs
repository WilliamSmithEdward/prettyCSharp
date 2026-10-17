public class Strings
{
    private const string Verbatim = @"C:\orders\  trailing spaces stay   ";
    private const string Raw = """
        { "id": 42 }
        """;

    // A comment with a URL: https://example.com/orders
    public string Describe(int id) => $"Order {id}: {Verbatim.Length}";

    [Obsolete("Use Describe")]
    public string Old(int id) => $@"Order {id}";
}
