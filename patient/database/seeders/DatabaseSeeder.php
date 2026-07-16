<?php

namespace Database\Seeders;

use App\Models\AppSetting;
use App\Models\Order;
use App\Models\User;
use App\Support\Settings;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    use WithoutModelEvents;

    public function run(): void
    {
        // Seed the patient's REAL config with its healthy, known-good values.
        foreach (Settings::defaults() as $key => $meta) {
            AppSetting::query()->updateOrInsert(
                ['key' => $key],
                ['value' => $meta['value'], 'description' => $meta['description'], 'updated_at' => now()],
            );
        }

        // Operator login for the admin console.
        User::query()->updateOrCreate(
            ['email' => 'admin@example.com'],
            ['name' => 'Operator', 'password' => \Illuminate\Support\Facades\Hash::make('password')],
        );

        // A few users for the /users page.
        if (User::query()->count() <= 1) {
            $names = [
                ['name' => 'Ada Lovelace',   'email' => 'ada@example.com'],
                ['name' => 'Alan Turing',    'email' => 'alan@example.com'],
                ['name' => 'Grace Hopper',   'email' => 'grace@example.com'],
                ['name' => 'Linus Torvalds', 'email' => 'linus@example.com'],
            ];
            foreach ($names as $u) {
                User::factory()->create($u);
            }
        }

        // A few orders for the /orders page.
        if (Order::query()->count() === 0) {
            $orders = [
                ['customer' => 'Ada Lovelace',   'item' => 'Analytical Engine', 'amount_cents' => 129900, 'status' => 'paid'],
                ['customer' => 'Alan Turing',    'item' => 'Enigma Decoder',    'amount_cents' => 4999,   'status' => 'paid'],
                ['customer' => 'Grace Hopper',   'item' => 'Compiler License',  'amount_cents' => 19900,  'status' => 'refunded'],
                ['customer' => 'Linus Torvalds', 'item' => 'Kernel Support',    'amount_cents' => 0,      'status' => 'paid'],
            ];
            foreach ($orders as $o) {
                Order::query()->create($o);
            }
        }
    }
}
