<?php

namespace App\Support;

use Illuminate\Support\Facades\Log;

/**
 * Structured logging for the patient. Every route logs through here so the
 * lines are uniform and greppable — these are the "clues" the AI doctor reads
 * later via the log.search MCP tool. Writes to the dedicated `patient` channel.
 */
class PatientLog
{
    public static function info(string $route, string $event, array $context = []): void
    {
        Log::channel('patient')->info("[$route] $event", $context);
    }

    public static function warning(string $route, string $event, array $context = []): void
    {
        Log::channel('patient')->warning("[$route] $event", $context);
    }

    public static function error(string $route, string $event, array $context = []): void
    {
        Log::channel('patient')->error("[$route] $event", $context);
    }
}
