@extends('layouts.app')
@section('title', 'Edit order')

@section('content')
    <div class="card" style="max-width:560px">
        <div class="card-head"><h2>Edit order #{{ $order->id }}</h2></div>
        <div class="card-body">
            <form method="POST" action="{{ route('admin.orders.update', $order) }}">
                @csrf @method('PUT')
                @include('admin.orders._form')
                <div class="form-actions">
                    <button class="btn">Save changes</button>
                    <a href="{{ route('admin.orders.index') }}" class="btn btn-ghost">Cancel</a>
                </div>
            </form>
        </div>
    </div>
@endsection
