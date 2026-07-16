<?php

use App\Http\Controllers\Admin\DashboardController;
use App\Http\Controllers\Admin\OrderController as AdminOrderController;
use App\Http\Controllers\Admin\ReportController as AdminReportController;
use App\Http\Controllers\Admin\SystemController;
use App\Http\Controllers\Admin\UserController as AdminUserController;
use App\Http\Controllers\Auth\LoginController;
use App\Http\Controllers\HealthController;
use App\Http\Controllers\WatchController;
use Illuminate\Support\Facades\Route;

/*
|--------------------------------------------------------------------------
| Internal monitoring endpoints (public, unauthenticated)
|--------------------------------------------------------------------------
| Not part of the user-facing app — these are how the Watchman monitors health.
| /health derives status from app_settings + live probes (never the `faults` table).
| /edit is kept as the route_renamed fault's target.
*/

Route::get('/health', [HealthController::class, 'show']);   // dependency probes (config faults surface here)

// Watch-target discovery: the Watchman fetches this to patrol the whole console.
Route::get('/_watch/targets', [WatchController::class, 'targets']);

/*
|--------------------------------------------------------------------------
| Operator Console (human-facing) — login + dashboard + CRUD
|--------------------------------------------------------------------------
| Separate from the machine-facing patient API above so auth redirects never
| interfere with the Watchman's patrols or the fault detection codes.
*/

Route::get('/', fn () => redirect()->route('dashboard'));

Route::middleware('guest')->group(function () {
    Route::get('/login', [LoginController::class, 'show'])->name('login');
    Route::post('/login', [LoginController::class, 'login']);
});

Route::middleware('auth')->group(function () {
    Route::post('/logout', [LoginController::class, 'logout'])->name('logout');

    Route::get('/dashboard', [DashboardController::class, 'index'])->name('dashboard');

    Route::get('/_auth/ping', fn () => response('ok'))->name('auth.ping');

    Route::prefix('admin')->name('admin.')->group(function () {
        Route::resource('users', AdminUserController::class)->except('show');
        Route::resource('orders', AdminOrderController::class)->except('show');
        Route::get('report', [AdminReportController::class, 'index'])->name('report');
        Route::get('system', [SystemController::class, 'index'])->name('system');
    });
});
