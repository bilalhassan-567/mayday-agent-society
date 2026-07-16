<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Support\HealthProbes;
use App\Support\Settings;
use Illuminate\View\View;

class SystemController extends Controller
{
    public function index(): View
    {
        $settings = [];
        foreach (array_keys(Settings::defaults()) as $key) {
            $settings[$key] = Settings::get($key);
        }

        return view('admin.system', [
            'health'   => HealthProbes::run(),
            'settings' => $settings,
        ]);
    }
}
