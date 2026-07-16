<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\Order;
use App\Models\User;
use App\Support\HealthProbes;
use Illuminate\View\View;

class DashboardController extends Controller
{
    public function index(): View
    {
        $health = HealthProbes::run();

        return view('dashboard', [
            'userCount'   => User::query()->count(),
            'orderCount'  => Order::query()->count(),
            'grossCents'  => (int) Order::query()->sum('amount_cents'),
            'health'      => $health,
            'recentOrders' => Order::query()->latest('id')->take(5)->get(),
        ]);
    }
}
