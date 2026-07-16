<?php

namespace App\Support;

use App\Models\AppSetting;

/**
 * The patient's REAL configuration layer.
 *
 * Every route derives its behavior from these values (read from the
 * `app_settings` table). The fault injector corrupts them; the AI doctor's
 * fix.apply repairs them. This class is the single source of truth for the
 * canonical (healthy) values — used by the seeder and by `fault:clear`.
 *
 * DB-agnostic on purpose: values are plain strings, so a fault behaves
 * identically on SQLite (dev) and Postgres/ApsaraDB (prod). See PLAN.md
 * "LOCAL DEV vs PROD DB PARITY".
 */
class Settings
{
    // Canonical setting keys.
    public const USER_STORE_PATH   = 'user_store_path';
    public const DB_POOL_AVAILABLE = 'db_pool_available';
    public const EDIT_SAVE_ROUTE   = 'edit_save_route';
    public const ORDERS_DELAY_MS   = 'orders_service_delay_ms';
    public const ORDERS_TIMEOUT_MS = 'orders_service_timeout_ms';
    public const OSS_API_KEY       = 'oss_api_key';

    /**
     * The healthy, known-good values. `null` means "computed at runtime".
     *
     * @return array<string, array{value: string, description: string}>
     */
    public static function defaults(): array
    {
        return [
            self::USER_STORE_PATH => [
                'value'       => database_path('database.sqlite'),
                'description' => 'Filesystem/host location of the user store the /users page reads.',
            ],
            self::DB_POOL_AVAILABLE => [
                'value'       => '10',
                'description' => 'Available DB connections in the pool (of a max of 10).',
            ],
            self::EDIT_SAVE_ROUTE => [
                'value'       => 'admin.users.update',
                'description' => 'Named route the admin user-edit form posts to when saving.',
            ],
            self::ORDERS_DELAY_MS => [
                'value'       => '40',
                'description' => 'Simulated latency (ms) of the internal orders dependency.',
            ],
            self::ORDERS_TIMEOUT_MS => [
                'value'       => '1500',
                'description' => 'Timeout budget (ms) for the internal orders dependency.',
            ],
            self::OSS_API_KEY => [
                'value'       => 'LTAI-oss-valid-key-9f3a2',
                'description' => 'Access key used to upload reports to object storage (OSS).',
            ],
        ];
    }

    public static function get(string $key, ?string $fallback = null): ?string
    {
        $row = AppSetting::query()->where('key', $key)->first();

        return $row?->value ?? $fallback;
    }

    public static function set(string $key, ?string $value): void
    {
        AppSetting::query()->updateOrInsert(
            ['key' => $key],
            ['value' => $value, 'updated_at' => now()],
        );
    }
}
