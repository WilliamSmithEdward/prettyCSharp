var x = a.B.C(1, 2).D<int>().E;
var y = c ? d : e;
var z = new Foo { A = 1, B = { 2 } };
int[] w = [1, .. r];
var f = (int a) => { return a; };
var g = x switch { 1 => "a", _ => "b" };
var q = from o in orders where o.Paid select o.Id;
var s = $"a{b,5:N2}c";
var r = @"x";
var t = """
    raw
    """;
x?.Y?[0]!.Z();
#if DEBUG
Log();
#else
Skip();
#endif
foreach (var (k, v) in dict) { }
for (int i = 0, j = 1; i < 10; i++, j--) { }
using (var h = Open()) Run();
using var u = Open();
lock (o) { }
switch (n) { case 1 when n > 0: case 2: break; default: { return; } }
try { } catch (E e) when (e != null) { } catch { } finally { }
do { } while (x);
label: goto label;
yield return 1;
throw new X();
checked { }
fixed (int* p = &a) { }
if (o is Foo { Bar: > 3 } foo && o is not null) { }
var anon = new { A = 1, b.C };
var arr = new int[] { 1, 2 };
var cast = (int)d + -e * !f;
x += await Task.Run(() => 1).ConfigureAwait(false);
local();
void local() => Do();
var tuple = (1, b: 2);
string? n2 = default;
var range = arr[1..^2];
var w2 = p with { X = 1 };
