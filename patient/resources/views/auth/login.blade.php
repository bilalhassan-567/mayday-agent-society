<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sign in — Patient Console</title>
    <link rel="stylesheet" href="{{ asset('css/app.css') }}">
</head>
<body>
<div class="login-wrap">
    <div class="login-card">
        <div class="brand"><span class="dot"></span> Patient Console</div>
        <h1>Welcome back</h1>
        <p class="sub">Sign in to the operator dashboard.</p>

        @if ($errors->any())
            <div class="alert alert-error">{{ $errors->first() }}</div>
        @endif

        <form method="POST" action="{{ route('login') }}">
            @csrf
            <div class="form-row">
                <label for="email">Email</label>
                <input id="email" type="email" name="email" value="{{ old('email', 'admin@example.com') }}" required autofocus>
            </div>
            <div class="form-row">
                <label for="password">Password</label>
                <input id="password" type="password" name="password" required>
            </div>
            <div class="form-row" style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                <input type="checkbox" name="remember" id="remember" style="width:auto">
                <label for="remember" style="margin:0;font-weight:500">Remember me</label>
            </div>
            <button type="submit" class="btn" style="width:100%;justify-content:center">Sign in</button>
        </form>

        <div class="login-hint">
            Demo credentials — <code>admin@example.com</code> / <code>password</code>
        </div>
    </div>
</div>
</body>
</html>
