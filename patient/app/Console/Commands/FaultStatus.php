<?php

namespace App\Console\Commands;

use App\Support\FaultInjector;
use App\Support\Settings;
use Illuminate\Console\Command;

class FaultStatus extends Command
{
    protected $signature = 'fault:status {--catalog : List all injectable faults instead of active ones}';

    protected $description = 'Show active faults, or the full fault catalog with --catalog.';

    public function handle(): int
    {
        if ($this->option('catalog')) {
            $rows = [];
            foreach (FaultInjector::catalog() as $key => $spec) {
                $rows[] = [$key, 'config', $spec['setting'], implode(' ', $spec['breaks']), $spec['symptom']];
            }
            foreach (FaultInjector::codeCatalog() as $key => $spec) {
                $rows[] = [$key, 'code', $spec['file'], implode(' ', $spec['breaks']), $spec['symptom']];
            }
            $this->table(['fault', 'kind', 'target', 'breaks', 'symptom'], $rows);

            return self::SUCCESS;
        }

        $active = FaultInjector::active();
        if ($active->isEmpty()) {
            $this->info('No active faults — patient is healthy.');
        } else {
            $rows = $active->map(fn ($f) => [
                $f->fault_key, $f->target_setting, $f->bad_value, $f->injected_at?->toDateTimeString(),
            ])->all();
            $this->table(['fault', 'setting', 'bad value', 'injected at'], $rows);
        }

        $this->newLine();
        $this->line('Current real config (app_settings):');
        foreach (array_keys(Settings::defaults()) as $key) {
            $this->line(sprintf('  %-24s = %s', $key, Settings::get($key)));
        }

        return self::SUCCESS;
    }
}
