global using System;
extern alias Foo;
namespace N;
#nullable enable
#pragma warning disable CS1591
public record Person(string First, [property: JsonIgnore] int Age) : Base(First), IFoo;
public record struct P(int X);
public class D(int x) : B(x) { }
public enum E : byte { A = 1, [Obsolete] B, }
public delegate int Del<T>(T a) where T : class;
public interface I { void M(); int P { get; init; } event EventHandler E; }
public class C
{
    public event EventHandler E { add { _e += value; } remove => _e -= value; }
    public static implicit operator int(C c) => 1;
    public static explicit operator C(int c) { return null; }
    [return: NotNull] public required string Name { get; init; }
    public int X { get => _x; set => _x = value; }
    void L() { int Local(int a) { return a; } var o = new() { A = 1 }; var d = new Dictionary<string, int> { ["a"] = 1, { "b", 2 } }; Func<int, int> f = x => x; var a = delegate (int q) { return q; }; Span<int> s = stackalloc int[3]; }
    public const int K = 1;
    protected internal virtual void V() { }
    unsafe fixed char buf[3];
}
#pragma warning restore CS1591
