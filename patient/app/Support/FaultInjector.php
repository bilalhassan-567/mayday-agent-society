<?php

namespace App\Support;

use App\Models\Fault;

/**
 * The fault injector. Corrupts the patient's REAL state (app_settings) and
 * records what it did in its PRIVATE ledger (the faults table).
 *
 * 🔴 GOLDEN RULE: this is the ONLY writer of the `faults` table. The patient
 * routes, /health, and the AI doctor never touch it. `clear()` here is the
 * injector resetting its own damage between runs — it is NOT the doctor's fix.
 * The doctor repairs app_settings from evidence via a separate path.
 */
class FaultInjector
{
    /**
     * The five faults. Each names the REAL setting it corrupts and the bad
     * value it writes. Keep in sync with faults/manifest.json (frozen truth).
     *
     * @return array<string, array{setting: string, bad_value: string, breaks: array<int, string>, symptom: string}>
     */
    public static function catalog(): array
    {
        return [
            'db_host_broken' => [
                'setting'   => Settings::USER_STORE_PATH,
                'bad_value' => '/mnt/db-primary-10.0.0.5/users.sqlite',
                'breaks'    => ['/users', '/health'],
                'symptom'   => 'user store points at a dead host; connections fail',
            ],
            'db_pool_exhausted' => [
                'setting'   => Settings::DB_POOL_AVAILABLE,
                'bad_value' => '0',
                'breaks'    => ['/users', '/health'],
                'symptom'   => 'connection pool drained to 0 available',
            ],
            'route_renamed' => [
                'setting'   => Settings::EDIT_SAVE_ROUTE,
                'bad_value' => 'admin.users.updatex',
                'breaks'    => ['/admin/users/1/edit', '/health'],
                'symptom'   => 'user-edit form references a save route name that no longer exists',
            ],
            'dependency_timeout' => [
                'setting'   => Settings::ORDERS_DELAY_MS,
                'bad_value' => '8000',
                'breaks'    => ['/orders', '/health'],
                'symptom'   => 'orders enrichment dependency latency exceeds its timeout budget',
            ],
            'env_key_corrupted' => [
                'setting'   => Settings::OSS_API_KEY,
                'bad_value' => 'INVALID_KEY',
                'breaks'    => ['/report', '/health'],
                'symptom'   => 'object storage access key is invalid; report upload is rejected',
            ],
        ];
    }

    /**
     * CODE faults — real single-line source bugs that make a page throw a fatal
     * error. The doctor must read the exception + source and patch the file (not
     * a config value). `find` is the correct snippet; `broken` is the corruption.
     *
     * @return array<string, array{file: string, find: string, broken: string, breaks: array<int, string>, symptom: string}>
     */
    public static function codeCatalog(): array
    {
        return [
            'code_orders_bad_method' => [
                'file'    => 'app/Http/Controllers/Admin/OrderController.php',
                'find'    => "->orderBy('id')->paginate(",
                'broken'  => "->orderByx('id')->paginate(",
                'breaks'  => ['/admin/orders'],
                'symptom' => 'Orders page controller calls an undefined query builder method; /admin/orders throws a fatal error',
            ],
            'code_report_bad_method' => [
                'file'    => 'app/Http/Controllers/Admin/ReportController.php',
                'find'    => "\$orders->sum('amount_cents')",
                'broken'  => "\$orders->sumx('amount_cents')",
                'breaks'  => ['/admin/report'],
                'symptom' => 'Reports page controller calls an undefined collection method; /admin/report throws a fatal error',
            ],
            'code_edit_blade_error' => [
                'file'    => 'resources/views/dashboard.blade.php',
                'find'    => '{{ number_format($userCount) }}',
                'broken'  => '{{ number_format($userCount)->x() }}',
                'breaks'  => ['/dashboard'],
                'symptom' => 'Dashboard view calls a method on a string; /dashboard throws a fatal error while rendering',
            ],
        ];
    }

    /** @return array{setting: string, from: ?string, to: string} */
    public static function inject(string $faultKey): array
    {
        if (isset(self::codeCatalog()[$faultKey])) {
            return self::injectCode($faultKey);
        }

        $spec = self::catalog()[$faultKey] ?? throw new \InvalidArgumentException("Unknown fault: {$faultKey}");

        $original = Settings::get($spec['setting']);
        Settings::set($spec['setting'], $spec['bad_value']);

        Fault::query()->create([
            'fault_key'      => $faultKey,
            'kind'           => 'config',
            'target_setting' => $spec['setting'],
            'bad_value'      => $spec['bad_value'],
            'original_value' => $original,
            'status'         => 'active',
            'injected_at'    => now(),
        ]);

        return ['setting' => $spec['setting'], 'from' => $original, 'to' => $spec['bad_value']];
    }

    private static function injectCode(string $faultKey): array
    {
        $spec = self::codeCatalog()[$faultKey];
        $path = base_path($spec['file']);
        $content = file_get_contents($path);

        if (! str_contains($content, $spec['find'])) {
            throw new \RuntimeException("Anchor not found in {$spec['file']} (already injected, or source changed?).");
        }

        file_put_contents($path, str_replace($spec['find'], $spec['broken'], $content));

        Fault::query()->create([
            'fault_key'      => $faultKey,
            'kind'           => 'code',
            'target_setting' => $spec['file'],
            'target_file'    => $spec['file'],
            'bad_value'      => $spec['broken'],
            'original_value' => $spec['find'],
            'status'         => 'active',
            'injected_at'    => now(),
        ]);

        return ['setting' => $spec['file'], 'from' => $spec['find'], 'to' => $spec['broken']];
    }

    /**
     * Restore state for one fault (or all active faults if $faultKey is null).
     *
     * @return array<int, array{fault_key: string, setting: string, restored_to: ?string}>
     */
    public static function clear(?string $faultKey = null): array
    {
        $query = Fault::query()->where('status', 'active');
        if ($faultKey !== null) {
            $query->where('fault_key', $faultKey);
        }

        $restored = [];
        foreach ($query->get() as $fault) {
            if ($fault->kind === 'code') {
                $path = base_path($fault->target_file);
                $content = file_get_contents($path);
                file_put_contents($path, str_replace($fault->bad_value, $fault->original_value, $content));
            } else {
                Settings::set($fault->target_setting, $fault->original_value);
            }
            $fault->update(['status' => 'cleared', 'cleared_at' => now()]);
            $restored[] = [
                'fault_key'   => $fault->fault_key,
                'setting'     => $fault->target_setting,
                'restored_to' => $fault->kind === 'code' ? '(source restored)' : $fault->original_value,
            ];
        }

        return $restored;
    }

    /** @return \Illuminate\Support\Collection<int, Fault> */
    public static function active()
    {
        return Fault::query()->where('status', 'active')->orderBy('id')->get();
    }
}
