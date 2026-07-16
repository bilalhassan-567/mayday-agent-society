<?php

namespace App\Services;

use App\Support\Settings;
use RuntimeException;

/**
 * The internal dependency the /orders page calls. It reads its latency and
 * timeout budget from REAL config. The `dependency_timeout` fault raises the
 * latency past the budget, so this genuinely times out — a real consequence of
 * a real config value, discoverable and fixable.
 */
class OrdersService
{
    /**
     * Simulate the downstream call. Sleeps for the (capped) configured latency;
     * if the configured latency exceeds the timeout budget, it aborts.
     *
     * @throws RuntimeException on timeout
     */
    public function fetchEnrichment(): array
    {
        $delayMs   = (int) Settings::get(Settings::ORDERS_DELAY_MS, '40');
        $timeoutMs = (int) Settings::get(Settings::ORDERS_TIMEOUT_MS, '1500');

        if ($delayMs >= $timeoutMs) {
            // Wait out the budget (bounded) then fail, like a real timeout.
            usleep(min($timeoutMs, 1500) * 1000);
            throw new RuntimeException(
                "orders-enrichment dependency timed out after {$timeoutMs}ms (latency was {$delayMs}ms)"
            );
        }

        usleep(min($delayMs, 1500) * 1000);

        return ['enriched' => true, 'latency_ms' => $delayMs];
    }
}
