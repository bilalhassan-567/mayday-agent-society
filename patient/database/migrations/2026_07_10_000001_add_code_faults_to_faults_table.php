<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Extends the injector ledger to support CODE faults (real source-file bugs),
 * alongside the existing config/state faults.
 *   kind        = 'config' | 'code'
 *   target_file = repo-relative source path a code fault corrupts (null for config)
 * For code faults, original_value/bad_value hold the correct/broken code snippet.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('faults', function (Blueprint $table) {
            $table->string('kind')->default('config')->after('fault_key');
            $table->string('target_file')->nullable()->after('target_setting');
        });
    }

    public function down(): void
    {
        Schema::table('faults', function (Blueprint $table) {
            $table->dropColumn(['kind', 'target_file']);
        });
    }
};
