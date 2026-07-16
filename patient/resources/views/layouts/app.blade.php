<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>@yield('title', 'Dashboard') — Patient Console</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
</head>
<body>
<div class="layout">
    <aside class="sidebar">
        <div class="brand">
            <span class="dot"></span>
            <span>Patient Console<small>operator dashboard</small></span>
        </div>

        <nav class="nav">
            <span class="nav-label">Manage</span>
            <a href="{{ route('dashboard') }}" class="{{ request()->routeIs('dashboard') ? 'active' : '' }}"><span class="ic">▚</span> Dashboard</a>
            <a href="{{ route('admin.users.index') }}" class="{{ request()->routeIs('admin.users.*') ? 'active' : '' }}"><span class="ic">◍</span> Users</a>
            <a href="{{ route('admin.orders.index') }}" class="{{ request()->routeIs('admin.orders.*') ? 'active' : '' }}"><span class="ic">▦</span> Orders</a>
            <a href="{{ route('admin.report') }}" class="{{ request()->routeIs('admin.report') ? 'active' : '' }}"><span class="ic">▤</span> Reports</a>
            <a href="{{ route('admin.system') }}" class="{{ request()->routeIs('admin.system') ? 'active' : '' }}"><span class="ic">✦</span> System Health</a>

            <span class="nav-label">Monitoring</span>
            <a href="/health" target="_blank"><span class="ic">↗</span> Health JSON</a>
        </nav>

        <div class="sidebar-foot">
            <div class="who">{{ auth()->user()->name }}<small>{{ auth()->user()->email }}</small></div>
            <form method="POST" action="{{ route('logout') }}" style="margin-top:8px">
                @csrf
                <button type="submit" class="btn btn-ghost btn-sm" style="width:100%">Sign out</button>
            </form>
        </div>
    </aside>

    <div class="main">
        <div class="topbar">
            <h1>@yield('title', 'Dashboard')</h1>
            @yield('topbar')
        </div>
        <div class="content">
            @if (session('status'))
                <div class="alert alert-success">{{ session('status') }}</div>
            @endif
            @if (session('error'))
                <div class="alert alert-error">{{ session('error') }}</div>
            @endif
            @yield('content')
        </div>
    </div>
</div>
</body>
</html>
