@extends('layouts.app')
@section('title', 'Users')

@section('content')
    <div class="page-actions">
        <span class="muted">{{ $users->total() }} user(s)</span>
        <a href="{{ route('admin.users.create') }}" class="btn">+ New user</a>
    </div>

    <div class="card">
        @if ($users->isEmpty())
            <div class="empty">No users yet. <a href="{{ route('admin.users.create') }}">Create one</a>.</div>
        @else
            <table>
                <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Created</th><th></th></tr></thead>
                <tbody>
                @foreach ($users as $user)
                    <tr>
                        <td class="muted">#{{ $user->id }}</td>
                        <td>{{ $user->name }}</td>
                        <td class="muted">{{ $user->email }}</td>
                        <td class="muted">{{ $user->created_at?->format('M j, Y') }}</td>
                        <td>
                            <div class="row-actions">
                                <a href="{{ route('admin.users.edit', $user) }}" class="btn btn-ghost btn-sm">Edit</a>
                                <form method="POST" action="{{ route('admin.users.destroy', $user) }}" onsubmit="return confirm('Delete {{ $user->name }}?')">
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

    @include('partials.pager', ['paginator' => $users])
@endsection
