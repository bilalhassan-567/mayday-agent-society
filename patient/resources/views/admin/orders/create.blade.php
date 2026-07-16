@extends('layouts.app')
@section('title', 'New order')

@section('content')
    <div class="card" style="max-width:560px">
        <div class="card-head"><h2>Create order</h2></div>
        <div class="card-body">
            <form method="POST" action="{{ route('admin.orders.store') }}">
                @csrf
                @include('admin.orders._form')
                <div class="form-actions">
                    <button class="btn">Create order</button>
                    <a href="{{ route('admin.orders.index') }}" class="btn btn-ghost">Cancel</a>
                </div>
            </form>
        </div>
    </div>
@endsection
