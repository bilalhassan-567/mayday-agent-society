@extends('layouts.app')
@section('title', 'System Health')

@section('content')
    <div class="card" style="margin-bottom:20px">
        <div class="card-head">
            <h2>Live health</h2>
            @if ($health['healthy'])
                <span class="status-pill badge-green">● All systems operational</span>
            @else
                <span class="status-pill badge-red">● Degraded — dependency failing</span>
            @endif
        </div>
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
        <div class="card-head"><h2>Runtime configuration</h2><span class="muted" style="font-size:13px">app_settings (real state)</span></div>
        <div class="card-body">
            <table class="kv">
                @foreach ($settings as $key => $value)
                    <tr><td>{{ $key }}</td><td><code>{{ $value }}</code></td></tr>
                @endforeach
            </table>
            <p class="muted" style="font-size:13px;margin-top:16px;margin-bottom:0">
                These values drive the patient's behavior. A fault corrupts one of them; the fix restores it.
                This page derives status from live probes — it never reads the fault ledger.
            </p>
        </div>
    </div>
@endsection
