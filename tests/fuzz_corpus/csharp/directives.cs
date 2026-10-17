#if !(NET20)
class A { }
#elif DEBUG
class B { }
#endif
class C
{
    void M()
    {
#if X
        Run();
#endif
    }
}
