// leading
using System;
using static System.Math;
using Json = Newtonsoft.Json;
[assembly: Foo]
namespace A.B
{
    #region Props
    [Obsolete, Serializable]
    public sealed partial class C<T> : Base, IFoo where T : class, new()
    {
        private readonly int _x = 1, _y; // trailing
        public int P { get; private set; } = 3;
        public int Q => _x;
        public int R { get { return _x; } set { _x = value; } }
        public C(int x) : base(x) { _x = x; }
        static public async Task<int> M<U>(int a, ref string b, params int[] c) where U : struct
        {
            if (a > 0) return 1;
            else if (a < 0)
            {
                return 2;
            }
            else
                return 3;
        }
        public event EventHandler E;
        public int this[int i] => i;
        public static C operator +(C a, C b) => a;
        ~C() { }
    }
    #endregion
}
