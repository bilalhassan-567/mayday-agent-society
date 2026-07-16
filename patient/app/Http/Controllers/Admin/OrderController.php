<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\Order;
use App\Services\OrdersService;
use App\Support\PatientLog;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\View\View;
use Throwable;

class OrderController extends Controller
{
    private const STATUSES = ['paid', 'pending', 'refunded'];

    public function index(OrdersService $ordersService): View
    {
        // Real dependency: the orders list is enriched via an internal service,
        // so the dependency-timeout fault breaks THIS page, visibly.
        try {
            $ordersService->fetchEnrichment();
        } catch (Throwable $e) {
            PatientLog::error('/admin/orders', 'orders enrichment dependency failed', ['reason' => $e->getMessage()]);
            abort(504, 'The orders enrichment service did not respond in time.');
        }

        return view('admin.orders.index', [
            'orders' => Order::query()->orderBy('id')->paginate(10),
        ]);
    }

    public function create(): View
    {
        return view('admin.orders.create', ['order' => new Order(['status' => 'paid']), 'statuses' => self::STATUSES]);
    }

    public function store(Request $request): RedirectResponse
    {
        Order::query()->create($this->validated($request));

        return redirect()->route('admin.orders.index')->with('status', 'Order created.');
    }

    public function edit(Order $order): View
    {
        return view('admin.orders.edit', ['order' => $order, 'statuses' => self::STATUSES]);
    }

    public function update(Request $request, Order $order): RedirectResponse
    {
        $order->update($this->validated($request));

        return redirect()->route('admin.orders.index')->with('status', 'Order updated.');
    }

    public function destroy(Order $order): RedirectResponse
    {
        $order->delete();

        return redirect()->route('admin.orders.index')->with('status', 'Order deleted.');
    }

    /** Accept a dollar amount in the form, store integer cents. */
    private function validated(Request $request): array
    {
        $data = $request->validate([
            'customer'   => ['required', 'string', 'max:255'],
            'item'       => ['required', 'string', 'max:255'],
            'amount'     => ['required', 'numeric', 'min:0'],
            'status'     => ['required', 'in:'.implode(',', self::STATUSES)],
        ]);

        return [
            'customer'     => $data['customer'],
            'item'         => $data['item'],
            'amount_cents' => (int) round($data['amount'] * 100),
            'status'       => $data['status'],
        ];
    }
}
