<?php

namespace App\Support;

use Illuminate\Support\Facades\Route;
use Throwable;

/**
 * Live health probes. Each probe derives a symptom from REAL state
 * (app_settings + an actual DB dial) — NEVER from the `faults` table. This is
 * what makes /health an honest signal: it reports what is actually broken, not
 * what was injected.
 *
 * The Verifier (Python, later) reuses this same idea of key-page checks, so
 * "fixed" means every probe is green again.
 */
class HealthProbes
{
    /**
     * @return array{healthy: bool, checks: array<string, array{ok: bool, detail: string}>}
     */
    public static function run(): array
    {
        $checks = [
            'database'          => self::probeDatabase(),
            'connection_pool'   => self::probePool(),
            'routing'           => self::probeRouting(),
            'orders_dependency' => self::probeOrdersDependency(),
            'object_storage'    => self::probeObjectStorage(),
        ];

        $healthy = ! collect($checks)->contains(fn ($c) => $c['ok'] === false);

        return ['healthy' => $healthy, 'checks' => $checks];
    }

    private static function probeDatabase(): array
    {
        try {
            UserStore::connection()->table('users')->count();

            return ['ok' => true, 'detail' => 'user store reachable'];
        } catch (Throwable $e) {
            return ['ok' => false, 'detail' => 'user store unreachable: '.$e->getMessage()];
        }
    }

    private static function probePool(): array
    {
        $available = (int) Settings::get(Settings::DB_POOL_AVAILABLE, '0');

        return $available > 0
            ? ['ok' => true, 'detail' => "{$available}/10 connections available"]
            : ['ok' => false, 'detail' => 'connection pool exhausted (0/10 available)'];
    }

    private static function probeRouting(): array
    {
        $name = (string) Settings::get(Settings::EDIT_SAVE_ROUTE, '');

        return Route::has($name)
            ? ['ok' => true, 'detail' => "save route '{$name}' resolves"]
            : ['ok' => false, 'detail' => "save route '{$name}' is not defined"];
    }

    private static function probeOrdersDependency(): array
    {
        $delay   = (int) Settings::get(Settings::ORDERS_DELAY_MS, '0');
        $timeout = (int) Settings::get(Settings::ORDERS_TIMEOUT_MS, '1500');

        return $delay < $timeout
            ? ['ok' => true, 'detail' => "latency {$delay}ms within {$timeout}ms budget"]
            : ['ok' => false, 'detail' => "latency {$delay}ms exceeds {$timeout}ms budget"];
    }

    private static function probeObjectStorage(): array
    {
        $key = (string) Settings::get(Settings::OSS_API_KEY, '');
        $valid = str_starts_with($key, 'LTAI') && strlen($key) >= 12;

        return $valid
            ? ['ok' => true, 'detail' => 'object storage credentials valid']
            : ['ok' => false, 'detail' => 'object storage access key invalid'];
    }
}
