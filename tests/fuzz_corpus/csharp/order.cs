using System;
using System.Collections.Generic;
using System.Linq;

namespace Shop.Orders;

public class Order
{
    private readonly List<OrderLine> _lines = new();

    public int Id { get; set; }

    public decimal Total => _lines.Where(l => l.IsTaxable).Sum(l => l.Amount);

    public void Ship()
    {
        if (Total > 100m)
        {
            Send();
        }
        else
        {
            Hold();
        }
    }

    private void Send() { }

    private void Hold() { }
}

public record OrderLine(decimal Amount, bool IsTaxable);
