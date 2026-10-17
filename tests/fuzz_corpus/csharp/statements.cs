namespace Shop.Statements
{
    using System.IO;

    public static class Statements
    {
        public static string Label(int status) => status switch
        {
            0 => "Pending",
            1 => "Paid",
            _ => "Unknown"
        };

        public static void Run(Queue<string> queue)
        {
            string? item;
            do
            {
                item = queue.Count > 0 ? queue.Dequeue() : null;
            } while (item != null);

            try
            {
                File.ReadAllText("orders.txt");
            }
            catch (IOException ex) when (ex.HResult != 0)
            {
                throw;
            }
            finally
            {
                queue.Clear();
            }

            switch (queue.Count)
            {
                case 0:
                case 1:
                    break;
                default:
                    return;
            }
        }
    }
}
