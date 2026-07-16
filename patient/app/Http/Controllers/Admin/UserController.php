<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\User;
use App\Support\PatientLog;
use App\Support\Settings;
use App\Support\UserStore;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Hash;
use Illuminate\Validation\Rule;
use Illuminate\View\View;
use Symfony\Component\Routing\Exception\RouteNotFoundException;
use Throwable;

class UserController extends Controller
{
    public function index(): View
    {
        // Real dependencies (so DB faults break THIS page, visibly):
        // the connection pool must have capacity, and the user store must be reachable.
        $available = (int) Settings::get(Settings::DB_POOL_AVAILABLE, '0');
        if ($available <= 0) {
            PatientLog::error('/admin/users', 'connection pool exhausted', ['available' => $available, 'pool_size' => 10]);
            abort(503, 'Database connection pool exhausted.');
        }

        try {
            UserStore::connection(); // configure the runtime connection from real config
            $users = User::on('user_store')->orderBy('id')->paginate(10);
        } catch (Throwable $e) {
            PatientLog::error('/admin/users', 'failed to read user store', [
                'target' => Settings::get(Settings::USER_STORE_PATH),
                'reason' => $e->getMessage(),
            ]);
            abort(503, 'The user store is unreachable.');
        }

        return view('admin.users.index', ['users' => $users]);
    }

    public function create(): View
    {
        return view('admin.users.create', ['user' => new User()]);
    }

    public function store(Request $request): RedirectResponse
    {
        $data = $this->validateUser($request, null);
        $data['password'] = Hash::make($data['password']);
        User::query()->create($data);

        return redirect()->route('admin.users.index')->with('status', 'User created.');
    }

    public function edit(User $user): View|Response
    {
        // Real dependency: the edit form resolves its save target by NAMED route.
        // If that route name is renamed (fault), route() throws and this page 500s
        // — exactly like a real form pointing at a route that no longer exists.
        $saveRoute = (string) Settings::get(Settings::EDIT_SAVE_ROUTE, 'admin.users.update');
        try {
            $action = route($saveRoute, $user);
        } catch (RouteNotFoundException $e) {
            PatientLog::error('/admin/users/edit', 'save route could not be resolved', [
                'looked_up' => $saveRoute,
                'reason'    => $e->getMessage(),
            ]);
            abort(500, 'The edit form could not resolve its save route.');
        }

        return view('admin.users.edit', ['user' => $user, 'action' => $action]);
    }

    public function update(Request $request, User $user): RedirectResponse
    {
        $data = $this->validateUser($request, $user);

        if (! empty($data['password'])) {
            $data['password'] = Hash::make($data['password']);
        } else {
            unset($data['password']);
        }

        $user->update($data);

        return redirect()->route('admin.users.index')->with('status', 'User updated.');
    }

    public function destroy(Request $request, User $user): RedirectResponse
    {
        if ($request->user()->is($user)) {
            return redirect()->route('admin.users.index')->with('error', 'You cannot delete the account you are signed in as.');
        }

        $user->delete();

        return redirect()->route('admin.users.index')->with('status', 'User deleted.');
    }

    private function validateUser(Request $request, ?User $user): array
    {
        return $request->validate([
            'name'     => ['required', 'string', 'max:255'],
            'email'    => ['required', 'email', 'max:255', Rule::unique('users', 'email')->ignore($user?->id)],
            'password' => [$user ? 'nullable' : 'required', 'string', 'min:6'],
        ]);
    }
}
