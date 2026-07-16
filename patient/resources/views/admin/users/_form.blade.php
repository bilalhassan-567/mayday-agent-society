    <div class="form-row">
        <label for="name">Name</label>
        <input id="name" name="name" value="{{ old('name', $user->name) }}" required>
        @error('name') <div class="form-error">{{ $message }}</div> @enderror
    </div>
    <div class="form-row">
        <label for="email">Email</label>
        <input id="email" type="email" name="email" value="{{ old('email', $user->email) }}" required>
        @error('email') <div class="form-error">{{ $message }}</div> @enderror
    </div>
    <div class="form-row">
        <label for="password">Password</label>
        <input id="password" type="password" name="password" {{ $user->exists ? '' : 'required' }}>
        <div class="hint">{{ $user->exists ? 'Leave blank to keep the current password.' : 'Minimum 6 characters.' }}</div>
        @error('password') <div class="form-error">{{ $message }}</div> @enderror
    </div>
