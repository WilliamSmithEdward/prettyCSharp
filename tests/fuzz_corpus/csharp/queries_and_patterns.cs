a?.B.C();
a?.B()?.C();
this.A.B();
Foo<int>().Bar();
await foreach (var i in xs) { }
await using (var r = R()) { }
using (a) using (b) { }
switch (a, b) { case (1, 2): goto case 3; }
var q = from c in cs join o in os on c.Id equals o.CId into g let n = g.Count() orderby n descending, c.Name group c by n into grp select grp;
var t = x is int and > 3 or < 0;
var u = s is { Length: > 0 } s2;
(a, b) = (1, 2);
F(out var v, out _, ref w, in z, name: 3);
var y = x ?? throw new E();
x = y = z;
var w2 = checked(x + 1) + default(int) + sizeof(int) + typeof(X).Name.Length + nameof(x).Length;
