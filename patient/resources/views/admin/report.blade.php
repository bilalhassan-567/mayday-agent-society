@extends('layouts.app')
@section('title', 'Reports')

@section('content')
    <div class="card" style="max-width:640px">
        <div class="card-head"><h2>Latest report</h2><span class="badge badge-green">uploaded</span></div>
        <div class="card-body">
            <table class="kv">
                <tr><td>Generated at</td><td><code>{{ $report['generated_at'] }}</code></td></tr>
                <tr><td>Order count</td><td>{{ $report['order_count'] }}</td></tr>
                <tr><td>Gross revenue</td><td>${{ number_format($report['gross_cents'] / 100, 2) }}</td></tr>
                <tr><td>Stored at</td><td><code>{{ $uri }}</code></td></tr>
            </table>
            <p class="muted" style="font-size:13px;margin-top:16px;margin-bottom:0">
                This report was generated from live order data and uploaded to object storage (OSS).
            </p>
        </div>
    </div>
@endsection
