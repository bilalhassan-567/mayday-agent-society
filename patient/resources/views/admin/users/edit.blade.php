@extends('layouts.app')
@section('title', 'Edit user')

@section('content')
    <div class="card" style="max-width:560px">
        <div class="card-head"><h2>Edit {{ $user->name }}</h2></div>
        <div class="card-body">
            <form method="POST" action="{{ $action }}">
                @csrf @method('PUT')
                @include('admin.users._form')
                <div class="form-actions">
                    <button class="btn">Save changes</button>
                    <a href="{{ route('admin.users.index') }}" class="btn btn-ghost">Cancel</a>
                </div>
            </form>
        </div>
    </div>
@endsection
