<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * faults = the fault injector's PRIVATE LEDGER. Ground-truth of what was
 * injected, so the injector can inject/clear and so the benchmark has truth.
 *
 * 🔴 GOLDEN RULE: the patient routes, /health, and the AI doctor (Investigators,
 * Verifier, fix.apply) MUST NEVER read or write this table. Symptoms are derived
 * only from `app_settings` + live probes. If fix code touches `faults`, the demo
 * is fake. See PLAN.md PART 0 / PART 1B.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('faults', function (Blueprint $table) {
            $table->id();
            $table->string('fault_key');            // e.g. db_host_broken
            $table->string('target_setting');       // app_settings key it corrupts
            $table->text('bad_value')->nullable();  // value written to break it
            $table->text('original_value')->nullable(); // good value, for clean-up
            $table->string('status')->default('active'); // active | cleared
            $table->timestamp('injected_at')->nullable();
            $table->timestamp('cleared_at')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('faults');
    }
};
