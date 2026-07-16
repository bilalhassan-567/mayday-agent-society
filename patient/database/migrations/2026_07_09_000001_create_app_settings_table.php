<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * app_settings = the patient's REAL runtime config.
 *
 * The patient reads its behavior from this table (real state). The fault
 * injector corrupts rows here; fix.apply repairs rows here. This layer is
 * DB-agnostic (works identically on SQLite and Postgres) — see PLAN.md
 * "LOCAL DEV vs PROD DB PARITY". Nothing here references the `faults` table.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::create('app_settings', function (Blueprint $table) {
            $table->id();
            $table->string('key')->unique();
            $table->text('value')->nullable();
            $table->string('description')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('app_settings');
    }
};
