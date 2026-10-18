class Assignments
{
    public required string Name { get; init; }
    void Update(dynamic target, int[] items, int index)
    {
        long required = 0;
        required = Math.Max(required, index + 1);
        required -= index;
        target?.Route = required;
        items?[index] += 1;
        target?.Child?.Route = target?.Route;
    }
}
