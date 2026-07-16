<?php

namespace App\Support;

use Illuminate\Database\Connection;
use Illuminate\Support\Facades\DB;

/**
 * The user store the /users page reads from. Its connection target is REAL
 * config (Settings::USER_STORE_PATH), so the `db_host_broken` fault — which
 * points it at a dead location — produces a genuine connection failure, not a
 * simulated one.
 *
 * Dev (SQLite): the target is a file path; a path under a non-existent
 * directory throws "unable to open database file".
 * Prod (Postgres/ApsaraDB): swap this builder to a pgsql config whose `host`
 * is the setting value; a dead host throws "connection refused". Same fault,
 * same evidence shape. See PLAN.md "LOCAL DEV vs PROD DB PARITY".
 */
class UserStore
{
    public static function connection(): Connection
    {
        $target = Settings::get(Settings::USER_STORE_PATH, database_path('database.sqlite'));

        config(['database.connections.user_store' => [
            'driver'                  => 'sqlite',
            'database'                => $target,
            'prefix'                  => '',
            'foreign_key_constraints' => true,
        ]]);

        // Drop any cached PDO so a changed target is actually re-dialed.
        DB::purge('user_store');

        return DB::connection('user_store');
    }
}
