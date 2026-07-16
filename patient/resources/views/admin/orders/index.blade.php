@extends('layouts.app')
@section('title', 'Orders')

@section('content')
    <div class="page-actions">
        <span class="muted">{{ $orders->total() }} order(s)</span>
        <a href="{{ route('admin.orders.create') }}" class="btn">+ New order</a>
    </div>

    <div class="card">
        @if ($orders->isEmpty())
            <div class="empty">No orders yet. <a href="{{ route('admin.orders.create') }}">Create one</a>.</div>
        @else
            <table>
                <thead><tr><th>ID</th><th>Customer</th><th>Item</th><th>Amount</th><th>Status</th><th></th></tr></thead>
                <tbody>
                @foreach ($orders as $order)
                    <tr>
                        <td class="muted">#{{ $order->id }}</td>
                        <td>{{ $order->customer }}</td>
                        <td class="muted">{{ $order->item }}</td>
                        <td>${{ number_format($order->amount_cents / 100, 2) }}</td>
                        <td><span class="badge {{ $order->status === 'paid' ? 'badge-green' : ($order->status === 'refunded' ? 'badge-red' : 'badge-amber') }}">{{ $order->status }}</span></td>
                        <td>
                            <div class="row-actions">
                                <a href="{{ route('admin.orders.edit', $order) }}" class="btn btn-ghost btn-sm">Edit</a>
                                <form method="POST" action="{{ route('admin.orders.destroy', $order) }}" onsubmit="return confirm('Delete order #{{ $order->id }}?')">
                                    @csrf @method('DELETE')
                                    <button class="btn btn-danger btn-sm">Delete</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                @endforeach
                </tbody>
            </table>
        @endif
    </div>

    @include('partials.pager', ['paginator' => $orders])
@endsection
