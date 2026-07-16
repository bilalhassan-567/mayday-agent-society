<?php

namespace App\Console\Commands;

use App\Support\FaultInjector;
use Illuminate\Console\Command;

class FaultInject extends Command
{
    protected $signature = 'fault:inject {key : One of the fault keys (see fault:status --catalog)}';

    protected $description = 'Inject a fault by corrupting the patient\'s real config (app_settings).';

    public function handle(): int
    {
        $key = $this->argument('key');

        $known = array_merge(array_keys(FaultInjector::catalog()), array_keys(FaultInjector::codeCatalog()));
        if (! in_array($key, $known, true)) {
            $this->error("Unknown fault '{$key}'. Known: ".implode(', ', $known));

            return self::FAILURE;
        }

        if (FaultInjector::active()->isNotEmpty()) {
            $this->warn('A fault is already active. Run `php artisan fault:clear` first for a clean single-incident demo.');
        }

        $r = FaultInjector::inject($key);
        $this->info("Injected '{$key}'.");
        $this->line("  setting: {$r['setting']}");
        $this->line("  {$r['from']}  ->  {$r['to']}");
        $this->comment('The patient now has a real defect. Hit its pages (or let the Watchman patrol) to observe.');

        return self::SUCCESS;
    }
}
