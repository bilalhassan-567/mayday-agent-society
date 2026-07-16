@extends('layouts.app')
@section('title', 'New user')

@section('content')
    <div class="card" style="max-width:560px">
        <div class="card-head"><h2>Create user</h2></div>
        <div class="card-body">
            <form method="POST" action="{{ route('admin.users.store') }}">
                @csrf
                @include('admin.users._form')
                <div class="form-actions">
                    <button class="btn">Create user</button>
                    <a href="{{ route('admin.users.index') }}" class="btn btn-ghost">Cancel</a>
                </div>
            </form>
        </div>
    </div>
@endsection
