@extends('layouts.app')
@section('title', 'Dashboard')

@section('content')
    <div class="stats">
        <div class="stat">
            <div class="label">Total users</div>
            <div class="value">{{ number_format($userCount) }}</div>
            <div class="sub">registered accounts</div>
        </div>
        <div class="stat">
            <div class="label">Total orders</div>
            <div class="value">{{ number_format($orderCount) }}</div>
            <div class="sub">across all statuses</div>
        </div>
        <div class="stat">
            <div class="label">Gross revenue</div>
            <div class="value">${{ number_format($grossCents / 100, 2) }}</div>
            <div class="sub">sum of order amounts</div>
        </div>
        <div class="stat">
            <div class="label">Patient health</div>
            <div class="value" style="display:flex;align-items:center;gap:10px">
                @if ($health['healthy'])
                    <span class="badge badge-green">OK</span>
                @else
                    <span class="badge badge-red">SICK</span>
                @endif
            </div>
            <div class="sub">
                {{ collect($health['checks'])->where('ok', true)->count() }}/{{ count($health['checks']) }} checks passing
            </div>
        </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <div class="card">
            <div class="card-head"><h2>Dependency checks</h2><a href="{{ route('admin.system') }}" class="btn btn-ghost btn-sm">Details</a></div>
            <div class="card-body">
                <ul class="checks">
                    @foreach ($health['checks'] as $name => $check)
                        <li>
                            <span class="badge {{ $check['ok'] ? 'badge-green' : 'badge-red' }}">{{ $check['ok'] ? 'OK' : 'FAIL' }}</span>
                            <span class="k">{{ str_replace('_', ' ', $name) }}</span>
                            <span class="d">{{ $check['detail'] }}</span>
                        </li>
                    @endforeach
                </ul>
            </div>
        </div>

        <div class="card">
            <div class="card-head"><h2>Recent orders</h2><a href="{{ route('admin.orders.index') }}" class="btn btn-ghost btn-sm">All orders</a></div>
            <div class="card-body" style="padding:0">
                @if ($recentOrders->isEmpty())
                    <div class="empty">No orders yet.</div>
                @else
                    <table>
                        <thead><tr><th>Customer</th><th>Item</th><th>Amount</th><th>Status</th></tr></thead>
                        <tbody>
                        @foreach ($recentOrders as $o)
                            <tr>
                                <td>{{ $o->customer }}</td>
                                <td class="muted">{{ $o->item }}</td>
                                <td>${{ number_format($o->amount_cents / 100, 2) }}</td>
                                <td><span class="badge {{ $o->status === 'paid' ? 'badge-green' : ($o->status === 'refunded' ? 'badge-red' : 'badge-amber') }}">{{ $o->status }}</span></td>
                            </tr>
                        @endforeach
                        </tbody>
                    </table>
                @endif
            </div>
        </div>
    </div>
@endsection
