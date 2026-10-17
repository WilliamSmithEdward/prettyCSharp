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
